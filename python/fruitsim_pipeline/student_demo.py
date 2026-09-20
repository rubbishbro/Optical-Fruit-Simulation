from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .audit import audit_run, write_audit_report
from .physical_run import PhysicalRunConfig, generate_physical_run
from .synthetic_math import MathSyntheticConfig, generate_math_run


def _fresh_id(root: Path, prefix: str, seed: int) -> str:
    base = f"{prefix}_seed{seed}"
    candidate = base
    suffix = 2
    while (root / candidate).exists():
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fruitsim-student",
        description="Run the small Fruitsim end-to-end demo: generate, audit, visualize, simulate.",
    )
    parser.add_argument("--output-root", type=Path, default=Path("results/student_demo"))
    parser.add_argument("--seed", type=int, default=20260919)
    parser.add_argument(
        "--photons",
        type=int,
        default=4096,
        help="Photons per wavelength for the physical demo (default: 4096; use a smaller value only for a smoke test).",
    )
    parser.add_argument("--skip-physical", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    math_id = _fresh_id(output_root, "math", args.seed)
    math_run = generate_math_run(
        output_root,
        math_id,
        MathSyntheticConfig(samples=32, seed=args.seed, batch_count=4),
    )
    math_report = audit_run(math_run)
    write_audit_report(math_run)
    from fruitsim_ml.visualize import build_visualizations
    build_visualizations(math_run)
    outputs = [{"kind": "math", "run_dir": str(math_run), "audit": math_report["overall"]}]

    if not args.skip_physical:
        repo_root = Path(__file__).resolve().parents[2]
        binary = repo_root / "build-mesh" / "apps" / "fruitsim_cli" / "fruitsim_cli"
        config = repo_root / "configs" / "ring_sensor_demo.json"
        if binary.is_file() and config.is_file():
            physical_id = _fresh_id(output_root, "physical", args.seed)
            physical_run = generate_physical_run(
                output_root,
                physical_id,
                PhysicalRunConfig(binary, config, photons=args.photons, seed=args.seed, threads=1),
            )
            physical_report = audit_run(physical_run)
            write_audit_report(physical_run)
            build_visualizations(physical_run)
            outputs.append({"kind": "physical", "run_dir": str(physical_run), "audit": physical_report["overall"]})
        else:
            outputs.append({"kind": "physical", "status": "skipped", "reason": "build-mesh C++ CLI not found"})
    print(json.dumps({
        "student_demo": "completed",
        "outputs": outputs,
        "next": "Open each run directory and inspect qa/audit_report.json and visualizations/.",
    }, ensure_ascii=False, indent=2))
    return 0 if all(item.get("audit", "pass") != "fail" for item in outputs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
