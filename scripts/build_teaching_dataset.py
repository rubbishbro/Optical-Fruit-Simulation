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
PROFILES = {
    "clean_signal": {
        "name": "合成数据 A · 清晰信号",
        "description": "信号较清晰、噪声较低，作为基础教学对照。",
        "batch_count": 3, "scale_sd": 0.025, "baseline_sd": 0.003,
        "noise_sd": 0.0018, "batch_effect": 0.002, "band_scale": 1.0, "spikes": False,
    },
    "baseline_shift": {
        "name": "合成数据 B · 基线与尺度偏移",
        "description": "样本具有更强基线和幅度差异，可观察 SNV 的作用。",
        "batch_count": 3, "scale_sd": 0.13, "baseline_sd": 0.022,
        "noise_sd": 0.003, "batch_effect": 0.012, "band_scale": 1.0, "spikes": False,
    },
    "broad_bands": {
        "name": "合成数据 C · 宽波段重叠",
        "description": "目标相关谱带更宽且相互重叠，可观察特征冗余。",
        "batch_count": 3, "scale_sd": 0.06, "baseline_sd": 0.009,
        "noise_sd": 0.0035, "batch_effect": 0.006, "band_scale": 1.65, "spikes": False,
    },
    "noisy_spectra": {
        "name": "合成数据 D · 高噪声与异常点",
        "description": "包含较强测量噪声和少量局部尖峰。",
        "batch_count": 3, "scale_sd": 0.06, "baseline_sd": 0.01,
        "noise_sd": 0.0085, "batch_effect": 0.006, "band_scale": 1.0, "spikes": True,
    },
    "batch_shift": {
        "name": "合成数据 E · 批次偏移",
        "description": "批次间存在明显系统偏移，用于观察分组结构和泛化风险。",
        "batch_count": 4, "scale_sd": 0.055, "baseline_sd": 0.012,
        "noise_sd": 0.0035, "batch_effect": 0.025, "band_scale": 1.0, "spikes": False,
    },
}


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
    profile: str = "clean_signal",
) -> Path:
    """Write a reproducible run directory with 128 samples × 61 wavelengths."""
    if samples < 16:
        raise ValueError("teaching dataset needs at least 16 samples")
    if profile not in PROFILES:
        raise ValueError(f"unknown teaching profile: {profile}")
    settings = PROFILES[profile]
    rng = np.random.default_rng(seed)
    wavelengths = DEFAULT_WAVELENGTHS.copy()
    output_root = Path(output_root)
    data_dir = output_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    spectra_rows: list[dict[str, object]] = []
    for index in range(samples):
        sample_id = f"ST-{index + 1:04d}"
        batch_index = index % settings["batch_count"]
        batch_id = f"teaching-batch-{batch_index + 1}"
        latent = float(rng.normal(0.0, 1.0))
        ssc = float(np.clip(12.5 + 2.0 * latent + rng.normal(0.0, 0.22), 8.0, 17.0))
        scale = float(1.0 + rng.normal(0.0, settings["scale_sd"]))
        baseline = float(rng.normal(0.0, settings["baseline_sd"]) + (batch_index - (settings["batch_count"] - 1) / 2) * settings["batch_effect"])
        slope = float(rng.normal(0.0, 0.000018))
        band_scale = settings["band_scale"]
        signal = (
            0.022 * latent * np.exp(-0.5 * ((wavelengths - 670.0) / (30.0 * band_scale)) ** 2)
            - 0.016 * latent * np.exp(-0.5 * ((wavelengths - 780.0) / (38.0 * band_scale)) ** 2)
            + 0.019 * latent * np.exp(-0.5 * ((wavelengths - 920.0) / (28.0 * band_scale)) ** 2)
        )
        batch_shape = (batch_index - (settings["batch_count"] - 1) / 2) * settings["batch_effect"] * np.exp(-0.5 * ((wavelengths - 550.0) / 115.0) ** 2)
        base = 0.59 - 0.00013 * (wavelengths - 400.0)
        base += 0.014 * np.exp(-0.5 * ((wavelengths - 540.0) / 55.0) ** 2)
        base += 0.010 * np.exp(-0.5 * ((wavelengths - 960.0) / 45.0) ** 2)
        noise = rng.normal(0.0, settings["noise_sd"], wavelengths.size)
        noise = 0.25 * np.roll(noise, 1) + 0.5 * noise + 0.25 * np.roll(noise, -1)
        if settings["spikes"] and index % 9 == 0:
            spike_index = int(rng.integers(0, wavelengths.size))
            noise[spike_index] += float(rng.choice([-1.0, 1.0]) * rng.uniform(0.018, 0.035))
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
        "dataset_id": f"synthetic_teaching_{profile}_v1",
        "display_name": settings["name"],
        "profile": profile,
        "source_type": "SYNTHETIC_TEACHING",
        "purpose": "visualization_and_teaching",
        "not_experimental_evidence": True,
        "seed": seed,
        "sample_count": samples,
        "feature_count": int(len(wavelengths)),
        "wavelengths_nm": wavelengths.tolist(),
        "construction": [settings["description"], "SSC-related smooth spectral components", "profile-specific scale, baseline, noise, or batch effects"],
        "warning": "Synthetic teaching construction; not real fruit measurements or experimental evidence.",
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="clean_signal")
    args = parser.parse_args()
    output = args.output or Path("results/teaching/datasets") / args.profile
    print(build_teaching_run(output, samples=args.samples, seed=args.seed, profile=args.profile))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
