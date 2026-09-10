from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pandas as pd


def apply_column_mapping(frame: pd.DataFrame, mapping: Mapping[str, str], required: set[str] | None = None) -> pd.DataFrame:
    """Apply an explicit source-column -> canonical-column mapping without filling values."""
    if len(set(mapping.values())) != len(mapping.values()):
        raise ValueError("Column mapping maps multiple source columns to one canonical column")
    result = frame.rename(columns=dict(mapping)).copy()
    if required:
        missing = sorted(set(required) - set(result.columns))
        if missing:
            raise ValueError(f"Explicit mapping did not produce required columns: {missing}")
    return result


def write_canonical_tables(
    output_root: Path,
    manifest: Mapping[str, object],
    samples: pd.DataFrame,
    spectra: pd.DataFrame,
    *,
    samples_mapping: Mapping[str, str] | None = None,
    spectra_mapping: Mapping[str, str] | None = None,
) -> Path:
    """Write explicitly mapped tables; caller owns unit conversion and provenance notes."""
    output_root = Path(output_root)
    samples = apply_column_mapping(samples, samples_mapping or {})
    spectra = apply_column_mapping(spectra, spectra_mapping or {})
    if not {"dataset_id", "sample_id"}.issubset(samples.columns):
        raise ValueError("samples requires dataset_id and sample_id")
    if not {"dataset_id", "sample_id", "wavelength_nm"}.issubset(spectra.columns):
        raise ValueError("spectra requires dataset_id, sample_id and wavelength_nm")
    (output_root / "processed").mkdir(parents=True, exist_ok=True)
    (output_root / "manifest.json").write_text(json.dumps(dict(manifest), indent=2), encoding="utf-8")
    samples.to_csv(output_root / "processed" / "samples.csv", index=False)
    spectra.to_csv(output_root / "processed" / "spectra.csv", index=False)
    return output_root
