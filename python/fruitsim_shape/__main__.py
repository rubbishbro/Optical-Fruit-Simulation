from __future__ import annotations

import argparse
import json
from pathlib import Path

from .model import StatisticalFujiShape
from .training import TrainingOptions, train_statistical_shape


def main() -> None:
    parser = argparse.ArgumentParser(prog="fruitsim-shape")
    commands = parser.add_subparsers(dest="command", required=True)

    train = commands.add_parser("train", help="learn a radial PCA model from aligned PLY clouds")
    train.add_argument("--input-dir", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--directions", type=int, default=2048)
    train.add_argument("--modes", type=int, default=8)
    train.add_argument("--neighbors", type=int, default=12)
    train.add_argument("--max-points", type=int, default=300_000)
    train.add_argument("--input-unit", choices=["m", "mm"], default="m")
    train.add_argument("--cultivar-label", default="Fuji")

    sample = commands.add_parser("sample", help="sample a random closed apple mesh")
    sample.add_argument("--model", type=Path, required=True)
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--seed", type=int, default=20260901)
    sample.add_argument("--modes", type=int)
    sample.add_argument("--sigma-clip", type=float, default=3.0)

    inspect = commands.add_parser("inspect", help="print model provenance and dimensions")
    inspect.add_argument("--model", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "train":
        options = TrainingOptions(
            direction_count=args.directions,
            mode_count=args.modes,
            neighbor_count=args.neighbors,
            max_points_per_cloud=args.max_points,
            input_unit_to_mm=1000.0 if args.input_unit == "m" else 1.0,
        )
        print(train_statistical_shape(
            args.input_dir, args.output, options, cultivar_label=args.cultivar_label
        ))
    elif args.command == "sample":
        model = StatisticalFujiShape.load(args.model)
        instance = model.sample(
            seed=args.seed, mode_count=args.modes, sigma_clip=args.sigma_clip
        )
        print(instance.write_ply(args.output))
    else:
        model = StatisticalFujiShape.load(args.model)
        print(json.dumps({
            "geometry_type": "StatisticalFujiShape",
            "vertex_count": len(model.directions),
            "face_count": len(model.faces),
            "mode_count": model.mode_count,
            "cultivar_status": model.metadata.get("cultivar_status"),
            "provenance": model.metadata.get("provenance"),
            "training": model.metadata.get("training"),
        }, indent=2))


if __name__ == "__main__":
    main()
