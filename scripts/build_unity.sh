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
job_workers="${FRUITSIM_JOB_WORKERS:-4}"
cpu_list="${FRUITSIM_CPU_LIST:-}"
python_bin="${PYTHON_BIN:-python3}"

expected_version=""
if [[ -f "${project_dir}/ProjectSettings/ProjectVersion.txt" ]]; then
  expected_version="$(sed -n 's/^m_EditorVersion: //p' "${project_dir}/ProjectSettings/ProjectVersion.txt" | head -1)"
fi

# Locate a Unity launcher in this order:
#   1. UNITY_BIN (explicit pin; CI and custom installs)
#   2. a Hub-style "unity build" launcher such as ~/.local/bin/unity
#   3. a Unity Hub editor binary, invoked with -batchmode flags
# The launcher style decides the command line: a Hub editor path ends in
# /Editor/Unity and is called directly in batch mode.
resolve_unity() {
  if [[ -n "${UNITY_BIN:-}" ]]; then printf '%s\n' "${UNITY_BIN}"; return; fi
  local candidates=(
    "${HOME}/.local/bin/unity"
    "${HOME}/Unity/Hub/Editor/${expected_version}/Editor/Unity"
    "/opt/Unity/Hub/Editor/${expected_version}/Editor/Unity"
    "/opt/unity/editors/${expected_version}/Editor/Unity"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "${candidate}" ]]; then printf '%s\n' "${candidate}"; return; fi
  done
  if command -v unity >/dev/null 2>&1; then command -v unity; return; fi
  printf '\n'
}

if [[ "${build_target}" == "webgl" ]]; then
  unity_target="WebGL"
  build_method="Fruitsim.Editor.FruitsimBuild.BuildWebGL"
  output_path="${FRUITSIM_WEBGL_OUTPUT:-${project_dir}/build/WebGL}"
  log_path="${project_dir}/build/unity-webgl-build.log"
  build_timeout="${FRUITSIM_BUILD_TIMEOUT:-900}"
else
  unity_target="StandaloneLinux64"
  build_method="Fruitsim.Editor.FruitsimBuild.BuildLinux"
  output_path="${FRUITSIM_BUILD_OUTPUT:-${project_dir}/build/Fruitsim.x86_64}"
  log_path="${project_dir}/build/unity-build.log"
  build_timeout="${FRUITSIM_BUILD_TIMEOUT:-600}"
fi

unity_bin="$(resolve_unity)"
if [[ -z "${unity_bin}" || ! -x "${unity_bin}" ]]; then
  cat >&2 <<EOF
Unity editor not found.
  project expects: Unity ${expected_version:-unknown}
  searched:        ~/Unity/Hub/Editor/${expected_version:-<version>}/Editor/Unity, /opt/Unity/..., PATH
Install Unity ${expected_version:-6} with the WebGL Build Support module, or set UNITY_BIN=/path/to/Unity.
EOF
  exit 2
fi

# Hub editors keep the WebGL playback engines next to the editor binary; a
# wrapper launcher hides that, so fall back to the versioned Hub install.
if [[ "${unity_bin}" == */Editor/Unity ]]; then
  editor_dir="$(cd "$(dirname "${unity_bin}")" && pwd)"
else
  editor_dir="${HOME}/Unity/Hub/Editor/${expected_version}/Editor"
fi
webgl_module="${editor_dir}/Data/PlaybackEngines/WebGLSupport"
if [[ "${build_target}" == "webgl" ]]; then
  if [[ -d "${webgl_module}" ]]; then
    echo "Unity WebGL module: ${webgl_module}"
  elif [[ "${FRUITSIM_REQUIRE_WEBGL_MODULE:-0}" == "1" ]]; then
    echo "Unity WebGL Build Support is missing (checked ${webgl_module})" >&2
    exit 2
  else
    echo "Note: cannot confirm WebGL Build Support for ${unity_bin}; ensure the module is installed." >&2
  fi
fi
if [[ -n "${expected_version}" ]]; then
  echo "Unity editor: ${unity_bin} (project version ${expected_version})"
fi

if [[ "${build_target}" == "webgl" ]]; then
  "${python_bin}" "${repo_root}/scripts/verify_web_teaching_assets.py" --require-catalog
fi

mkdir -p "$(dirname "${output_path}")" "$(dirname "${log_path}")" "${output_path}"

run_unity() {
  if [[ -n "${cpu_list}" ]] && command -v taskset >/dev/null 2>&1; then
    taskset -c "${cpu_list}" env FRUITSIM_BUILD_OUTPUT="${output_path}" "$@"
  else
    env FRUITSIM_BUILD_OUTPUT="${output_path}" "$@"
  fi
}

if [[ "${unity_bin}" == */Editor/Unity ]]; then
  unity_timeout=()
  command -v timeout >/dev/null 2>&1 && unity_timeout=(timeout "${build_timeout}")
  run_unity "${unity_timeout[@]}" "${unity_bin}" \
    -batchmode -nographics -quit \
    -projectPath "${project_dir}" \
    -executeMethod "${build_method}" \
    -logFile "${log_path}" \
    -job-worker-count "${job_workers}"
else
  run_unity "${unity_bin}" --non-interactive --no-banner build "${project_dir}" \
    --target "${unity_target}" \
    --execute-method "${build_method}" \
    --output-path "${output_path}" \
    --allow-dirty-build \
    --log-file "${log_path}" \
    --timeout "${build_timeout}" \
    --args "-job-worker-count ${job_workers}"
fi

if [[ "${build_target}" == "webgl" ]]; then
  "${python_bin}" "${repo_root}/scripts/apply_webgl_demo_shell.py" --build-root "${output_path}"
  "${python_bin}" "${repo_root}/scripts/verify_web_teaching_assets.py" \
    --build-root "${output_path}" --require-catalog
  echo "WebGL demo ready under ${output_path}"
  echo "Serve it with: bash scripts/run_web_demo.sh"
fi
