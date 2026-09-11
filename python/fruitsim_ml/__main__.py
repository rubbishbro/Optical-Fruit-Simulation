from __future__ import annotations

import argparse
from pathlib import Path

from .data import generate_synthetic_golden_delicious, validate_dataset
from .datasets import load_experimental_dataset, validate_experimental_dataset
from .datasets.loader import ExperimentalDatasetPending
from .train import train_from_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="fruitsim-ml")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate-demo")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--samples", type=int, default=600)
    generate.add_argument("--seed", type=int, default=20260819)
    train = commands.add_parser("train")
    train.add_argument("--config", type=Path, required=True)
    validate = commands.add_parser("validate-data")
    validate.add_argument("--input", type=Path, required=True)
    experimental = commands.add_parser("validate-experimental")
    experimental.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate-demo":
        print(generate_synthetic_golden_delicious(args.output, args.samples, args.seed))
    elif args.command == "train":
        train_from_config(args.config)
    elif args.command == "validate-data":
        import json
        print(json.dumps(validate_dataset(args.input), indent=2))
    else:
        import json
        try:
            dataset = load_experimental_dataset(args.input)
        except ExperimentalDatasetPending as exc:
            print(json.dumps({
                "schema_version": 2,
                "valid": None,
                "status": "pending",
                "message": str(exc),
            }, indent=2, ensure_ascii=False))
            return
        print(json.dumps(validate_experimental_dataset(dataset), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
