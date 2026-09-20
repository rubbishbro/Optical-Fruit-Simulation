# Work Package 8 — Stage acceptance and student entry point

This package adds the final acceptance layer rather than another model. The
acceptance command checks the Run contract first, then checks the source-specific
formula domains and identities, target boundaries, sample/spectral grain and
ML split artifacts.

```bash
PYTHONPATH=python python -m fruitsim_pipeline audit-run results/runs/<run_id>
```

The report distinguishes `pass`, `pass_with_caveats` and `fail`. A caveat is
used for known synthetic limitations; it is not silently promoted to a real-data
claim.

The student-facing end-to-end path is documented in
[`STUDENT_QUICKSTART.md`](STUDENT_QUICKSTART.md) and exposed through
`scripts/run_student_demo.sh` / `fruitsim-student`.

For maintainers, the complete stage acceptance entry point is:

```bash
bash scripts/run_stage_acceptance.sh
```

It runs the available C++ tests, the Python contract/data/visualization tests,
then runs the same small student flow and leaves its audit reports under
`results/stage_acceptance/`. If the C++ build directory is absent, the Python
and student checks still run; that omission must remain visible in the final
acceptance record.

The measured result and the current formula/leakage/visualization boundary are
recorded in [`STAGE_ACCEPTANCE_REPORT.md`](STAGE_ACCEPTANCE_REPORT.md).
