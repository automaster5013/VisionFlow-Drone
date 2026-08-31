"""Reproducible YOLO detection accuracy evaluation for VisionFlow."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

IMAGE_EXTENSIONS = {
    ".bmp",
    ".dng",
    ".jpeg",
    ".jpg",
    ".mpo",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
CRITICAL_CANONICAL_CLASSES = [
    "fire",
    "smoke",
    "gun",
    "knife",
    "weapon",
    "accident",
    "fight",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_names(raw_names: Any) -> dict[int, str]:
    if isinstance(raw_names, list):
        names = {index: str(name) for index, name in enumerate(raw_names)}
    elif isinstance(raw_names, dict):
        names = {int(class_id): str(name) for class_id, name in raw_names.items()}
    else:
        raise ValueError(
            "data.yaml의 names는 목록 또는 클래스 ID 사전이어야 합니다."
        )

    if not names or sorted(names) != list(range(len(names))):
        raise ValueError("클래스 ID는 0부터 빠짐없이 연속되어야 합니다.")
    if any(not name.strip() for name in names.values()):
        raise ValueError("비어 있는 클래스 이름이 있습니다.")
    if len({name.strip() for name in names.values()}) != len(names):
        raise ValueError("중복된 클래스 이름이 있습니다.")
    return {class_id: names[class_id].strip() for class_id in sorted(names)}


def _resolve_dataset_base(data_yaml: Path, config: dict[str, Any]) -> Path:
    configured_path = Path(str(config.get("path", ".")))
    if configured_path.is_absolute():
        return configured_path.resolve()
    return (data_yaml.parent / configured_path).resolve()


def _resolve_file_reference(reference: str, base: Path, list_parent: Path | None = None) -> Path:
    candidate = Path(reference)
    if candidate.is_absolute():
        return candidate.resolve()
    if list_parent is not None:
        from_list = (list_parent / candidate).resolve()
        if from_list.exists():
            return from_list
    return (base / candidate).resolve()


def _collect_images(source: Any, base: Path) -> list[Path]:
    sources = source if isinstance(source, list) else [source]
    images: set[Path] = set()

    for item in sources:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                "검증 split 경로는 비어 있지 않은 문자열이어야 합니다."
            )
        reference = item.strip()
        if any(character in reference for character in "*?["):
            for matched in base.glob(reference):
                if matched.is_file() and matched.suffix.lower() in IMAGE_EXTENSIONS:
                    images.add(matched.resolve())
            continue

        resolved = _resolve_file_reference(reference, base)
        if resolved.is_dir():
            images.update(
                path.resolve()
                for path in resolved.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            )
        elif resolved.is_file() and resolved.suffix.lower() == ".txt":
            for line in resolved.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                image = _resolve_file_reference(line, base, resolved.parent)
                if image.is_file() and image.suffix.lower() in IMAGE_EXTENSIONS:
                    images.add(image)
        elif resolved.is_file() and resolved.suffix.lower() in IMAGE_EXTENSIONS:
            images.add(resolved)

    return sorted(images, key=lambda path: str(path).casefold())


def label_path(image_path: Path) -> Path:
    parts = list(image_path.parts)
    image_indexes = [index for index, value in enumerate(parts) if value.lower() == "images"]
    if image_indexes:
        parts[image_indexes[-1]] = "labels"
        return Path(*parts).with_suffix(".txt")
    return image_path.with_suffix(".txt")


def _label_path(image_path: Path) -> Path:
    """Backward-compatible alias for callers predating the public helper."""
    return label_path(image_path)


def _portable_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def dataset_fingerprint(
    data_yaml: Path,
    images: Iterable[Path],
    base: Path,
    hash_mode: str,
) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    digest.update(b"visionflow-dataset-fingerprint-v1\0")
    digest.update(data_yaml.read_bytes())
    image_count = 0
    label_count = 0

    for image in images:
        image_count += 1
        digest.update(_portable_path(image, base).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(image.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        if hash_mode == "full":
            digest.update(bytes.fromhex(sha256_file(image)))

        label = label_path(image)
        digest.update(_portable_path(label, base).encode("utf-8"))
        digest.update(b"\0")
        if label.is_file():
            label_count += 1
            digest.update(label.read_bytes())
        else:
            digest.update(b"<missing-label>")

    return digest.hexdigest(), image_count, label_count


def load_dataset_inventory(
    data_yaml: Path,
    split: str,
    hash_mode: str,
) -> tuple[dict[str, Any], tuple[Path, ...]]:
    if not data_yaml.is_file():
        raise FileNotFoundError(f"data.yaml을 찾을 수 없습니다: {data_yaml}")
    config = yaml.safe_load(data_yaml.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("data.yaml 최상위 값은 사전이어야 합니다.")
    if split not in config:
        raise ValueError(f"data.yaml에 '{split}' split이 없습니다.")

    names = normalize_names(config.get("names"))
    base = _resolve_dataset_base(data_yaml, config)
    images = _collect_images(config[split], base)
    if not images:
        raise ValueError(
            f"'{split}' split에서 평가 이미지를 찾지 못했습니다: {base}"
        )
    fingerprint, image_count, label_count = dataset_fingerprint(
        data_yaml,
        images,
        base,
        hash_mode,
    )
    spec = {
        "yamlPath": str(data_yaml.resolve()),
        "yamlSha256": sha256_file(data_yaml),
        "basePath": str(base),
        "split": split,
        "names": names,
        "imageCount": image_count,
        "labelFileCount": label_count,
        "missingLabelFileCount": image_count - label_count,
        "fingerprintMode": hash_mode,
        "fingerprintSha256": fingerprint,
    }
    return spec, tuple(images)


def load_dataset_spec(data_yaml: Path, split: str, hash_mode: str) -> dict[str, Any]:
    spec, _images = load_dataset_inventory(data_yaml, split, hash_mode)
    return spec


def compare_model_and_dataset_names(
    model_names: dict[int, str],
    dataset_names: dict[int, str],
) -> None:
    if model_names == dataset_names:
        return
    differences = []
    for class_id in sorted(set(model_names) | set(dataset_names)):
        model_name = model_names.get(class_id, "<missing>")
        dataset_name = dataset_names.get(class_id, "<missing>")
        if model_name != dataset_name:
            differences.append(f"{class_id}: model='{model_name}', data='{dataset_name}'")
    detail = "; ".join(differences[:10])
    raise ValueError(f"모델과 data.yaml의 클래스 계약이 다릅니다. {detail}")


def build_mapping_template(
    model_names: dict[int, str],
    model_sha256: str,
    dataset_fingerprint_sha256: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "modelSha256": model_sha256,
        "datasetFingerprintSha256": dataset_fingerprint_sha256,
        "backendContract": {
            "criticalCanonicalClasses": CRITICAL_CANONICAL_CLASSES,
            "criticalConfidence": 0.60,
            "warningConfidence": 0.70,
            "note": (
                "백엔드 AiAlertRiskEvaluator 기준. "
                "변경 시 백엔드와 함께 갱신하세요."
            ),
        },
        "classes": [
            {
                "sourceClassId": class_id,
                "sourceClassName": class_name,
                "canonicalName": "",
                "enabled": False,
                "minConfidence": 0.35,
                "reviewStatus": "REQUIRED",
                "notes": (
                    "실제 의미를 확인한 후 canonicalName과 상태를 수정하세요."
                ),
            }
            for class_id, class_name in model_names.items()
        ],
    }


def validate_mapping(
    mapping: dict[str, Any],
    model_names: dict[int, str],
    model_sha256: str,
) -> list[str]:
    errors: list[str] = []
    if mapping.get("schemaVersion") != 1:
        errors.append("schemaVersion은 1이어야 합니다.")
    mapped_model_sha = str(mapping.get("modelSha256", "")).strip()
    if mapped_model_sha and mapped_model_sha.lower() != model_sha256.lower():
        errors.append("매핑 파일의 modelSha256이 평가 모델과 다릅니다.")

    classes = mapping.get("classes")
    if not isinstance(classes, list):
        return [*errors, "classes는 목록이어야 합니다."]

    seen: set[int] = set()
    for index, item in enumerate(classes):
        prefix = f"classes[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}는 사전이어야 합니다.")
            continue
        try:
            class_id = int(item.get("sourceClassId"))
        except (TypeError, ValueError):
            errors.append(f"{prefix}.sourceClassId가 올바르지 않습니다.")
            continue
        if class_id in seen:
            errors.append(f"sourceClassId {class_id}가 중복되었습니다.")
        seen.add(class_id)
        expected_name = model_names.get(class_id)
        if expected_name is None:
            errors.append(f"모델에 없는 sourceClassId입니다: {class_id}")
        elif item.get("sourceClassName") != expected_name:
            errors.append(f"sourceClassId {class_id}의 sourceClassName이 모델과 다릅니다.")

        confidence = item.get("minConfidence")
        if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
            errors.append(f"{prefix}.minConfidence는 0~1 사이여야 합니다.")
        review_status = item.get("reviewStatus")
        if review_status not in {"APPROVED", "IGNORED"}:
            errors.append(
                f"{prefix}.reviewStatus는 검토 후 APPROVED 또는 IGNORED여야 합니다."
            )
        if item.get("enabled") is True:
            if not str(item.get("canonicalName", "")).strip():
                errors.append(f"활성화된 {prefix}에는 canonicalName이 필요합니다.")
            if review_status != "APPROVED":
                errors.append(f"활성화된 {prefix}의 reviewStatus는 APPROVED여야 합니다.")

    missing = sorted(set(model_names) - seen)
    if missing:
        errors.append(f"매핑에서 누락된 sourceClassId: {missing}")
    return errors


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value.item() if hasattr(value, "item") else value)
    except (TypeError, ValueError):
        return default


def _to_builtin(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(item) for item in value]
    if hasattr(value, "tolist"):
        return _to_builtin(value.tolist())
    if hasattr(value, "item"):
        return value.item()
    return value


def _sequence_value(values: Any, index: int, default: float = 0.0) -> float:
    try:
        return _number(values[index], default)
    except (IndexError, KeyError, TypeError):
        return default


def extract_per_class_metrics(metrics: Any, names: dict[int, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ap_indexes = [int(value) for value in getattr(metrics.box, "ap_class_index", [])]
    position_by_class = {class_id: position for position, class_id in enumerate(ap_indexes)}
    target_counts = getattr(metrics, "nt_per_class", [])
    image_counts = getattr(metrics, "nt_per_image", [])
    confusion = getattr(getattr(metrics, "confusion_matrix", None), "matrix", None)

    for class_id, class_name in names.items():
        position = position_by_class.get(class_id)
        precision = recall = ap50 = ap5095 = f1 = 0.0
        if position is not None:
            precision, recall, ap50, ap5095 = (
                _number(value) for value in metrics.class_result(position)
            )
            f1 = _sequence_value(getattr(metrics.box, "f1", []), position)

        instances = int(round(_sequence_value(target_counts, class_id)))
        images = int(round(_sequence_value(image_counts, class_id)))
        count_source = "optimal_pr_estimate"
        true_positive = min(instances, int(round(recall * instances)))
        false_negative = max(0, instances - true_positive)
        false_positive: int | None = (
            max(0, int(round(true_positive / precision - true_positive)))
            if precision > 0.0
            else None
        )
        try:
            matrix_size = len(confusion)
            true_positive = int(round(_number(confusion[class_id][class_id])))
            false_positive = max(
                0,
                int(
                    round(
                        sum(_number(confusion[class_id][column]) for column in range(matrix_size))
                        - true_positive
                    )
                ),
            )
            false_negative = max(
                0,
                int(
                    round(
                        sum(_number(confusion[row][class_id]) for row in range(matrix_size))
                        - true_positive
                    )
                ),
            )
            count_source = "confusion_matrix"
        except (IndexError, KeyError, TypeError):
            pass
        rows.append(
            {
                "classId": class_id,
                "className": class_name,
                "images": images,
                "instances": instances,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "map50": ap50,
                "map50_95": ap5095,
                "tp": true_positive,
                "fp": false_positive,
                "fn": false_negative,
                "countSource": count_source,
            }
        )
    return rows


def extract_image_metrics(metrics: Any) -> list[dict[str, Any]]:
    raw = getattr(metrics.box, "image_metrics", {})
    if not isinstance(raw, dict):
        return []
    rows = [
        {
            "image": str(image),
            "precision": _number(values.get("precision")),
            "recall": _number(values.get("recall")),
            "f1": _number(values.get("f1")),
            "tp": int(values.get("tp", 0)),
            "fp": int(values.get("fp", 0)),
            "fn": int(values.get("fn", 0)),
        }
        for image, values in raw.items()
        if isinstance(values, dict)
    ]
    return sorted(rows, key=lambda row: (row["f1"], -row["fn"], -row["fp"], row["image"]))


def extract_confusion_matrix(metrics: Any) -> dict[str, Any]:
    matrix = getattr(metrics, "confusion_matrix", None)
    if matrix is None or not hasattr(matrix, "summary"):
        return {"raw": [], "normalized": []}
    return {
        "raw": _to_builtin(matrix.summary(normalize=False, decimals=5)),
        "normalized": _to_builtin(matrix.summary(normalize=True, decimals=5)),
    }


def evaluate_thresholds(
    overall: dict[str, float],
    thresholds: dict[str, float | None],
) -> dict[str, Any]:
    metric_keys = {
        "precision": "precision",
        "recall": "recall",
        "map50": "map50",
        "map50_95": "map50_95",
    }
    checks = []
    for threshold_name, metric_name in metric_keys.items():
        minimum = thresholds.get(threshold_name)
        if minimum is None:
            continue
        actual = overall[metric_name]
        checks.append(
            {
                "metric": metric_name,
                "minimum": minimum,
                "actual": actual,
                "passed": actual >= minimum,
            }
        )
    status = (
        "MEASURED"
        if not checks
        else ("PASSED" if all(check["passed"] for check in checks) else "FAILED")
    )
    return {"status": status, "checks": checks}


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _runtime_metadata(torch_module: Any, ultralytics_module: Any) -> dict[str, Any]:
    cuda_available = bool(torch_module.cuda.is_available())
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": str(torch_module.__version__),
        "ultralytics": str(ultralytics_module.__version__),
        "cudaAvailable": cuda_available,
        "cudaVersion": str(getattr(torch_module.version, "cuda", None)),
        "cudnnVersion": torch_module.backends.cudnn.version() if cuda_available else None,
        "gpuCount": torch_module.cuda.device_count() if cuda_available else 0,
        "gpuNames": [
            torch_module.cuda.get_device_name(index)
            for index in range(torch_module.cuda.device_count())
        ]
        if cuda_available
        else [],
    }


def _markdown(report: dict[str, Any], run_directory: Path) -> str:
    overall = report["metrics"]["overall"]
    gate = report["qualityGate"]
    mapping = report["classMapping"]
    worst = report["metrics"]["worstImages"][:10]
    lines = [
        "# VisionFlow YOLO 정확도 평가",
        "",
        f"- 상태: **{gate['status']}**",
        f"- 모델: `{report['model']['path']}`",
        f"- 모델 SHA-256: `{report['model']['sha256']}`",
        f"- 데이터셋 지문: `{report['dataset']['fingerprintSha256']}`",
        f"- 검증 이미지: {report['dataset']['imageCount']}장",
        f"- 장치: `{report['evaluation']['device']}`",
        "",
        "## 전체 지표",
        "",
        "| Precision | Recall | mAP50 | mAP50-95 |",
        "|---:|---:|---:|---:|",
        (
            f"| {overall['precision']:.4f} | {overall['recall']:.4f} | "
            f"{overall['map50']:.4f} | {overall['map50_95']:.4f} |"
        ),
        "",
        "## 관제 클래스 매핑",
        "",
        f"- 상태: **{mapping['status']}**",
        f"- 오류 수: {len(mapping['errors'])}",
        "- 템플릿: `class-mapping.template.json`",
        "- 클래스 의미 확인 전에는 런타임 매핑으로 사용하지 마세요.",
        "",
        "## 오류가 큰 이미지 상위 10개",
        "",
        "| 이미지 | F1 | FP | FN |",
        "|---|---:|---:|---:|",
    ]
    if worst:
        for row in worst:
            lines.append(f"| {row['image']} | {row['f1']:.4f} | {row['fp']} | {row['fn']} |")
    else:
        lines.append("| 개별 이미지 지표 미제공 | - | - | - |")
    lines.extend(
        [
            "",
            "## 생성 파일",
            "",
            "- `evaluation-report.json`: 전체 재현 정보와 결과",
            "- `per-class-metrics.csv`: 클래스별 P/R/F1/AP와 TP/FP/FN",
            "- `worst-image-errors.csv`: 이미지별 오류 우선순위",
            "- `confusion-matrix.json`: 원본/정규화 혼동행렬",
            "- `ultralytics/`: PR 곡선과 Ultralytics 기본 플롯",
            "",
            f"결과 폴더: `{run_directory}`",
            "",
        ]
    )
    return "\n".join(lines)


def run_evaluation(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    model_path = Path(args.model).resolve()
    data_yaml = Path(args.data).resolve()
    if not model_path.is_file():
        raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {model_path}")

    dataset = load_dataset_spec(data_yaml, args.split, args.dataset_hash_mode)
    model_sha = sha256_file(model_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_directory = Path(args.output).resolve() / f"{model_path.stem}-{timestamp}"
    ultralytics_directory = run_directory / "ultralytics"
    run_directory.mkdir(parents=True, exist_ok=False)

    import torch
    import ultralytics
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    model_names = normalize_names(model.names)
    dataset_names = {int(key): value for key, value in dataset["names"].items()}
    compare_model_and_dataset_names(model_names, dataset_names)

    validation_arguments = {
        "data": str(data_yaml),
        "split": args.split,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "device": args.device,
        "workers": args.workers,
        "conf": args.conf,
        "iou": args.iou,
        "plots": True,
        "project": str(ultralytics_directory.parent),
        "name": ultralytics_directory.name,
        "exist_ok": True,
        "verbose": True,
    }
    if args.save_json:
        validation_arguments["save_json"] = True
    metrics = model.val(**validation_arguments)

    per_class = extract_per_class_metrics(metrics, model_names)
    image_metrics = extract_image_metrics(metrics)
    confusion_matrix = extract_confusion_matrix(metrics)
    overall = {
        "precision": _number(metrics.box.mp),
        "recall": _number(metrics.box.mr),
        "map50": _number(metrics.box.map50),
        "map75": _number(metrics.box.map75),
        "map50_95": _number(metrics.box.map),
    }
    thresholds = {
        "precision": args.min_precision,
        "recall": args.min_recall,
        "map50": args.min_map50,
        "map50_95": args.min_map50_95,
    }
    quality_gate = evaluate_thresholds(overall, thresholds)

    template = build_mapping_template(
        model_names,
        model_sha,
        dataset["fingerprintSha256"],
    )
    template_path = run_directory / "class-mapping.template.json"
    template_path.write_text(
        json.dumps(template, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    mapping_errors: list[str] = []
    mapping_path = None
    mapping_status = "REVIEW_REQUIRED"
    if args.class_mapping:
        mapping_path = str(Path(args.class_mapping).resolve())
        mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8-sig"))
        if not isinstance(mapping, dict):
            mapping_errors = ["매핑 파일 최상위 값은 사전이어야 합니다."]
        else:
            mapping_errors = validate_mapping(mapping, model_names, model_sha)
        mapping_status = "VALID" if not mapping_errors else "INVALID"

    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "model": {
            "path": str(model_path),
            "fileName": model_path.name,
            "sizeBytes": model_path.stat().st_size,
            "sha256": model_sha,
            "classNames": model_names,
        },
        "dataset": dataset,
        "evaluation": {
            "split": args.split,
            "imageSize": args.imgsz,
            "batch": args.batch,
            "workers": args.workers,
            "device": args.device,
            "confidence": args.conf,
            "iou": args.iou,
            "runtime": _runtime_metadata(torch, ultralytics),
            "speedMilliseconds": {
                key: _number(value) for key, value in getattr(metrics, "speed", {}).items()
            },
        },
        "qualityGate": quality_gate,
        "classMapping": {
            "status": mapping_status,
            "providedPath": mapping_path,
            "templatePath": str(template_path),
            "errors": mapping_errors,
        },
        "metrics": {
            "overall": overall,
            "perClass": per_class,
            "worstImages": image_metrics,
            "confusionMatrix": confusion_matrix,
        },
    }

    (run_directory / "evaluation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_directory / "confusion-matrix.json").write_text(
        json.dumps(confusion_matrix, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(
        run_directory / "per-class-metrics.csv",
        per_class,
        [
            "classId",
            "className",
            "images",
            "instances",
            "precision",
            "recall",
            "f1",
            "map50",
            "map50_95",
            "tp",
            "fp",
            "fn",
            "countSource",
        ],
    )
    _write_csv(
        run_directory / "worst-image-errors.csv",
        image_metrics,
        ["image", "precision", "recall", "f1", "tp", "fp", "fn"],
    )
    (run_directory / "README.md").write_text(
        _markdown(report, run_directory),
        encoding="utf-8",
    )
    return run_directory, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VisionFlow YOLO 정확도 평가")
    parser.add_argument("--model", required=True, help="YOLO .pt 모델 경로")
    parser.add_argument("--data", required=True, help="YOLO data.yaml 경로")
    parser.add_argument("--output", default="artifacts/model-evaluation")
    parser.add_argument("--split", default="val")
    parser.add_argument("--device", default="0")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--conf", type=float, default=0.001)
    parser.add_argument("--iou", type=float, default=0.7)
    parser.add_argument("--dataset-hash-mode", choices=("labels", "full"), default="labels")
    parser.add_argument("--class-mapping")
    parser.add_argument("--require-approved-mapping", action="store_true")
    parser.add_argument("--save-json", action="store_true")
    parser.add_argument("--min-precision", type=float)
    parser.add_argument("--min-recall", type=float)
    parser.add_argument("--min-map50", type=float)
    parser.add_argument("--min-map50-95", type=float)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 0.0 <= args.conf <= 1.0 or not 0.0 <= args.iou <= 1.0:
        raise ValueError("conf와 iou는 0~1 사이여야 합니다.")
    if args.imgsz <= 0 or args.batch <= 0 or args.workers < 0:
        raise ValueError("imgsz/batch는 양수이고 workers는 0 이상이어야 합니다.")
    thresholds = (
        args.min_precision,
        args.min_recall,
        args.min_map50,
        args.min_map50_95,
    )
    if any(value is not None and not 0.0 <= value <= 1.0 for value in thresholds):
        raise ValueError("최소 품질 기준은 0~1 사이여야 합니다.")

    run_directory, report = run_evaluation(args)
    print(f"\nVisionFlow model evaluation: {report['qualityGate']['status']}")
    print(f"Report: {run_directory / 'README.md'}")
    print(f"JSON  : {run_directory / 'evaluation-report.json'}")

    if report["qualityGate"]["status"] == "FAILED":
        return 2
    mapping = report["classMapping"]
    if args.require_approved_mapping and mapping["status"] != "VALID":
        print("Approved class mapping is required.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
