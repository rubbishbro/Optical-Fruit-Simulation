#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  linux|webgl) build_target="$1"; shift ;;
  *) echo "Usage: bash scripts/build_unity.sh {linux|webgl}" >&2; exit 2 ;;
esac
if (( $# > 0 )); then
  echo "Usage: bash scripts/build_unity.sh {linux|webgl}" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir="${repo_root}/apps/fruitsim_unity"
unity_bin="${UNITY_BIN:-${HOME}/.local/bin/unity}"
job_workers="${FRUITSIM_JOB_WORKERS:-4}"
cpu_list="${FRUITSIM_CPU_LIST:-}"

if [[ "${build_target}" == "webgl" ]]; then
  unity_target="WebGL"
  build_method="Fruitsim.Editor.FruitsimBuild.BuildWebGL"
  output_path="${FRUITSIM_WEBGL_OUTPUT:-${project_dir}/build/WebGL}"
  log_path="${project_dir}/build/unity-webgl-build.log"
  build_timeout="${FRUITSIM_BUILD_TIMEOUT:-900}"
  mkdir -p "${output_path}"
else
  unity_target="StandaloneLinux64"
  build_method="Fruitsim.Editor.FruitsimBuild.BuildLinux"
  output_path="${FRUITSIM_BUILD_OUTPUT:-${project_dir}/build/Fruitsim.x86_64}"
  log_path="${project_dir}/build/unity-build.log"
  build_timeout="${FRUITSIM_BUILD_TIMEOUT:-600}"
fi

if [[ ! -x "${unity_bin}" ]] && ! command -v "${unity_bin}" >/dev/null 2>&1; then
  echo "Unity build launcher not found: ${unity_bin}. Set UNITY_BIN to its path." >&2
  exit 2
fi

mkdir -p "$(dirname "${output_path}")" "$(dirname "${log_path}")"
build_args=(build "${project_dir}"
  --target "${unity_target}"
  --execute-method "${build_method}"
  --output-path "${output_path}"
  --allow-dirty-build
  --log-file "${log_path}"
  --timeout "${build_timeout}"
  --args "-job-worker-count ${job_workers}")

if [[ -n "${cpu_list}" ]] && command -v taskset >/dev/null 2>&1; then
  taskset -c "${cpu_list}" env FRUITSIM_BUILD_OUTPUT="${output_path}" "${unity_bin}" "${build_args[@]}"
else
  env FRUITSIM_BUILD_OUTPUT="${output_path}" "${unity_bin}" "${build_args[@]}"
fi

if [[ "${build_target}" == "webgl" ]]; then
  "${PYTHON_BIN:-python3}" "${repo_root}/scripts/apply_webgl_demo_shell.py" --build-root "${output_path}"
fi
