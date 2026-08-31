from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.model_contract import (
    ModelContractError,
    load_json_object,
    validate_weight_manifest,
)

DEFAULT_PROFILES_PATH = "config/model-profiles-v1.json"


def _inside_root(root: Path, candidate: Path, field: str) -> Path:
    resolved_root = root.resolve(strict=True)
    selected_candidate = candidate if candidate.is_absolute() else resolved_root / candidate
    resolved_candidate = selected_candidate.resolve(strict=True)
    if not resolved_candidate.is_relative_to(resolved_root):
        raise ModelContractError(f"{field}은 AI 프로젝트 루트 안에 있어야 합니다.")
    return resolved_candidate


def inspect_ultralytics_weight(weight_path: Path) -> dict[str, object]:
    try:
        from ultralytics import YOLO

        model = YOLO(str(weight_path))
    except Exception as error:
        raise ModelContractError(
            f"Ultralytics 가중치를 로드하지 못했습니다: {error}"
        ) from error

    names = getattr(model, "names", None)
    if isinstance(names, Mapping):
        classes = [
            {"id": int(class_id), "name": str(class_name)}
            for class_id, class_name in sorted(names.items(), key=lambda item: int(item[0]))
        ]
    elif isinstance(names, (list, tuple)):
        classes = [
            {"id": class_id, "name": str(class_name)}
            for class_id, class_name in enumerate(names)
        ]
    else:
        classes = []

    from app.model_contract import sha256_file

    return {
        "resolvedPath": str(weight_path),
        "sizeBytes": weight_path.stat().st_size,
        "sha256": sha256_file(weight_path),
        "task": str(getattr(model, "task", "")),
        "classCount": len(classes),
        "classes": classes,
    }


def run_preflight(
    *,
    root: Path,
    manifest_path: Path,
    weight_path: Path,
    profiles_path: Path | None = None,
    activation: bool = False,
    status_loader: Callable[[Path], Mapping[str, object]] = inspect_ultralytics_weight,
) -> dict[str, object]:
    resolved_root = root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ModelContractError("AI 프로젝트 루트가 디렉터리가 아닙니다.")
    resolved_manifest = _inside_root(resolved_root, manifest_path, "manifest")
    resolved_weight = _inside_root(resolved_root, weight_path, "weight")
    selected_profiles = profiles_path or (resolved_root / DEFAULT_PROFILES_PATH)
    resolved_profiles = _inside_root(resolved_root, selected_profiles, "profiles")

    manifest = load_json_object(resolved_manifest)
    registry = load_json_object(resolved_profiles)
    status = dict(status_loader(resolved_weight))
    contract = validate_weight_manifest(
        manifest,
        registry,
        weight_path=resolved_weight,
        model_status=status,
        activation=activation,
    )
    return {
        "success": True,
        "mode": "ACTIVATION" if activation else "CONTRACT_ONLY",
        "contract": contract,
        "model": status,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow Phase 2B-1 weight contract preflight")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--weight", type=Path, required=True)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--activation", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = run_preflight(
            root=arguments.root,
            manifest_path=arguments.manifest,
            weight_path=arguments.weight,
            profiles_path=arguments.profiles,
            activation=arguments.activation,
        )
    except Exception as error:
        result: dict[str, Any] = {"success": False, "message": str(error)}
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
