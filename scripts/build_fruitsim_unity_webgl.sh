#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../apps/fruitsim_unity" && pwd)"
unity_bin="${UNITY_BIN:-/home/rubbishbro/.local/bin/unity}"
output_path="${FRUITSIM_WEBGL_OUTPUT:-${project_dir}/build/WebGL}"
log_path="${project_dir}/build/unity-webgl-build.log"
job_workers="${FRUITSIM_JOB_WORKERS:-4}"
build_timeout="${FRUITSIM_BUILD_TIMEOUT:-900}"
cpu_list="${FRUITSIM_CPU_LIST:-}"
if [[ -z "${cpu_list}" ]]; then
  cpu_count="$(nproc 2>/dev/null || printf '1')"
  if (( cpu_count > 4 )); then cpu_list="0-3"; else cpu_list="0-$((cpu_count - 1))"; fi
fi
mkdir -p "${output_path}" "$(dirname "${log_path}")"
build_args=(build "${project_dir}" \
  --target WebGL \
  --execute-method Fruitsim.Editor.FruitsimBuild.BuildWebGL \
  --output-path "${output_path}" \
  --allow-dirty-build \
  --log-file "${log_path}" \
  --timeout "${build_timeout}" \
  --args "-job-worker-count ${job_workers}")
if [[ -n "${cpu_list}" ]] && command -v taskset >/dev/null 2>&1; then
  taskset -c "${cpu_list}" env FRUITSIM_BUILD_OUTPUT="${output_path}" "${unity_bin}" "${build_args[@]}"
else
  env FRUITSIM_BUILD_OUTPUT="${output_path}" "${unity_bin}" "${build_args[@]}"
fi

python3 "${project_dir}/../../scripts/apply_webgl_demo_shell.py" --build-root "${output_path}"
