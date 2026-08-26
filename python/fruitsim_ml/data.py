from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


WARNING = "METHOD DEMONSTRATION ONLY - NOT VALID FOR REAL APPLE SSC PREDICTION"

REQUIRED_COLUMNS = {
    "dataset_id", "sample_id", "source_type", "cultivar", "tissue",
    "wavelength_nm", "mu_a_mm_inv", "mu_s_prime_mm_inv", "g",
    "refractive_index", "ssc_brix", "batch_id", "source_doi",
    "measurement_method", "uncertainty", "notes",
}


def validate_dataset(path: Path) -> dict[str, object]:
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    numeric = ["wavelength_nm", "mu_a_mm_inv", "mu_s_prime_mm_inv", "g", "refractive_index", "ssc_brix"]
    if frame[numeric].isna().any().any():
        raise ValueError("Dataset contains missing numeric optical or SSC values")
    if (frame[["mu_a_mm_inv", "mu_s_prime_mm_inv"]] < 0.0).any().any():
        raise ValueError("Optical coefficients must be non-negative")
    if ((frame["g"] < -1.0) | (frame["g"] >= 1.0)).any():
        raise ValueError("g must be in [-1, 1)")
    duplicate = frame.duplicated(["sample_id", "tissue", "wavelength_nm"])
    if duplicate.any():
        raise ValueError("Dataset has duplicate sample/tissue/wavelength rows")
    wavelength_counts = frame.groupby(["sample_id", "tissue"])["wavelength_nm"].nunique()
    if wavelength_counts.nunique() != 1:
        raise ValueError("Samples do not share a complete common wavelength grid")
    if frame[["sample_id", "batch_id"]].astype(str).apply(lambda column: column.str.len().eq(0)).any().any():
        raise ValueError("sample_id and batch_id must be non-empty")
    return {
        "schema_version": 1,
        "rows": int(len(frame)),
        "samples": int(frame["sample_id"].nunique()),
        "batches": int(frame["batch_id"].nunique()),
        "source_types": sorted(frame["source_type"].astype(str).unique().tolist()),
        "wavelength_min_nm": float(frame["wavelength_nm"].min()),
        "wavelength_max_nm": float(frame["wavelength_nm"].max()),
        "wavelength_count": int(wavelength_counts.iloc[0]),
        "valid": True,
    }


def generate_synthetic_golden_delicious(
    output: Path, samples: int = 600, seed: int = 20260819
) -> Path:
    """Generate reproducible literature-constrained, explicitly synthetic spectra."""
    rng = np.random.default_rng(seed)
    wavelengths = np.arange(500.0, 1000.1, 10.0)
    rows: list[dict[str, object]] = []
    for sample_index in range(samples):
        sample_id = f"SGD-{sample_index + 1:04d}"
        batch_id = f"synthetic-batch-{sample_index % 6 + 1}"
        ssc = float(np.clip(rng.normal(12.5, 1.55), 8.0, 17.0))
        apple_scale = rng.normal(1.0, 0.035)
        for wavelength in wavelengths:
            chlorophyll = 0.010 * np.exp(-0.5 * ((wavelength - 675.0) / 24.0) ** 2)
            water = 0.013 * np.exp(-0.5 * ((wavelength - 970.0) / 33.0) ** 2)
            baseline = 0.018 + 0.010 * np.exp(-(wavelength - 500.0) / 150.0)
            mu_a = (baseline + chlorophyll + water) * (1.0 + 0.022 * (ssc - 12.5))
            mu_a *= apple_scale * rng.normal(1.0, 0.025)
            mu_sp = (1.10 - 0.00030 * (wavelength - 500.0))
            mu_sp *= (1.0 + 0.010 * (ssc - 12.5)) * rng.normal(1.0, 0.018)
            mu_eff = np.sqrt(3.0 * mu_a * (mu_a + mu_sp))
            reflectance = np.exp(-2.6 * mu_eff) * rng.normal(1.0, 0.008)
            penetration = 1.0 / max(mu_eff, 1.0e-9)
            radial_decay = mu_eff / max(mu_sp, 1.0e-9)
            rows.append(
                {
                    "dataset_id": "synthetic_golden_delicious_v1",
                    "sample_id": sample_id,
                    "source_type": "synthetic",
                    "cultivar": "Golden Delicious",
                    "tissue": "flesh",
                    "wavelength_nm": wavelength,
                    "mu_a_mm_inv": mu_a,
                    "mu_s_prime_mm_inv": mu_sp,
                    "g": 0.90,
                    "refractive_index": 1.36,
                    "ssc_brix": ssc,
                    "batch_id": batch_id,
                    "source_doi": (
                        "10.1016/j.compag.2009.04.002;"
                        "10.13031/2013.26807;"
                        "10.17660/ActaHortic.2012.945.24"
                    ),
                    "measurement_method": "synthetic literature-constrained demonstration",
                    "uncertainty": "synthetic_noise_model_v1",
                    "notes": WARNING,
                    "reflectance": reflectance,
                    "penetration_depth_mm": penetration,
                    "radial_decay": radial_decay,
                }
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)
    metadata = {
        "schema_version": 1,
        "dataset_id": "synthetic_golden_delicious_v1",
        "seed": seed,
        "samples": samples,
        "wavelengths_nm": wavelengths.tolist(),
        "warning": WARNING,
        "purpose": "exercise the SSC workflow; not scientific training data",
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return output
