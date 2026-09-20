from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .contracts import (
    BACKENDS,
    ContractError,
    SOURCE_TYPES,
    STATES,
    validate_request,
    validate_run_directory,
)


SYNTHETIC_WARNING = "Synthetic data; not valid for real apple SSC prediction."
COORDINATE_SYSTEM = {
    "name": "fruitsim_rh_y_up",
    "handedness": "right",
    "up_axis": "+Y",
    "length_unit": "mm",
    "world_to_unity": [
        0.001, 0.0, 0.0, 0.0,
        0.0, 0.001, 0.0, 0.0,
        0.0, 0.0, -0.001, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ],
}
TERMINAL_STATES = {"completed", "failed", "cancelled"}
TRANSITIONS = {
    "created": {"validating", "generating_data", "failed", "cancelled"},
    "validating": {"queued", "generating_data", "failed", "cancelled"},
    "queued": {"generating_data", "simulating", "failed", "cancelled"},
    "generating_data": {"postprocessing", "simulating", "failed", "cancelling"},
    "simulating": {"postprocessing", "failed", "cancelling"},
    "postprocessing": {"preprocessing", "training", "rendering", "completed", "failed"},
    "preprocessing": {"training", "failed", "cancelling"},
    "training": {"evaluating", "failed", "cancelling"},
    "evaluating": {"rendering", "completed", "failed"},
    "rendering": {"completed", "failed"},
    "cancelling": {"cancelled", "failed"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class RunManager:
    """Create and update one immutable-once-completed Run directory."""

    root: Path
    manifest: dict[str, Any]
    request: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]

    @classmethod
    def create(
        cls,
        output_root: Path,
        run_id: str,
        source_type: str,
        seed: int,
        steps: Iterable[str],
        *,
        backend: str = "none",
        generator_version: str | None = None,
        configuration: Any | None = None,
        notes: list[str] | None = None,
    ) -> "RunManager":
        if source_type not in SOURCE_TYPES:
            raise ContractError(f"unsupported source_type: {source_type}")
        if backend not in BACKENDS:
            raise ContractError(f"unsupported backend: {backend}")
        root = Path(output_root).expanduser().resolve() / run_id
        if root.exists():
            raise ContractError(f"run already exists and will not be overwritten: {root}")
        root.mkdir(parents=True)
        for directory in ("data", "logs", "simulation", "ml", "spatial", "visualizations"):
            (root / directory).mkdir()

        request = {
            "schema_version": 1,
            "run_id": run_id,
            "source_type": source_type,
            "seed": int(seed),
            "output_dir": str(root),
            "steps": list(steps),
        }
        validate_request(request)
        configuration_hash = stable_hash(configuration if configuration is not None else request)
        synthetic = source_type in {"synthetic_math", "synthetic_physics", "literature_constrained"}
        model_status = "method_demo" if source_type == "synthetic_math" else (
            "synthetic_simulation_demo" if synthetic else "experimental_pending_validation"
        )
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "parent_run_id": None,
            "created_at": utc_now(),
            "status": "created",
            "source_type": source_type,
            "generator_version": generator_version or __version__,
            "configuration_hash": configuration_hash,
            "seed": int(seed),
            "software": {
                "fruitsim_pipeline": __version__,
                "python": platform.python_version(),
            },
            "git_commit": os.environ.get("FRUITSIM_GIT_COMMIT"),
            "backend": backend,
            "coordinate_system": COORDINATE_SYSTEM,
            "data_status": "synthetic_demonstration" if synthetic else "unverified",
            "model_status": model_status,
            "warnings": [SYNTHETIC_WARNING] if synthetic else [],
            "artifacts_index": "artifacts.json",
            "notes": notes or [],
        }
        manager = cls(root, manifest, request, {})
        _atomic_write_json(root / "request.json", request)
        _atomic_write_json(root / "manifest.json", manifest)
        _atomic_write_json(root / "status.json", manager._status_document("created"))
        manager._write_artifacts()
        manager.log("created", message="Run directory created")
        return manager

    @property
    def run_id(self) -> str:
        return self.manifest["run_id"]

    @property
    def state(self) -> str:
        return self.manifest["status"]

    def _status_document(self, state: str, **fields: Any) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": 1,
            "run_id": self.run_id,
            "state": state,
            "updated_at": utc_now(),
        }
        document.update({key: value for key, value in fields.items() if value is not None})
        return document

    def _write_manifest_and_status(self, status: dict[str, Any]) -> None:
        self.manifest["status"] = status["state"]
        _atomic_write_json(self.root / "manifest.json", self.manifest)
        _atomic_write_json(self.root / "status.json", status)

    def set_state(self, state: str, *, stage: str | None = None,
                  completed: int | None = None, total: int | None = None,
                  message: str | None = None) -> None:
        if state not in STATES:
            raise ContractError(f"unsupported state: {state}")
        if self.state in TERMINAL_STATES and state != self.state:
            raise ContractError(f"terminal Run cannot transition from {self.state} to {state}")
        if state != self.state and state not in TRANSITIONS.get(self.state, set()):
            raise ContractError(f"invalid Run transition: {self.state} -> {state}")
        status = self._status_document(
            state, stage=stage, completed=completed, total=total, message=message
        )
        self._write_manifest_and_status(status)
        self.log("state_changed", state=state, stage=stage, message=message)

    def fail(self, error: Exception | str, *, error_code: str = "run_failed") -> None:
        if self.state in TERMINAL_STATES:
            return
        message = str(error)
        status = self._status_document("failed", message=message, error_code=error_code)
        self._write_manifest_and_status(status)
        self.log("failed", error_code=error_code, message=message)

    def log(self, event: str, **fields: Any) -> None:
        document = {"timestamp": utc_now(), "run_id": self.run_id, "event": event}
        document.update(fields)
        with (self.root / "logs" / "pipeline.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(document, ensure_ascii=False) + "\n")

    def add_artifact(self, artifact_id: str, path: Path, *, role: str,
                     media_type: str, schema_version: int | None = 1,
                     producer: str | None = None, unit: str | None = None,
                     shape: list[int] | None = None, dtype: str | None = None) -> None:
        path = Path(path).resolve()
        if not path.is_file():
            raise ContractError(f"artifact file does not exist: {path}")
        if not path.is_relative_to(self.root):
            raise ContractError(f"artifact must be inside Run directory: {path}")
        relative_path = path.relative_to(self.root).as_posix()
        self.artifacts[artifact_id] = {
            "artifact_id": artifact_id,
            "role": role,
            "relative_path": relative_path,
            "media_type": media_type,
            "schema_version": schema_version,
            "producer": producer or "fruitsim_pipeline",
            "unit": unit,
            "shape": shape,
            "dtype": dtype,
            "sha256": _sha256(path),
        }
        self._write_artifacts()

    def _write_artifacts(self) -> None:
        _atomic_write_json(self.root / "artifacts.json", {
            "schema_version": 1,
            "artifacts": list(self.artifacts.values()),
        })

    def complete(self, *, message: str = "Run completed") -> dict[str, Any]:
        if self.state not in {"postprocessing", "evaluating", "rendering", "generating_data"}:
            raise ContractError(f"cannot complete Run from state {self.state}")
        if self.state != "rendering":
            self.set_state("completed", message=message)
        else:
            self.set_state("completed", message=message)
        return validate_run_directory(self.root)
