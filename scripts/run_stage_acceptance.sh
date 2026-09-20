#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  python_bin="${PYTHON_BIN}"
elif [[ -x "/home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python" ]]; then
  python_bin="/home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python"
else
  python_bin="python"
fi
export PYTHON_BIN="${python_bin}"

mkdir -p "${repo_root}/.cache/matplotlib"
export PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}"
export MPLCONFIGDIR="${repo_root}/.cache/matplotlib"

if [[ -d "${repo_root}/build-mesh" ]]; then
  ctest --test-dir "${repo_root}/build-mesh" --output-on-failure
fi

"${python_bin}" -m unittest discover -s "${repo_root}/python/tests" -v
"${repo_root}/scripts/run_student_demo.sh" --output-root "${repo_root}/results/stage_acceptance"

echo "Stage acceptance completed. Inspect results/stage_acceptance/*/qa/audit_report.json."
