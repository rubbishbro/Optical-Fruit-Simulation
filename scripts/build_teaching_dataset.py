#!/usr/bin/env python3
"""Build the deterministic, explicitly synthetic dataset used by Teaching Mode.

This dataset is deliberately separate from the correctness fixtures.  Its
structured signal makes the visual story readable, but it is not experimental
evidence and must never be used to claim real-apple performance.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


DEFAULT_SAMPLES = 128
DEFAULT_SEED = 20260922
DEFAULT_WAVELENGTHS = np.arange(400.0, 1000.1, 10.0, dtype=float)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_teaching_run(
    output_root: Path,
    *,
    samples: int = DEFAULT_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> Path:
    """Write a reproducible run directory with 128 samples × 61 wavelengths."""
    if samples < 16:
        raise ValueError("teaching dataset needs at least 16 samples")
    rng = np.random.default_rng(seed)
    wavelengths = DEFAULT_WAVELENGTHS.copy()
    output_root = Path(output_root)
    data_dir = output_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    spectra_rows: list[dict[str, object]] = []
    for index in range(samples):
        sample_id = f"ST-{index + 1:04d}"
        batch_index = index % 3
        batch_id = f"teaching-batch-{batch_index + 1}"
        latent = float(rng.normal(0.0, 1.0))
        ssc = float(np.clip(12.5 + 2.0 * latent + rng.normal(0.0, 0.22), 8.0, 17.0))
        scale = float(1.0 + rng.normal(0.0, 0.075))
        baseline = float(rng.normal(0.0, 0.012) + (batch_index - 1) * 0.009)
        slope = float(rng.normal(0.0, 0.000018))
        signal = (
            0.022 * latent * np.exp(-0.5 * ((wavelengths - 670.0) / 30.0) ** 2)
            - 0.016 * latent * np.exp(-0.5 * ((wavelengths - 780.0) / 38.0) ** 2)
            + 0.019 * latent * np.exp(-0.5 * ((wavelengths - 920.0) / 28.0) ** 2)
        )
        batch_shape = (batch_index - 1) * 0.007 * np.exp(-0.5 * ((wavelengths - 550.0) / 115.0) ** 2)
        base = 0.59 - 0.00013 * (wavelengths - 400.0)
        base += 0.014 * np.exp(-0.5 * ((wavelengths - 540.0) / 55.0) ** 2)
        base += 0.010 * np.exp(-0.5 * ((wavelengths - 960.0) / 45.0) ** 2)
        noise = rng.normal(0.0, 0.0028, wavelengths.size)
        noise = 0.25 * np.roll(noise, 1) + 0.5 * noise + 0.25 * np.roll(noise, -1)
        reflectance = np.clip(scale * (base + signal + batch_shape) + baseline + slope * (wavelengths - 700.0) + noise, 0.05, 0.95)
        rows.append({
            "sample_id": sample_id,
            "fruit_id": sample_id,
            "batch_id": batch_id,
            "source_type": "SYNTHETIC_TEACHING",
            "synthetic_ssc_proxy": f"{ssc:.8f}",
            "teaching_latent": f"{latent:.8f}",
        })
        for wavelength, value in zip(wavelengths, reflectance):
            spectra_rows.append({
                "sample_id": sample_id,
                "fruit_id": sample_id,
                "batch_id": batch_id,
                "source_type": "SYNTHETIC_TEACHING",
                "wavelength_nm": f"{wavelength:.6f}",
                "reflectance": f"{value:.8f}",
                "synthetic_ssc_proxy": f"{ssc:.8f}",
            })

    _write_csv(
        data_dir / "samples.csv",
        ["sample_id", "fruit_id", "batch_id", "source_type", "synthetic_ssc_proxy", "teaching_latent"],
        rows,
    )
    _write_csv(
        data_dir / "spectra.csv",
        ["sample_id", "fruit_id", "batch_id", "source_type", "wavelength_nm", "reflectance", "synthetic_ssc_proxy"],
        spectra_rows,
    )
    manifest = {
        "schema_version": 1,
        "dataset_id": "synthetic_teaching_v1",
        "source_type": "SYNTHETIC_TEACHING",
        "purpose": "visualization_and_teaching",
        "not_experimental_evidence": True,
        "seed": seed,
        "sample_count": samples,
        "feature_count": int(len(wavelengths)),
        "wavelengths_nm": wavelengths.tolist(),
        "construction": [
            "SSC-related smooth spectral components",
            "multiplicative scale nuisance",
            "additive baseline nuisance",
            "smooth measurement noise",
            "three categorical batch groups",
        ],
        "warning": "Synthetic teaching construction; not real fruit measurements or experimental evidence.",
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/ml_teaching_dataset"))
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    print(build_teaching_run(args.output, samples=args.samples, seed=args.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
