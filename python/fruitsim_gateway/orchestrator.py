from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Awaitable, Callable

from fruitsim_protocol.journal import EventJournal


EventSink = Callable[[dict[str, Any]], Awaitable[None]]
CommandFactory = Callable[[str, int, int], list[str]]  # (run_id, seed, samples) -> argv

# Run states that must never be overwritten by a late cancellation.
TERMINAL_RUN_STATES = {"completed", "failed", "cancelled"}

# Mirrors fruitsim_pipeline.contracts.RUN_ID_RE: an identifier may not start with
# a dot and never contains path separators, which blocks "." / ".." / traversal.
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
RESERVED_RUN_IDS = {".", ".."}
DEFAULT_SEED = 20260919
DEFAULT_SAMPLES = 120
MAX_SEED = 2**31 - 1
# MathSyntheticConfig defaults batch_count=6 and requires batch_count <= samples,
# so samples below 6 would only fail later inside the pipeline.
MIN_SAMPLES = 6
MAX_SAMPLES = 5000
MAX_CAPTURED_OUTPUT = 4000


class RunInputError(ValueError):
    """Raised when a run.start / run.cancel command is unsafe or out of range."""


class _RunCancelled(Exception):
    """Internal signal: the run was cancelled by the user (handled, not a crash)."""


