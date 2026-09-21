/* Reproducible interaction checks for the actual ML page DOM. Loaded only with ?harness. */
(function () {
  'use strict';

  const report = document.createElement('pre');
  report.id = 'ml-p1-harness-result';
  report.style.cssText = 'position:fixed;z-index:99999;left:4px;bottom:4px;max-width:95vw;max-height:45vh;overflow:auto;background:#111;color:#d7f7d7;padding:8px;font:11px monospace;white-space:pre-wrap';
  document.body.appendChild(report);

  const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
  async function waitFor(predicate, timeout) {
    const started = performance.now();
    while (performance.now() - started < (timeout || 6000)) {
      if (predicate()) return;
      await sleep(25);
    }
    throw new Error('timeout waiting for browser state');
  }
  function dispatchChange(element) { element.dispatchEvent(new Event('change', { bubbles: true })); }
  function stageButton(key) { return document.querySelector(`#ml-stage-tabs button[data-stage-key="${key}"]`); }
  function check(condition, message) { if (!condition) throw new Error(message); }
  let phase = 'bootstrap';

  async function run() {
    await waitFor(() => window.__FruitsimP1Debug && window.__FruitsimP1Debug.state.bundle);
    const debug = window.__FruitsimP1Debug;
    const state = debug.state;
    const results = [];
    phase = 'loaded';
    const pass = (name) => results.push({ name, pass: true });
    const runCheck = (name, fn) => { fn(); pass(name); };

    phase = 'select-comparison';
    stageButton('preprocessing').click();
    const comparison = document.querySelector('#ml-stage-controls select');
    const snv = Array.from(comparison.options).find((option) => option.textContent.startsWith('snv '));
    check(snv, 'SNV comparison option is unavailable');
    comparison.value = snv.value;
    dispatchChange(comparison);
    debug.playAnimation(false, false);
    await waitFor(() => state.animation.steps.length && state.animation.steps[0].event === 'highlight_sample');
    runCheck('preprocessing highlight_sample uses raw renderer', () => {
      check(state.animation.steps[0].state === state.bundle.stages.preprocessing.comparisons.find((item) => item.stage_run_id === snv.value).states[0], 'SNV teaching source is not selected comparison');
      check(document.querySelector('#ml-chart-error').hidden, 'preprocessing highlight_sample raised chart error');
    });
    debug.pauseAnimation();

    const sg15 = Array.from(comparison.options).find((option) => option.textContent.includes('sg15') && !option.textContent.includes('snv-after'));
    check(sg15, 'SG15 comparison option is unavailable');
    comparison.value = sg15.value;
    dispatchChange(comparison);
    runCheck('analysis selection keeps SG15 comparison', () => check(state.comparisonId === sg15.value, 'SG15 comparison was not selected'));

    phase = 'pipeline-source';
    document.querySelector('#ml-play-pipeline').click();
    await waitFor(() => state.animation.pipeline && state.stageKey === 'preprocessing' && state.animation.steps.length);
    runCheck('pipeline playback keeps ExperimentRun preprocessing', () => {
      check(state.animation.steps[0].state === state.bundle.stages.preprocessing.states[0], 'pipeline used selected comparison instead of experiment preprocessing');
      check(state.animation.steps[0].state !== state.bundle.stages.preprocessing.comparisons.find((item) => item.stage_run_id === sg15.value).states[0], 'pipeline comparison contaminated the active route');
    });
    debug.pauseAnimation();

    phase = 'cars-step-zero';
    debug.setStageByRunId('feature-analysis-cars');
    state.renderMode = 'analysis'; state.animation.index = 0; debug.render();
    runCheck('CARS step zero is iteration one', () => check(document.querySelector('#ml-chart').dataset.carsIteration === '1', `CARS iteration was ${document.querySelector('#ml-chart').dataset.carsIteration}`));

    phase = 'linked-wavelength';
    const feature = document.querySelector('#ml-feature-select');
    feature.value = '4'; dispatchChange(feature);
    const selectedLabel = `${state.selectedWavelengthNm.toFixed(0)} nm`;
    const linkedPages = [
      ['data_inspection', 'spectrum', 'spectrum'],
      ['preprocessing', 'overlay', 'overlay'],
      ['feature_analysis', 'pca', 'loadings'],
      ['feature_analysis', 'cars', 'iteration'],
      ['feature_selection', 'selection', 'selection'],
      ['modeling', 'validation', 'coefficients'],
    ];
    linkedPages.forEach(([stage, stageMode, chartMode]) => {
      state.stageKey = stage; state.stageMode = stageMode; state.chartMode = chartMode; state.renderMode = 'analysis'; state.animation.index = 0; debug.render();
      check(document.querySelector('#ml-legend').textContent.includes(selectedLabel), `selected wavelength missing on ${stage}/${chartMode}`);
    });
    pass('selected wavelength remains linked across raw/preprocessing/PCA/CARS/selection/model');

    phase = 'pause-resume';
    state.animation.pipeline = false;
    debug.setStageByRunId('preprocessing');
    state.renderMode = 'analysis'; state.animation.index = 0; debug.render();
    check(state.animation.steps[0] && state.animation.steps[0].event === 'morph_curve', 'pause/resume fixture is not a tween event');
    debug.pauseAnimation();
    state.renderMode = 'teaching'; state.animation.index = 0; state.animation.transitionProgress = 0.5; state.animation.playing = true;
    const pausedAt = state.animation.transitionProgress;
    document.querySelector('#ml-pause').click();
    await sleep(120);
    runCheck('pause preserves transition progress', () => {
      check(!state.animation.playing, 'pause did not stop playback');
      check(Math.abs(state.animation.transitionProgress - pausedAt) < 0.04, `pause moved transition from ${pausedAt} to ${state.animation.transitionProgress}`);
    });
    document.querySelector('#ml-pause').click();
    check(state.animation.playing && Math.abs(state.animation.transitionProgress - pausedAt) < 0.04, 'resume restarted transition from zero');
    pass('resume continues transition from paused progress');

    debug.pauseAnimation();
    report.textContent = JSON.stringify({ pass: true, checks: results }, null, 2);
    document.body.dataset.mlP1Harness = 'pass';
  }

  run().catch((error) => {
    report.textContent = JSON.stringify({ pass: false, phase, error: error.message, state: window.__FruitsimP1Debug && window.__FruitsimP1Debug.state && {
      stageKey: window.__FruitsimP1Debug.state.stageKey,
      pipeline: window.__FruitsimP1Debug.state.animation.pipeline,
      playing: window.__FruitsimP1Debug.state.animation.playing,
      index: window.__FruitsimP1Debug.state.animation.index,
      stepCount: window.__FruitsimP1Debug.state.animation.steps.length,
      transitionProgress: window.__FruitsimP1Debug.state.animation.transitionProgress,
      event: window.__FruitsimP1Debug.state.animation.steps[window.__FruitsimP1Debug.state.animation.index] && window.__FruitsimP1Debug.state.animation.steps[window.__FruitsimP1Debug.state.animation.index].event,
    }, chartError: document.querySelector('#ml-chart-error') && document.querySelector('#ml-chart-error').textContent }, null, 2);
    document.body.dataset.mlP1Harness = 'fail';
  });
}());
