# Work Packages 4/5

## WP4 — Run visual analytics

The Python command below consumes a validated Run and writes figures beside
the data. It does not train a model or claim real SSC accuracy.

```bash
PYTHONPATH=python python -m fruitsim_ml visualize-run \
  --run-dir results/runs/<run_id> \
  --output results/runs/<run_id>/visualizations
```

The output includes:

- `pipeline_path.png`: source → spectra → preprocessing → PCA/features → model → evaluation → Unity;
- `spectra_heatmap.png`: sample × wavelength reflectance;
- `pca_scatter.png`: PCA projection colored by the synthetic proxy;
- `proxy_correlation_heatmap.png`: wavelength correlation with the proxy;
- `spectra_overview.png`: representative curves and mean curve;
- `visualization_manifest.json`: figure list, dimensions and warning.

## WP5 — Unity Run Viewer and development build

The canonical Unity project reads `manifest.json`, `status.json`,
`artifacts.json`, `data/samples.csv` and `data/spectra.csv` through the
file-only `RunArtifactLoader`. The runtime debug panel polls `status.json` and
shows the run identity, state, source, sample counts, artifact count, backend
and warnings. It does not start Python or C++ and does not mutate the Run.

Build the Linux Development Player with:

```bash
bash scripts/build_fruitsim_unity_linux.sh
```

The build is Development + Script Debugging + Profiler-connected. A later
release profile can reuse the same scene and contract while disabling those
debug flags. The build helper requires an activated Unity license and a usable
Package Manager; without those external prerequisites, the source-level C#
compile check remains the fallback verification.
