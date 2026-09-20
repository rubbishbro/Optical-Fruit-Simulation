from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from fruitsim_protocol.journal import EventJournal

from .orchestrator import RunOrchestrator
from .server import ProtocolHub, ProtocolServer


def _demo_handlers(hub: ProtocolHub, orchestrator: RunOrchestrator) -> None:
    hub.register("run.start", orchestrator.accept_start)
    hub.register("run.cancel", orchestrator.accept_cancel)
    hub.register("viewer.set_wavelength", lambda command: {
        "kind": "viewer_state",
        "stage": "viewer",
        "status": "updated",
        "payload": command.get("payload", {}),
    })


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
