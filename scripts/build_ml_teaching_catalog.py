#!/usr/bin/env python3
"""Build five independent, explicitly synthetic ML teaching datasets and bundles."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static"
BUILDER = ROOT / "scripts/build_web_teaching_assets.py"
PROFILES = [
    ("clean_signal", "合成数据 A · 清晰信号", "信号较清晰、噪声较低，作为基础教学对照。"),
    ("baseline_shift", "合成数据 B · 基线与尺度偏移", "样本具有更强基线和幅度差异，可观察 SNV 的作用。"),
    ("broad_bands", "合成数据 C · 宽波段重叠", "目标相关谱带更宽且相互重叠，可观察特征冗余。"),
    ("noisy_spectra", "合成数据 D · 高噪声与异常点", "包含较强测量噪声和少量局部尖峰。"),
    ("batch_shift", "合成数据 E · 批次偏移", "批次间存在明显系统偏移，用于观察分组结构和泛化风险。"),
]


def main() -> int:
    datasets = []
    for profile, name, description in PROFILES:
        output = STATIC / "ml_datasets" / profile
        env = os.environ.copy()
        env["FRUITSIM_TEACHING_PROFILE"] = profile
        env["FRUITSIM_WEB_ASSET_OUTPUT"] = str(output)
        subprocess.run([sys.executable, str(BUILDER)], cwd=ROOT, env=env, check=True)
        datasets.append({
            "dataset_id": f"synthetic_teaching_{profile}_v1",
            "name": name,
            "description": description,
            "profile": profile,
            "source_type": "SYNTHETIC_TEACHING",
            "synthetic": True,
            "sample_count": 128,
            "feature_count": 61,
            "bundle_url": f"static/ml_datasets/{profile}/ml_p1_bundle.json",
        })
    catalog = {
        "schema_version": 1,
        "source_type": "SYNTHETIC_TEACHING",
        "synthetic": True,
        "warning": "All five datasets are simulated teaching examples, not experimental measurements.",
        "datasets": datasets,
    }
    (STATIC / "ml_p1_datasets.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Built {len(datasets)} synthetic teaching datasets in {STATIC / 'ml_datasets'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
