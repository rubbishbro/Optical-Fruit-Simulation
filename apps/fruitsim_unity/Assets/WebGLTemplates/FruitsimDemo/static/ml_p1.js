/* Fruitsim P1 teaching renderer. It consumes saved StageRun evidence only. */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const STAGE_LABELS = {
    data_inspection: 'Data Inspection',
    preprocessing: 'Preprocessing',
    feature_analysis: 'Feature Analysis',
    feature_selection: 'Feature Selection',
    modeling: 'Modeling',
    results: 'Results'
  };
  const PALETTE = { blue: '#205c86', blueLight: '#cfe0ec', orange: '#b45f38', gold: '#c78b2b', ink: '#17212b', muted: '#64717d', grid: '#dfe5e8', red: '#9b4b3d', green: '#3e7652' };
  const CONTRACT = window.FruitsimP1Contract;
  const state = {
    bundle: null,
    activeExperimentId: null,
    comparisonExperimentId: null,
    stageKey: 'data_inspection',
    stageMode: 'spectrum',
    comparisonId: null,
    selectedSampleId: null,
    selectedFeatureIndex: 0,
    selectedFeatureSourceIndex: 0,
    selectedWavelengthNm: null,
    pcaColorBy: 'target',
    renderMode: 'analysis',
    animation: { steps: [], index: 0, playing: false, timerId: null, rafId: null, transitionProgress: 1, pipeline: false, pipelineIndex: 0, plan: [] },
    canvasLogical: { width: 980, height: 520 },
    hitPoints: []
  };

  function decode(value) {
    if (value && typeof value === 'object' && Array.isArray(value.__ndarray__)) return value.__ndarray__;
    if (Array.isArray(value)) return value.map(decode);
    if (value && typeof value === 'object') {
      const output = {};
      Object.keys(value).forEach((key) => { output[key] = decode(value[key]); });
      return output;
    }
    return value;
  }

  function arr(value, label) {
    const output = decode(value);
    if (!Array.isArray(output)) throw new Error(`${label || 'array'} is unavailable in this StageRun bundle`);
    return output;
  }

  function number(value, fallback) {
    return Number.isFinite(Number(value)) ? Number(value) : fallback;
  }

  function flatMax(matrix) {
    return Math.max.apply(null, matrix.flat ? matrix.flat() : [].concat.apply([], matrix));
  }

  function format(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
    return Number(value).toFixed(digits === undefined ? 3 : digits);
  }

  function activeDescriptor() {
    // StageRun evidence in this bundle belongs to the active experiment. The
    // comparison selector intentionally drives the Results table only until
    // comparison-stage lazy loading is added; it must not relabel active data.
    return state.bundle.experiment;
  }

  function activeStage() {
    return state.bundle.stages[state.stageKey];
  }

  function activeStageForKey(key) {
    return state.bundle.stages[key];
  }

  function setText(id, value) { if ($(id)) $(id).textContent = value === undefined || value === null ? '-' : String(value); }

  function setSelectedFeature(index) {
    const wavelengths = state.bundle && state.bundle.source ? state.bundle.stages.data_inspection.visual.wavelengths : [];
    state.selectedFeatureIndex = Math.max(0, Number(index) || 0);
    state.selectedFeatureSourceIndex = state.selectedFeatureIndex;
    state.selectedWavelengthNm = wavelengths[state.selectedFeatureIndex] === undefined ? null : Number(wavelengths[state.selectedFeatureIndex]);
  }

  function canvasContext() {
    const canvas = $('ml-chart');
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width || 980));
    const height = 520;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.height = `${height}px`;
    const ctx = canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, width, height);
    state.canvasLogical = { width, height };
    return { ctx, width, height };
  }

  function plotArea(width, height) { return { left: 64, top: 30, right: width - 25, bottom: height - 58, width: width - 89, height: height - 88 }; }

  function extent(values, fallbackMin, fallbackMax) {
    const flat = values.flat ? values.flat() : [].concat.apply([], values);
    const finite = flat.map(Number).filter(Number.isFinite);
    if (!finite.length) return [fallbackMin, fallbackMax];
    let min = Math.min.apply(null, finite), max = Math.max.apply(null, finite);
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.06;
    return [min - pad, max + pad];
  }

  function xyMapper(area, xMin, xMax, yMin, yMax) {
    return {
      x: (value) => area.left + ((value - xMin) / (xMax - xMin)) * area.width,
      y: (value) => area.bottom - ((value - yMin) / (yMax - yMin)) * area.height
    };
  }

  function axes(ctx, area, xMin, xMax, yMin, yMax, xLabel, yLabel) {
    ctx.strokeStyle = PALETTE.grid; ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i += 1) {
      const x = area.left + area.width * i / 5;
      const y = area.bottom - area.height * i / 5;
      ctx.beginPath(); ctx.moveTo(x, area.top); ctx.lineTo(x, area.bottom); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(area.left, y); ctx.lineTo(area.right, y); ctx.stroke();
    }
    ctx.strokeStyle = '#52606c'; ctx.lineWidth = 1.1;
    ctx.beginPath(); ctx.moveTo(area.left, area.top); ctx.lineTo(area.left, area.bottom); ctx.lineTo(area.right, area.bottom); ctx.stroke();
    ctx.fillStyle = PALETTE.muted; ctx.font = '11px ui-monospace, monospace';
    ctx.fillText(format(xMin, 2), area.left - 5, area.bottom + 18); ctx.fillText(format(xMax, 2), area.right - 30, area.bottom + 18);
    ctx.fillText(format(yMin, 2), 8, area.bottom + 3); ctx.fillText(format(yMax, 2), 8, area.top + 3);
    ctx.font = '12px Arial, sans-serif'; ctx.fillStyle = PALETTE.ink; ctx.fillText(xLabel || '', area.left + area.width / 2 - 35, area.bottom + 42);
    ctx.save(); ctx.translate(17, area.top + area.height / 2 + 30); ctx.rotate(-Math.PI / 2); ctx.fillText(yLabel || '', 0, 0); ctx.restore();
  }

  function title(ctx, text, subtitle) {
    ctx.fillStyle = PALETTE.ink; ctx.font = '600 15px Arial, sans-serif'; ctx.fillText(text, 64, 20);
    if (subtitle) { ctx.fillStyle = PALETTE.muted; ctx.font = '11px Arial, sans-serif'; ctx.fillText(subtitle, 64, 39); }
  }

  function line(ctx, points, mapper, color, width, alpha) {
    if (!points || !points.length) return;
    ctx.save(); ctx.globalAlpha = alpha === undefined ? 1 : alpha; ctx.strokeStyle = color; ctx.lineWidth = width || 1.5; ctx.beginPath();
    points.forEach((point, index) => { const x = mapper.x(point[0]), y = mapper.y(point[1]); if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
    ctx.stroke(); ctx.restore();
  }

  function legend(items) {
    $('ml-legend').innerHTML = (items || []).map((item) => `<span><i style="background:${item.color}"></i>${item.label}</span>`).join('');
  }

  function drawSpectrum(matrixBefore, matrixAfter, wavelengths, sampleIndex, mode, caption) {
    const visual = canvasContext(), ctx = visual.ctx, area = plotArea(visual.width, visual.height);
    const before = arr(matrixBefore, 'before spectrum'), after = matrixAfter ? arr(matrixAfter, 'after spectrum') : null, x = arr(wavelengths, 'wavelengths');
    const rows = before.length, selected = Math.max(0, Math.min(rows - 1, sampleIndex));
    const values = before.concat(after || []).flat(); const yRange = extent(values, -1, 1); const mapper = xyMapper(area, Math.min.apply(null, x), Math.max.apply(null, x), yRange[0], yRange[1]);
    axes(ctx, area, Math.min.apply(null, x), Math.max.apply(null, x), yRange[0], yRange[1], 'Wavelength (nm)', 'Signal'); title(ctx, caption || 'Spectrum', 'selected sample is drawn with a dark stroke');
    if (mode === 'overlay' || !after) {
      before.forEach((row, index) => line(ctx, x.map((value, i) => [value, row[i]]), mapper, index === selected ? PALETTE.ink : PALETTE.blueLight, index === selected ? 2.6 : 0.7, index === selected ? 1 : 0.65));
      if (after) line(ctx, x.map((value, i) => [value, after[selected][i]]), mapper, PALETTE.orange, 2.2);
    } else if (mode === 'difference') {
      const diff = after[selected].map((value, i) => value - before[selected][i]);
      const dRange = extent(diff, -1, 1), dMapper = xyMapper(area, Math.min.apply(null, x), Math.max.apply(null, x), dRange[0], dRange[1]); axes(ctx, area, Math.min.apply(null, x), Math.max.apply(null, x), dRange[0], dRange[1], 'Wavelength (nm)', 'After − before');
      line(ctx, x.map((value, i) => [value, diff[i]]), dMapper, PALETTE.orange, 2.2);
    } else if (mode === 'heatmap') drawHeatmap(ctx, area, after || before, x, 'Sample × wavelength');
    else {
      const mean = after[selected].reduce((sum, value) => sum + value, 0) / after[selected].length;
      const std = Math.sqrt(after[selected].reduce((sum, value) => sum + (value - mean) ** 2, 0) / after[selected].length);
      before.forEach((row, index) => line(ctx, x.map((value, i) => [value, row[i]]), mapper, index === selected ? PALETTE.blue : PALETTE.blueLight, index === selected ? 2.4 : 0.7, index === selected ? 1 : 0.35));
      line(ctx, x.map((value, i) => [value, after[selected][i]]), mapper, PALETTE.orange, 2.3); ctx.fillStyle = PALETTE.muted; ctx.font = '11px ui-monospace,monospace'; ctx.fillText(`selected mean ${format(mean)} · std ${format(std)}`, area.left, visual.height - 12);
    }
    state.hitPoints = [];
    legend(after ? [{ color: PALETTE.blue, label: 'before / raw' }, { color: PALETTE.orange, label: 'after / selected sample' }] : [{ color: PALETTE.blue, label: 'spectra' }]);
  }

  function colorScale(value, min, max) { const t = Math.max(0, Math.min(1, (value - min) / (max - min || 1))); return `rgb(${Math.round(34 + 200 * t)},${Math.round(83 + 110 * t)},${Math.round(130 - 70 * t)})`; }

  function drawHeatmap(ctx, area, matrix, wavelengths, caption) {
    const rows = arr(matrix, 'heatmap matrix'), cols = arr(wavelengths, 'wavelengths').length; const flat = rows.flat(); const min = Math.min.apply(null, flat), max = Math.max.apply(null, flat); const cellW = area.width / cols, cellH = area.height / rows.length;
    rows.forEach((row, r) => row.forEach((value, c) => { ctx.fillStyle = colorScale(value, min, max); ctx.fillRect(area.left + c * cellW, area.top + r * cellH, Math.ceil(cellW) + 1, Math.ceil(cellH) + 1); }));
    ctx.strokeStyle = '#52606c'; ctx.strokeRect(area.left, area.top, area.width, area.height); ctx.fillStyle = PALETTE.ink; ctx.font = '600 15px Arial, sans-serif'; ctx.fillText(caption, 64, 20); ctx.fillStyle = PALETTE.muted; ctx.font = '11px ui-monospace,monospace'; ctx.fillText(`${rows.length} samples × ${cols} wavelengths`, area.left, area.bottom + 28);
  }

  function drawData(mode) {
    const visual = activeStage().visual, sampleIndex = visual.sample_ids.indexOf(state.selectedSampleId);
    if (mode === 'heatmap') { const c = canvasContext(); drawHeatmap(c.ctx, plotArea(c.width, c.height), arr(visual.spectra, 'spectra'), arr(visual.wavelengths, 'wavelengths'), 'Raw sample × wavelength'); legend([{ color: PALETTE.blue, label: 'low signal' }, { color: PALETTE.orange, label: 'high signal' }]); return; }
    if (mode === 'target') { drawTargetDistribution(visual); return; }
    drawSpectrum(visual.spectra, null, visual.wavelengths, sampleIndex, 'overlay', 'Raw spectra');
  }

  function drawTargetDistribution(visual) {
    const target = arr(visual.target, 'target distribution'), split = arr(visual.split || [], 'target split'), c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height), range = extent(target, 0, 1), bins = 8, counts = { calibration: Array(bins).fill(0), validation: Array(bins).fill(0) }, step = (range[1] - range[0]) / bins;
    target.forEach((value, index) => { const bucket = Math.max(0, Math.min(bins - 1, Math.floor((value - range[0]) / step))); const key = split[index] === 'validation' ? 'validation' : 'calibration'; counts[key][bucket] += 1; });
    const maxCount = Math.max.apply(null, counts.calibration.concat(counts.validation).concat([1])); axes(ctx, area, range[0], range[1], 0, maxCount * 1.15, 'Target SSC (°Brix)', 'Sample count'); title(ctx, 'Target distribution', 'calibration and validation are shown separately; this is not a performance chart'); for (let index = 0; index < bins; index += 1) { const x0 = area.left + area.width * index / bins, width = area.width / bins * .38; ctx.fillStyle = PALETTE.blue; ctx.fillRect(x0, area.bottom - counts.calibration[index] / (maxCount * 1.15) * area.height, width, counts.calibration[index] / (maxCount * 1.15) * area.height); ctx.fillStyle = PALETTE.orange; ctx.fillRect(x0 + width, area.bottom - counts.validation[index] / (maxCount * 1.15) * area.height, width, counts.validation[index] / (maxCount * 1.15) * area.height); } legend([{ color: PALETTE.blue, label: 'calibration' }, { color: PALETTE.orange, label: 'validation' }]);
  }

  function drawPreprocessing(mode) {
    const comparison = selectedPreprocessingComparison();
    const visual = (comparison && comparison.visual && comparison.visual.before) ? comparison.visual : activeStage().visual, sampleIndex = visual.sample_ids.indexOf(state.selectedSampleId);
    if (!visual || !visual.before || !visual.after || !visual.wavelengths) { drawData('spectrum'); return; }
    if (mode === 'heatmap') { const c = canvasContext(); drawHeatmap(c.ctx, plotArea(c.width, c.height), arr(visual.after, 'after'), arr(visual.wavelengths, 'wavelengths'), `${comparison.method_specs.map((spec) => spec.invocation_id).join(' → ')} heatmap`); legend([{ color: PALETTE.blue, label: 'low signal' }, { color: PALETTE.orange, label: 'high signal' }]); return; }
    drawSpectrum(visual.before, visual.after, visual.wavelengths, sampleIndex, mode === 'difference' ? 'difference' : 'overlay', `${comparison.method_specs.map((spec) => spec.method_id).join(' → ')} · ${comparison.method_specs.map((spec) => JSON.stringify(spec.parameters)).join(' ')}`);
  }

  function selectedPreprocessingComparison() {
    const stage = activeStage(), comparisons = stage.comparisons || [];
    return comparisons.find((item) => item.stage_run_id === state.comparisonId) || comparisons.find((item) => item.method_specs.some((spec) => spec.invocation_id === 'snv')) || comparisons.find((item) => item.visual && item.visual.before) || { stage_run_id: stage.stage_run_id, method_specs: stage.method_specs || [], visual: stage.visual, states: stage.states || [] };
  }

  function selectedPreprocessingVisual() {
    const comparison = selectedPreprocessingComparison();
    return comparison && comparison.visual && comparison.visual.wavelengths ? comparison.visual : activeStage().visual;
  }

  function drawPreprocessEvent(event, item, progress) {
    if (!item || !item.arrays) { drawPreprocessing('overlay'); return; }
    const raw = item.arrays.raw, target = item.arrays.normalized || item.arrays.smoothed, selectedVisual = selectedPreprocessingVisual(), x = selectedVisual.wavelengths, sampleIndex = selectedVisual.sample_ids.indexOf(state.selectedSampleId), tween = Math.max(0, Math.min(1, progress === undefined ? 1 : progress));
    if (!raw || !target) { drawPreprocessing('overlay'); return; }
    if (event === 'show_mean' || event === 'show_std') {
      const before = arr(raw, 'SNV raw'), c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height), xValues = arr(x, 'wavelengths'), row = before[sampleIndex], mean = arr(item.arrays.sample_mean, 'sample means')[sampleIndex], std = arr(item.arrays.sample_std, 'sample stds')[sampleIndex], yRange = extent(before, -1, 1), mapper = xyMapper(area, Math.min(...xValues), Math.max(...xValues), yRange[0], yRange[1]); axes(ctx, area, Math.min(...xValues), Math.max(...xValues), yRange[0], yRange[1], 'Wavelength (nm)', 'Raw signal'); title(ctx, event === 'show_mean' ? 'SNV teaching step · sample mean μ' : 'SNV teaching step · sample std σ', 'the highlighted sample is the same selected sample used by the other pages'); line(ctx, xValues.map((value, i) => [value, row[i]]), mapper, PALETTE.blue, 2.4); ctx.strokeStyle = PALETTE.orange; ctx.setLineDash([5, 4]); ctx.beginPath(); ctx.moveTo(area.left, mapper.y(mean)); ctx.lineTo(area.right, mapper.y(mean)); ctx.stroke(); if (event === 'show_std') { ctx.strokeStyle = PALETTE.gold; ctx.beginPath(); ctx.moveTo(area.left, mapper.y(mean + std)); ctx.lineTo(area.right, mapper.y(mean + std)); ctx.moveTo(area.left, mapper.y(mean - std)); ctx.lineTo(area.right, mapper.y(mean - std)); ctx.stroke(); } ctx.setLineDash([]); legend([{ color: PALETTE.blue, label: 'raw selected sample' }, { color: PALETTE.orange, label: 'mean μ' }, { color: PALETTE.gold, label: event === 'show_std' ? 'μ ± σ' : 'sample scale' }]); return;
    }
    if (event === 'show_formula') { drawSpectrum(raw, target, x, sampleIndex, 'overlay', 'Preprocessing teaching step · formula'); const c = $('ml-chart').getContext('2d'); c.fillStyle = PALETTE.orange; c.font = '600 20px ui-monospace,monospace'; c.fillText(item.values && item.values.formula ? item.values.formula : 'x′ = (x − μ) / σ', 78, 78); return; }
    if (event === 'morph_curve') {
      const intermediate = CONTRACT.interpolateMatrix(arr(raw, 'preprocessing raw'), arr(target, 'preprocessing target'), tween);
      drawSpectrum(intermediate, null, x, sampleIndex, 'overlay', `Preprocessing teaching step · raw → output · ${Math.round(tween * 100)}%`);
      return;
    }
    drawSpectrum(raw, target, x, sampleIndex, 'overlay', 'Preprocessing teaching step · raw spectrum');
  }

  function drawPca(mode) {
    const visual = currentStageObject().visual; const scores = arr(visual.scores, 'PCA scores'); const sampleIds = arr(visual.sample_ids, 'PCA sample ids');
    if (mode === 'variance') { const c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height), values = arr(visual.explained_variance_ratio, 'explained variance'); const yRange = [0, Math.max.apply(null, values) * 1.2]; axes(ctx, area, 1, values.length, yRange[0], yRange[1], 'Principal component', 'Explained variance ratio'); title(ctx, 'PCA explained variance', 'the bar height is variance accounted for by each component'); values.forEach((value, i) => { ctx.fillStyle = i === 0 ? PALETTE.blue : PALETTE.blueLight; ctx.fillRect(area.left + area.width * (i + .15) / values.length, area.bottom - (value / yRange[1]) * area.height, area.width * .7 / values.length, (value / yRange[1]) * area.height); ctx.fillStyle = PALETTE.ink; ctx.fillText(`PC${i + 1}`, area.left + area.width * (i + .35) / values.length, area.bottom + 18); }); legend([{ color: PALETTE.blue, label: 'explained variance ratio' }]); return; }
    if (mode === 'loadings') { const c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height), loadings = arr(visual.loadings, 'PCA loadings'), x = arr(visual.wavelengths, 'wavelengths'), yRange = extent(loadings, -1, 1), mapper = xyMapper(area, Math.min(...x), Math.max(...x), yRange[0], yRange[1]); axes(ctx, area, Math.min(...x), Math.max(...x), yRange[0], yRange[1], 'Wavelength (nm)', 'Loading'); title(ctx, 'PCA loading plot', 'which wavelengths contribute to each principal direction'); loadings[0].forEach((_, component) => line(ctx, x.map((value, i) => [value, loadings[i][component]]), mapper, component === 0 ? PALETTE.blue : component === 1 ? PALETTE.orange : PALETTE.gold, 1.8)); if (state.selectedWavelengthNm !== null) { ctx.strokeStyle = PALETTE.red; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(mapper.x(state.selectedWavelengthNm), area.top); ctx.lineTo(mapper.x(state.selectedWavelengthNm), area.bottom); ctx.stroke(); ctx.setLineDash([]); } legend(loadings[0].map((_, i) => ({ color: i === 0 ? PALETTE.blue : i === 1 ? PALETTE.orange : PALETTE.gold, label: `PC${i + 1} loading` })).concat([{ color: PALETTE.red, label: `selected ${format(state.selectedWavelengthNm, 0)} nm` }])); return; }
    const xValues = scores.map((row) => row[0]), yValues = scores.map((row) => row[1] || 0), xRange = extent(xValues, -1, 1), yRange = extent(yValues, -1, 1), c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height), mapper = xyMapper(area, xRange[0], xRange[1], yRange[0], yRange[1]); axes(ctx, area, xRange[0], xRange[1], yRange[0], yRange[1], 'PC1 score', 'PC2 score'); title(ctx, 'PCA score plot', `click a point · color by ${state.pcaColorBy}`); const target = arr(visual.target, 'PCA target'), groups = visual.groups || [], colorValues = state.pcaColorBy === 'batch' && groups.length ? groups.map((value) => String(value).split('').reduce((sum, char) => sum + char.charCodeAt(0), 0)) : target, tRange = extent(colorValues, 0, 1); state.hitPoints = []; scores.forEach((row, i) => { const px = mapper.x(row[0]), py = mapper.y(row[1] || 0), selected = sampleIds[i] === state.selectedSampleId; state.hitPoints.push({ x: px, y: py, sampleId: sampleIds[i] }); ctx.beginPath(); ctx.fillStyle = selected ? PALETTE.orange : colorScale(colorValues[i], tRange[0], tRange[1]); ctx.strokeStyle = selected ? PALETTE.ink : '#fff'; ctx.lineWidth = selected ? 2.2 : 1; ctx.arc(px, py, selected ? 6 : 4.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }); legend([{ color: PALETTE.blue, label: state.pcaColorBy === 'batch' ? 'low batch/group code' : 'low target' }, { color: PALETTE.orange, label: 'selected sample' }]);
  }

  function drawCars(mode, stepIndex, progress) {
    const visual = currentStageObject().visual, x = arr(visual.wavelengths, 'wavelengths'), states = visual.states || [], stateIndex = Math.max(0, Math.min(states.length - 1, stepIndex || states.length - 1)), tween = Math.max(0, Math.min(1, progress === undefined ? 1 : progress));
    if (mode === 'rmsecv') { const c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height), values = arr(visual.rmsecv_progression, 'RMSECV progression'), xRange = [1, values.length], yRange = extent(values, 0, 1), mapper = xyMapper(area, xRange[0], xRange[1], yRange[0], yRange[1]); axes(ctx, area, xRange[0], xRange[1], yRange[0], yRange[1], 'CARS iteration', 'Internal RMSECV'); title(ctx, 'CARS internal selection heuristic', 'lower is preferred within this selection run; not nested-CV generalization error'); line(ctx, values.map((value, i) => [i + 1, value]), mapper, PALETTE.orange, 2.4); values.forEach((value, i) => { ctx.fillStyle = PALETTE.orange; ctx.beginPath(); ctx.arc(mapper.x(i + 1), mapper.y(value), 4, 0, Math.PI * 2); ctx.fill(); }); legend([{ color: PALETTE.orange, label: 'internal RMSECV heuristic' }]); return; }
    const current = states.length ? arr(states[stateIndex].arrays.current_indices, 'current indices') : arr(visual.selected_indices, 'selected indices');
    const selected = states.length ? arr(states[stateIndex].arrays.retained_indices, 'retained indices') : arr(visual.selected_indices, 'selected indices');
    const coefficients = states.length ? arr(states[stateIndex].arrays.coefficients, 'coefficients') : [];
    const c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height), yRange = [0, 1], mapper = xyMapper(area, Math.min(...x), Math.max(...x), yRange[0], yRange[1]); axes(ctx, area, Math.min(...x), Math.max(...x), yRange[0], yRange[1], 'Wavelength (nm)', 'retained / importance'); title(ctx, `CARS iteration ${stateIndex + 1}`, `${selected.length} wavelengths retained; removed wavelengths fade out`); const currentSet = new Set(current), retainedSet = new Set(selected); x.forEach((value, i) => { const isCurrent = currentSet.has(i), keep = retainedSet.has(i), removed = isCurrent && !keep, opacity = isCurrent ? CONTRACT.fadeOpacity(removed, tween) : 0.08, coefficient = states.length ? CONTRACT.mapCarsCoefficient(current, coefficients, i) : null, importance = coefficient === null ? 0 : Math.abs(coefficient); ctx.save(); ctx.globalAlpha = opacity; ctx.strokeStyle = keep ? PALETTE.blue : '#cbd2d6'; ctx.lineWidth = keep ? 2.5 : 1.3; ctx.beginPath(); ctx.moveTo(mapper.x(value), area.bottom); ctx.lineTo(mapper.x(value), area.bottom - Math.min(.92, keep ? .18 + importance * 2.4 : .04) * area.height); ctx.stroke(); ctx.restore(); }); legend([{ color: PALETTE.blue, label: 'retained wavelength' }, { color: '#cbd2d6', label: 'removed wavelength (fade)' }]);
  }

  function drawSelection() {
    const visual = activeStage().visual, x = arr(visual.wavelengths, 'wavelengths'), selected = new Set(arr(visual.selected_indices, 'selected indices')); const c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height), mapper = xyMapper(area, Math.min(...x), Math.max(...x), 0, 1); axes(ctx, area, Math.min(...x), Math.max(...x), 0, 1, 'Wavelength (nm)', 'selection state'); title(ctx, 'Selected wavelengths entering the model', `${visual.original_feature_count} original → ${visual.selected_feature_count} selected; click a bar to highlight it`); x.forEach((value, i) => { const keep = selected.has(i), active = i === state.selectedFeatureIndex; ctx.fillStyle = keep ? (active ? PALETTE.orange : PALETTE.blue) : '#dfe4e7'; ctx.fillRect(mapper.x(value) - Math.max(1, area.width / x.length * .32), keep ? mapper.y(.85) : mapper.y(.14), Math.max(2, area.width / x.length * .64), keep ? area.height * .7 : area.height * .08); }); legend([{ color: PALETTE.blue, label: 'selected feature' }, { color: '#dfe4e7', label: 'removed feature' }, { color: PALETTE.orange, label: 'selected wavelength' }]); state.hitPoints = x.map((value, i) => ({ x: mapper.x(value), y: area.bottom, featureIndex: i }));
  }

  function drawModel(mode, progress) {
    const visual = activeStage().visual, yTrue = arr(visual.y_true, 'true target'), yPred = arr(visual.y_pred, 'predictions'), residuals = arr(visual.residuals, 'residuals'), split = arr(visual.split, 'split'), ids = arr(visual.sample_ids, 'sample ids'); let indices = split.map((value, i) => value === 'validation' ? i : -1).filter((value) => value >= 0); if (state.stageMode === 'calibration') indices = split.map((value, i) => value === 'calibration' ? i : -1).filter((value) => value >= 0);
    const c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height); state.hitPoints = [];
    if (mode === 'residual') { const xRange = extent(indices.map((i) => yTrue[i]), 0, 1), yRange = extent(indices.map((i) => residuals[i]), -1, 1), mapper = xyMapper(area, xRange[0], xRange[1], yRange[0], yRange[1]); axes(ctx, area, xRange[0], xRange[1], yRange[0], yRange[1], 'True target (°Brix)', 'Prediction residual'); title(ctx, `PLSR residuals · ${state.stageMode}`, 'residual = prediction − true; zero is the reference line'); ctx.strokeStyle = '#52606c'; ctx.beginPath(); ctx.moveTo(area.left, mapper.y(0)); ctx.lineTo(area.right, mapper.y(0)); ctx.stroke(); indices.forEach((i) => { const px = mapper.x(yTrue[i]), py = mapper.y(residuals[i]), selected = ids[i] === state.selectedSampleId; state.hitPoints.push({ x: px, y: py, sampleId: ids[i] }); ctx.beginPath(); ctx.fillStyle = selected ? PALETTE.orange : PALETTE.blue; ctx.arc(px, py, selected ? 6 : 4.5, 0, Math.PI * 2); ctx.fill(); }); legend([{ color: PALETTE.blue, label: `${state.stageMode} residual` }, { color: PALETTE.orange, label: 'selected sample' }]); return; }
    if (mode === 'scores') { const scores = arr(visual.scores, 'PLSR scores'), scoreIds = arr(visual.scores_sample_ids || visual.sample_ids, 'PLSR score sample ids'), scoreById = new Map(scoreIds.map((id, index) => [id, scores[index]])), rows = ids.map((id) => scoreById.get(id)).filter(Boolean), xVals = rows.map((row) => row[0]), yVals = rows.map((row) => row[1] || 0), xRange = extent(xVals, -1, 1), yRange = extent(yVals, -1, 1), mapper = xyMapper(area, xRange[0], xRange[1], yRange[0], yRange[1]); axes(ctx, area, xRange[0], xRange[1], yRange[0], yRange[1], 'latent score 1', 'latent score 2'); title(ctx, 'PLSR latent scores', 'validation points are projected into the calibration-fitted latent space'); ids.forEach((id, i) => { const row = scoreById.get(id); if (!row || split[i] === 'unused') return; const selected = id === state.selectedSampleId; ctx.beginPath(); ctx.fillStyle = split[i] === 'validation' ? PALETTE.orange : PALETTE.blue; ctx.arc(mapper.x(row[0]), mapper.y(row[1] || 0), selected ? 6 : 4, 0, Math.PI * 2); ctx.fill(); }); legend([{ color: PALETTE.blue, label: 'calibration scores' }, { color: PALETTE.orange, label: 'validation projection' }]); return; }
    if (mode === 'coefficients') { const coefficients = arr(visual.coefficients, 'PLSR coefficients'), sourceIndices = arr(visual.coefficient_source_indices, 'coefficient source indices'), wavelengths = arr(visual.wavelengths, 'wavelengths'), points = coefficients.map((value, i) => [wavelengths[sourceIndices[i]] === undefined ? i : wavelengths[sourceIndices[i]], value]), xRange = extent(points.map((point) => point[0]), 0, 1), yRange = extent(coefficients, -1, 1), mapper = xyMapper(area, xRange[0], xRange[1], yRange[0], yRange[1]); axes(ctx, area, xRange[0], xRange[1], yRange[0], yRange[1], 'original wavelength (nm)', 'coefficient'); title(ctx, 'PLSR regression coefficients', 'coefficient index is mapped back to the original wavelength'); line(ctx, points, mapper, PALETTE.blue, 2); if (state.selectedWavelengthNm !== null) { ctx.strokeStyle = PALETTE.red; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(mapper.x(state.selectedWavelengthNm), area.top); ctx.lineTo(mapper.x(state.selectedWavelengthNm), area.bottom); ctx.stroke(); ctx.setLineDash([]); } state.hitPoints = points.map((point, i) => ({ x: mapper.x(point[0]), y: mapper.y(point[1]), featureIndex: sourceIndices[i] })); legend([{ color: PALETTE.blue, label: 'coefficient' }, { color: PALETTE.red, label: `selected ${format(state.selectedWavelengthNm, 0)} nm` }]); return; }
    const indicesForPlot = indices.length ? indices : split.map((_, i) => i); const xRange = extent(indicesForPlot.map((i) => yTrue[i]), 0, 1), yRange = extent(indicesForPlot.map((i) => yPred[i]), 0, 1), mapper = xyMapper(area, xRange[0], xRange[1], yRange[0], yRange[1]), tween = Math.max(0, Math.min(1, progress === undefined ? 1 : progress)), baseline = yTrue.reduce((sum, value) => sum + value, 0) / Math.max(1, yTrue.length); axes(ctx, area, xRange[0], xRange[1], yRange[0], yRange[1], 'True target (°Brix)', 'Predicted target (°Brix)'); title(ctx, `Predicted versus true · ${state.stageMode}`, `prediction points enter continuously · ${Math.round(tween * 100)}%`); ctx.strokeStyle = PALETTE.muted; ctx.setLineDash([5, 4]); ctx.beginPath(); ctx.moveTo(mapper.x(xRange[0]), mapper.y(xRange[0])); ctx.lineTo(mapper.x(xRange[1]), mapper.y(xRange[1])); ctx.stroke(); ctx.setLineDash([]); indicesForPlot.forEach((i) => { const predicted = baseline + (yPred[i] - baseline) * tween, px = mapper.x(yTrue[i]), py = mapper.y(predicted), selected = ids[i] === state.selectedSampleId; state.hitPoints.push({ x: px, y: py, sampleId: ids[i] }); ctx.beginPath(); ctx.globalAlpha = .25 + .75 * tween; ctx.fillStyle = selected ? PALETTE.orange : (split[i] === 'validation' ? PALETTE.blue : PALETTE.blueLight); ctx.strokeStyle = selected ? PALETTE.ink : '#fff'; ctx.lineWidth = selected ? 2 : 1; ctx.arc(px, py, selected ? 6 : 4.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.globalAlpha = 1; }); legend([{ color: PALETTE.blue, label: state.stageMode }, { color: PALETTE.orange, label: 'selected sample' }, { color: 'transparent', label: 'dashed ideal 1:1' }]);
  }

  function drawResults() { const stage = activeStage(), metrics = stage.visual.metrics || {}, c = canvasContext(), ctx = c.ctx, area = plotArea(c.width, c.height); title(ctx, 'Experiment result summary', 'final metrics are validation-only; model selection used calibration CV RMSE'); ctx.fillStyle = PALETTE.ink; ctx.font = '600 22px ui-monospace,monospace'; ctx.fillText(`RMSE  ${format(metrics.rmse)}`, area.left, area.top + 45); ctx.fillText(`MAE   ${format(metrics.mae)}`, area.left, area.top + 95); ctx.fillText(`R²    ${format(metrics.r2)}`, area.left, area.top + 145); ctx.fillText(`CV RMSE ${format(metrics.cv_rmse)}`, area.left, area.top + 195); ctx.fillStyle = PALETTE.muted; ctx.font = '13px Arial, sans-serif'; ctx.fillText(`bias ${format(metrics.bias)} · n=${metrics.sample_count || '-'} · feature count=${metrics.feature_count || '-'}`, area.left, area.top + 245); const ratio = stage.visual.collapse_ratio; ctx.fillStyle = ratio !== null && ratio < .35 ? PALETTE.red : PALETTE.green; ctx.font = '600 17px Arial, sans-serif'; ctx.fillText(`prediction collapse ratio = ${format(ratio)}`, area.left, area.top + 300); ctx.fillStyle = PALETTE.muted; ctx.font = '12px Arial, sans-serif'; ctx.fillText(ratio !== null && ratio < .35 ? 'Low prediction variance: possible information insufficiency; cause is not inferred automatically.' : 'Prediction variance is not flagged by the simple diagnostic threshold.', area.left, area.top + 330); legend([{ color: PALETTE.blue, label: 'validation metrics' }]); }

  const RENDERERS = {
    show_spectrum: (step) => drawData('spectrum', step),
    highlight_sample: (step) => drawData('spectrum', step),
    morph_curve: (step, context) => drawPreprocessEvent(step.event, step.state, context.progress),
    show_mean: (step) => drawPreprocessEvent(step.event, step.state, 1),
    show_std: (step) => drawPreprocessEvent(step.event, step.state, 1),
    show_formula: (step) => drawPreprocessEvent(step.event, step.state, 1),
    project_points: () => drawPca('scores'),
    highlight_loading: () => drawPca('loadings'),
    remove_features: (step, context) => drawCars('iteration', context.stepIndex, context.progress),
    select_features: () => drawSelection(),
    connect_feature_to_prediction: () => drawModel('scores', 1),
    show_prediction: (step, context) => drawModel('prediction', context.progress),
    show_residual: () => drawModel('residual', 1),
    show_metric: () => drawResults()
  };

  function stageItems() { const stage = activeStage(); if (state.stageKey === 'feature_analysis') return Array.isArray(stage) ? stage : []; return stage ? [stage] : []; }
  function currentStageObject() { if (state.stageKey !== 'feature_analysis') return state.bundle.stages[state.stageKey]; const list = stageItems(); return list.find((item) => item.method_specs.some((spec) => spec.invocation_id === state.stageMode)) || list[0]; }
  function stageByRunId(stageRunId) {
    const keys = Object.keys(state.bundle.stages || {});
    for (const key of keys) {
      const value = state.bundle.stages[key];
      const items = Array.isArray(value) ? value : [value];
      const found = items.find((item) => item && item.stage_run_id === stageRunId);
      if (found) return { key, stage: found };
    }
    return null;
  }

  function setStageByRunId(stageRunId) {
    const resolved = stageByRunId(stageRunId);
    if (!resolved) throw new Error(`StageRun is not available in bundle: ${stageRunId}`);
    state.stageKey = resolved.key;
    state.stageMode = resolved.key === 'feature_analysis' ? resolved.stage.method_specs[0].invocation_id : resolved.key === 'modeling' ? 'validation' : resolved.key === 'preprocessing' ? 'overlay' : 'spectrum';
    state.chartMode = resolved.key === 'feature_analysis' && resolved.stage.method_specs[0].method_id === 'pca' ? 'scores' : resolved.key === 'feature_analysis' ? 'iteration' : resolved.key === 'modeling' ? 'prediction' : 'default';
  }

  function eventSteps(stage) {
    if (!stage) return [];
    // Results is an overview StageRun. Always render its saved metrics during
    // playback, even if the summary IntermediateState carries a residual-like
    // event from an upstream producer.
    if (stage.stage === 'results') return [{ event: 'show_metric', state: { values: {} }, narration: narration('show_metric', {}) }];
    const steps = [];
    const sourceStage = stage.stage === 'preprocessing' ? selectedPreprocessingComparison() : stage;
    const states = sourceStage && sourceStage.states ? sourceStage.states : [];
    states.forEach((item) => {
      const event = item.event || 'unknown';
      if (stage.stage === 'preprocessing' && event === 'show_formula') {
        steps.push({ event: 'highlight_sample', state: item, narration: 'Step 1 · 原始光谱：先固定同一个 sample，后续所有页面沿用它。' });
        steps.push({ event: 'show_mean', state: item, narration: 'Step 2 · 对每个 sample 计算自己的光谱均值 μ。' });
        steps.push({ event: 'show_std', state: item, narration: 'Step 3 · 对每个 sample 计算自己的标准差 σ。' });
        steps.push({ event: 'show_formula', state: item, narration: `Step 4 · ${item.values && item.values.formula ? item.values.formula : 'x′ = (x − μ) / σ'}` });
        steps.push({ event: 'morph_curve', state: item, narration: 'Step 5 · 使用同一个 IntermediateState，把曲线从 raw morph 到 normalized。' });
      } else if (stage.stage === 'modeling' && event === 'connect_feature_to_prediction') {
        steps.push({ event: 'connect_feature_to_prediction', state: item, narration: narration('connect_feature_to_prediction', item.values || {}) });
        steps.push({ event: 'show_prediction', state: item, narration: narration('show_prediction', item.values || {}) });
        steps.push({ event: 'show_residual', state: item, narration: narration('show_residual', item.values || {}) });
      } else steps.push({ event, state: item, narration: narration(event, item.values || {}) });
    });
    if (!steps.length) steps.push({ event: 'show_metric', state: { values: {} }, narration: '当前 Stage 没有可播放的 IntermediateState；以下展示已保存结果。' });
    return steps;
  }

  function narration(event, values) { const table = { highlight_sample: '固定一个 sample，观察它在不同阶段的对应位置。', morph_curve: '曲线形状发生变化，但 sample id 与 wavelength axis 保持不变。', show_mean: '均值是该 sample 的基线位置，不是跨样本的全局均值。', show_std: '标准差描述该 sample 沿波长方向的尺度。', show_formula: values.formula || '显示该方法的计算关系。', project_points: '高维光谱被投影到少数几个可观察的主方向。', highlight_loading: 'loading 把主方向与原始 wavelength 联系起来。', remove_features: `第 ${values.iteration || '-'} 轮保留约 ${values.feature_count || '-'} 个波长。`, select_features: '只有高亮的 selected wavelengths 会进入模型。', connect_feature_to_prediction: 'selected feature 经过模型映射，生成 prediction 与 residual。', show_prediction: '逐个 sample 对照 true target 与 prediction。', show_residual: '残差是 prediction − true，零线是无偏差参照。', show_metric: '展示当前 ExperimentRun 已保存的指标。' }; return table[event] || `event: ${event} · 未知事件使用安全回退，不重新执行算法。`; }

  function stageLabel(stage) { if (!stage) return '-'; if (stage.stage === 'feature_analysis') return `Feature Analysis · ${(stage.methods[0] || 'method').toUpperCase()}`; return STAGE_LABELS[stage.stage] || stage.stage; }

  function explain(stage) {
    const visual = stage.visual || {}, key = stage.stage, target = visual.target ? arr(visual.target, 'target') : [], metrics = visual.metrics || visual.evaluation || stage.statistics || {};
    const text = {
      data_inspection: { what: '每条曲线代表一个苹果样本的一次光谱观测。', why: '模型只能从实际提供的光谱与标签中寻找关系。', how: '把 sample × wavelength 表读取为矩阵 X，并保留 sample id、波长轴和划分信息。', read: '观察样本之间的稳定波段差异是否大于噪声；热力图用于看整体结构。', happened: `${(visual.sample_ids || []).length} 个样本、${(visual.wavelengths || []).length} 个波长点，范围 ${format(Math.min(...arr(visual.wavelengths || [], 'wavelengths')), 0)}–${format(Math.max(...arr(visual.wavelengths || [], 'wavelengths')), 0)} nm。`, interpretation: '这是输入数据的边界，不自动说明任何波段具有因果意义。' },
      preprocessing: { what: '预处理改变光谱的表示形式，同时保留 sample 和 wavelength 对齐。', why: '减小尺度、基线或局部噪声对后续分析的干扰。', how: '按已保存的 MethodSpec 顺序读取 Raw、SG、SNV 等 StageRun 输出。', read: '切换 before/after、difference 和 heatmap，先看形状变化，再看是否改变样本间可比性。', happened: `${(stage.comparisons || []).length} 个处理组合可比较；当前组合为 ${((selectedPreprocessingComparison() || {}).method_specs || []).map((spec) => `${spec.invocation_id}(${JSON.stringify(spec.parameters)})`).join(' → ') || '未选择'}。`, interpretation: '预处理不是增加信息；它只是在表示层面重新组织已有信号。' },
      feature_analysis: { what: 'PCA 或 CARS 从光谱中寻找低维结构或有用波长。', why: '先理解变化方向或筛选变量，再把更小的特征集合交给模型。', how: 'PCA 投影中心化矩阵；CARS 按每轮系数和内部 RMSECV 逐步减少波长。', read: 'PCA 看点云与 explained variance；CARS 看保留波长、迭代曲线和 internal heuristic。', happened: key === 'feature_analysis' && stage.method_specs ? `${stage.method_specs[0].method_id.toUpperCase()} 已完成 ${stage.intermediate_state_count} 个中间状态。` : '已完成分析。', interpretation: key === 'feature_analysis' && stage.method_specs && stage.method_specs[0].method_id === 'cars' ? 'CARS 的 RMSECV 是 internal selection heuristic，不是 nested-CV 无偏泛化性能。' : '点云分离只能说明当前表示中的结构，不自动证明与 SSC 的因果关系。' },
      feature_selection: { what: '把分析结果转成最终进入模型的 SelectedFeatureSet。', why: '让建模输入可追溯，并减少无关或冗余波长。', how: `从 invocation ${visual.source_invocation_id} 读取 selected_indices，再切出对应列。`, read: '蓝色波段进入模型，灰色波段被排除；点击波长可在页面间保持高亮。', happened: `${visual.original_feature_count} 个原始特征中选择了 ${visual.selected_feature_count} 个。`, interpretation: '选择结果是当前参数、seed 和 calibration 数据的结果，不是永久的物理真理。' },
      modeling: { what: 'PLSR 把 selected features 映射到目标变量。', why: '把筛选后的光谱信息转成可评估的预测。', how: '先得到 latent scores，再通过回归系数计算 prediction，最后计算 residual。', read: '默认只看 validation；理想线是 1:1，残差图关注零线附近是否有系统结构。', happened: `${metrics.sample_count || '-'} 个 validation sample，${metrics.feature_count || '-'} 个输入特征；collapse ratio=${format(visual.collapse_ratio)}。`, interpretation: visual.collapse_ratio !== null && visual.collapse_ratio < .35 ? '预测方差较低，存在 collapse 诊断信号；这里只列可能原因，不自动断言具体根因。' : '当前简单 collapse 诊断未触发；仍需结合样本量和划分解读。' },
      results: { what: 'Results 汇总整个 ExperimentRun 的验证结果和可回溯链路。', why: '答辩时需要同时说明指标、数据边界和每个处理节点。', how: '指标来自 Results StageRun；模型选择使用 calibration CV，最终报告使用 validation。', read: '先看 pipeline 和 input_ref，再看指标；不要把 validation 指标当成训练过程中的选择依据。', happened: `最终模型 invocation 为 ${activeDescriptor().final_model_id || '-'}，RMSE=${format(metrics.rmse)}，R²=${format(metrics.r2)}。`, interpretation: '结果是这个 ExperimentRun 在当前数据边界下的证据，不等价于真实苹果泛化性能。' }
    };
    const value = text[key] || text.results; ['what', 'why', 'how', 'read', 'happened', 'interpretation'].forEach((name) => setText(`ml-${name}`, value[name]));
  }

  function updateMeta(stage) {
    const spec = stage && stage.method_specs && stage.method_specs[0]; setText('ml-experiment-id', activeDescriptor().experiment_id); setText('ml-dataset-id', activeDescriptor().dataset_id); setText('ml-stage-run-id', stage && stage.stage_run_id); setText('ml-invocation-id', spec && spec.invocation_id); setText('ml-input-ref', stage && stage.input_ref); setText('ml-source-type', state.bundle.source.source_type);
  }

  function controlsForStage(stage) {
    const container = $('ml-stage-controls'); if (!container) return; container.innerHTML = '';
    const button = (label, mode, active, target) => { const item = document.createElement('button'); item.textContent = label; item.className = active ? 'active' : ''; item.onclick = () => { state[target === 'chart' ? 'chartMode' : 'stageMode'] = mode; render(); }; return item; };
    if (state.stageKey === 'data_inspection') { container.appendChild(button('Spectra', 'spectrum', state.stageMode === 'spectrum')); container.appendChild(button('Heatmap', 'heatmap', state.stageMode === 'heatmap')); container.appendChild(button('Target distribution', 'target', state.stageMode === 'target')); }
    if (state.stageKey === 'preprocessing') { ['overlay', 'difference', 'heatmap'].forEach((mode) => container.appendChild(button(mode, mode, state.chartMode === mode, 'chart'))); const select = document.createElement('select'); state.bundle.stages.preprocessing.comparisons.forEach((item) => { const option = document.createElement('option'); option.value = item.stage_run_id; option.textContent = item.method_specs.map((spec) => `${spec.invocation_id} ${JSON.stringify(spec.parameters)}`).join(' → '); option.selected = item.stage_run_id === state.comparisonId; select.appendChild(option); }); select.onchange = () => { state.comparisonId = select.value; render(); }; container.appendChild(select); }
    if (state.stageKey === 'feature_analysis') { stageItems().forEach((item) => container.appendChild(button(item.methods[0].toUpperCase(), item.method_specs[0].invocation_id, state.stageMode === item.method_specs[0].invocation_id, 'stage'))); if (state.stageMode === 'pca') { ['scores', 'loadings', 'variance'].forEach((mode) => container.appendChild(button(mode, mode, state.chartMode === mode, 'chart'))); ['target', 'batch'].forEach((mode) => { const item = document.createElement('button'); item.textContent = `color: ${mode}`; item.className = state.pcaColorBy === mode ? 'active' : ''; item.onclick = () => { state.pcaColorBy = mode; render(); }; container.appendChild(item); }); } if (state.stageMode && state.stageMode.indexOf('cars') === 0) ['iteration', 'rmsecv'].forEach((mode) => container.appendChild(button(mode, mode, state.chartMode === mode, 'chart'))); }
    if (state.stageKey === 'feature_selection') container.appendChild(button('Selected wavelengths', 'selection', true));
    if (state.stageKey === 'modeling') { ['validation', 'calibration'].forEach((mode) => container.appendChild(button(mode, mode, state.stageMode === mode, 'stage'))); ['prediction', 'residual', 'scores', 'coefficients'].forEach((mode) => container.appendChild(button(mode, mode, state.chartMode === mode, 'chart'))); }
    if (state.stageKey === 'results') container.appendChild(button('Metrics', 'metrics', true));
  }

  function stageTabs() { const tabs = $('ml-stage-tabs'); tabs.innerHTML = ''; state.bundle.pipeline_order.forEach((key) => { const button = document.createElement('button'); button.dataset.stageKey = key; button.textContent = STAGE_LABELS[key]; button.onclick = () => { stopAnimation(); state.renderMode = 'analysis'; state.stageKey = key; state.stageMode = key === 'feature_analysis' ? 'pca' : key === 'preprocessing' ? 'overlay' : key === 'modeling' ? 'validation' : 'spectrum'; state.chartMode = key === 'modeling' ? 'prediction' : key === 'feature_analysis' ? 'scores' : key === 'preprocessing' ? 'overlay' : 'default'; state.animation.index = 0; render(); }; tabs.appendChild(button); }); }

  function renderAnalysisStage() {
    if (state.stageKey === 'data_inspection') drawData(state.stageMode);
    else if (state.stageKey === 'preprocessing') drawPreprocessing(state.chartMode || 'overlay');
    else if (state.stageKey === 'feature_analysis') { if (state.stageMode === 'pca' || state.stageMode.indexOf('pca') === 0) drawPca(state.chartMode || 'scores'); else drawCars(state.chartMode === 'rmsecv' ? 'rmsecv' : 'iteration', state.animation.index, 1); }
    else if (state.stageKey === 'feature_selection') drawSelection();
    else if (state.stageKey === 'modeling') drawModel(state.chartMode || 'prediction', 1);
    else if (state.stageKey === 'results') drawResults();
  }

  function fallbackRenderer(step) {
    renderAnalysisStage();
    setText('ml-event-narration', `Unknown teaching event: ${step.event} · stage=${step.stage_run_id || '-'} · static StageRun result kept; no algorithm was re-run.`);
  }

  function renderTeachingStep(step) {
    const renderer = CONTRACT.resolveRenderer(step.event, RENDERERS, fallbackRenderer);
    setText('ml-event-narration', step.narration || narration(step.event, step.values || {}));
    renderer(step, { stage: currentStageObject(), stepIndex: state.animation.index, progress: state.animation.transitionProgress });
  }

  function render() {
    if (!state.bundle) return; const stage = currentStageObject(); if (!stage) return; const buttons = document.querySelectorAll('#ml-stage-tabs button'); buttons.forEach((button) => button.classList.toggle('active', button.dataset.stageKey === state.stageKey)); updateMeta(stage); setText('ml-stage-title', stageLabel(stage)); setText('ml-stage-subtitle', `${stage.methods.join(' → ')} · ${stage.intermediate_state_count} saved IntermediateState`); explain(stage); controlsForStage(stage); hideError();
    // Refresh the event list before selecting the current step. At a
    // pipeline stage boundary the previous stage's event must never render
    // against the newly selected StageRun.
    updateTimeline();
    try {
      const step = state.animation.steps[state.animation.index];
      if (state.renderMode === 'teaching' && step) renderTeachingStep(step);
      else renderAnalysisStage();
      renderResultsOverview();
    } catch (error) { showError(error); }
  }

  function showError(error) { const box = $('ml-chart-error'); box.hidden = false; box.textContent = `图表数据不可用：${error.message || error}`; }
  function hideError() { const box = $('ml-chart-error'); box.hidden = true; box.textContent = ''; }

  function updateTimeline() { const stage = currentStageObject(), steps = eventSteps(stage); state.animation.steps = steps; state.animation.index = Math.min(state.animation.index, Math.max(0, steps.length - 1)); const slider = $('ml-timeline'); slider.max = Math.max(0, steps.length - 1); slider.value = state.animation.index; setText('ml-timeline-label', `Step ${steps.length ? state.animation.index + 1 : 0} / ${steps.length}`); const item = steps[state.animation.index] || steps[0]; setText('ml-event-label', `event: ${item ? item.event : '-'}`); if (state.renderMode !== 'teaching') setText('ml-event-narration', item ? item.narration : '当前阶段没有可播放事件。'); }

  function cancelMotion() { if (state.animation.rafId !== null) window.cancelAnimationFrame(state.animation.rafId); if (state.animation.timerId !== null) window.clearTimeout(state.animation.timerId); state.animation.rafId = null; state.animation.timerId = null; }
  function isTweenEvent(event) { return event === 'morph_curve' || event === 'remove_features' || event === 'show_prediction'; }
  function applyStep(index, options) {
    const steps = state.animation.steps; if (!steps.length) return; const config = options || {}; cancelMotion(); state.renderMode = 'teaching'; state.animation.index = Math.max(0, Math.min(index, steps.length - 1)); const step = steps[state.animation.index]; state.animation.transitionProgress = config.animate === false || !isTweenEvent(step.event) ? 1 : 0; if (state.stageKey === 'feature_analysis' && state.stageMode && state.stageMode.indexOf('cars') === 0) state.chartMode = 'iteration'; if (state.stageKey === 'preprocessing' && step.event === 'morph_curve') state.stageMode = 'overlay'; render(); if (state.animation.transitionProgress < 1) startTween(step); else if (config.advance) queueAdvance();
  }
  function startTween(step) {
    const started = performance.now(), duration = step.event === 'morph_curve' ? 760 : step.event === 'remove_features' ? 680 : 620, manual = !state.animation.playing;
    const frame = (now) => { if (!state.animation.playing && !manual) return; state.animation.transitionProgress = Math.min(1, (now - started) / duration); render(); if (state.animation.transitionProgress < 1) state.animation.rafId = window.requestAnimationFrame(frame); else { state.animation.rafId = null; if (state.animation.playing) queueAdvance(); } };
    state.animation.rafId = window.requestAnimationFrame(frame);
  }
  function queueAdvance() { if (state.animation.timerId !== null) window.clearTimeout(state.animation.timerId); state.animation.timerId = window.setTimeout(advancePlayback, 260); }
  function advancePlayback() { state.animation.timerId = null; if (!state.animation.playing) return; const steps = state.animation.steps; if (state.animation.index < steps.length - 1) { applyStep(state.animation.index + 1, { advance: true }); return; } if (state.animation.pipeline && state.animation.pipelineIndex < state.animation.plan.length - 1) { state.animation.pipelineIndex += 1; setStageByRunId(state.animation.plan[state.animation.pipelineIndex].stage_run_id); state.animation.index = 0; updateTimeline(); render(); applyStep(0, { advance: true }); return; } stopAnimation(); hideError(); render(); }
  function stopAnimation() { cancelMotion(); state.animation.playing = false; state.animation.pipeline = false; state.animation.transitionProgress = 1; setText('ml-pause', '▶ Play'); }
  function pauseAnimation() { cancelMotion(); state.animation.playing = false; setText('ml-pause', '▶ Resume'); }
  function playAnimation(pipeline, resume) { if (!resume) { stopAnimation(); state.animation.pipeline = !!pipeline; state.animation.plan = state.animation.pipeline ? CONTRACT.buildPlaybackPlan(state.bundle) : []; state.animation.pipelineIndex = state.animation.pipeline ? 0 : state.animation.pipelineIndex; if (state.animation.pipeline) { setStageByRunId(state.animation.plan[0].stage_run_id); state.animation.index = 0; updateTimeline(); } } else { state.animation.pipeline = !!pipeline; } state.renderMode = 'teaching'; state.animation.playing = true; setText('ml-pause', 'Ⅱ Pause'); applyStep(state.animation.index, { advance: true }); }

  function safeText(value) { return String(value === undefined || value === null ? '-' : value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character])); }
  function renderResultsOverview() { const root = $('ml-results-overview'); if (!root || !state.bundle) return; const descriptor = activeDescriptor(), metrics = descriptor.final_metrics || {}, graph = state.bundle.results_graph || { nodes: [], edges: [] }, nodeMap = new Map(graph.nodes.map((node) => [node.stage_run_id, node])); const nodeButton = (id) => { const node = nodeMap.get(id); if (!node) return ''; return `<button data-jump-run="${safeText(node.stage_run_id)}"><strong>${safeText(node.method_id)}</strong><span>${safeText(node.invocation_id)}</span><small>${safeText(node.stage_run_id)}</small></button>`; }; const graphNodes = `<div class="ml-graph-row">${nodeButton('data-inspection')}<b>→</b>${nodeButton('preprocessing')}</div><div class="ml-graph-branches"><div><span class="ml-branch-label">diagnostic branch</span>${nodeButton('feature-analysis-pca')}</div><div><span class="ml-branch-label">model branch</span>${nodeButton('feature-analysis-cars')}</div></div><div class="ml-graph-row">${nodeButton('feature-selection-cars.select')}<b>→</b>${nodeButton('modeling-plsr')}<b>→</b>${nodeButton('results')}</div>`; const experiments = state.bundle.experiments.map((item) => { const m = item.final_metrics || {}; const preprocessing = (item.preprocessing_recipe || []).map((spec) => `${spec.invocation_id} ${JSON.stringify(spec.resolved_parameters || {})}`).join(' → ') || '-'; const analysis = (item.feature_analysis_recipe || []).flat().map((spec) => spec.invocation_id).join(' / ') || '-'; const model = (item.modeling_recipe || []).flat().map((spec) => `${spec.invocation_id} ${JSON.stringify(spec.resolved_parameters || {})}`).join(' / ') || item.final_model_id || '-'; return `<tr><td>${safeText(item.experiment_id)}</td><td>${safeText(preprocessing)}</td><td>${safeText(analysis)}</td><td>${safeText(item.selection_source_invocation_id || '-')}</td><td>${safeText(model)}</td><td>${safeText(item.selected_feature_count || '-')}</td><td>${format(m.rmse)}</td><td>${format(m.mae)}</td><td>${format(m.r2)}</td><td>${format(m.cv_rmse)}</td><td>${format(item.collapse_ratio)}</td></tr>`; }).join(''); root.innerHTML = `<article class="sheet ml-results-card"><div><h3>Experiment graph · ${descriptor.experiment_id}</h3><p class="ml-graph-note">Nodes and edges come from real StageRun refs. PCA is a diagnostic branch; CARS feeds selection and PLSR.</p><div class="ml-pipeline-links ml-stage-run-graph">${graphNodes}</div><h3 style="margin-top:18px">Existing ExperimentRun comparison</h3><div class="ml-table-scroll"><table class="ml-compare-table"><thead><tr><th>Experiment</th><th>Preprocessing</th><th>Feature analysis</th><th>Selection source</th><th>Model invocation</th><th>Selected</th><th>RMSE</th><th>MAE</th><th>R²</th><th>CV RMSE</th><th>Collapse</th></tr></thead><tbody>${experiments}</tbody></table></div></div><div><h3>Final validation metrics</h3><div class="ml-metric-grid"><div><span>RMSE</span><strong>${format(metrics.rmse)}</strong></div><div><span>MAE</span><strong>${format(metrics.mae)}</strong></div><div><span>R²</span><strong>${format(metrics.r2)}</strong></div><div><span>CV RMSE</span><strong>${format(metrics.cv_rmse)}</strong></div><div><span>bias</span><strong>${format(metrics.bias)}</strong></div><div><span>collapse ratio</span><strong>${format(state.bundle.stages.results.visual.collapse_ratio)}</strong></div></div></div></article>`; root.querySelectorAll('[data-jump-run]').forEach((button) => button.onclick = () => { stopAnimation(); setStageByRunId(button.dataset.jumpRun); state.renderMode = 'analysis'; state.animation.index = 0; render(); }); }

  function bind() {
    $('ml-sample-select').onchange = (event) => { state.selectedSampleId = event.target.value; render(); };
    $('ml-feature-select').onchange = (event) => { setSelectedFeature(Number(event.target.value)); render(); };
    $('ml-restart').onclick = () => { stopAnimation(); state.animation.index = 0; render(); };
    $('ml-previous').onclick = () => { pauseAnimation(); applyStep(state.animation.index - 1); };
    $('ml-next').onclick = () => { pauseAnimation(); applyStep(state.animation.index + 1); };
    $('ml-pause').onclick = () => { if (state.animation.playing) pauseAnimation(); else playAnimation(state.animation.pipeline, true); };
    $('ml-play-pipeline').onclick = () => { playAnimation(true, false); };
    $('ml-timeline').oninput = (event) => { pauseAnimation(); applyStep(Number(event.target.value)); };
    $('ml-chart').onclick = (event) => { const rect = event.target.getBoundingClientRect(); const point = CONTRACT.mapPointerToCanvas(event, rect, state.canvasLogical.width, state.canvasLogical.height); let nearest = null, distance = Infinity; state.hitPoints.forEach((candidate) => { const d = Math.hypot(candidate.x - point.x, candidate.y - point.y); if (d < distance) { nearest = candidate; distance = d; } }); if (!nearest || distance > 18) return; if (nearest.sampleId) { state.selectedSampleId = nearest.sampleId; $('ml-sample-select').value = nearest.sampleId; } if (nearest.featureIndex !== undefined) { setSelectedFeature(nearest.featureIndex); $('ml-feature-select').value = nearest.featureIndex; } render(); };
    window.addEventListener('resize', () => { if (state.bundle && document.querySelector('#page-ml').classList.contains('active')) render(); });
  }

    function loadBundle(bundle) { state.bundle = decode(bundle); state.activeExperimentId = state.bundle.experiment_id; state.comparisonExperimentId = state.bundle.experiment_id; state.selectedSampleId = state.bundle.selected_sample_id; const sampleSelect = $('ml-sample-select'), featureSelect = $('ml-feature-select'), data = state.bundle.stages.data_inspection.visual; arr(data.sample_ids, 'sample ids').forEach((id) => { const option = document.createElement('option'); option.value = id; option.textContent = id; sampleSelect.appendChild(option); }); sampleSelect.value = state.selectedSampleId; arr(data.wavelengths, 'wavelengths').forEach((value, index) => { const option = document.createElement('option'); option.value = index; option.textContent = `${value} nm`; featureSelect.appendChild(option); }); setSelectedFeature(0); featureSelect.value = '0'; state.comparisonId = state.bundle.stages.preprocessing.comparisons.find((item) => item.method_specs.some((spec) => spec.invocation_id === 'snv')).stage_run_id; const expSelect = $('ml-experiment-select'); state.bundle.experiments.forEach((item) => { const option = document.createElement('option'); option.value = item.experiment_id; option.textContent = item.experiment_id === state.bundle.experiment_id ? `${item.experiment_id} · active` : `${item.experiment_id} · comparison`; expSelect.appendChild(option); }); expSelect.value = state.comparisonExperimentId; expSelect.onchange = () => { state.comparisonExperimentId = expSelect.value; const isComparison = state.comparisonExperimentId !== state.bundle.experiment_id; setText('ml-play-status', isComparison ? 'comparison shown in Results table; stage detail remains active' : 'ready'); render(); }; setText('ml-source-tag', `${state.bundle.source.source_type.toUpperCase()} · ${state.bundle.source.sample_count} samples`); stageTabs(); bind(); render(); }

  fetch('static/ml_p1_bundle.json').then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); }).then(loadBundle).catch((error) => { console.error('[Fruitsim P1] bundle initialization failed', error && error.stack ? error.stack : error); setText('ml-play-status', 'bundle unavailable'); showError(error && error.stack ? error.stack : error); });
}());
