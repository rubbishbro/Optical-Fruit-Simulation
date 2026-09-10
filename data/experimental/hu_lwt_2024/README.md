# Hu et al. 2024 placeholder

Paper DOI: `10.1016/j.lwt.2024.116202`.

Status: `requested` / `pending`. No numerical Hu 2024 data is included in this repository. The
`raw/` and `processed/` directories are placeholders for files received under the author's
redistribution and licensing terms. When received, record the original filenames, restrictions,
units, and every conversion in `manifest.json`; do not infer missing `g`, refractive index, optical
channels, SSC, firmness, or wavelength samples.

Expected import flow:

1. Preserve the author's files under `raw/` only when redistribution permits it.
2. Use an explicit column mapping to write canonical `processed/samples.csv` and
   `processed/spectra.csv`.
3. Run `PYTHONPATH=python python -m fruitsim_ml validate-experimental --input data/experimental/hu_lwt_2024`.
