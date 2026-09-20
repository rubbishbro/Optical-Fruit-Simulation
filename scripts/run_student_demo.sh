#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python}"
mkdir -p "${repo_root}/.cache/matplotlib"
PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
MPLCONFIGDIR="${repo_root}/.cache/matplotlib" \
"${python_bin}" -m fruitsim_pipeline.student_demo "$@"
