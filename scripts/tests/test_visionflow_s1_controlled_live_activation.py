#!/usr/bin/env python3
"""Trace the exact S1 controlled-live activation patch without mutation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

MARKER = "VISIONFLOW_S1_CONTROLLED_LIVE_ACTIVATION_TRACE"
EXPECTED_HEAD = "8eff32c615d951b3a1e96b082797671f4964acc6"
EXPECTED_BRANCH = "feature/phase3-dji-bridge"
EXPECTED_WEIGHT_SHA256 = (
    "486f29a14b68201defb2148db923633f15b68f0304b50ff1f66b893ea4e16422"
)
EXPECTED_WEIGHT_SIZE = 44_121_433
EXPECTED_TRAINING_FINGERPRINT = (
    "a33a449363aca637e43b597537151ff5b61459b93b5e17fe48054f7ba22289a5"
)
AI = Path("03_ai-server/visionflow-ai")
MANIFEST = AI / "models/manifests/yolo26m-visdrone-s1-best.manifest.json"
WEIGHT = AI / "models/yolo26m-visdrone-s1-best.pt"
PROFILES = AI / "config/model-profiles-v1.json"
PLAN = AI / "config/visdrone-s1-training.plan.json"
RECEIPT = (
    AI / "output/training-execution/visdrone-s1-batch1-20260828-r2-resume.json"
)
INTAKE = AI / "output/dataset-intake/visdrone-s1-ready.json"
SPLIT = AI / "datasets/visdrone2019-det/split-manifest.json"
LABELED = (
    AI / "artifacts/labeled-small-object-evaluation/"
    "labeled-small-object-20260830T014903Z/evaluation-report.json"
)
STANDARD = (
    AI / "artifacts/ultralytics-standard-map-evaluation/"
    "visdrone-s1-official-test-v2/visionflow-s1-standard-map-evaluation.json"
)
OVERLAY = Path("compose.s1-live.yaml")
MODIFIED = {
    "03_ai-server/visionflow-ai/app/model_contract.py",
    "03_ai-server/visionflow-ai/app/model_runtime.py",
    "03_ai-server/visionflow-ai/config/model-profiles-v1.json",
    "03_ai-server/visionflow-ai/config/weight-manifest-v1.schema.json",
    "03_ai-server/visionflow-ai/tests/test_model_contract.py",
    "03_ai-server/visionflow-ai/tests/test_model_runtime.py",
}
CREATED = {
    (
        "03_ai-server/visionflow-ai/models/manifests/"
        "yolo26m-visdrone-s1-best.manifest.json"
    ),
    "compose.s1-live.yaml",
    "scripts/tests/test_visionflow_s1_controlled_live_activation.py",
}


class TraceError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise TraceError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        fail(f"JSON root is not an object: {path}")
    return value


def git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    print(f"RUN=git {' '.join(arguments)}")
    if completed.returncode != 0:
        fail((completed.stderr or completed.stdout).strip())
    return completed.stdout.rstrip("\r\n")


def expect(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        fail(f"{label}: expected={expected!r} actual={actual!r}")
    print(f"{label}=PASS")


def status_paths(repo: Path) -> tuple[set[str], set[str]]:
    modified: set[str] = set()
    created: set[str] = set()
    for line in git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).splitlines():
        code = line[:2]
        path = line[3:].replace("\\", "/")
        if code == " M":
            modified.add(path)
        elif code == "??":
            created.add(path)
        else:
            fail(f"unexpected git status entry: {line}")
    return modified, created


def main() -> int:
    print(f"{MARKER}=START")
    if len(sys.argv) != 2:
        print(f"USAGE={Path(sys.argv[0]).name} REPOSITORY_PATH")
        return 2
    repo = Path(sys.argv[1]).resolve()
    expect(git(repo, "branch", "--show-current"), EXPECTED_BRANCH, "BRANCH")
    expect(git(repo, "rev-parse", "HEAD"), EXPECTED_HEAD, "HEAD")
    modified, created = status_paths(repo)
    expect(modified, MODIFIED, "EXACT_6_MODIFIED_FILES")
    expect(created, CREATED, "EXACT_3_CREATED_FILES")

    ai_root = repo / AI
    sys.path.insert(0, str(ai_root))
    from app.model_contract import validate_weight_manifest
    from app.model_runtime import create_runtime_model_selection

    manifest = load_json(repo / MANIFEST)
    registry = load_json(repo / PROFILES)
    expect(manifest.get("template"), False, "CONCRETE_MANIFEST")
    model = manifest["model"]
    expect(model["trainingStage"], "VISDRONE_S1", "MANIFEST_STAGE")
    expect(model["activationEligible"], True, "MANIFEST_ACTIVATION_ELIGIBLE")
    expect(sha256_file(repo / WEIGHT), EXPECTED_WEIGHT_SHA256, "WEIGHT_SHA256")
    expect((repo / WEIGHT).stat().st_size, EXPECTED_WEIGHT_SIZE, "WEIGHT_SIZE")
    contract = validate_weight_manifest(
        manifest,
        registry,
        weight_path=repo / WEIGHT,
        activation=True,
    )
    expect(contract["trainingStage"], "VISDRONE_S1", "CONTRACT_STAGE")

    classes = manifest["classes"]
    status = {
        "profile": "AERIAL_SMALL_OBJECT_LIVE",
        "resolvedPath": str(repo / WEIGHT),
        "sizeBytes": EXPECTED_WEIGHT_SIZE,
        "sha256": EXPECTED_WEIGHT_SHA256,
        "task": "detect",
        "classCount": len(classes),
        "classes": [
            {"id": row["id"], "name": row["sourceName"]}
            for row in classes
        ],
    }
    selection = create_runtime_model_selection(
        model_profile="AERIAL_SMALL_OBJECT_LIVE",
        model_path=str(repo / WEIGHT),
        manifest_path=str(repo / MANIFEST),
        profiles_path=str(repo / PROFILES),
    )
    runtime_contract = selection.validate_loaded_status(status)
    expect(
        runtime_contract["validation"],
        "WEIGHT_MANIFEST",
        "RUNTIME_MANIFEST_VALIDATION",
    )

    plan = load_json(repo / PLAN)
    receipt = load_json(repo / RECEIPT)
    intake = load_json(repo / INTAKE)
    split = load_json(repo / SPLIT)
    labeled = load_json(repo / LABELED)
    standard = load_json(repo / STANDARD)
    data = manifest["data"]
    expect(
        data["datasetVersion"],
        plan["data"]["datasetVersion"],
        "MANIFEST_PLAN_DATASET_VERSION",
    )
    expect(
        data["datasetFingerprintSha256"],
        EXPECTED_TRAINING_FINGERPRINT,
        "MANIFEST_TRAINING_FINGERPRINT",
    )
    expect(
        data["datasetFingerprintSha256"],
        intake["dataset"]["combinedFingerprintSha256"],
        "MANIFEST_INTAKE_FINGERPRINT",
    )
    expect(data["splitPolicy"]["unit"], split["splitUnit"], "MANIFEST_SPLIT_UNIT")
    expect(
        manifest["training"]["epochs"],
        plan["training"]["epochs"],
        "MANIFEST_PLAN_EPOCHS",
    )
    expect(
        manifest["runtime"]["ultralytics"],
        receipt["runtime"]["ultralytics"],
        "MANIFEST_RUNTIME",
    )
    expect(
        manifest["evaluation"]["map50"],
        standard["metrics"]["mAP50"],
        "MANIFEST_STANDARD_MAP50",
    )
    expect(
        manifest["evaluation"]["smallObject"]["recall"],
        labeled["candidate"]["metrics"]["smallRecall"],
        "MANIFEST_LABELED_SMALL_RECALL",
    )

    overlay = yaml.safe_load((repo / OVERLAY).read_text(encoding="utf-8"))
    metadata = overlay["x-visionflow-s1-controlled-live"]
    expect(metadata["presentationOnly"], True, "PRESENTATION_ONLY")
    expect(
        metadata["productionSafetyCertification"],
        False,
        "PRODUCTION_SAFETY_CERTIFICATION_FALSE",
    )
    expect(metadata["s2TrainingComplete"], False, "S2_TRAINING_INCOMPLETE")
    environment = overlay["services"]["ai-server"]["environment"]
    expect(
        environment["AI_MODEL_PROFILE"],
        "AERIAL_SMALL_OBJECT_LIVE",
        "COMPOSE_MODEL_PROFILE",
    )
    expect(
        environment["AI_MODEL_MANIFEST_PATH"],
        "/app/models/manifests/yolo26m-visdrone-s1-best.manifest.json",
        "COMPOSE_MANIFEST_PATH",
    )
    expect(
        environment["AI_EXPECTED_MODEL_SHA256"],
        EXPECTED_WEIGHT_SHA256,
        "COMPOSE_WEIGHT_SHA256",
    )
    expect(git(repo, "diff", "--check"), "", "GIT_DIFF_CHECK")
    print("NO_DOCKER_PERFORMED=TRUE")
    print("NO_GPU_OR_INFERENCE_OR_TRAINING_PERFORMED=TRUE")
    print("NO_GIT_STAGE_COMMIT_PUSH_PERFORMED=TRUE")
    print(f"{MARKER}=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TraceError as error:
        print(f"FAILURE={type(error).__name__}: {error}")
        print(f"{MARKER}=FAIL")
        raise SystemExit(1) from error
