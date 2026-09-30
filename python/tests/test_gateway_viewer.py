from __future__ import annotations

import unittest

from fruitsim_gateway.__main__ import handle_viewer_wavelength


def _command(value):
    return {"name": "viewer.set_wavelength", "run_id": None, "payload": {"wavelength_nm": value}}


class ViewerWavelengthTests(unittest.TestCase):
    def test_accepts_in_range_wavelength_and_marks_preview_only(self) -> None:
        result = handle_viewer_wavelength(_command(700))
        self.assertEqual(result["kind"], "viewer_state")
        self.assertEqual(result["stage"], "viewer")
        self.assertIs(result["payload"]["preview_only"], True)
        self.assertEqual(result["payload"]["wavelength_nm"], 700.0)

    def test_rejects_out_of_range_or_non_finite_values(self) -> None:
        for bad in (399, 1101, 0, -5, "abc", "", None, True, float("nan"), float("inf")):
            with self.assertRaises(ValueError, msg=repr(bad)):
                handle_viewer_wavelength(_command(bad))

    def test_accepts_string_numeric(self) -> None:
        result = handle_viewer_wavelength(_command("450.5"))
        self.assertEqual(result["payload"]["wavelength_nm"], 450.5)


if __name__ == "__main__":
    unittest.main()
