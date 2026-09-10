from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .loader import load_experimental_dataset
from .model import CanonicalExperimentalDataset

SAMPLE_COLUMNS = {
    "dataset_id", "sample_id", "measurement_id", "cultivar", "tissue", "batch_id",
    "storage_day", "storage_temperature_c", "ssc_brix", "firmness_n",
    "sample_thickness_mm", "notes",
}
SPECTRA_COLUMNS = {
    "dataset_id", "sample_id", "measurement_id", "tissue", "wavelength_nm",
    "reflectance", "transmittance", "mu_a_mm_inv", "mu_s_prime_mm_inv",
}
CHANNEL_COLUMNS = {
    "reflectance": "reflectance",
    "transmittance": "transmittance",
    "mu_a": "mu_a_mm_inv",
    "mu_s_prime": "mu_s_prime_mm_inv",
}
EXPECTED_UNITS = {
    "wavelength": "nm", "reflectance": "fraction_0_1", "transmittance": "fraction_0_1",
    "mu_a": "mm^-1", "mu_s_prime": "mm^-1", "ssc": "degree_brix",
    "firmness": "N", "sample_thickness": "mm",
}


def _report() -> dict[str, Any]:
    return {"schema_version": 2, "valid": True, "errors": [], "warnings": [], "checks": {}, "stats": {}}


def _error(report: dict[str, Any], code: str, message: str, **details: Any) -> None:
    report["errors"].append({"code": code, "message": message, **details})
    report["valid"] = False


def _warning(report: dict[str, Any], code: str, message: str, **details: Any) -> None:
    report["warnings"].append({"code": code, "message": message, **details})


def _check_manifest(dataset: CanonicalExperimentalDataset, report: dict[str, Any]) -> None:
    manifest = dataset.manifest.raw
    required = {"schema_version", "dataset_id", "source_type", "status", "paper", "provenance",
                "available_channels", "units", "wavelength", "iad_settings", "measurement",
                "field_mapping", "notes"}
    missing = sorted(required - set(manifest))
    if missing:
        _error(report, "manifest_missing_fields", "Manifest is missing required fields", fields=missing)
    if manifest.get("schema_version") != 2:
        _error(report, "manifest_schema_version", "Experimental manifest must use schema version 2")
    if manifest.get("source_type") != "experimental":
        _error(report, "manifest_source_type", "Experimental dataset must have source_type=experimental")
    if not isinstance(manifest.get("dataset_id"), str) or not manifest.get("dataset_id", "").strip():
        _error(report, "manifest_dataset_id", "Manifest dataset_id must be non-empty")
    if manifest.get("status") not in {"pending", "received", "processed"}:
        _error(report, "manifest_status", "Manifest status is not a supported v2 status")
    units = manifest.get("units") if isinstance(manifest.get("units"), dict) else {}
    for key, expected in EXPECTED_UNITS.items():
        if units.get(key) != expected:
            _error(report, "unit_mismatch", f"Manifest unit for {key} must be {expected}", field=key)
    paper = manifest.get("paper") or {}
    if paper.get("doi") and not isinstance(paper["doi"], str):
        _error(report, "paper_doi_type", "paper.doi must be a string or null")
    channels = manifest.get("available_channels")
    if not isinstance(channels, list) or not set(channels).issubset(CHANNEL_COLUMNS):
        _error(report, "available_channels", "Manifest has an unknown available channel")


def _check_tables(dataset: CanonicalExperimentalDataset, report: dict[str, Any]) -> None:
    samples, spectra = dataset.samples, dataset.spectra
    for frame, name, required, known in (
        (samples, "samples", {"dataset_id", "sample_id", "measurement_id"}, SAMPLE_COLUMNS),
        (spectra, "spectra", {"dataset_id", "sample_id", "measurement_id", "wavelength_nm"}, SPECTRA_COLUMNS),
    ):
        missing = sorted(required - set(frame.columns))
        if missing:
            _error(report, f"{name}_columns", f"{name} table is missing required columns", fields=missing)
        unknown = sorted(set(frame.columns) - known)
        if unknown:
            _warning(report, f"{name}_unknown_columns", f"Unknown {name} columns were preserved", fields=unknown)
    for frame, name in ((samples, "samples"), (spectra, "spectra")):
        for column in ("dataset_id", "sample_id"):
            if column in frame and frame[column].isna().any():
                _error(report, f"{name}_{column}_missing", f"{name}.{column} cannot be null")
            if column in frame and frame[column].astype(str).str.strip().eq("").any():
                _error(report, f"{name}_{column}_empty", f"{name}.{column} cannot be empty")
    sample_keys = ["dataset_id", "sample_id", "measurement_id"]
    if all(column in samples for column in sample_keys) and samples.duplicated(sample_keys).any():
        _error(report, "duplicate_sample_measurement", "Duplicate sample/measurement rows detected")
    spectra_key = ["dataset_id", "sample_id", "measurement_id"]
    if "tissue" in spectra:
        spectra_key.append("tissue")
    spectra_key.append("wavelength_nm")
    if all(column in spectra for column in spectra_key) and spectra.duplicated(spectra_key).any():
        _error(report, "duplicate_spectrum_point", "Duplicate measurement/tissue/wavelength rows detected")

    if all(column in samples for column in sample_keys) and all(column in spectra for column in sample_keys):
        sample_set = set(map(tuple, samples[sample_keys].itertuples(index=False, name=None)))
        spectrum_set = set(map(tuple, spectra[sample_keys].itertuples(index=False, name=None)))
        missing = sorted(spectrum_set - sample_set)
        if missing:
            _error(report, "spectra_foreign_key", "Spectra contain samples absent from samples.csv", examples=missing[:5])


