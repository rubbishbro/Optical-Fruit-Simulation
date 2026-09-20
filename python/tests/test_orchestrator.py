from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest

from fruitsim_gateway.orchestrator import RunOrchestrator
from fruitsim_protocol import EventJournal, make_command


class OrchestratorTests(unittest.TestCase):
    def test_run_start_generates_a_canonical_math_run_and_events(self) -> None:
        asyncio.run(self._run_start())

    async def _run_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = EventJournal()
            published: list[dict] = []

            async def collect(event: dict) -> None:
                published.append(event)

            orchestrator = RunOrchestrator(
                journal,
                collect,
                output_root=root / "runs",
                repo_root=Path.cwd(),
                timeout_seconds=60.0,
            )
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


if __name__ == "__main__":
    unittest.main()
