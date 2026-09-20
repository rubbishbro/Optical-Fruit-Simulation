from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .run_manager import RunManager


@dataclass(frozen=True)
class PhysicalRunConfig:
    binary: Path
    config: Path
    photons: int = 256
    seed: int = 20260919
    threads: int = 1
    backend: str = "cpu"

    def validate(self) -> None:
        if self.photons < 1:
            raise ValueError("photons must be positive")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if self.threads < 1:
            raise ValueError("threads must be positive")
        if not self.binary.is_file():
            raise FileNotFoundError(f"C++ simulator binary does not exist: {self.binary}")
        if not self.config.is_file():
            raise FileNotFoundError(f"C++ simulator config does not exist: {self.config}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _copy_command_log(path: Path, command: list[str], completed: subprocess.CompletedProcess[str]) -> None:
    path.write_text(json.dumps({
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_physical_run(output_root: Path, run_id: str, config: PhysicalRunConfig) -> Path:
    """Run the C++ CPU/CUDA CLI and package its result as a canonical Run."""
    config = PhysicalRunConfig(
        binary=Path(config.binary).resolve(),
        config=Path(config.config).resolve(),
        photons=config.photons,
        seed=config.seed,
        threads=config.threads,
        backend=config.backend,
    )
    config.validate()
    run = RunManager.create(
        output_root,
        run_id,
        "synthetic_physics",
        config.seed,
        ["simulate", "postprocess"],
        backend=config.backend,
        configuration={
            "provider": "fruitsim_pipeline.physical_run",
            "binary": str(config.binary),
            "config": str(config.config),
            "photons": config.photons,
            "threads": config.threads,
            "backend": config.backend,
        },
        notes=["C++ Monte Carlo output; synthetic optical assumptions; no SSC target supplied."],
    )
    simulation_dir = run.root / "simulation" / "cpp"
    simulation_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(config.binary), "run", "--config", str(config.config),
        "--output", str(simulation_dir), "--photons", str(config.photons),
        "--seed", str(config.seed), "--threads", str(config.threads),
        "--backend", config.backend,
    ]
    command_log = run.root / "simulation" / "cpp_command.json"
    try:
        run.set_state("validating", stage="cpp_configuration")
        run.set_state("queued", stage="cpp_worker")
        run.set_state("simulating", stage="monte_carlo", completed=0, total=config.photons)
        run.log("simulation_started", command=command)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        _copy_command_log(command_log, command, completed)
        run.log("simulation_finished", returncode=completed.returncode)
        if completed.returncode != 0:
            raise RuntimeError(
                f"C++ simulator failed with return code {completed.returncode}: "
                f"{completed.stderr.strip()[-1000:]}"
            )

        instrument_path = simulation_dir / "instrument.csv"
        summary_path = simulation_dir / "summary.csv"
        if not instrument_path.is_file() or not summary_path.is_file():
            raise RuntimeError("C++ simulator did not produce summary.csv and instrument.csv")
        instrument = _read_csv(instrument_path)
        if not instrument:
            raise RuntimeError("C++ instrument.csv contains no wavelength rows")

        sample_id = f"PHYS-{run_id}"
        sample_row = {
            "sample_id": sample_id,
            "fruit_id": sample_id,
            "batch_id": "PHYS-B001",
            "source_type": "synthetic_physics",
            "target_name": "ssc_brix",
            "target_status": "not_available",
            "target_value": "",
            "notes": "C++ Monte Carlo detector run; no measured SSC label.",
        }
        _write_csv(
            run.root / "data" / "samples.csv",
            list(sample_row),
            [sample_row],
        )
        spectral_rows: list[dict[str, Any]] = []
        for row in instrument:
            spectral_rows.append({
                "sample_id": sample_id,
                "fruit_id": sample_id,
                "batch_id": "PHYS-B001",
                "source_type": "synthetic_physics",
                "wavelength_nm": row["wavelength_nm"],
                "detected_reflectance": row["detected_reflectance"],
                "detected_weight": row["detected_weight"],
                "detection_efficiency": row["detection_efficiency"],
                "detected_penetration_mean_mm": row["detected_penetration_mean_mm"],
                "detected_penetration_median_mm": row["detected_penetration_median_mm"],
                "skin_path_fraction": row["skin_path_fraction"],
                "flesh_path_fraction": row["flesh_path_fraction"],
            })
        _write_csv(
            run.root / "data" / "spectra.csv",
            list(spectral_rows[0]),
            spectral_rows,
        )
        _write_csv(
            run.root / "ml" / "input_long.csv",
            ["sample_id", "wavelength_nm", "detected_reflectance", "detected_weight", "source_type"],
            [
                {key: row[key] for key in ("sample_id", "wavelength_nm", "detected_reflectance", "detected_weight", "source_type")}
                for row in spectral_rows
            ],
        )
        run.set_state("postprocessing", stage="run_adapter")
        run.add_artifact("cpp_command", command_log, role="execution_log", media_type="application/json")
        run.add_artifact("cpp_manifest", simulation_dir / "manifest.json", role="simulation_provenance", media_type="application/json")
        run.add_artifact("cpp_summary", summary_path, role="simulation_summary", media_type="text/csv")
        run.add_artifact("cpp_instrument", instrument_path, role="detector_spectrum", media_type="text/csv")
        run.add_artifact("cpp_instrument_regions", simulation_dir / "instrument_regions.csv", role="detector_path_statistics", media_type="text/csv")
        run.add_artifact("cpp_performance", simulation_dir / "performance.csv", role="performance", media_type="text/csv")
        run.add_artifact("physical_samples", run.root / "data" / "samples.csv", role="sample_table", media_type="text/csv", shape=[1])
        run.add_artifact("physical_spectra", run.root / "data" / "spectra.csv", role="detector_spectrum_table", media_type="text/csv", shape=[len(spectral_rows)])
        run.add_artifact("ml_input_long", run.root / "ml" / "input_long.csv", role="ml_input_pending_label", media_type="text/csv", shape=[len(spectral_rows)])
        run.complete(message="C++ Monte Carlo result adapted into canonical Run")
        return run.root
    except Exception as exc:
        if not command_log.exists():
            command_log.write_text(json.dumps({"command": command, "error": str(exc)}, indent=2) + "\n", encoding="utf-8")
        run.fail(exc, error_code="physical_simulation_failed")
        raise
