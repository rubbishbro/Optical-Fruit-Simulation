from __future__ import annotations

import asyncio
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Awaitable, Callable

from fruitsim_protocol.journal import EventJournal


EventSink = Callable[[dict[str, Any]], Awaitable[None]]
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


class RunOrchestrator:
    """Small async bridge from accepted WebSocket commands to the Run pipeline."""

    def __init__(
        self,
        journal: EventJournal,
        emit: EventSink,
        *,
        output_root: Path,
        repo_root: Path,
        timeout_seconds: float = 300.0,
        python_executable: str | None = None,
    ) -> None:
        self.journal = journal
        self.emit = emit
        self.output_root = Path(output_root).resolve()
        self.repo_root = Path(repo_root).resolve()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.python_executable = python_executable or sys.executable
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def accept_start(self, command: dict[str, Any]) -> dict[str, Any]:
        payload = command.get("payload") or {}
        run_id = command.get("run_id") or payload.get("run_id")
        if not run_id:
            seed = int(payload.get("seed", 20260919))
            run_id = f"web_demo_seed{seed}"
        if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
            raise ValueError("run_id must contain only short safe identifier characters")

        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            raise ValueError(f"run is already active: {run_id}")

        mode = str(payload.get("mode", "math"))
        if mode != "math":
            raise ValueError("the demo orchestrator currently supports mode=math only")

        seed = int(payload.get("seed", 20260919))
        samples = max(20, min(5000, int(payload.get("samples", 120))))
        task = asyncio.create_task(self._execute(run_id, seed, samples))
        self._tasks[run_id] = task
        return {
            "kind": "run_accepted",
            "stage": "queued",
            "status": "queued",
            "payload": {"run_id": run_id, "mode": mode, "seed": seed, "samples": samples},
        }

    def accept_cancel(self, command: dict[str, Any]) -> dict[str, Any]:
        payload = command.get("payload") or {}
        run_id = command.get("run_id") or payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run.cancel requires run_id")
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
        return {
            "kind": "run_cancel_requested",
            "stage": "control",
            "status": "cancelling",
            "payload": {"run_id": run_id},
        }

    async def wait(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task is not None:
            await task

    async def close(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _publish(
        self,
        run_id: str,
        *,
        kind: str,
        stage: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = self.journal.append_event(
            run_id=run_id,
            kind=kind,
            stage=stage,
            status=status,
            payload=payload or {},
        )
        await self.emit(event)

    async def _execute(self, run_id: str, seed: int, samples: int) -> None:
        try:
            await self._publish(run_id, kind="run_progress", stage="queued", status="queued", payload={"run_id": run_id})
            await asyncio.sleep(0)
            await self._publish(
                run_id,
                kind="run_progress",
                stage="generating",
                status="running",
                payload={"run_id": run_id, "completed": 0, "total": samples},
            )
            self.output_root.mkdir(parents=True, exist_ok=True)
            command = [
                self.python_executable,
                "-m",
                "fruitsim_pipeline",
                "generate-math",
                "--output-root",
                str(self.output_root),
                "--run-id",
                run_id,
                "--samples",
                str(samples),
                "--seed",
                str(seed),
            ]
            environment = os.environ.copy()
            python_path = [str(self.repo_root / "python")]
            if environment.get("PYTHONPATH"):
                python_path.append(environment["PYTHONPATH"])
            environment["PYTHONPATH"] = os.pathsep.join(python_path)
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                cwd=str(self.repo_root),
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
            run_dir = self.output_root / run_id
            if completed.returncode != 0:
                message = (completed.stderr or completed.stdout or "pipeline returned a non-zero exit code")[-1000:]
                await self._publish(
                    run_id,
                    kind="run_failed",
                    stage="generating",
                    status="failed",
                    payload={"run_id": run_id, "error_code": "pipeline_failed", "message": message},
                )
                return
            await self._publish(
                run_id,
                kind="run_completed",
                stage="completed",
                status="completed",
                payload={"run_id": run_id, "run_dir": str(run_dir), "completed": samples, "total": samples},
            )
        except asyncio.CancelledError:
            await self._publish(
                run_id,
                kind="run_cancelled",
                stage="control",
                status="cancelled",
                payload={"run_id": run_id},
            )
        except subprocess.TimeoutExpired:
            await self._publish(
                run_id,
                kind="run_failed",
                stage="generating",
                status="failed",
                payload={"run_id": run_id, "error_code": "pipeline_timeout", "message": "pipeline timed out"},
            )
        except Exception as exception:
            await self._publish(
                run_id,
                kind="run_failed",
                stage="orchestrator",
                status="failed",
                payload={"run_id": run_id, "error_code": "orchestrator_error", "message": str(exception)[:1000]},
            )
