from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import generate_synthetic_golden_delicious, validate_dataset
from .datasets import load_experimental_dataset, validate_experimental_dataset
from .datasets.loader import ExperimentalDatasetPending
from .train import train_from_config
from .workflow import PipelineDefinition, run_workflow_from_run


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
    visualize = commands.add_parser("visualize-run")
    visualize.add_argument("--run-dir", type=Path, required=True)
    visualize.add_argument("--output", type=Path, default=None)
    workflow = commands.add_parser("run-workflow")
    workflow.add_argument("--run-dir", type=Path, required=True)
    workflow.add_argument("--output", type=Path, required=True)
    workflow.add_argument("--experiment-id", default=None)
    workflow.add_argument("--seed", type=int, default=20260920)
    args = parser.parse_args()
    if args.command == "generate-demo":
        print(generate_synthetic_golden_delicious(args.output, args.samples, args.seed))
    elif args.command == "train":
        train_from_config(args.config)
    elif args.command == "validate-data":
        print(json.dumps(validate_dataset(args.input), indent=2))
    elif args.command == "visualize-run":
        from .visualize import build_visualizations
        print(build_visualizations(args.run_dir, args.output))
    elif args.command == "run-workflow":
        experiment = run_workflow_from_run(
            args.run_dir,
            args.output,
            experiment_id=args.experiment_id,
            seed=args.seed,
            definition=PipelineDefinition(),
        )
        print(json.dumps({
            "experiment_id": experiment.experiment_id,
            "dataset_id": experiment.dataset_id,
            "pipeline": experiment.pipeline_definition.to_dict(),
            "stage_runs": [stage.stage_run_id for stage in experiment.stage_runs],
            "final_model_id": experiment.final_model_id,
            "final_metrics": None if experiment.final_metrics is None else experiment.final_metrics.to_dict(),
            "output": str((args.output / "experiment.json").resolve()),
        }, ensure_ascii=False, indent=2))
    else:
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
