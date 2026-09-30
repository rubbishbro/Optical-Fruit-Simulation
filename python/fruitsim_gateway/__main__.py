from __future__ import annotations

import argparse
import asyncio
import math
from pathlib import Path

from fruitsim_protocol.journal import EventJournal

from .orchestrator import RunOrchestrator
from .server import ProtocolHub, ProtocolServer


WAVELENGTH_MIN_NM = 400.0
WAVELENGTH_MAX_NM = 1100.0


def handle_viewer_wavelength(command: dict) -> dict:
    """Validate the preview-only wavelength before echoing viewer state.

    ``viewer.set_wavelength`` never triggers a physical calculation; the stored
    value is a preview request only and must not be reported as a Run update.
    """
    payload = command.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("viewer payload 必须是对象")
    raw = payload.get("wavelength_nm")
    if isinstance(raw, bool):
        raise ValueError("wavelength_nm 必须是数值")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError("wavelength_nm 不能为空")
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError("wavelength_nm 必须是数值") from exc
    elif isinstance(raw, (int, float)):
        value = float(raw)
    else:
        raise ValueError("wavelength_nm 必须是数值")
    if not math.isfinite(value) or value < WAVELENGTH_MIN_NM or value > WAVELENGTH_MAX_NM:
        raise ValueError(
            f"wavelength_nm 必须在 {WAVELENGTH_MIN_NM:.0f} 到 {WAVELENGTH_MAX_NM:.0f} nm 之间"
        )
    return {
        "kind": "viewer_state",
        "stage": "viewer",
        "status": "updated",
        "payload": {"wavelength_nm": value, "preview_only": True},
    }


def _demo_handlers(hub: ProtocolHub, orchestrator: RunOrchestrator) -> None:
    hub.register("run.start", orchestrator.accept_start)
    hub.register("run.cancel", orchestrator.accept_cancel)
    hub.register("viewer.set_wavelength", handle_viewer_wavelength)


async def _run(args: argparse.Namespace) -> None:
    journal = EventJournal(args.journal)
    hub = ProtocolHub(journal)
    server = ProtocolServer(hub, args.bind, args.port)
    orchestrator = RunOrchestrator(
        journal,
        server.broadcast,
        output_root=args.output_root,
        repo_root=args.repo_root,
        timeout_seconds=args.pipeline_timeout,
    )
    _demo_handlers(hub, orchestrator)
    await server.start()
    print(f"fruitsim-gateway listening on ws://{args.bind}:{args.port}", flush=True)
    assert server.server is not None
    try:
        async with server.server:
            await server.server.serve_forever()
    finally:
        await orchestrator.close()
        await server.close()


def main() -> int:
    parser = argparse.ArgumentParser(prog="fruitsim-gateway")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--journal", type=Path, default=Path("results/gateway/events.jsonl"))
    parser.add_argument("--output-root", type=Path, default=Path("results/web_demo/runs"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--pipeline-timeout", type=float, default=300.0)
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
