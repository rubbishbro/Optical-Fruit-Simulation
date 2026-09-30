from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest

from fruitsim_gateway.orchestrator import (
    MAX_SAMPLES,
    MIN_SAMPLES,
    RunInputError,
    RunOrchestrator,
    coerce_integer,
    validate_run_id,
)
from fruitsim_gateway.server import ProtocolHub
from fruitsim_protocol import EventJournal, make_command


def _sleeping_script(pid_file: Path, seconds: float, exit_code: int = 0, stderr: str = "") -> str:
    """A controlled child process that records its pid before sleeping."""
    return (
        "import os, sys, time\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        f"time.sleep({seconds!r})\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({exit_code})\n"
    )


def _sleeping_factory(pid_file: Path, seconds: float, exit_code: int = 0, stderr: str = ""):
    script = _sleeping_script(pid_file, seconds, exit_code, stderr)

    def factory(run_id: str, seed: int, samples: int) -> list[str]:
        return [sys.executable, "-c", script]

    return factory


def _sigterm_ignoring_script(pid_file: Path, seconds: float = 60.0) -> str:
    """A controlled child that ignores SIGTERM and records its pid."""
    return (
        "import os, signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "sys.stdout.write('ready\\n'); sys.stdout.flush()\n"
        f"time.sleep({seconds!r})\n"
    )


def _sigterm_ignoring_factory(pid_file: Path, seconds: float = 60.0):
    script = _sigterm_ignoring_script(pid_file, seconds)

    def factory(run_id: str, seed: int, samples: int) -> list[str]:
        return [sys.executable, "-c", script]

    return factory


class _StubbornProcess:
    """Fake child that never exits, to prove reaping is honest about failure."""

    returncode = None

    def terminate(self) -> None:  # pragma: no cover - exercised indirectly
        pass

    def kill(self) -> None:  # pragma: no cover - exercised indirectly
        pass

    async def wait(self) -> int:
        await asyncio.sleep(3600)
        return 0


def _run_child_factory(script: str):
    def factory(run_id: str, seed: int, samples: int) -> list[str]:
        return [sys.executable, "-c", script]

    return factory


def _partial_run_script(output_root: Path, run_id: str, pid_file: Path, sleep_seconds: float) -> str:
    """Child that creates a Run and pauses in generating_data."""
    return (
        "import os, time\n"
        "from pathlib import Path\n"
        "from fruitsim_pipeline.run_manager import RunManager\n"
        f"root = Path({str(output_root)!r})\n"
        f"run = RunManager.create(root, {run_id!r}, 'synthetic_math', 1, ['generate', 'postprocess'])\n"
        "run.set_state('validating', stage='configuration')\n"
        "run.set_state('generating_data', completed=0, total=10)\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        f"time.sleep({sleep_seconds!r})\n"
    )


def _completed_run_script(output_root: Path, run_id: str, pid_file: Path, sleep_seconds: float) -> str:
    """Child that records a completed Run before lingering briefly."""
    return (
        "import os, time\n"
        "from pathlib import Path\n"
        "from fruitsim_pipeline.run_manager import RunManager\n"
        f"root = Path({str(output_root)!r})\n"
        f"run = RunManager.create(root, {run_id!r}, 'synthetic_math', 1, ['generate', 'postprocess'])\n"
        "run.set_state('validating', stage='configuration')\n"
        "run.set_state('generating_data', completed=0, total=10)\n"
        "run.set_state('postprocessing', completed=10, total=10)\n"
        "run.set_state('completed', completed=10, total=10)\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        f"time.sleep({sleep_seconds!r})\n"
    )


