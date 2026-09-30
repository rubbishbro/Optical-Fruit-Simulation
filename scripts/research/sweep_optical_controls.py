#!/usr/bin/env python3
"""Sweep optical controls and rank robust simulation settings for PPT use."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_RESULTS = Path(os.environ.get("FRUITSIM_RESULTS_ROOT", "results"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from generate_causal_comparisons import apply_condition, simulate
from simulate_guided_photon_paths import COLORS, read_ascii_ply

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

WAVELENGTHS = (650, 800, 950)
SEEDS = (20260923, 20260924, 20260925)
DEFINITIONS = {
    "ring_radius": ("环形光源半径", "mm", [4.0, 6.0, 8.0, 10.0, 12.0]),
    "incident_angle": ("入射角", "deg", [0.0, 10.0, 20.0, 30.0, 40.0]),
    "detector_offset": ("探测器横向位置", "mm", [0.0, 2.0, 4.0, 6.0, 8.0]),
}


def evaluate_task(task: tuple[str, float, int, dict, str, str]) -> dict:
    factor, value, seed, base, mesh_path, config_path = task
    config = copy.deepcopy(base)
    apply_condition(config, factor, value)
    vertices, faces = read_ascii_ply(Path(mesh_path))
    _, metrics = simulate(config, vertices, faces, seed)
    row = {"factor": factor, "value": value, "seed": seed}
    response = [metrics[w]["response_proxy"] for w in WAVELENGTHS]
    row["mean_response"] = float(np.mean(response))
    row["std_response_across_wavelength"] = float(np.std(response))
    row["response_650"] = response[0]
    row["response_800"] = response[1]
    row["response_950"] = response[2]
    row["mean_events_800"] = metrics[800]["mean_events"]
    row["mean_path_length_800_mm"] = metrics[800]["mean_path_length_mm"]
    return row


def aggregate(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, float], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["factor"], row["value"]), []).append(row)
    result = []
    for (factor, value), items in grouped.items():
        result.append({
            "factor": factor,
            "value": value,
            "replicates": len(items),
            "mean_response": float(np.mean([x["mean_response"] for x in items])),
            "std_response": float(np.std([x["mean_response"] for x in items], ddof=1)) if len(items) > 1 else 0.0,
            "mean_response_650": float(np.mean([x["response_650"] for x in items])),
            "mean_response_800": float(np.mean([x["response_800"] for x in items])),
            "mean_response_950": float(np.mean([x["response_950"] for x in items])),
            "mean_events_800": float(np.mean([x["mean_events_800"] for x in items])),
            "mean_path_length_800_mm": float(np.mean([x["mean_path_length_800_mm"] for x in items])),
        })
    return sorted(result, key=lambda x: (x["factor"], x["value"]))


def factor_label(factor: str, value: float) -> str:
    unit = DEFINITIONS[factor][1]
    return f"{value:g} {unit}"


def plot_sweep(output: Path, aggregate_rows: list[dict], factor: str) -> None:
    title, unit, values = DEFINITIONS[factor]
    rows = [row for row in aggregate_rows if row["factor"] == factor]
    x = np.array([row["value"] for row in rows])
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.5), facecolor="#F8FAFC")
    ax = axes[0]
    for wavelength in WAVELENGTHS:
        means = np.array([row[f"mean_response_{wavelength}"] for row in rows])
        ax.plot(x, means, marker="o", linewidth=2, markersize=6, color=COLORS[wavelength], label=f"{wavelength} nm")
    best = max(rows, key=lambda row: row["mean_response"])
    ax.axvline(best["value"], color="#16A34A", linestyle="--", linewidth=1.5, alpha=0.8)
    ax.scatter([best["value"]], [best["mean_response_800"]], s=100, facecolors="none", edgecolors="#16A34A", linewidths=2)
    ax.set_xlabel(f"{title} ({unit})")
    ax.set_ylabel("Mean detector response proxy")
    ax.set_title("Sweep response point plot / 扫描响应点图", loc="left", fontweight="bold")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(frameon=False)
    ax.text(0.03, 0.04, f"best aggregate: {factor_label(factor, best['value'])}\nmean response: {best['mean_response']:.4f}",
            transform=ax.transAxes, fontsize=9, color="#166534",
            bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "#86EFAC"})
    ax = axes[1]
    means = np.array([row["mean_response"] for row in rows])
    errors = np.array([row["std_response"] for row in rows])
    ax.errorbar(x, means, yerr=errors, fmt="o-", color="#0F766E", ecolor="#99F6E4",
                elinewidth=3, capsize=4, linewidth=2, markersize=7)
    ax.set_xlabel(f"{title} ({unit})")
    ax.set_ylabel("Mean across wavelengths ± replicate SD")
    ax.set_title("Repeated-trial aggregate / 重复试验均值", loc="left", fontweight="bold")
    ax.grid(axis="y", alpha=0.22)
    for xv, yv in zip(x, means):
        ax.annotate(f"{yv:.3f}", (xv, yv), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
    fig.suptitle(f"{title} parameter sweep\nSimulation / 仿真结果", fontsize=17, fontweight="bold", color="#0F172A")
    fig.text(0.015, 0.015, "Each point: 3 fixed-budget random-seed replicates; all non-target parameters held constant.", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, 0.05, 1, 0.90))
    fig.savefig(output, dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def write_outputs(output: Path, raw_rows: list[dict], aggregate_rows: list[dict], joint: list[dict]) -> None:
    with (output / "sweep_raw_replicates.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = list(raw_rows[0].keys())
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(raw_rows)
    with (output / "sweep_aggregate.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = list(aggregate_rows[0].keys())
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(aggregate_rows)
    with (output / "joint_validation.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = list(joint[0].keys())
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(joint)

    lines = [
        "# Simulation / 仿真结果：光学参数扫描与候选最优",
        "",
        "扫描采用单变量控制：每次只改变一个变量；每个点使用 3 个随机种子重复。",
        "排序目标为 650/800/950 nm 三个波长的平均 detector response proxy。",
        "该指标来自引导蒙特卡洛的有效回传路径比例，用于方案比较，不等同于无偏检测效率。",
        "",
        "| 对比变量 | 候选最优值 | 平均响应 | 重复标准差 | 800 nm 响应 |",
        "|---|---:|---:|---:|---:|",
    ]
    best_by_factor = {}
    for factor in DEFINITIONS:
        rows = [row for row in aggregate_rows if row["factor"] == factor]
        best = max(rows, key=lambda row: row["mean_response"])
        best_by_factor[factor] = best
        lines.append(f"| {DEFINITIONS[factor][0]} | {factor_label(factor, best['value'])} | {best['mean_response']:.4f} | {best['std_response']:.4f} | {best['mean_response_800']:.4f} |")
    lines.extend(["", "## 联合候选验证", "", "| 设置 | 平均响应 | 650 nm | 800 nm | 950 nm |", "|---|---:|---:|---:|---:|"])
    for row in joint:
        lines.append(f"| {row['label']} | {row['mean_response']:.4f} | {row['response_650']:.4f} | {row['response_800']:.4f} | {row['response_950']:.4f} |")
    (output / "sweep_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "optimal_settings.json").write_text(json.dumps({
        "objective": "mean detector response proxy across 650/800/950 nm",
        "best_individual_factors": best_by_factor,
        "joint_validation": joint,
        "label": "Simulation / 仿真结果",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    def parse_values(raw: str) -> list[float]:
        return [float(item.strip()) for item in raw.split(",") if item.strip()]

    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", type=Path, default=_RESULTS / "photon_paths_demo/outer_mesh.ply")
    parser.add_argument("--config", type=Path, default=Path("configs/guided_paths.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/causal_comparisons_sweep"))
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--ring-values", default="4,6,8,10,12")
    parser.add_argument("--angle-values", default="0,10,20,30,40")
    parser.add_argument("--offset-values", default="0,2,4,6,8")
    args = parser.parse_args()
    global DEFINITIONS
    DEFINITIONS = {
        "ring_radius": ("环形光源半径", "mm", parse_values(args.ring_values)),
        "incident_angle": ("入射角", "deg", parse_values(args.angle_values)),
        "detector_offset": ("探测器横向位置", "mm", parse_values(args.offset_values)),
    }
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    base = json.loads(args.config.read_text(encoding="utf-8"))
    base["photons_per_wavelength"] = 200
    base["accepted_paths_per_wavelength"] = 10
    tasks = []
    for factor, (_, _, values) in DEFINITIONS.items():
        for value in values:
            for seed in SEEDS:
                tasks.append((factor, value, seed, base, str(args.mesh), str(args.config)))
    raw_rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(evaluate_task, task) for task in tasks]
        for index, future in enumerate(as_completed(futures), start=1):
            raw_rows.append(future.result())
            if index % 5 == 0 or index == len(futures):
                print(f"completed {index}/{len(futures)}", flush=True)
    raw_rows.sort(key=lambda row: (row["factor"], row["value"], row["seed"]))
    aggregate_rows = aggregate(raw_rows)
    for factor in DEFINITIONS:
        plot_sweep(output / f"{list(DEFINITIONS).index(factor) + 1:02d}_{factor}_sweep.png", aggregate_rows, factor)

    best_by_factor = {factor: max((row for row in aggregate_rows if row["factor"] == factor), key=lambda row: row["mean_response"]) for factor in DEFINITIONS}
    joint_values = {factor: best_by_factor[factor]["value"] for factor in DEFINITIONS}
    joint_rows = []
    for label, values in [("baseline", {"ring_radius": 8.0, "incident_angle": 0.0, "detector_offset": 0.0}),
                          ("joint_best", joint_values)]:
        for seed in SEEDS:
            config = copy.deepcopy(base)
            for factor, value in values.items():
                apply_condition(config, factor, value)
            vertices, faces = read_ascii_ply(args.mesh)
            _, metrics = simulate(config, vertices, faces, seed)
            response = [metrics[w]["response_proxy"] for w in WAVELENGTHS]
            joint_rows.append({"label": label, "seed": seed, "ring_radius": values["ring_radius"],
                               "incident_angle": values["incident_angle"], "detector_offset": values["detector_offset"],
                               "mean_response": float(np.mean(response)), "response_650": response[0],
                               "response_800": response[1], "response_950": response[2]})
    joint_summary = []
    for label in ("baseline", "joint_best"):
        rows = [row for row in joint_rows if row["label"] == label]
        joint_summary.append({"label": label, "ring_radius": rows[0]["ring_radius"],
                              "incident_angle": rows[0]["incident_angle"], "detector_offset": rows[0]["detector_offset"],
                              "mean_response": float(np.mean([row["mean_response"] for row in rows])),
                              "response_650": float(np.mean([row["response_650"] for row in rows])),
                              "response_800": float(np.mean([row["response_800"] for row in rows])),
                              "response_950": float(np.mean([row["response_950"] for row in rows]))})
    write_outputs(output, raw_rows, aggregate_rows, joint_summary)
    print(json.dumps({"output": str(output), "best_individual": best_by_factor, "joint": joint_summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
