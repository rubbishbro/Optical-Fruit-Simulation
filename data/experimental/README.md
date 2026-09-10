# Experimental datasets

Experimental data is kept separate from the synthetic Golden Delicious demo. Each dataset directory
contains a `manifest.json` and, once data is received, canonical long-form tables under `processed/`:
`samples.csv` for sample-level metadata and `spectra.csv` for wavelength-level observations.

The canonical contract is schema version 2. `g`, refractive index and other IAD settings belong in
manifest provenance when they are global assumptions; they must not be copied into experimental
spectra rows unless the author measured them for that sample and wavelength.

Unknown values remain null or absent. No literature value, mean, default, or interpolation may be
used to make an experimental dataset look complete. Raw files may be retained locally under `raw/`
when redistribution is restricted; the manifest records their names and licensing restrictions.