def _read_json(path: Path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _wait_for_pid(pid_file: Path, timeout: float = 5.0) -> int:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if pid_file.exists():
            text = pid_file.read_text(encoding="utf-8").strip()
            if text:
                return int(text)
        await asyncio.sleep(0.02)
    raise AssertionError(f"child pid file was never written: {pid_file}")


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition was not met before the timeout")


def _make_orchestrator(root: Path, published: list[dict], **kwargs) -> RunOrchestrator:
    journal = EventJournal()

    async def collect(event: dict) -> None:
        published.append(event)

    return RunOrchestrator(
        journal,
        collect,
        output_root=root / "runs",
        repo_root=Path.cwd(),
        **kwargs,
    )


class RunIdValidationTests(unittest.TestCase):
    def test_rejects_traversal_and_separators(self) -> None:
        for bad in (".", "..", "a/b", "a\\b", "a:b", "a b", "", "-leading"):
            with self.assertRaises(RunInputError, msg=bad):
                validate_run_id(bad)

    def test_accepts_safe_identifier(self) -> None:
        for good in ("web_demo_seed1", "review.math_2026-09-30", "A1"):
            self.assertEqual(validate_run_id(good), good)

    def test_rejects_unsafe_length(self) -> None:
        with self.assertRaises(RunInputError):
            validate_run_id("a" * 121)

    def test_coerce_integer_is_strict(self) -> None:
        self.assertEqual(coerce_integer("42", name="seed", minimum=0, maximum=100), 42)
        self.assertEqual(coerce_integer(42.0, name="seed", minimum=0, maximum=100), 42)
        for bad in (True, 1.5, "abc", "", None, [1]):
            with self.assertRaises(RunInputError, msg=repr(bad)):
                coerce_integer(bad, name="seed", minimum=0, maximum=100)
        with self.assertRaises(RunInputError):
            coerce_integer(-1, name="seed", minimum=0, maximum=100)
        with self.assertRaises(RunInputError):
            coerce_integer(101, name="seed", minimum=0, maximum=100)


class OrchestratorValidationTests(unittest.TestCase):
    def test_accept_start_rejects_bad_inputs_without_spawning(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                orchestrator = _make_orchestrator(root, published, command_factory=_sleeping_factory(root / "p", 30))
                cases = [
                    make_command("run.start", {"mode": "physics"}, run_id="bad-mode"),
                    make_command("run.start", {"mode": "math", "seed": -1}, run_id="bad-seed"),
                    make_command("run.start", {"mode": "math", "seed": 1.5}, run_id="float-seed"),
                    make_command("run.start", {"mode": "math", "samples": MIN_SAMPLES - 1}, run_id="tiny"),
                    make_command("run.start", {"mode": "math", "samples": MAX_SAMPLES + 1}, run_id="huge"),
                    # These pass the wire protocol but must be rejected by the orchestrator.
                    make_command("run.start", {"mode": "math"}, run_id=".."),
                    make_command("run.start", {"mode": "math"}, run_id="."),
                    make_command("run.start", {"mode": "math"}, run_id="a:b"),
                ]
                for command in cases:
                    with self.assertRaises(RunInputError, msg=str(command)):
                        orchestrator.accept_start(command)
                self.assertEqual(orchestrator._processes, {})
                self.assertEqual(published, [])
                await orchestrator.close()

        asyncio.run(scenario())

    def test_rejects_existing_run_directory(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "runs" / "taken").mkdir(parents=True)
                published: list[dict] = []
                orchestrator = _make_orchestrator(root, published, command_factory=_sleeping_factory(root / "p", 30))
                with self.assertRaisesRegex(RunInputError, "已存在"):
                    orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="taken"))
                await orchestrator.close()

        asyncio.run(scenario())

    def test_rejects_duplicate_active_run(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root, published, command_factory=_sleeping_factory(pid_file, 30)
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="active-run"))
                await _wait_for_pid(pid_file)
                with self.assertRaisesRegex(RunInputError, "正在运行"):
                    orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="active-run"))
                await orchestrator.close()

        asyncio.run(scenario())

    def test_allocated_id_not_reused_after_immediate_cancel(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root, published, command_factory=_sleeping_factory(pid_file, 30)
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="reuse-me"))
                orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="reuse-me"))
                await asyncio.wait_for(orchestrator.wait("reuse-me"), timeout=15)
                # The id was allocated, so a retry must be rejected instead of
                # silently reusing an id whose terminal state is already set.
                with self.assertRaisesRegex(RunInputError, "已被使用"):
                    orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="reuse-me"))
                await orchestrator.close()

        asyncio.run(scenario())

    def test_allocated_id_not_reused_after_failed_run(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    command_factory=_sleeping_factory(pid_file, 0.05, exit_code=2, stderr="nope"),
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="failed-id"))
                await asyncio.wait_for(orchestrator.wait("failed-id"), timeout=15)
                with self.assertRaisesRegex(RunInputError, "已被使用"):
                    orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="failed-id"))
                await orchestrator.close()

        asyncio.run(scenario())

    def test_close_rejects_new_starts(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root, published, command_factory=_sleeping_factory(pid_file, 30)
                )
                await orchestrator.close()
                with self.assertRaisesRegex(RunInputError, "关闭"):
                    orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="after-close"))
                self.assertEqual(orchestrator._processes, {})

        asyncio.run(scenario())

    def test_min_samples_matches_pipeline_batch_count(self) -> None:
        # MathSyntheticConfig defaults batch_count=6, so the front/back ranges
        # must not permit a samples value the pipeline would later reject.
        from fruitsim_pipeline.synthetic_math import MathSyntheticConfig

        self.assertEqual(MIN_SAMPLES, MathSyntheticConfig().batch_count)

    def test_default_run_id_is_unique(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root, published, command_factory=_sleeping_factory(pid_file, 30)
                )
                first = orchestrator.accept_start(make_command("run.start", {"mode": "math", "seed": 7}))
                second = orchestrator.accept_start(make_command("run.start", {"mode": "math", "seed": 7}))
                self.assertNotEqual(first["payload"]["run_id"], second["payload"]["run_id"])
                await orchestrator.close()

        asyncio.run(scenario())


