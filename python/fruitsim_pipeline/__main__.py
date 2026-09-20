from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .contracts import ContractError, validate_run_directory_from_path


def main() -> int:
    parser = argparse.ArgumentParser(prog="fruitsim-pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-run", help="validate one immutable Run directory")
    validate.add_argument("run_dir", type=Path)
    generate = commands.add_parser("generate-math", help="generate a reproducible math-synthetic Run")
    generate.add_argument("--output-root", type=Path, default=Path("results/runs"))
    generate.add_argument("--run-id", default=None)
    generate.add_argument("--samples", type=int, default=600)
    generate.add_argument("--seed", type=int, default=20260819)
    generate.add_argument("--wavelength-start", type=float, default=500.0)
    generate.add_argument("--wavelength-end", type=float, default=1000.0)
    generate.add_argument("--wavelength-step", type=float, default=10.0)
    generate.add_argument("--batch-count", type=int, default=6)
    generate.add_argument("--noise-sigma", type=float, default=0.008)
    physical = commands.add_parser("simulate-physical", help="run C++ Monte Carlo and package a Run")
    physical.add_argument("--binary", type=Path, default=Path("build-mesh/apps/fruitsim_cli/fruitsim_cli"))
    physical.add_argument("--config", type=Path, default=Path("configs/ring_sensor_demo.json"))
    physical.add_argument("--output-root", type=Path, default=Path("results/runs"))
    physical.add_argument("--run-id", required=True)
    physical.add_argument("--photons", type=int, default=256)
    physical.add_argument("--seed", type=int, default=20260919)
    physical.add_argument("--threads", type=int, default=1)
    physical.add_argument("--backend", choices=["cpu", "cuda"], default="cpu")
    audit = commands.add_parser("audit-run", help="audit formulas, leakage boundaries and result identities")
    audit.add_argument("run_dir", type=Path)
    audit.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if args.command == "validate-run":
        try:
            report = validate_run_directory_from_path(args.run_dir)
        except ContractError as exc:
            print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "generate-math":
        from .synthetic_math import MathSyntheticConfig, generate_math_run

        run_id = args.run_id or f"math_demo_seed{args.seed}"
        config = MathSyntheticConfig(
            samples=args.samples,
            seed=args.seed,
            wavelength_start_nm=args.wavelength_start,
            wavelength_end_nm=args.wavelength_end,
            wavelength_step_nm=args.wavelength_step,
            batch_count=args.batch_count,
            noise_sigma=args.noise_sigma,
        )
        try:
            run_dir = generate_math_run(args.output_root, run_id, config)
        except (ContractError, ValueError, OSError) as exc:
            print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps({"valid": True, "run_dir": str(run_dir)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "simulate-physical":
        from .physical_run import PhysicalRunConfig, generate_physical_run
        try:
            run_dir = generate_physical_run(
                args.output_root,
                args.run_id,
                PhysicalRunConfig(
                    binary=args.binary,
                    config=args.config,
                    photons=args.photons,
                    seed=args.seed,
                    threads=args.threads,
                    backend=args.backend,
                ),
            )
        except (ContractError, ValueError, OSError, RuntimeError) as exc:
            print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps({"valid": True, "run_dir": str(run_dir)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "audit-run":
        from .audit import audit_run, write_audit_report
        report = audit_run(args.run_dir)
        if args.output is not None:
            write_audit_report(args.run_dir, args.output)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["overall"] != "fail" else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
