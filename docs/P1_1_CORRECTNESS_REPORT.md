# Fruitsim P1.1 Correctness and Teaching Playback Report

Date: 2026-09-21

P1.1 repairs the correctness boundary of the existing P1 teaching workbench. It does not add a new ML algorithm or refit a model in the browser. The browser consumes the saved `StageRun` bundle and renders its arrays, values, sample IDs, feature indices, and references.

## Delivered

- PLSR latent scores now carry explicit `scores_sample_ids`, `scores_calibration`, `calibration_sample_ids`, `fit_indices`, and `validation_indices`. Non-contiguous calibration/validation rows therefore cannot be mistaken for positional alignment.
- CARS intermediate states now carry `current_indices`, `retained_indices`, and coefficient arrays with the contract `coefficients[j]` belongs to `current_indices[j]`.
- The generated bundle contains a real `playback_plan`, resolvable `results_graph` nodes/edges, invocation metadata, and schema version 2.
- The browser has a pure renderer contract in `static/ml_p1_contract.js`. It covers interpolation, CARS coefficient mapping, model coefficient-to-wavelength mapping, pointer scaling, known-event dispatch, safe fallback, and playback plan resolution.
- Teaching playback refreshes the event list before rendering each stage boundary, updates narration from the actual event step, uses one cancellable `requestAnimationFrame`/timeout chain, and renders Results as a saved-metrics event.
- Preprocessing teaching steps use saved `raw`, `sample_mean`, `sample_std`, `normalized`, and SG `smoothed` arrays. No browser-side algorithm recomputation was added.
- CARS teaching uses the current wavelength identity rather than retained-array position guessing; removed wavelengths fade out and retained wavelengths remain highlighted.
- Modeling score plots resolve rows through `scores_sample_ids`; validation remains the default prediction view.

## Code paths

- Python workflow: `/home/rubbishbro/desktop/simulator/fruitsim/python/fruitsim_ml/workflow.py`
- Web bundle builder: `/home/rubbishbro/desktop/simulator/fruitsim/scripts/build_web_research_assets.py`
- Web renderer: `/home/rubbishbro/desktop/simulator/fruitsim/apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1.js`
- Renderer contract: `/home/rubbishbro/desktop/simulator/fruitsim/apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_contract.js`
- Bundle: `/home/rubbishbro/desktop/simulator/fruitsim/apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_bundle.json`
- JavaScript contract test: `/home/rubbishbro/desktop/simulator/fruitsim/scripts/test_ml_p1_renderer.js`

## Verification

```bash
PYTHONPATH=python /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python \
  -m unittest discover -s python/tests -p 'test_*.py' -v
```

Result: **74 tests passed, 2 skipped**. The two skips are the existing C++ mesh tests because the current C++ mesh build is unavailable. Gateway WebSocket E2E was also run in the host environment and passed.

```bash
node --check apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1.js
node --check apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_contract.js
node scripts/test_ml_p1_renderer.js
git diff --check
```

Result: JavaScript syntax, renderer contract, and whitespace checks passed.

```bash
FRUITSIM_BUILD_TIMEOUT=900 bash scripts/build_fruitsim_unity_webgl.sh
/home/rubbishbro/.local/bin/unity run apps/fruitsim_unity --timeout 420 -- \
  -executeMethod AppleCorrectnessChecks.RunFromCommandLine -nographics \
  -logFile /tmp/fruitsim-unity-p11-correctness.log
```

Result: Unity WebGL build completed successfully. The Unity correctness harness reported `passed=29 failed=0`.

## Front-end acceptance

The built WebGL artifact was served with `scripts/serve_webgl_demo.py`, which supplies the required gzip encoding and cross-origin headers. In the actual built page:

1. Unity reached `UNITY READY`.
2. ML page loaded the six Stage pages and real bundle metadata.
3. Pipeline playback visibly reached CARS iteration 6, then Results.
4. Results showed the real pipeline graph, comparison table, validation metrics, and collapse ratio.
5. Browser console error/warning query returned no entries after the built-page playback.
6. Pause changed the control to `Resume` and held the current step; the normal completion changed it back to `Play`.

The first check with `python -m http.server` showed Unity failure because that generic server does not declare `.gz` assets as gzip encoded. This was a serving-mode issue, not a Unity build issue. Repeating the test with `scripts/serve_webgl_demo.py` reached `UNITY READY`.

## Remaining boundaries

- The demonstration bundle remains explicitly synthetic (`SYNTHETIC_MATH`) and is labeled as such in the UI. It is not evidence of real-apple generalization.
- The Results page is intentionally a metrics overview; residual-shaped data in a Results `IntermediateState` is not used as a Results renderer input.
- The CARS curve remains an internal selection heuristic, not an unbiased nested-CV estimate.
- Manim export, new ML algorithms, and richer Unity physical NIR rendering remain P2 work.