class OrchestratorProcessLifetimeTests(unittest.TestCase):
    def test_cancel_terminates_and_awaits_real_child(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root, published, command_factory=_sleeping_factory(pid_file, 30)
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="cancel-me"))
                pid = await _wait_for_pid(pid_file)
                self.assertTrue(_pid_alive(pid))
                request = orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="cancel-me"))
                self.assertTrue(request["payload"]["active"])
                self.assertEqual(request["status"], "cancelling")
                await asyncio.wait_for(orchestrator.wait("cancel-me"), timeout=15)
                await _wait_until(lambda: not _pid_alive(pid), timeout=5)
                kinds = [event["kind"] for event in published]
                self.assertIn("run_cancelled", kinds)
                self.assertNotIn("run_completed", kinds)
                self.assertFalse(_pid_alive(pid))
                await orchestrator.close()

        asyncio.run(scenario())

    def test_cancel_kills_child_that_ignores_sigterm(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    # Bound the escalation so the test cannot wait the default 10s.
                    terminate_seconds=0.5,
                    kill_seconds=5.0,
                    command_factory=_sigterm_ignoring_factory(pid_file, 60.0),
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="stubborn"))
                pid = await _wait_for_pid(pid_file)
                self.assertTrue(_pid_alive(pid))
                orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="stubborn"))
                await asyncio.wait_for(orchestrator.wait("stubborn"), timeout=15)
                await _wait_until(lambda: not _pid_alive(pid), timeout=5)
                self.assertFalse(_pid_alive(pid), "SIGTERM-ignoring child survived cancel")
                kinds = [event["kind"] for event in published]
                self.assertIn("run_cancelled", kinds)
                self.assertNotIn("run_completed", kinds)
                self.assertNotIn("run_failed", kinds)
                self.assertEqual(published[-1]["status"], "cancelled")
                self.assertTrue(published[-1]["payload"].get("process_reaped"))
                await orchestrator.close()

        asyncio.run(scenario())

    def test_close_kills_child_that_ignores_sigterm(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    terminate_seconds=0.5,
                    kill_seconds=5.0,
                    shutdown_seconds=15.0,
                    command_factory=_sigterm_ignoring_factory(pid_file, 60.0),
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="stubborn-close"))
                pid = await _wait_for_pid(pid_file)
                await asyncio.wait_for(orchestrator.close(), timeout=20)
                await _wait_until(lambda: not _pid_alive(pid), timeout=5)
                self.assertFalse(_pid_alive(pid), "SIGTERM-ignoring child survived close")
                self.assertNotIn("run_completed", [event["kind"] for event in published])

        asyncio.run(scenario())

    def test_terminate_and_reap_reports_failure_instead_of_lying(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    terminate_seconds=0.1,
                    kill_seconds=0.1,
                )
                stubborn = _StubbornProcess()
                reaped = await orchestrator._terminate_and_reap(stubborn)  # type: ignore[arg-type]
                self.assertFalse(reaped, "reap reported success while the process never exited")
                await orchestrator.close()

        asyncio.run(scenario())

    def test_cancellation_failure_reports_failed_not_cancelled(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                # Child exits on its own quickly; the reap stub always claims
                # failure so the gateway must not pretend it was cancelled.
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    command_factory=_sleeping_factory(pid_file, 0.5),
                )

                async def fake_reap(process):  # noqa: ANN001 - test stub
                    return False

                orchestrator._terminate_and_reap = fake_reap  # type: ignore[assignment]
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="no-reap"))
                await _wait_for_pid(pid_file)
                orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="no-reap"))
                await asyncio.wait_for(orchestrator.wait("no-reap"), timeout=15)
                final = published[-1]
                self.assertEqual(final["kind"], "run_failed")
                self.assertEqual(final["payload"]["error_code"], "cancellation_failed")
                self.assertFalse(final["payload"]["process_reaped"])
                self.assertNotIn("run_cancelled", [event["kind"] for event in published])
                await orchestrator.close()

        asyncio.run(scenario())

    def test_cancel_syncs_partial_run_status_to_cancelled(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                output_root = root / "runs"
                script = _partial_run_script(output_root, "partial-run", pid_file, 30.0)
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    terminate_seconds=1.0,
                    kill_seconds=5.0,
                    command_factory=_run_child_factory(script),
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="partial-run"))
                pid = await _wait_for_pid(pid_file)
                status_path = output_root / "partial-run" / "status.json"
                await _wait_until(
                    lambda: _read_json(status_path).get("state") == "generating_data", timeout=5
                )
                orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="partial-run"))
                await asyncio.wait_for(orchestrator.wait("partial-run"), timeout=15)
                await _wait_until(lambda: not _pid_alive(pid), timeout=5)
                self.assertEqual(published[-1]["kind"], "run_cancelled")
                self.assertTrue(published[-1]["payload"]["process_reaped"])
                self.assertEqual(_read_json(status_path)["state"], "cancelled")
                manifest = _read_json(output_root / "partial-run" / "manifest.json")
                self.assertEqual(manifest["status"], "cancelled")
                await orchestrator.close()

        asyncio.run(scenario())

    def test_completed_run_wins_over_late_cancel(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                output_root = root / "runs"
                script = _completed_run_script(output_root, "done-run", pid_file, 1.0)
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    terminate_seconds=1.0,
                    kill_seconds=5.0,
                    command_factory=_run_child_factory(script),
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="done-run"))
                await _wait_for_pid(pid_file)
                status_path = output_root / "done-run" / "status.json"
                self.assertEqual(_read_json(status_path)["state"], "completed")
                # A cancel that arrives after the Run was recorded as completed
                # must not rewrite it to cancelled.
                orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="done-run"))
                await asyncio.wait_for(orchestrator.wait("done-run"), timeout=15)
                self.assertEqual(published[-1]["kind"], "run_completed")
                self.assertEqual(published[-1]["status"], "completed")
                self.assertNotIn("run_cancelled", [event["kind"] for event in published])
                self.assertEqual(_read_json(status_path)["state"], "completed")
                self.assertEqual(_read_json(output_root / "done-run" / "manifest.json")["status"], "completed")
                await orchestrator.close()

        asyncio.run(scenario())

    def test_close_twice_is_idempotent_and_waits_tasks(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root, published, command_factory=_sleeping_factory(pid_file, 30)
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="double-close"))
                pid = await _wait_for_pid(pid_file)
                await asyncio.wait_for(orchestrator.close(), timeout=15)
                await asyncio.wait_for(orchestrator.close(), timeout=15)
                await _wait_until(lambda: not _pid_alive(pid), timeout=5)
                self.assertFalse(_pid_alive(pid), "child survived a repeated close")
                self.assertNotIn("run_completed", [event["kind"] for event in published])

        asyncio.run(scenario())

    def test_unreaped_cancel_keeps_handle_and_close_retries(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    timeout_seconds=0.5,
                    terminate_seconds=0.1,
                    kill_seconds=0.1,
                    command_factory=_sigterm_ignoring_factory(pid_file, 60.0),
                )

                async def fake_reap(process):  # noqa: ANN001 - test stub
                    return False

                orchestrator._terminate_and_reap = fake_reap  # type: ignore[assignment]
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="stuck"))
                pid = await _wait_for_pid(pid_file)
                orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="stuck"))
                await asyncio.wait_for(orchestrator.wait("stuck"), timeout=15)
                final = published[-1]
                self.assertEqual(final["kind"], "run_failed")
                self.assertEqual(final["payload"]["error_code"], "cancellation_failed")
                self.assertFalse(final["payload"]["process_reaped"])
                # The still-alive handle is retained for a later cleanup.
                self.assertIsNotNone(orchestrator._processes.get("stuck"))
                # Restoring real reaping lets close() make good on the retry.
                del orchestrator._terminate_and_reap
                await asyncio.wait_for(orchestrator.close(), timeout=15)
                await _wait_until(lambda: not _pid_alive(pid), timeout=5)
                self.assertFalse(_pid_alive(pid), "close did not retry the retained handle")

        asyncio.run(scenario())

    def test_timeout_kills_child_and_reports_timeout(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    timeout_seconds=1.0,
                    command_factory=_sleeping_factory(pid_file, 30),
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="timeout-me"))
                pid = await _wait_for_pid(pid_file)
                await asyncio.wait_for(orchestrator.wait("timeout-me"), timeout=15)
                await _wait_until(lambda: not _pid_alive(pid), timeout=5)
                final = published[-1]
                self.assertEqual(final["kind"], "run_failed")
                self.assertEqual(final["payload"]["error_code"], "pipeline_timeout")
                self.assertFalse(_pid_alive(pid))
                await orchestrator.close()

        asyncio.run(scenario())

    def test_close_terminates_active_child(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root, published, command_factory=_sleeping_factory(pid_file, 30)
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="close-me"))
                pid = await _wait_for_pid(pid_file)
                await asyncio.wait_for(orchestrator.close(), timeout=15)
                await _wait_until(lambda: not _pid_alive(pid), timeout=5)
                self.assertFalse(_pid_alive(pid))
                kinds = [event["kind"] for event in published]
                self.assertIn("run_cancelled", kinds)
                self.assertNotIn("run_completed", kinds)

        asyncio.run(scenario())

    def test_immediate_cancel_before_process_start_is_safe(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root, published, command_factory=_sleeping_factory(pid_file, 30)
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="race"))
                orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="race"))
                await asyncio.wait_for(orchestrator.wait("race"), timeout=15)
                self.assertEqual(orchestrator._processes, {})
                self.assertFalse(pid_file.exists())
                kinds = [event["kind"] for event in published]
                self.assertEqual(kinds.count("run_cancelled"), 1)
                self.assertNotIn("run_completed", kinds)
                await orchestrator.close()

        asyncio.run(scenario())

    def test_failed_pipeline_reports_message_and_no_success_event(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root,
                    published,
                    command_factory=_sleeping_factory(pid_file, 0.05, exit_code=3, stderr="boom"),
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="fail-me"))
                await asyncio.wait_for(orchestrator.wait("fail-me"), timeout=15)
                final = published[-1]
                self.assertEqual(final["kind"], "run_failed")
                self.assertEqual(final["payload"]["error_code"], "pipeline_failed")
                self.assertIn("boom", final["payload"]["message"])
                self.assertNotIn("run_completed", [event["kind"] for event in published])
                await orchestrator.close()

        asyncio.run(scenario())

    def test_terminal_event_is_published_once(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                pid_file = root / "pid"
                orchestrator = _make_orchestrator(
                    root, published, command_factory=_sleeping_factory(pid_file, 30)
                )
                orchestrator.accept_start(make_command("run.start", {"mode": "math"}, run_id="once"))
                await _wait_for_pid(pid_file)
                orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="once"))
                # A second cancel after the terminal state must not emit another terminal event.
                await orchestrator.wait("once")
                orchestrator.accept_cancel(make_command("run.cancel", {}, run_id="once"))
                await asyncio.sleep(0.1)
                terminals = [
                    event
                    for event in published
                    if event["kind"] in {"run_completed", "run_cancelled", "run_failed"}
                ]
                self.assertEqual(len(terminals), 1)
                await orchestrator.close()

        asyncio.run(scenario())

    def test_hub_cancel_ack_is_immediate_and_terminal_is_deferred(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                journal = EventJournal()

                async def collect(event: dict) -> None:
                    published.append(event)

                pid_file = root / "pid"
                orchestrator = RunOrchestrator(
                    journal,
                    collect,
                    output_root=root / "runs",
                    repo_root=Path.cwd(),
                    command_factory=_sleeping_factory(pid_file, 30),
                )
                hub = ProtocolHub(journal)
                hub.register("run.start", orchestrator.accept_start)
                hub.register("run.cancel", orchestrator.accept_cancel)

                start_command = make_command("run.start", {"mode": "math"}, run_id="hub-run")
                ack, events = hub.handle(start_command)
                self.assertTrue(ack["accepted"])
                self.assertEqual(ack["command_id"], start_command["command_id"])
                self.assertEqual(events[0]["kind"], "run_accepted")
                # ProtocolHub copies command_id into the event payload so a
                # client can claim only its own run_accepted event.
                self.assertEqual(events[0]["payload"]["command_id"], start_command["command_id"])
                await _wait_for_pid(pid_file)

                cancel_ack, cancel_events = hub.handle(
                    make_command("run.cancel", {}, run_id="hub-run")
                )
                self.assertTrue(cancel_ack["accepted"])
                self.assertEqual(cancel_events[0]["kind"], "run_cancel_requested")
                self.assertTrue(cancel_events[0]["payload"]["active"])

                await asyncio.wait_for(orchestrator.wait("hub-run"), timeout=15)
                kinds = [event["kind"] for event in published]
                self.assertIn("run_cancelled", kinds)
                self.assertNotIn("run_completed", kinds)

                # A rejected command surfaces a concrete reason to the client.
                rejected_ack, _ = hub.handle(
                    make_command("run.start", {"mode": "math"}, run_id="..")
                )
                self.assertFalse(rejected_ack["accepted"])
                self.assertIn("error", rejected_ack)
                await orchestrator.close()

        asyncio.run(scenario())

    def test_successful_math_run_still_works(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                published: list[dict] = []
                orchestrator = _make_orchestrator(root, published, timeout_seconds=120.0)
                command = make_command(
                    "run.start",
                    {"mode": "math", "seed": 20260919, "samples": 20},
                    run_id="wp23_test_run",
                    command_id="wp23-test-command",
                )
                accepted = orchestrator.accept_start(command)
                self.assertEqual(accepted["status"], "queued")
                await orchestrator.wait("wp23_test_run")
                run_dir = root / "runs" / "wp23_test_run"
                self.assertTrue((run_dir / "manifest.json").exists())
                self.assertTrue((run_dir / "status.json").exists())
                self.assertEqual(published[-1]["kind"], "run_completed")
                self.assertEqual(published[-1]["status"], "completed")
                await orchestrator.close()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
