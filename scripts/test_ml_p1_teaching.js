const assert = require('assert');
const teaching = require('../apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_teaching.js');

function bundle() {
  const wavelengths = [400, 500, 600, 700];
  const spectra = [[1, 2, 3, 4], [2, 3, 4, 5]];
  const base = { stage_run_id: 'data-run', stage: 'data_inspection', method_specs: [{ method_id: 'raw', invocation_id: 'raw@1' }], visual: { spectra, wavelengths, sample_ids: ['s1', 's2'] } };
  const snv = { stage_run_id: 'snv-run', stage: 'preprocessing', method_specs: [{ method_id: 'snv', invocation_id: 'snv@1' }], visual: { before: spectra, after: [[-1.34, -.45, .45, 1.34], [-1.34, -.45, .45, 1.34]], wavelengths, sample_ids: ['s1', 's2'] } };
  const pca = { stage_run_id: 'pca-run', stage: 'feature_analysis', method_specs: [{ method_id: 'pca', invocation_id: 'pca@1' }], states: [{ event: 'project_points', arrays: { centered_X: spectra, scores: [[-1, 0], [1, 0]], loadings: [[1, 0], [0, 1]] }, values: { explained_variance_ratio: [.7, .2] } }], visual: { scores: [[-1, 0], [1, 0]], loadings: [[1, 0], [0, 1]], explained_variance_ratio: [.7, .2], wavelengths, sample_ids: ['s1', 's2'] } };
  const cars = { stage_run_id: 'cars-run', stage: 'feature_analysis', method_specs: [{ method_id: 'cars', invocation_id: 'cars@1' }], visual: { wavelengths, sample_ids: ['s1', 's2'], states: [{ arrays: { current_indices: [0, 1, 2], retained_indices: [0, 2], coefficients: [1, .5, .1] }, values: { rmsecv: .2 } }] } };
  const selection = { stage_run_id: 'selection-run', stage: 'feature_selection', method_specs: [{ method_id: 'cars_selection', invocation_id: 'selection@1' }], visual: { wavelengths, selected_indices: [0, 2], original_feature_count: 4 } };
  return { source: { sample_count: 2, feature_count: 4 }, stages: { data_inspection: base, preprocessing: { ...snv, comparisons: [snv] }, feature_analysis: [pca, cars], feature_selection: selection }, selected_sample_id: 's1' };
}

const area = teaching.plotArea(980, 470);
assert.deepStrictEqual(teaching.clipPoint({ x: -10, y: 999 }, area), { x: area.left, y: area.bottom });
assert.deepStrictEqual(teaching.matrixShape([[1, 2], [3, 4]]), [2, 2]);
assert.deepStrictEqual(teaching.normalizeImportance([2, -1, 0]), [1, .5, 0]);
assert(teaching.wavelengthPositions([400, 500, 600], area).every((item) => item.x >= area.left && item.x <= area.right));

const b = bundle();
const state = { selectedSampleId: 's1', selectedWavelengthNm: 500, selectedFeatureIndex: 1, animation: { pipeline: false } };
const scenes = [
  teaching.buildScene(b.stages.data_inspection, b, state),
  teaching.buildScene(b.stages.preprocessing, b, state),
  teaching.buildScene(b.stages.feature_analysis[0], b, state),
  teaching.buildScene(b.stages.feature_analysis[1], b, state),
  teaching.buildScene(b.stages.feature_selection, b, state)
];
scenes.forEach((scene) => {
  ['scene_id', 'stage_run_id', 'method_invocation_id', 'input_object', 'operation', 'output_object', 'next_stage', 'explanation'].forEach((key) => assert(scene[key] !== undefined, `${key} missing from ${scene.scene_id}`));
  assert(Array.isArray(scene.input_object.shape));
  assert(Array.isArray(scene.output_object.shape));
});
assert.strictEqual(scenes[1].operation.formula, 'x′ = (x − μ) / σ');
assert.strictEqual(scenes[2].output_object.type, 'LatentFeatureSet');
assert(scenes[2].explanation.why.includes('不直接预测 SSC'));
assert.strictEqual(scenes[3].output_object.type, 'FeatureAnalysisResult');
assert.strictEqual(scenes[4].operation.formula, 'X_selected = X[:, selected_indices]');
console.log('ml_p1_teaching: geometry and scene contract checks passed');
