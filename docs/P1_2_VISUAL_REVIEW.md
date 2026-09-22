# Fruitsim P1.2 Visual Review Checklist

This checklist is intentionally manual. Automated tests verify data identity,
scene structure, geometry bounds, browser interaction, and console-safe fallbacks;
they cannot decide whether a teaching figure is readable at presentation distance.

## A. Mode separation

- [ ] Analysis Mode still presents the dense Canvas evidence view.
- [ ] Teaching Mode is selected explicitly and does not silently replace Analysis Mode.
- [ ] Returning to Analysis Mode does not change the selected sample, wavelength, or active ExperimentRun.

## B. Teaching contract

- [ ] Every scene visibly shows Input, Operation, and Output object badges.
- [ ] Shapes are readable and use the `sample × feature` convention.
- [ ] The Chinese primary label and English subtitle agree.
- [ ] Each scene has a clear next-step explanation.

## C. Data Inspection

- [ ] The selected sample has the same identity in the spectrum view and the sample selector.
- [ ] The raw spectrum, heatmap, target distribution, and source warning are understandable without a separate lecture.
- [ ] `SYNTHETIC_TEACHING` and `not experimental evidence` are visible before interpretation.

## D. Preprocessing / SNV

- [ ] The selected raw spectrum is distinguishable from the other samples.
- [ ] Mean, centered spectrum, standard deviation, formula, and morph are legible in order.
- [ ] The axis range stays fixed while the curve morphs.
- [ ] No sample or wavelength identity changes during the animation.

## E. PCA diagnostic branch

- [ ] Matrix X, centered matrix Xc, and score plot read as one transformation.
- [ ] The selected sample remains highlighted in the score plot.
- [ ] Batch/group colors are categorical and do not imply a continuous numeric scale.
- [ ] The annotation explicitly says PCA is a diagnostic branch, not an SSC predictor.

## F. CARS and selection

- [ ] Wavelengths remain in their original left-to-right order at every iteration.
- [ ] Removed wavelengths fade; retained wavelengths remain visible.
- [ ] Relative importance is visually normalized, with no clipped marks.
- [ ] Internal RMSECV is labelled as a selection heuristic, not final generalization performance.
- [ ] Selection shows `X_selected = X[:, selected_indices]` without re-running CARS.

## G. Modeling and Results

- [ ] Validation is the default view; calibration is visibly a separate option.
- [ ] The selected sample is linked in prediction and residual views.
- [ ] Prediction collapse is described as a diagnostic signal and not assigned an unverified root cause.
- [ ] Results graph shows PCA and CARS as parallel children of preprocessing.

## H. Full pipeline playback

- [ ] Play, pause, previous, next, restart, timeline, and stage jump are usable.
- [ ] Pause/resume continues from the visible transition position.
- [ ] The active ExperimentRun preprocessing StageRun is used even after an Analysis comparison is selected.
- [ ] The final Results scene is reached without duplicate timers or console errors.

## I. Browser and presentation checks

- [ ] Test at the intended Ubuntu 22.04 Chrome viewport and at a projector-sized viewport.
- [ ] Chinese labels do not collide with English subtitles or object badges.
- [ ] SVG marks stay inside the plot area when resized.
- [ ] The WebGL simulation and the ML page can be switched without losing the selected sample contract.

## J. Evidence boundary

- [ ] The synthetic dataset manifest is available to the presenter.
- [ ] No visual claim is phrased as evidence from real fruit measurements.
- [ ] CARS RMSECV and validation metrics are not conflated.
