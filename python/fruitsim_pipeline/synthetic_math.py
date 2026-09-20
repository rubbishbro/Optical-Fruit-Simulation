from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .run_manager import RunManager, SYNTHETIC_WARNING


@dataclass(frozen=True)
class MathSyntheticConfig:
    """Configuration for a reproducible, explicitly non-calibrated dataset."""

    samples: int = 600
    seed: int = 20260819
    wavelength_start_nm: float = 500.0
    wavelength_end_nm: float = 1000.0
    wavelength_step_nm: float = 10.0
    batch_count: int = 6
    ssc_mean: float = 12.5
    ssc_std: float = 1.55
    noise_sigma: float = 0.008

    def validate(self) -> None:
        if self.samples < 2:
            raise ValueError("samples must be at least 2")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if self.wavelength_step_nm <= 0:
            raise ValueError("wavelength_step_nm must be positive")
        if self.wavelength_end_nm <= self.wavelength_start_nm:
            raise ValueError("wavelength_end_nm must be greater than wavelength_start_nm")
        if not 1 <= self.batch_count <= self.samples:
            raise ValueError("batch_count must be between 1 and samples")
        if self.ssc_std < 0 or self.noise_sigma < 0:
            raise ValueError("ssc_std and noise_sigma must be non-negative")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _smooth_noise(rng: np.random.Generator, count: int, sigma: float) -> np.ndarray:
    noise = rng.normal(0.0, sigma, count)
    if count < 3:
        return noise
    return (0.25 * np.roll(noise, 1) + 0.5 * noise + 0.25 * np.roll(noise, -1))