def validate_run_id(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise RunInputError("run_id 必须是非空字符串")
    if value in RESERVED_RUN_IDS or "/" in value or "\\" in value:
        raise RunInputError("run_id 不允许使用 '.'、'..' 或路径分隔符")
    if not RUN_ID_RE.fullmatch(value):
        raise RunInputError(
            "run_id 只能包含字母、数字、下划线、点和连字符，且以字母或数字开头（最长 120 字符）"
        )
    return value


def coerce_integer(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise RunInputError(f"{name} 必须是整数")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise RunInputError(f"{name} 必须是整数")
        number = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not re.fullmatch(r"[+-]?\d+", text):
            raise RunInputError(f"{name} 必须是整数")
        number = int(text)
    else:
        raise RunInputError(f"{name} 必须是整数")
    if number < minimum or number > maximum:
        raise RunInputError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return number


class RunOrchestrator:
    """Async bridge from accepted WebSocket commands to real child processes.

    Each ``run.start`` runs ``fruitsim_pipeline generate-math`` as an
    ``asyncio`` subprocess so cancel, timeout and shutdown can terminate and
    await the actual process instead of abandoning a worker thread.
    """

    def __init__(
        self,
        journal: EventJournal,
        emit: EventSink,
        *,
        output_root: Path,
        repo_root: Path,
        timeout_seconds: float = 300.0,
        python_executable: str | None = None,
        command_factory: CommandFactory | None = None,
        shutdown_seconds: float = 10.0,
        terminate_seconds: float = 5.0,
        kill_seconds: float = 5.0,
    ) -> None:
        self.journal = journal
        self.emit = emit
        self.output_root = Path(output_root).resolve()
        self.repo_root = Path(repo_root).resolve()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.shutdown_seconds = max(1.0, float(shutdown_seconds))
        # Bounded escalation window: SIGTERM first, then SIGKILL. A child that
        # ignores SIGTERM must still be reaped in finite time.
        self.terminate_seconds = max(0.1, float(terminate_seconds))
        self.kill_seconds = max(0.1, float(kill_seconds))
        self.python_executable = python_executable or sys.executable
        self._command_factory = command_factory or self._default_command
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        # Every identifier ever accepted is reserved for the lifetime of the
        # orchestrator: a failed or immediately-cancelled run must not let the
        # caller reuse the id and collide with the reserved terminal state.
        self._allocated: set[str] = set()
        self._cancel_requested: set[str] = set()
        self._terminal: set[str] = set()
        self._reapers: dict[str, asyncio.Task[None]] = {}
        self._unreaped: set[str] = set()
        self._closing = False

    # ------------------------------------------------------------------ start
    def accept_start(self, command: dict[str, Any]) -> dict[str, Any]:
        if self._closing:
            raise RunInputError("服务正在关闭，无法接受新任务")
        payload = command.get("payload") or {}
        if not isinstance(payload, dict):
            raise RunInputError("payload 必须是对象")

        mode = str(payload.get("mode", "math"))
        if mode != "math":
            raise RunInputError("演示服务当前仅支持 mode=math")

        seed = coerce_integer(payload.get("seed", DEFAULT_SEED), name="seed", minimum=0, maximum=MAX_SEED)
        samples = coerce_integer(
            payload.get("samples", DEFAULT_SAMPLES),
            name="samples",
            minimum=MIN_SAMPLES,
            maximum=MAX_SAMPLES,
        )

        requested = command.get("run_id") or payload.get("run_id")
        if requested is None or (isinstance(requested, str) and not requested.strip()):
            run_id = self._unique_run_id(f"web_demo_seed{seed}")
        else:
            run_id = validate_run_id(requested)
            self._require_available(run_id)
        self._allocated.add(run_id)

        task = asyncio.create_task(self._execute(run_id, seed, samples))
        self._tasks[run_id] = task
        task.add_done_callback(lambda finished, rid=run_id: self._cleanup(rid, finished))
        return {
            "kind": "run_accepted",
            "stage": "queued",
            "status": "queued",
            "payload": {"run_id": run_id, "mode": mode, "seed": seed, "samples": samples},
        }

    def _require_available(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task is not None and not task.done() and run_id not in self._terminal:
            raise RunInputError(f"任务 {run_id} 正在运行，请勿重复提交")
        if run_id in self._allocated:
            raise RunInputError(f"任务标识 {run_id} 已被使用，请指定新的任务名称")
        if (self.output_root / run_id).exists():
            raise RunInputError(f"结果目录已存在：{run_id}；请使用新的任务名称")

    def _unique_run_id(self, base: str) -> str:
        candidate = validate_run_id(base)
        if not self._is_taken(candidate):
            return candidate
        for suffix in range(2, 1000):
            candidate = validate_run_id(f"{base}_{suffix}")
            if not self._is_taken(candidate):
                return candidate
        raise RunInputError("无法生成唯一 run_id，请指定新的任务名称")

    def _is_taken(self, run_id: str) -> bool:
        if run_id in self._allocated:
            return True
        task = self._tasks.get(run_id)
        if task is not None and not task.done() and run_id not in self._terminal:
            return True
        return (self.output_root / run_id).exists()

    # ----------------------------------------------------------------- cancel
    def accept_cancel(self, command: dict[str, Any]) -> dict[str, Any]:
        payload = command.get("payload") or {}
        if not isinstance(payload, dict):
            raise RunInputError("payload 必须是对象")
        requested = command.get("run_id") or payload.get("run_id")
        if not requested:
            raise RunInputError("run.cancel 需要 run_id")
        run_id = validate_run_id(requested)

        task = self._tasks.get(run_id)
        active = task is not None and not task.done() and run_id not in self._terminal
        if active:
            # Acknowledge the request immediately; the terminal run_cancelled
            # event is only published after the child process has exited.
            self._cancel_requested.add(run_id)
            self._ensure_reaper(run_id)
            message = "已请求取消，等待子进程退出"
        else:
            message = "该任务不在运行中"
        return {
            "kind": "run_cancel_requested",
            "stage": "control",
            "status": "cancelling",
            "payload": {"run_id": run_id, "active": active, "message": message},
        }

    async def wait(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task is not None:
            await task

    # ------------------------------------------------------------------ close
    async def close(self) -> None:
        # Idempotent: repeated calls must still wait for any Run tasks (not just
        # reapers) so a second close cannot return while a child is alive.
        self._closing = True
        active = [(rid, task) for rid, task in self._tasks.items() if not task.done()]
        for run_id, _ in active:
            self._cancel_requested.add(run_id)
            self._ensure_reaper(run_id)
        # A previously unreaped handle (task already finished, child still
        # alive) gets one more bounded attempt instead of being leaked.
        for run_id in list(self._unreaped):
            process = self._processes.get(run_id)
            if process is not None and process.returncode is None:
                if await self._terminate_and_reap(process):
                    self._unreaped.discard(run_id)
        if active:
            tasks = [task for _, task in active]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=self.shutdown_seconds,
                )
            except asyncio.TimeoutError:
                # Last-resort SIGKILL for anything the bounded reaper missed.
                for run_id, task in active:
                    process = self._processes.get(run_id)
                    if process is not None and process.returncode is None:
                        reaped = await self._terminate_and_reap(process)
                        if not reaped:
                            # Do not quietly pretend the child was reclaimed.
                            self._unreaped.add(run_id)
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        await self._drain_reapers()

    async def _drain_reapers(self) -> None:
        if not self._reapers:
            return
        reapers = list(self._reapers.values())
        try:
            await asyncio.wait_for(
                asyncio.gather(*reapers, return_exceptions=True),
                timeout=self.shutdown_seconds,
            )
        except asyncio.TimeoutError:
            for reaper in reapers:
                reaper.cancel()
            await asyncio.gather(*reapers, return_exceptions=True)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _terminate(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except (ProcessLookupError, OSError):
            pass

    def _ensure_reaper(self, run_id: str) -> None:
        """Escalate SIGTERM -> SIGKILL in the background so a child that
        ignores SIGTERM cannot keep ``communicate()`` blocked for the whole
        pipeline timeout while the caller already asked to cancel."""
        existing = self._reapers.get(run_id)
        if existing is not None and not existing.done():
            return
        process = self._processes.get(run_id)
        if process is None:
            return
        reaper = asyncio.create_task(self._reap(run_id, process))
        self._reapers[run_id] = reaper
        reaper.add_done_callback(lambda finished, rid=run_id: self._reapers.pop(rid, None))

    async def _reap(self, run_id: str, process: asyncio.subprocess.Process) -> None:
        try:
            await self._terminate_and_reap(process)
        except Exception:  # noqa: BLE001 - reaping must never crash the loop
            pass

    async def _await_exit(self, process: asyncio.subprocess.Process, timeout: float) -> bool:
        if process.returncode is not None:
            return True
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return process.returncode is not None

    async def _terminate_and_reap(self, process: asyncio.subprocess.Process) -> bool:
        """Bounded stop: terminate, wait, kill, wait.

        Returns ``True`` only when the child has actually exited. It never
        pretends a still-running process was stopped, so the caller can report
        the timeout honestly instead of claiming cancellation succeeded.
        """
        if process.returncode is not None:
            return True
        self._terminate(process)
        if await self._await_exit(process, self.terminate_seconds):
            return True
        try:
            process.kill()
        except (ProcessLookupError, OSError):
            pass
        return await self._await_exit(process, self.kill_seconds)

    # ------------------------------------------------- run status reconciliation
    @staticmethod
    def _read_json_object(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _atomic_write_json(path: Path, document: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _run_manifest_state(self, run_id: str) -> str | None:
        manifest = self._read_json_object(self.output_root / run_id / "manifest.json")
        if manifest is None:
            return None
        state = manifest.get("status")
        return state if isinstance(state, str) else None

    def _sync_run_terminal(
        self, run_id: str, state: str, *, error_code: str, message: str
    ) -> bool:
        """Reconcile a partial Run's manifest/status with a gateway terminal.

        Only called after the child has safely exited. It refuses to overwrite
        an already-terminal Run (completed/failed/cancelled), and never touches
        any data artifact. Returns True when a write happened.
        """
        if state not in {"cancelled", "failed"}:
            return False
        run_dir = self.output_root / run_id
        manifest = self._read_json_object(run_dir / "manifest.json")
        status = self._read_json_object(run_dir / "status.json")
        if manifest is None and status is None:
            return False
        current = None
        if isinstance(status, dict):
            current = status.get("state")
        if not isinstance(current, str) and isinstance(manifest, dict):
            current = manifest.get("status")
        if current in TERMINAL_RUN_STATES:
            return False
        updated_at = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        try:
            if isinstance(manifest, dict):
                manifest = dict(manifest)
                manifest["status"] = state
                self._atomic_write_json(run_dir / "manifest.json", manifest)
            if isinstance(status, dict):
                status = dict(status)
                status["state"] = state
                status["updated_at"] = updated_at
                status["error_code"] = error_code
                status["message"] = message
                self._atomic_write_json(run_dir / "status.json", status)
        except OSError:
            # Reconciliation is best-effort and must never mask the terminal
            # event the client is waiting for.
            return False
        return True


    def _cleanup(self, run_id: str, task: asyncio.Task[None]) -> None:
        # Keep the handle of a child that is still alive so close() can retry;
        # dropping it would lose the only way to reclaim the process.
        process = self._processes.get(run_id)
        if process is None or process.returncode is not None:
            self._processes.pop(run_id, None)
            self._unreaped.discard(run_id)
        self._cancel_requested.discard(run_id)
        if len(self._tasks) > 500:
            for old_id, old_task in list(self._tasks.items()):
                if old_task.done() and old_id != run_id:
                    del self._tasks[old_id]

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

    async def _finish(
        self,
        run_id: str,
        *,
        kind: str,
        stage: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        # A terminal state is published at most once per run.
        if run_id in self._terminal:
            return
        self._terminal.add(run_id)
        try:
            await self._publish(run_id, kind=kind, stage=stage, status=status, payload=payload or {})
        except Exception:
            pass

    def _default_command(self, run_id: str, seed: int, samples: int) -> list[str]:
        return [
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

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        python_path = [str(self.repo_root / "python")]
        if environment.get("PYTHONPATH"):
            python_path.append(environment["PYTHONPATH"])
        environment["PYTHONPATH"] = os.pathsep.join(python_path)
        return environment

    # ---------------------------------------------------------------- execute
    async def _execute(self, run_id: str, seed: int, samples: int) -> None:
        try:
            await self._publish(
                run_id, kind="run_progress", stage="queued", status="queued", payload={"run_id": run_id}
            )
            await asyncio.sleep(0)
            if self._closing or run_id in self._cancel_requested:
                raise _RunCancelled
            await self._publish(
                run_id,
                kind="run_progress",
                stage="generating",
                status="running",
                payload={"run_id": run_id, "completed": 0, "total": samples},
            )
            self.output_root.mkdir(parents=True, exist_ok=True)
            command = list(await self._maybe_async_command(run_id, seed, samples))
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self.repo_root),
                env=self._environment(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._processes[run_id] = process
            # Cancel may arrive before the process handle exists; honour it now
            # and make sure SIGTERM escalation is armed for stubborn children.
            if self._closing or run_id in self._cancel_requested:
                self._ensure_reaper(run_id)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
            except asyncio.TimeoutError:
                reaped = await self._terminate_and_reap(process)
                cancelled = self._closing or run_id in self._cancel_requested
                if cancelled and reaped:
                    # A cancel/close that raced the timeout is a cancellation.
                    self._sync_run_terminal(
                        run_id, "cancelled", error_code="run_cancelled",
                        message="任务在超时竞态中被取消",
                    )
                    await self._finish(
                        run_id,
                        kind="run_cancelled",
                        stage="control",
                        status="cancelled",
                        payload={"run_id": run_id, "process_reaped": True},
                    )
                    return
                if cancelled and not reaped:
                    self._unreaped.add(run_id)
                    await self._finish(
                        run_id,
                        kind="run_failed",
                        stage="control",
                        status="failed",
                        payload={
                            "run_id": run_id,
                            "error_code": "cancellation_failed",
                            "message": "取消请求已发出，但子进程未能在限时内终止，可能仍在运行",
                            "process_reaped": False,
                        },
                    )
                    return
                if reaped:
                    self._sync_run_terminal(
                        run_id, "failed", error_code="pipeline_timeout",
                        message="任务超时，已终止子进程",
                    )
                    payload = {
                        "run_id": run_id,
                        "error_code": "pipeline_timeout",
                        "message": "任务超时，已终止子进程",
                        "process_reaped": True,
                    }
                else:
                    self._unreaped.add(run_id)
                    payload = {
                        "run_id": run_id,
                        "error_code": "pipeline_timeout_unreaped",
                        "message": "任务超时，子进程未能在限时内终止",
                        "process_reaped": False,
                    }
                await self._finish(
                    run_id, kind="run_failed", stage="generating", status="failed", payload=payload
                )
                return

            exit_code = process.returncode
            cancelled = self._closing or run_id in self._cancel_requested
            # A Run that genuinely recorded completion wins over a late cancel:
            # the child already wrote a completed manifest/status before exiting.
            if self._run_manifest_state(run_id) == "completed":
                run_dir = self.output_root / run_id
                await self._finish(
                    run_id,
                    kind="run_completed",
                    stage="completed",
                    status="completed",
                    payload={
                        "run_id": run_id,
                        "run_dir": str(run_dir),
                        "completed": samples,
                        "total": samples,
                    },
                )
                return
            if cancelled:
                raise _RunCancelled
            if exit_code != 0:
                message = self._tail((stderr or b"").decode("utf-8", "replace"))
                if not message:
                    message = self._tail((stdout or b"").decode("utf-8", "replace"))
                if not message:
                    message = f"pipeline 退出码 {process.returncode}"
                self._sync_run_terminal(
                    run_id, "failed", error_code="pipeline_failed", message=message
                )
                await self._finish(
                    run_id,
                    kind="run_failed",
                    stage="generating",
                    status="failed",
                    payload={"run_id": run_id, "error_code": "pipeline_failed", "message": message},
                )
                return
            run_dir = self.output_root / run_id
            await self._finish(
                run_id,
                kind="run_completed",
                stage="completed",
                status="completed",
                payload={
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "completed": samples,
                    "total": samples,
                },
            )
        except asyncio.CancelledError:
            await self._handle_cancelled(run_id)
            raise
        except _RunCancelled:
            await self._handle_cancelled(run_id)
        except Exception as exception:  # noqa: BLE001 - surface any launch/IO failure
            await self._finish(
                run_id,
                kind="run_failed",
                stage="orchestrator",
                status="failed",
                payload={
                    "run_id": run_id,
                    "error_code": "orchestrator_error",
                    "message": str(exception)[:1000],
                },
            )
        finally:
            process = self._processes.get(run_id)
            if process is not None and process.returncode is None:
                try:
                    await self._terminate_and_reap(process)
                except Exception:
                    pass

    async def _handle_cancelled(self, run_id: str) -> None:
        """Publish the honest outcome of a cancellation request.

        A cancelled terminal is only emitted once the child is confirmed gone;
        otherwise the run is reported as failed with ``cancellation_failed`` so
        the UI cannot claim it stopped when it may still be running.
        """
        process = self._processes.get(run_id)
        reaped = True if process is None else await self._terminate_and_reap(process)
        if not reaped:
            self._unreaped.add(run_id)
            await self._finish(
                run_id,
                kind="run_failed",
                stage="control",
                status="failed",
                payload={
                    "run_id": run_id,
                    "error_code": "cancellation_failed",
                    "message": "取消请求已发出，但子进程未能在限时内终止，可能仍在运行",
                    "process_reaped": False,
                },
            )
            return
        self._sync_run_terminal(
            run_id, "cancelled", error_code="run_cancelled", message="用户取消"
        )
        await self._finish(
            run_id,
            kind="run_cancelled",
            stage="control",
            status="cancelled",
            payload={"run_id": run_id, "process_reaped": True},
        )

    async def _maybe_async_command(self, run_id: str, seed: int, samples: int) -> list[str]:
        result = self._command_factory(run_id, seed, samples)
        if asyncio.iscoroutine(result):
            result = await result
        return list(result)

    @staticmethod
    def _tail(text: str, limit: int = MAX_CAPTURED_OUTPUT) -> str:
        text = text.strip()
        return text[-limit:]
