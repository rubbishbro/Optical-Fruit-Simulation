from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .model import CanonicalExperimentalDataset, DatasetManifest

SAMPLE_REQUIRED_COLUMNS = {"dataset_id", "sample_id"}
SPECTRA_REQUIRED_COLUMNS = {"dataset_id", "sample_id", "wavelength_nm"}


class ExperimentalDatasetLoadError(ValueError):
    """Raised for a structurally unreadable canonical dataset."""


class ExperimentalDatasetPending(ExperimentalDatasetLoadError):
    """Raised when a pending manifest has not received canonical tables yet."""


def _dataset_root(path: Path) -> Path:
    path = Path(path)
    if path.is_file():
        if path.name == "manifest.json":
            return path.parent
        raise ExperimentalDatasetLoadError(f"Expected an experimental dataset directory: {path}")
    return path


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ExperimentalDatasetLoadError(f"{name} is missing required columns: {missing}")


def _add_internal_measurement_key(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "measurement_id" not in result.columns:
        result["measurement_id"] = result["sample_id"]
    else:
        missing = result["measurement_id"].isna() | result["measurement_id"].astype(str).str.strip().eq("")
        result.loc[missing, "measurement_id"] = result.loc[missing, "sample_id"]
    return result


def load_experimental_dataset(path: Path) -> CanonicalExperimentalDataset:
    """Load manifest and processed canonical tables without interpolation or imputation."""
    root = _dataset_root(Path(path))
    manifest_path = root / "manifest.json"
    samples_path = root / "processed" / "samples.csv"
    spectra_path = root / "processed" / "spectra.csv"
    if not manifest_path.exists():
        raise ExperimentalDatasetLoadError(f"Missing experimental dataset file: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExperimentalDatasetLoadError(f"Invalid manifest JSON: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise ExperimentalDatasetLoadError("manifest.json must contain an object")
    missing_tables = [path for path in (samples_path, spectra_path) if not path.exists()]
    if missing_tables and manifest.get("status") == "pending":
        raise ExperimentalDatasetPending(
            f"dataset pending; canonical tables not present yet: {', '.join(str(path) for path in missing_tables)}"
        )
    for required_path in missing_tables:
        raise ExperimentalDatasetLoadError(f"Missing experimental dataset file: {required_path}")
    samples = pd.read_csv(samples_path)
    spectra = pd.read_csv(spectra_path)
    # Validate structural identity before deriving the optional internal key;
    # malformed author mappings should produce our designed load error, not a
    # pandas KeyError from indexing sample_id.
    _require_columns(samples, SAMPLE_REQUIRED_COLUMNS, "samples.csv")
    _require_columns(spectra, SPECTRA_REQUIRED_COLUMNS, "spectra.csv")
    samples = _add_internal_measurement_key(samples)
    spectra = _add_internal_measurement_key(spectra)
    return CanonicalExperimentalDataset(root, DatasetManifest(manifest), samples, spectra)