def generate_math_run(output_root: Path, run_id: str, config: MathSyntheticConfig) -> Path:
    """Generate a complete synthetic math Run and validate it before returning."""
    config.validate()
    wavelengths = np.arange(
        config.wavelength_start_nm,
        config.wavelength_end_nm + config.wavelength_step_nm * 0.1,
        config.wavelength_step_nm,
        dtype=np.float64,
    )
    configuration = {
        "provider": "fruitsim_pipeline.synthetic_math",
        "target": "synthetic_ssc_proxy",
        "config": asdict(config),
        "wavelengths_nm": wavelengths.tolist(),
    }
    run = RunManager.create(
        output_root,
        run_id,
        "synthetic_math",
        config.seed,
        ["generate", "postprocess"],
        configuration=configuration,
        notes=["Synthetic data; method demonstration only; no real SSC claim."],
    )
    try:
        run.set_state("validating", stage="configuration")
        rng = np.random.default_rng(config.seed)
        samples_rows: list[dict[str, object]] = []
        spectra_rows: list[dict[str, object]] = []
        spectra = np.empty((config.samples, wavelengths.size), dtype=np.float32)
        absorption = np.empty_like(spectra)
        reduced_scattering = np.empty_like(spectra)
        effective = np.empty_like(spectra)
        proxy_values = np.empty(config.samples, dtype=np.float32)
        batch_edges = np.linspace(0, config.samples, config.batch_count + 1, dtype=int)

        run.set_state(
            "generating_data",
            stage="synthetic_math",
            completed=0,
            total=config.samples,
        )
        for index in range(config.samples):
            fruit_id = f"SM-F{index + 1:05d}"
            batch_index = min(np.searchsorted(batch_edges[1:], index, side="right"), config.batch_count - 1)
            batch_id = f"SM-B{batch_index + 1:03d}"
            latent_ssc = float(np.clip(rng.normal(config.ssc_mean, config.ssc_std), 7.0, 19.0))
            moisture = float(np.clip(rng.normal(0.74, 0.04), 0.55, 0.90))
            gain = float(rng.normal(1.0, 0.025))
            wavelength_shift = float(rng.normal(0.0, 1.8))
            x = wavelengths - wavelength_shift
            band = np.exp(-0.5 * ((x - 680.0) / (42.0 + moisture * 12.0)) ** 2)
            water_band = np.exp(-0.5 * ((x - 940.0) / 48.0) ** 2)
            mu_a = 0.012 + 0.0009 * latent_ssc * band + 0.0045 * moisture * water_band
            mu_s_prime = 0.44 * (wavelengths / 700.0) ** -0.72
            mu_eff = np.sqrt(3.0 * mu_a * (mu_a + mu_s_prime))
            optical_depth = (mu_a + mu_s_prime) * (1.0 + 0.015 * latent_ssc)
            reflectance = gain * np.exp(-0.55 * optical_depth)
            reflectance *= 1.0 + _smooth_noise(rng, wavelengths.size, config.noise_sigma)
            reflectance = np.clip(reflectance, 0.0, 1.0).astype(np.float32)
            mu_a = mu_a.astype(np.float32)
            mu_s_prime = mu_s_prime.astype(np.float32)
            mu_eff = mu_eff.astype(np.float32)
            proxy = float(np.clip(10.0 + 240.0 * float(np.mean(mu_a * band)), 0.0, 30.0))

            samples_rows.append({
                "sample_id": fruit_id,
                "fruit_id": fruit_id,
                "batch_id": batch_id,
                "source_type": "synthetic_math",
                "synthetic_ssc_proxy": f"{proxy:.8f}",
                "moisture_proxy": f"{moisture:.8f}",
                "wavelength_shift_nm": f"{wavelength_shift:.8f}",
            })
            spectra[index] = reflectance
            absorption[index] = mu_a
            reduced_scattering[index] = mu_s_prime
            effective[index] = mu_eff
            proxy_values[index] = proxy
            for wavelength_index, wavelength in enumerate(wavelengths):
                spectra_rows.append({
                    "sample_id": fruit_id,
                    "fruit_id": fruit_id,
                    "batch_id": batch_id,
                    "source_type": "synthetic_math",
                    "wavelength_nm": f"{wavelength:.6f}",
                    "reflectance": f"{reflectance[wavelength_index]:.8f}",
                    "mu_a": f"{mu_a[wavelength_index]:.8f}",
                    "mu_s_prime": f"{mu_s_prime[wavelength_index]:.8f}",
                    "mu_eff": f"{mu_eff[wavelength_index]:.8f}",
                    "synthetic_ssc_proxy": f"{proxy:.8f}",
                })
            if index == config.samples - 1 or (index + 1) % max(1, config.samples // 10) == 0:
                run.set_state(
                    "generating_data",
                    stage="synthetic_math",
                    completed=index + 1,
                    total=config.samples,
                )

        _write_csv(
            run.root / "data" / "samples.csv",
            ["sample_id", "fruit_id", "batch_id", "source_type", "synthetic_ssc_proxy",
             "moisture_proxy", "wavelength_shift_nm"],
            samples_rows,
        )
        _write_csv(
            run.root / "data" / "spectra.csv",
            ["sample_id", "fruit_id", "batch_id", "source_type", "wavelength_nm",
             "reflectance", "mu_a", "mu_s_prime", "mu_eff", "synthetic_ssc_proxy"],
            spectra_rows,
        )
        _write_csv(
            run.root / "ml" / "input_long.csv",
            ["sample_id", "wavelength_nm", "reflectance", "synthetic_ssc_proxy"],
            [
                {
                    "sample_id": row["sample_id"],
                    "wavelength_nm": row["wavelength_nm"],
                    "reflectance": row["reflectance"],
                    "synthetic_ssc_proxy": row["synthetic_ssc_proxy"],
                }
                for row in spectra_rows
            ],
        )
        np.savez_compressed(
            run.root / "data" / "spectra.npz",
            sample_id=np.asarray([row["sample_id"] for row in samples_rows]),
            wavelength_nm=wavelengths,
            reflectance=spectra,
            mu_a=absorption,
            mu_s_prime=reduced_scattering,
            mu_eff=effective,
            synthetic_ssc_proxy=proxy_values,
        )
        synthetic_manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "warning": SYNTHETIC_WARNING,
            "target": "synthetic_ssc_proxy",
            "config": asdict(config),
            "wavelengths_nm": wavelengths.tolist(),
        }
        (run.root / "data" / "synthetic_math_manifest.json").write_text(
            json.dumps(synthetic_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        run.set_state("postprocessing", stage="artifacts")
        run.add_artifact("samples", run.root / "data" / "samples.csv", role="sample_table", media_type="text/csv", shape=[config.samples])
        run.add_artifact("spectra", run.root / "data" / "spectra.csv", role="spectral_table", media_type="text/csv", shape=[config.samples, int(wavelengths.size)])
        run.add_artifact("spectra_npz", run.root / "data" / "spectra.npz", role="spectral_tensor", media_type="application/octet-stream", shape=[config.samples, int(wavelengths.size)], dtype="float32")
        run.add_artifact("ml_input_long", run.root / "ml" / "input_long.csv", role="ml_input", media_type="text/csv", shape=[config.samples, int(wavelengths.size)])
        run.add_artifact("synthetic_manifest", run.root / "data" / "synthetic_math_manifest.json", role="data_provenance", media_type="application/json")
        run.complete(message="Synthetic math demonstration completed")
        return run.root
    except Exception as exc:
        run.fail(exc, error_code="synthetic_generation_failed")
        raise
