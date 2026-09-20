from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SYNTHETIC_SOURCES = {"synthetic_math", "synthetic_physics", "literature_constrained"}
STATES = {
    "created", "validating", "queued", "generating_data", "simulating",
    "postprocessing", "preprocessing", "training", "evaluating", "rendering",
    "completed", "failed", "cancelling", "cancelled",
}
SOURCE_TYPES = SYNTHETIC_SOURCES | {"real_measurement", "hybrid_calibrated"}
MODEL_STATUSES = {
    "method_demo", "synthetic_simulation_demo",
    "experimental_pending_validation", "experiment_calibrated",
}
BACKENDS = {"cpu", "cuda", "mixed", "none"}
REQUIRED_SAMPLE_COLUMNS = {"sample_id", "fruit_id", "batch_id", "source_type"}


class ContractError(ValueError):
    """Raised when a run contract is structurally or semantically invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"Missing JSON file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Invalid JSON in {path.name}: {exc.msg}") from exc
    _require(isinstance(value, dict), f"{path.name} must contain a JSON object")
    return value


def _require_schema_version(document: dict[str, Any], name: str) -> None:
    _require(document.get("schema_version") == SCHEMA_VERSION,
             f"{name}: schema_version must be {SCHEMA_VERSION}")


def _require_run_id(value: Any, name: str = "run_id") -> str:
    _require(isinstance(value, str) and RUN_ID_RE.fullmatch(value) is not None,
             f"{name} must match {RUN_ID_RE.pattern}")
    return value


def validate_manifest(document: dict[str, Any]) -> None:
    _require_schema_version(document, "manifest")
    run_id = _require_run_id(document.get("run_id"))
    _require(isinstance(document.get("created_at"), str) and document["created_at"],
             "manifest.created_at must be a non-empty string")
    _require(document.get("status") in STATES, "manifest.status is not a supported state")
    _require(document.get("source_type") in SOURCE_TYPES,
             "manifest.source_type is not supported")
    _require(isinstance(document.get("generator_version"), str)
             and document["generator_version"],
             "manifest.generator_version must be non-empty")
    _require(isinstance(document.get("configuration_hash"), str)
             and document["configuration_hash"],
             "manifest.configuration_hash must be non-empty")
    _require(isinstance(document.get("seed"), int) and document["seed"] >= 0,
             "manifest.seed must be a non-negative integer")
    _require(isinstance(document.get("software"), dict), "manifest.software must be an object")
    _require(document.get("backend") in BACKENDS, "manifest.backend is not supported")
    _validate_coordinate_system(document.get("coordinate_system"))
    _require(isinstance(document.get("data_status"), str) and document["data_status"],
             "manifest.data_status must be non-empty")
    _require(document.get("model_status") in MODEL_STATUSES,
             "manifest.model_status is not supported")
    _require(document.get("artifacts_index") == "artifacts.json",
             "manifest.artifacts_index must be artifacts.json")
    _require(isinstance(document.get("warnings"), list)
             and all(isinstance(item, str) for item in document["warnings"]),
             "manifest.warnings must be a string array")
    if document["source_type"] in SYNTHETIC_SOURCES:
        _require(document["warnings"],
                 f"synthetic run {run_id} must contain at least one warning")
        _require(document["model_status"] in {"method_demo", "synthetic_simulation_demo"},
                 "synthetic runs cannot be marked experiment_calibrated")


def _validate_coordinate_system(value: Any) -> None:
    _require(isinstance(value, dict), "manifest.coordinate_system must be an object")
    expected = {
        "name": "fruitsim_rh_y_up",
        "handedness": "right",
        "up_axis": "+Y",
        "length_unit": "mm",
    }
    for key, expected_value in expected.items():
        _require(value.get(key) == expected_value,
                 f"coordinate_system.{key} must be {expected_value!r}")
    transform = value.get("world_to_unity")
    _require(isinstance(transform, list) and len(transform) == 16
             and all(isinstance(item, (int, float)) for item in transform),
             "coordinate_system.world_to_unity must contain 16 numbers")


def validate_request(document: dict[str, Any]) -> None:
    _require_schema_version(document, "request")
    _require_run_id(document.get("run_id"))
    _require(document.get("source_type") in SOURCE_TYPES,
             "request.source_type is not supported")
    _require(isinstance(document.get("seed"), int) and document["seed"] >= 0,
             "request.seed must be a non-negative integer")
    _require(isinstance(document.get("output_dir"), str) and document["output_dir"],
             "request.output_dir must be non-empty")
    steps = document.get("steps")
    _require(isinstance(steps, list) and steps and len(set(steps)) == len(steps),
             "request.steps must be a non-empty list of unique steps")
    _require(set(steps) <= {"generate", "simulate", "postprocess", "train", "visualize"},
             "request.steps contains an unsupported step")


def validate_status(document: dict[str, Any], expected_run_id: str | None = None) -> None:
    _require_schema_version(document, "status")
    run_id = _require_run_id(document.get("run_id"))
    if expected_run_id is not None:
        _require(run_id == expected_run_id, "status.run_id does not match manifest.run_id")
    _require(document.get("state") in STATES, "status.state is not supported")
    _require(isinstance(document.get("updated_at"), str) and document["updated_at"],
             "status.updated_at must be non-empty")
    for key in ("completed", "total"):
        if key in document:
            _require(isinstance(document[key], int) and document[key] >= 0,
                     f"status.{key} must be a non-negative integer")


def _validate_artifact_index(document: dict[str, Any]) -> list[dict[str, Any]]:
    _require_schema_version(document, "artifacts")
    artifacts = document.get("artifacts")
    _require(isinstance(artifacts, list), "artifacts.artifacts must be a list")
    ids: set[str] = set()
    for artifact in artifacts:
        _require(isinstance(artifact, dict), "each artifact must be an object")
        artifact_id = artifact.get("artifact_id")
        _require(isinstance(artifact_id, str) and artifact_id, "artifact_id must be non-empty")
        _require(artifact_id not in ids, f"duplicate artifact_id: {artifact_id}")
        ids.add(artifact_id)
        relative_path = artifact.get("relative_path")
        _require(isinstance(relative_path, str) and relative_path,
                 f"artifact {artifact_id} has no relative_path")
        _require(not Path(relative_path).is_absolute(),
                 f"artifact {artifact_id} must use a relative path")
        _require(".." not in Path(relative_path).parts,
                 f"artifact {artifact_id} may not escape the run directory")
        digest = artifact.get("sha256")
        _require(isinstance(digest, str) and len(digest) == 64
                 and all(char in "0123456789abcdefABCDEF" for char in digest),
                 f"artifact {artifact_id} has invalid sha256")
    return artifacts


def _validate_samples(path: Path) -> None:
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            columns = set(reader.fieldnames or [])
            missing = REQUIRED_SAMPLE_COLUMNS - columns
            _require(not missing, f"samples.csv is missing columns: {sorted(missing)}")
            for row_number, row in enumerate(reader, start=2):
                for column in REQUIRED_SAMPLE_COLUMNS:
                    _require(row.get(column, "").strip() != "",
                             f"samples.csv row {row_number} has empty {column}")
    except UnicodeDecodeError as exc:
        raise ContractError("samples.csv must be UTF-8") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_run_directory(run_dir: Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    _require(root.is_dir(), f"run directory does not exist: {run_dir}")
    manifest = _read_json(root / "manifest.json")
    validate_manifest(manifest)
    run_id = manifest["run_id"]
    _require(root.name == run_id,
             f"run directory name {root.name!r} does not match manifest.run_id {run_id!r}")

    request_path = root / "request.json"
    if request_path.exists():
        request = _read_json(request_path)
        validate_request(request)
        _require(request["run_id"] == run_id, "request.run_id does not match manifest.run_id")

    status = _read_json(root / "status.json")
    validate_status(status, run_id)
    _require(status["state"] == manifest["status"],
             "status.state does not match manifest.status")

    artifacts_document = _read_json(root / "artifacts.json")
    artifacts = _validate_artifact_index(artifacts_document)
    checked = 0
    for artifact in artifacts:
        path = (root / artifact["relative_path"]).resolve()
        _require(path.is_relative_to(root),
                 f"artifact escapes run directory: {artifact['relative_path']}")
        _require(path.is_file(), f"artifact file does not exist: {artifact['relative_path']}")
        actual = _sha256(path)
        _require(actual.lower() == artifact["sha256"].lower(),
                 f"artifact hash mismatch: {artifact['relative_path']}")
        checked += 1

    samples_path = root / "data" / "samples.csv"
    if samples_path.exists():
        _validate_samples(samples_path)

    return {
        "valid": True,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": manifest["status"],
        "source_type": manifest["source_type"],
        "artifacts_checked": checked,
        "samples_checked": samples_path.exists(),
    }


def validate_run_directory_from_path(path: str | Path) -> dict[str, Any]:
    try:
        return validate_run_directory(Path(path))
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError(str(exc)) from exc