def _check_spectra(dataset: CanonicalExperimentalDataset, report: dict[str, Any]) -> None:
    spectra = dataset.spectra
    if "wavelength_nm" not in spectra:
        return
    wavelengths = pd.to_numeric(spectra["wavelength_nm"], errors="coerce")
    if wavelengths.isna().any() or (~np.isfinite(wavelengths)).any() or (wavelengths <= 0).any():
        _error(report, "wavelength_values", "wavelength_nm must be finite and positive")
    for channel, column in CHANNEL_COLUMNS.items():
        if column not in spectra:
            continue
        values = pd.to_numeric(spectra[column], errors="coerce")
        present = values.notna()
        if channel in {"reflectance", "transmittance"} and ((values[present] < 0) | (values[present] > 1)).any():
            _error(report, "fraction_range", f"{column} must be in [0, 1]")
        if channel in {"mu_a", "mu_s_prime"} and (values[present] < 0).any():
            _error(report, "coefficient_range", f"{column} must be non-negative")
        if channel in dataset.manifest.available_channels:
            fraction_missing = float((~present).mean()) if len(values) else 1.0
            if not present.any():
                _error(report, "declared_channel_absent", f"Declared channel {channel} has no values")
            elif fraction_missing > 0.05:
                _error(report, "declared_channel_missing", f"Declared channel {channel} has unexplained missing values", fraction_missing=fraction_missing)
            elif fraction_missing > 0:
                _warning(report, "declared_channel_partial", f"Declared channel {channel} has some missing values", fraction_missing=fraction_missing)
        elif present.any():
            _warning(report, "undeclared_channel", f"Column {column} contains values but is not declared available", channel=channel)

    grid_columns = ["dataset_id", "sample_id", "measurement_id"]
    if "tissue" in spectra:
        grid_columns.append("tissue")
    grids: list[tuple[tuple[Any, ...], tuple[float, ...]]] = []
    for key, group in spectra.groupby(grid_columns, dropna=False, sort=True):
        raw_grid = tuple(float(value) for value in group["wavelength_nm"].drop_duplicates())
        grid = tuple(sorted(raw_grid))
        if raw_grid != grid:
            _error(report, "wavelength_monotonic", "Wavelength grid is not strictly increasing", group=str(key))
        grids.append((key if isinstance(key, tuple) else (key,), grid))
    if grids:
        reference = grids[0][1]
        inconsistent = [key for key, grid in grids[1:] if grid != reference]
        if inconsistent:
            _error(report, "wavelength_grid_mismatch", "Wavelength grids differ; no interpolation was performed", examples=[str(key) for key in inconsistent[:5]])
        report["stats"]["wavelength_count"] = len(reference)
        report["stats"]["wavelength_min_nm"] = min(reference)
        report["stats"]["wavelength_max_nm"] = max(reference)


def validate_experimental_dataset(dataset: CanonicalExperimentalDataset | Path) -> dict[str, Any]:
    """Return a machine-readable report; no missing experimental value is imputed."""
    if isinstance(dataset, (str, Path)):
        dataset = load_experimental_dataset(Path(dataset))
    report = _report()
    _check_manifest(dataset, report)
    _check_tables(dataset, report)
    _check_spectra(dataset, report)
    report["stats"].update({
        "dataset_id": dataset.dataset_id,
        "sample_rows": int(len(dataset.samples)),
        "spectrum_rows": int(len(dataset.spectra)),
        "sample_count": int(dataset.samples["sample_id"].nunique()) if "sample_id" in dataset.samples else 0,
    })
    report["checks"]["iad_g_and_refractive_index_required"] = False
    report["checks"]["interpolation_performed"] = False
    return report
