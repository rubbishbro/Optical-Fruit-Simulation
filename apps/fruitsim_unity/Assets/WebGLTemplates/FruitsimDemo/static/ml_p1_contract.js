/* Pure P1.1 renderer contracts. No DOM, Canvas or algorithm execution. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.FruitsimP1Contract = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const ANIMATION_EVENTS = [
    'show_spectrum', 'highlight_sample', 'morph_curve', 'show_mean', 'show_std', 'show_formula',
    'project_points', 'highlight_loading', 'remove_features', 'select_features',
    'connect_feature_to_prediction', 'show_prediction', 'show_residual', 'show_metric'
  ];

  function interpolateArray(start, end, progress) {
    const a = Array.isArray(start) ? start : [];
    const b = Array.isArray(end) ? end : [];
    const t = Math.max(0, Math.min(1, Number(progress) || 0));
    if (a.length !== b.length) throw new Error('cannot interpolate arrays with different lengths');
    return a.map((value, index) => Number(value) + (Number(b[index]) - Number(value)) * t);
  }

  function interpolateMatrix(start, end, progress) {
    const a = Array.isArray(start) ? start : [];
    const b = Array.isArray(end) ? end : [];
    if (a.length !== b.length) throw new Error('cannot interpolate matrices with different row counts');
    return a.map((row, index) => interpolateArray(row, b[index], progress));
  }

  function fadeOpacity(isRemoved, progress) {
    const t = Math.max(0, Math.min(1, Number(progress) || 0));
    return isRemoved ? 1 - t : 1;
  }

  function mapCarsCoefficient(currentIndices, coefficients, originalFeatureIndex) {
    const indices = Array.isArray(currentIndices) ? currentIndices : [];
    const values = Array.isArray(coefficients) ? coefficients : [];
    if (indices.length !== values.length) throw new Error('CARS current_indices and coefficients must have equal length');
    const index = indices.indexOf(Number(originalFeatureIndex));
    return index < 0 ? null : Number(values[index]);
  }

  function mapModelCoefficientToWavelength(coefficients, sourceIndices, wavelengths, coefficientIndex) {
    const index = Number(coefficientIndex);
    if (!Array.isArray(coefficients) || !Array.isArray(sourceIndices) || index < 0 || index >= coefficients.length) return null;
    const sourceIndex = Number(sourceIndices[index]);
    return {
      coefficientIndex: index,
      coefficient: Number(coefficients[index]),
      originalFeatureIndex: sourceIndex,
      wavelengthNm: Array.isArray(wavelengths) ? Number(wavelengths[sourceIndex]) : null
    };
  }

  function mapPointerToCanvas(event, rect, logicalWidth, logicalHeight) {
    const width = Number(logicalWidth);
    const height = Number(logicalHeight);
    if (!rect || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      throw new Error('invalid canvas coordinate contract');
    }
    return {
      x: (Number(event.clientX) - Number(rect.left)) * width / Number(rect.width),
      y: (Number(event.clientY) - Number(rect.top)) * height / Number(rect.height)
    };
  }

  function resolveRenderer(event, renderers, fallback) {
    const map = renderers || {};
    return typeof map[event] === 'function' ? map[event] : fallback;
  }

  function buildPlaybackPlan(bundle) {
    if (!bundle || !Array.isArray(bundle.playback_plan)) throw new Error('bundle playback_plan is missing');
    const ids = new Set(Object.keys(bundle.stage_runs || {}));
    const stages = bundle.stages || {};
    const stageIds = new Set();
    Object.keys(stages).forEach((key) => {
      const value = Array.isArray(stages[key]) ? stages[key] : [stages[key]];
      value.forEach((stage) => { if (stage && stage.stage_run_id) stageIds.add(stage.stage_run_id); });
    });
    const known = ids.size ? ids : stageIds;
    return bundle.playback_plan.map((item) => {
      if (!known.has(item.stage_run_id)) throw new Error(`playback stage is unresolved: ${item.stage_run_id}`);
      return Object.assign({}, item);
    });
  }

  return {
    ANIMATION_EVENTS,
    interpolateArray,
    interpolateMatrix,
    fadeOpacity,
    mapCarsCoefficient,
    mapModelCoefficientToWavelength,
    mapPointerToCanvas,
    resolveRenderer,
    buildPlaybackPlan
  };
}));
