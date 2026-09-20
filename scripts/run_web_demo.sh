#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bind_address="${FRUITSIM_DEMO_BIND:-0.0.0.0}"
web_port="${FRUITSIM_WEB_PORT:-8080}"
gateway_port="${FRUITSIM_GATEWAY_PORT:-8765}"
web_root="${FRUITSIM_WEB_ROOT:-${repo_root}/apps/fruitsim_unity/build/WebGL}"
output_root="${FRUITSIM_DEMO_OUTPUT_ROOT:-${repo_root}/results/web_demo/runs}"
journal="${FRUITSIM_GATEWAY_JOURNAL:-${repo_root}/results/web_demo/events.jsonl}"

if [[ ! -f "${web_root}/index.html" ]]; then
  echo "WebGL build not found: ${web_root}" >&2
  echo "Run: bash scripts/build_fruitsim_unity_webgl.sh" >&2
  exit 2
fi

cleanup() {
  if [[ -n "${gateway_pid:-}" ]]; then kill "${gateway_pid}" 2>/dev/null || true; fi
  if [[ -n "${web_pid:-}" ]]; then kill "${web_pid}" 2>/dev/null || true; fi
  wait "${gateway_pid:-}" 2>/dev/null || true
  wait "${web_pid:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "${repo_root}"
PYTHONPATH="${repo_root}/python${PYTHONPATH:+:${PYTHONPATH}}" \
  python -m fruitsim_gateway \
    --bind "${bind_address}" \
    --port "${gateway_port}" \
    --journal "${journal}" \
    --output-root "${output_root}" \
    --repo-root "${repo_root}" &
gateway_pid=$!

python scripts/serve_webgl_demo.py \
  --root "${web_root}" \
  --bind "${bind_address}" \
  --port "${web_port}" &
web_pid=$!

echo "Fruitsim Web demo: http://$(hostname -f 2>/dev/null || hostname):${web_port}"
echo "Fruitsim Gateway: ws://$(hostname -f 2>/dev/null || hostname):${gateway_port}"
wait -n "${gateway_pid}" "${web_pid}"
