from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_web_demo.sh"


class RunWebDemoPythonBinTests(unittest.TestCase):
    def test_missing_interpreter_fails_before_starting_servers(self) -> None:
        environment = os.environ.copy()
        environment["PYTHON_BIN"] = "/nonexistent/fruitsim-python"
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=str(ROOT),
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Python interpreter not found", result.stderr)
        # The failure must name the override so the operator knows what to fix.
        self.assertIn("/nonexistent/fruitsim-python", result.stderr)

    def test_defaults_to_python3_and_shares_one_interpreter(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        # No bare ``python`` default, which is absent on this host.
        self.assertIn("PYTHON_BIN:-python3", text)
        # Gateway and static server must launch with the same resolved binary.
        self.assertIn('"${python_path}" -m fruitsim_gateway', text)
        self.assertIn('"${python_path}" scripts/serve_webgl_demo.py', text)
        # The results API must be opt-in and use the same output root as the Gateway.
        self.assertIn('--runs-root "${output_root}"', text)


if __name__ == "__main__":
    unittest.main()
