/* 生成光谱分析讲解图，并呈现数据到结果的处理链路。 */
(function (root, factory) {
  const api = factory(root);
  if (root) root.FruitsimP1Teaching = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';

  const COLORS = {
    ink: '#17212b', muted: '#596875', blue: '#205c86', blueLight: '#cfe0ec',
    orange: '#b45f38', gold: '#c78b2b', red: '#9b4b3d', green: '#3e7652',
    grid: '#dfe5e8', removed: '#c9d1d6', paper: '#fbfcfc'
  };
  const CATEGORY = ['#205c86', '#b45f38', '#3e7652', '#7b5ea7', '#9b4b3d'];

  function finiteValues(values) {
    return (Array.isArray(values) ? values : []).flat(Infinity).map(Number).filter(Number.isFinite);
  }

  function extent(values, fallbackMin, fallbackMax) {
    const finite = finiteValues(values);
    if (!finite.length) return [fallbackMin, fallbackMax];
    let min = Math.min.apply(null, finite), max = Math.max.apply(null, finite);
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.08;
    return [min - pad, max + pad];
  }

  function plotArea(width, height) {
    const area = { left: 82, top: 48, right: width - 34, bottom: height - 58 };
    area.width = area.right - area.left;
    area.height = area.bottom - area.top;
    return area;
  }

  function linearScale(domainMin, domainMax, rangeMin, rangeMax) {
    const span = Number(domainMax) - Number(domainMin) || 1;
    return (value) => Number(rangeMin) + ((Number(value) - Number(domainMin)) / span) * (Number(rangeMax) - Number(rangeMin));
  }

  function clipPoint(point, area) {
    return { x: Math.max(area.left, Math.min(area.right, Number(point.x))), y: Math.max(area.top, Math.min(area.bottom, Number(point.y))) };
  }

  function normalizeImportance(values) {
    const numbers = (Array.isArray(values) ? values : []).map((value) => Math.abs(Number(value) || 0));
    const max = Math.max.apply(null, numbers.concat([0]));
    return numbers.map((value) => max > 0 ? value / max : 0);
  }

  function wavelengthPositions(wavelengths, area) {
    const values = Array.isArray(wavelengths) ? wavelengths.map(Number) : [];
    if (!values.length) return [];
    const x = linearScale(Math.min.apply(null, values), Math.max.apply(null, values), area.left, area.right);
    return values.map((value, index) => ({ index, wavelength: value, x: Math.max(area.left, Math.min(area.right, x(value))) }));
  }

  function matrixShape(value) {
    if (!Array.isArray(value)) return [];
    return [value.length, Array.isArray(value[0]) ? value[0].length : 0];
  }

  function shapeText(shape) {
    if (!shape || !shape.length) return '-';
    return shape.join(' × ');
  }

  function method(stage) {
    return stage && stage.method_specs && stage.method_specs[0] ? stage.method_specs[0] : {};
  }

  function sourceStage(stage, bundle, state) {
    if (!stage || stage.stage !== 'preprocessing' || state.animation.pipeline) return stage;
    const comparisons = bundle.stages.preprocessing.comparisons || [];
    return comparisons.find((item) => item.stage_run_id === state.comparisonId) || stage;
  }

  function buildScene(stage, bundle, state) {
    const current = sourceStage(stage, bundle, state);
    const spec = method(current);
    const visual = current && current.visual ? current.visual : {};
    const methodId = String(spec.method_id || current.stage || '').toLowerCase();
    const sampleCount = Number(bundle.source.sample_count || (visual.sample_ids || []).length || 0);
    const featureCount = Number(bundle.source.feature_count || (visual.wavelengths || []).length || 0);
    const scene = {
      scene_id: `${current.stage_run_id || 'stage'}-${methodId || 'scene'}`,
      stage_run_id: current.stage_run_id,
      method_invocation_id: spec.invocation_id || '-',
      input_object: { type: 'StageInput', shape: [sampleCount, featureCount] },
      operation: { name_zh: '读取并解释数据', name_en: '输入光谱', formula: '' },
      output_object: { type: 'StageOutput', shape: [sampleCount, featureCount] },
      next_stage: [],
      explanation: {
        what: '这一步处理什么？', why: '为什么要这样处理？', math: '数学上做了什么？',
        visual: '图上发生了什么？', output: '我们得到了什么？', next: '下一步做什么？'
      }
    };
    if (current.stage === 'data_inspection') {
      scene.input_object = { type: '光谱矩阵', shape: matrixShape(visual.spectra) };
      scene.output_object = { type: '光谱矩阵', shape: matrixShape(visual.spectra) };
      scene.operation = { name_zh: '认识输入光谱矩阵', name_en: '输入光谱', formula: 'X ∈ ℝ^(N×M)' };
      scene.next_stage = ['preprocessing'];
      scene.explanation = { what: '合成样本的光谱矩阵：每行一个样本，每列一个波长。', why: '模型从光谱与标签中学习可重复的关系。', math: 'X 的行对应样本，列对应波长。', visual: '先突出一条光谱，再把它抽象成矩阵。', output: '光谱矩阵及其波长轴。', next: '下一步比较光谱预处理方法。' };
    } else if (current.stage === 'preprocessing') {
      const raw = visual.before || (visual.spectra || []);
      const after = visual.after || [];
      scene.input_object = { type: '光谱矩阵', shape: matrixShape(raw) };
      scene.output_object = { type: '光谱矩阵', shape: matrixShape(after) };
      if (methodId === 'snv') {
        scene.operation = { name_zh: '标准正态变量变换', name_en: '标准正态变量变换', formula: "x′ = (x − μ) / σ" };
        scene.next_stage = ['feature_analysis'];
        scene.explanation = { what: '处理随机选中样本的光谱，并同步处理整批样本。', why: '削弱基线和尺度差异，让波长方向的形状更容易比较。', math: '先计算每个样本的均值 μ 和标准差 σ，再对每个波长做 (x−μ)/σ。', visual: '均值线、±σ 范围和固定坐标轴保持可见。', output: `标准化光谱矩阵 · ${shapeText(matrixShape(after))}`, next: '接下来可观察 PCA 结构，或用 CARS 筛选波长。' };
      } else {
        scene.operation = { name_zh: '光谱预处理比较', name_en: '预处理对比', formula: '' };
        scene.next_stage = ['feature_analysis'];
        scene.explanation = { what: '同一批样本在相同波长轴上的多种处理结果。', why: '比较不同表示形式对后续分析的影响。', math: '对照原始光谱与处理后的光谱。', visual: '前后曲线使用相同坐标范围叠加。', output: `光谱矩阵 · ${shapeText(matrixShape(after))}`, next: '选择一种表示方式继续分析。' };
      }
    } else if (current.stage === 'feature_analysis' && methodId === 'pca') {
      const stateItem = (current.states || [])[0] || {};
      const centered = stateItem.arrays && stateItem.arrays.centered_X;
      const scores = visual.scores || [];
      scene.input_object = { type: '光谱矩阵', shape: centered ? matrixShape(centered) : [sampleCount, featureCount] };
      scene.output_object = { type: '主成分得分', shape: matrixShape(scores) };
      scene.operation = { name_zh: '主成分分析（诊断分支）', name_en: '主成分分析', formula: 'Xc = X − μ  ;  T = Xc·P' };
      scene.next_stage = ['cars', 'feature_selection'];
      scene.explanation = { what: '将光谱波长变量重新表达为少数主成分。', why: '观察主要变化方向、批次结构和异常点；PCA 不直接预测糖度。', math: '中心化 X 得到 Xc，寻找方差最大的方向，再把每行投影为得分。', visual: '矩阵中的每个样本对应散点图中的一个点。', output: `主成分得分 · ${shapeText(matrixShape(scores))}；仅用于观察结构，不进入预测主链。`, next: '回到 SNV 输出，再用 CARS 筛选输入模型的波长。' };
    } else if (current.stage === 'feature_analysis' && methodId === 'cars') {
      const states = visual.states || [];
      const first = states[0] && states[0].arrays ? states[0].arrays.current_indices : [];
      scene.input_object = { type: '光谱矩阵', shape: [sampleCount, first.length || featureCount] };
      scene.output_object = { type: '候选波长', shape: [sampleCount, Number(visual.selected_feature_count || (visual.selected_indices || []).length)] };
      scene.operation = { name_zh: '竞争性自适应重加权采样', name_en: 'CARS 波长筛选', formula: 'X_current → |β| ranking → retain' };
      scene.next_stage = ['feature_selection'];
      scene.explanation = { what: '分析 SNV 处理后的全部波长变量。', why: '减少对糖度建模帮助有限的波长。', math: '根据 PLSR 系数评估波长重要性，并逐轮淘汰部分变量。', visual: '保留波长高亮，被淘汰波长淡化。', output: `候选波长 · ${visual.selected_count || (visual.selected_indices || []).length} 个；RMSECV 用于内部筛选。`, next: '下一步将筛选波长作为模型输入。' };
    } else if (current.stage === 'feature_selection') {
      const selected = visual.selected_indices || [];
      scene.input_object = { type: '候选波长', shape: [sampleCount, Number(visual.original_feature_count || featureCount)] };
      scene.output_object = { type: '筛选后的光谱', shape: [sampleCount, selected.length] };
      scene.operation = { name_zh: '形成模型特征集合', name_en: '波长筛选', formula: 'X_selected = X[:, selected_indices]' };
      scene.next_stage = ['modeling'];
      scene.explanation = { what: '从 CARS 结果中取出已筛选波长。', why: '形成回归模型实际使用的光谱矩阵。', math: '按筛选结果提取对应波长列。', visual: '保留波长高亮，其余波长淡化。', output: `筛选后的光谱 · ${shapeText(scene.output_object.shape)}`, next: '下一步使用这些波长训练并验证 PLSR。' };
    } else if (current.stage === 'modeling') {
      const scores = visual.scores || [];
      const featureCountModel = Number(method(current).resolved_parameters && method(current).resolved_parameters.feature_count) || Number((visual.coefficients || []).length);
      scene.input_object = { type: '筛选后的光谱', shape: [sampleCount, featureCountModel] };
      scene.output_object = { type: '糖度预测', shape: [sampleCount, 1] };
      scene.operation = { name_zh: '偏最小二乘回归', name_en: '偏最小二乘回归', formula: 'T = XW  ;  ŷ = Tq  ;  e = ŷ − y' };
      scene.next_stage = ['results'];
      scene.explanation = { what: `将筛选出的 ${featureCountModel} 个波长变量送入 PLSR。`, why: '用少量潜变量压缩相关特征，再映射到糖度。', math: `X (${sampleCount}×${featureCountModel}) → T (${matrixShape(scores)[0] || sampleCount}×${matrixShape(scores)[1] || '-'}) → ŷ`, visual: '随机选中的样本会在潜变量、预测和残差图中持续高亮。', output: `预测值 · ${shapeText(scene.output_object.shape)}；结果在独立验证集上评估。`, next: '最后查看验证集预测、残差和误差指标。' };
    } else if (current.stage === 'results') {
      scene.input_object = { type: '糖度预测', shape: [sampleCount, 1] };
      scene.output_object = { type: '验证指标', shape: [1, 6] };
      scene.operation = { name_zh: '验证结果汇总', name_en: '', formula: 'RMSE, MAE, R², bias' };
      scene.next_stage = [];
      scene.explanation = { what: '查看模型在独立验证样本上的结果。', why: '检查预测误差、系统偏差和预测变化范围。', math: '根据真实标签与预测值计算误差指标。', visual: '结合预测趋势、残差和指标观察模型表现。', output: '当前合成数据划分下的验证结果。', next: '结果仅反映当前合成数据和样本划分。' };
    }
    return scene;
  }

  function esc(value) {
    return String(value === undefined || value === null ? '-' : value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  }

  function svgHeader(scene, width, height, title, subtitle) {
    const id = `teaching-clip-${String(scene.scene_id).replace(/[^a-zA-Z0-9_-]/g, '-')}`;
    return { id, head: `<svg class="teaching-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}"><defs><clipPath id="${id}"><rect x="82" y="48" width="${width - 116}" height="${height - 106}"/></clipPath></defs><text class="teaching-svg-title" x="30" y="25">${esc(title)}</text><text class="teaching-svg-subtitle" x="30" y="42">${esc(subtitle)}</text>`, tail: '</svg>' };
  }

  function axes(area, xLabel, yLabel, xMin, xMax, yMin, yMax) {
    return `<g class="teaching-axes"><line x1="${area.left}" y1="${area.top}" x2="${area.left}" y2="${area.bottom}"/><line x1="${area.left}" y1="${area.bottom}" x2="${area.right}" y2="${area.bottom}"/><text x="${area.left}" y="${area.bottom + 25}">${esc(Number(xMin).toFixed(0))}</text><text x="${area.right - 28}" y="${area.bottom + 25}">${esc(Number(xMax).toFixed(0))}</text><text x="${area.left + area.width / 2 - 42}" y="${area.bottom + 44}">${esc(xLabel)}</text><text transform="translate(20 ${area.top + area.height / 2 + 30}) rotate(-90)">${esc(yLabel)}</text><text x="20" y="${area.bottom + 2}">${esc(Number(yMin).toFixed(2))}</text><text x="20" y="${area.top + 4}">${esc(Number(yMax).toFixed(2))}</text></g>`;
  }

  function pathFor(values, xValues, area, xScale, yScale) {
    return (Array.isArray(values) ? values : []).map((value, index) => {
      const point = clipPoint({ x: xScale(xValues[index]), y: yScale(value) }, area);
      return `${index ? 'L' : 'M'}${point.x.toFixed(2)},${point.y.toFixed(2)}`;
    }).join(' ');
  }

  function spectrumScene(scene, visual, step, state, context) {
    const raw = (step.state && step.state.arrays && step.state.arrays.raw) || visual.before || visual.spectra || [];
    const target = (step.state && step.state.arrays && (step.state.arrays.normalized || step.state.arrays.smoothed)) || visual.after || [];
    const wavelengths = visual.wavelengths || [];
    const selected = Math.max(0, (visual.sample_ids || []).indexOf(state.selectedSampleId));
    const row = raw[selected] || raw[0] || [], after = target[selected] || [];
    const values = raw.concat(target || []), xMin = Math.min.apply(null, wavelengths), xMax = Math.max.apply(null, wavelengths), yRange = extent(values, -1, 1);
    const width = 980, height = 470, area = plotArea(width, height), x = linearScale(xMin, xMax, area.left, area.right), y = linearScale(yRange[0], yRange[1], area.bottom, area.top);
    const header = svgHeader(scene, width, height, scene.operation.name_zh, scene.operation.name_en); let body = axes(area, '波长 (nm)', '信号', xMin, xMax, yRange[0], yRange[1]);
    const event = step.event, progress = Number(context.progress === undefined ? 1 : context.progress), mean = step.state && step.state.arrays && step.state.arrays.sample_mean ? Number(step.state.arrays.sample_mean[selected]) : null, std = step.state && step.state.arrays && step.state.arrays.sample_std ? Number(step.state.arrays.sample_std[selected]) : null;
    let display = row;
    if (event === 'show_centered' && mean !== null) display = row.map((value) => Number(value) - mean);
    if (event === 'morph_curve' && after.length) {
      const t = Math.max(0, Math.min(1, progress));
      display = row.map((value, index) => Number(value) + (Number(after[index]) - Number(value)) * t);
    }
    body += `<g clip-path="url(#${header.id})"><path class="teaching-spectrum raw" d="${pathFor(display, wavelengths, area, x, y)}"/><line class="teaching-guide" x1="${area.left}" y1="${y(display.reduce((a, b) => a + b, 0) / Math.max(1, display.length))}" x2="${area.right}" y2="${y(display.reduce((a, b) => a + b, 0) / Math.max(1, display.length))}"/>`;
    if ((event === 'show_formula' || event === 'morph_curve') && after.length) body += `<path class="teaching-spectrum output" d="${pathFor(after, wavelengths, area, x, y)}"/>`;
    if ((event === 'show_mean' || event === 'show_std') && mean !== null) body += `<line class="teaching-mean" x1="${area.left}" y1="${y(mean)}" x2="${area.right}" y2="${y(mean)}"/>`;
    if (event === 'show_std' && mean !== null && std !== null) body += `<rect class="teaching-spread" x="${area.left}" y="${y(mean + std)}" width="${area.width}" height="${Math.max(1, y(mean - std) - y(mean + std))}"/>`;
    if (state.selectedWavelengthNm !== null) { const sx = x(Number(state.selectedWavelengthNm)); body += `<line class="teaching-selected-wavelength" x1="${sx}" y1="${area.top}" x2="${sx}" y2="${area.bottom}"/>`; }
    body += '</g>';
    if (event === 'show_formula') body += `<text class="teaching-formula" x="${area.left + 14}" y="${area.top + 28}">${esc(scene.operation.formula)}</text>`;
    body += `<text class="teaching-callout" x="${area.left}" y="${height - 16}">${'随机选中样本'} · ${row.length} wavelength values</text>`;
    return header.head + body + header.tail;
  }

  function matrixScene(scene, visual, step) {
    const width = 980, height = 470, header = svgHeader(scene, width, height, scene.operation.name_zh, scene.operation.name_en);
    const matrix = (step.state && step.state.arrays && (step.state.arrays.centered_X || step.state.arrays.scores)) || visual.spectra || visual.scores || [];
    const shape = matrixShape(matrix), left = 100, top = 92, cellW = 12, cellH = 3.1, shownRows = Math.min(shape[0], 76), shownCols = Math.min(shape[1], 61); let body = `<g class="teaching-matrix" clip-path="url(#${header.id})"><rect x="${left}" y="${top}" width="${shownCols * cellW}" height="${shownRows * cellH}"/>`;
    for (let r = 0; r < shownRows; r += 1) for (let c = 0; c < shownCols; c += 1) { const value = Number(matrix[r] && matrix[r][c]) || 0; const opacity = Math.max(.08, Math.min(.95, .46 + Math.abs(value) * .24)); body += `<rect x="${left + c * cellW}" y="${top + r * cellH}" width="${cellW + .5}" height="${cellH + .5}" fill="${value >= 0 ? COLORS.blue : COLORS.orange}" opacity="${opacity}"/>`; }
    body += '</g>';
    body += `<text class="teaching-matrix-label" x="${left}" y="${top - 12}">X${step.event === 'center_matrix' ? 'c' : ''} · ${shapeText(shape)}</text><text class="teaching-matrix-label" x="${left + shownCols * cellW + 24}" y="${top + shownRows * cellH / 2}">${step.event === 'center_matrix' ? '每列减去均值' : '每行 = 样本 · 每列 = 波长'}</text><text class="teaching-callout" x="${left}" y="${height - 16}">PCA 用于观察样本结构，不直接预测糖度</text>`;
    return header.head + body + header.tail;
  }

  function pcaScene(scene, visual, step, state) {
    const scores = visual.scores || [], ids = visual.sample_ids || [], width = 980, height = 470, area = plotArea(width, height), xValues = scores.map((row) => Number(row[0] || 0)), yValues = scores.map((row) => Number(row[1] || 0)), xRange = extent(xValues, -1, 1), yRange = extent(yValues, -1, 1), x = linearScale(xRange[0], xRange[1], area.left, area.right), y = linearScale(yRange[0], yRange[1], area.bottom, area.top), header = svgHeader(scene, width, height, '光谱行 → PCA 点', ''); let body = axes(area, 'PC1 得分', 'PC2 得分', xRange[0], xRange[1], yRange[0], yRange[1]);
    body += `<g clip-path="url(#${header.id})">`;
    const target = visual.target || [], groups = visual.groups || visual.batch || [], tRange = extent(target, 0, 1), uniqueGroups = Array.from(new Set(groups.map(String))), groupIndex = new Map(uniqueGroups.map((value, index) => [value, index]));
    scores.forEach((row, index) => { const selected = ids[index] === state.selectedSampleId; const groupColor = groups.length ? CATEGORY[groupIndex.get(String(groups[index])) % CATEGORY.length] : CATEGORY[index % CATEGORY.length]; const color = selected ? COLORS.orange : state.pcaColorBy === 'batch' ? groupColor : CATEGORY[index % CATEGORY.length]; body += `<circle class="teaching-pca-point" data-sample-id="${esc(ids[index])}" data-group="${esc(groups[index] || '')}" cx="${x(row[0] || 0)}" cy="${y(row[1] || 0)}" r="${selected ? 8 : 5}" fill="${color}" stroke="${selected ? COLORS.ink : '#fff'}" stroke-width="${selected ? 2.5 : 1}" opacity="${target.length && state.pcaColorBy !== 'batch' ? .62 + .3 * Math.max(0, Math.min(1, (target[index] - tRange[0]) / (tRange[1] - tRange[0] || 1))) : .8}"/>`; });
    body += '</g>';
    const variance = visual.explained_variance_ratio || [];
    body += `<text class="teaching-callout" x="${area.left}" y="${height - 16}">PC1 解释 ${((variance[0] || 0) * 100).toFixed(1)}% · PC2 解释 ${((variance[1] || 0) * 100).toFixed(1)}% · 仅用于观察结构</text>`;
    return header.head + body + header.tail;
  }

  function carsScene(scene, visual, step, state, context) {
    const states = visual.states || [], index = Math.max(0, Math.min(states.length - 1, Number(context.stepIndex) || 0)), currentState = states[index] || {}, arrays = currentState.arrays || {}, current = arrays.current_indices || [], retained = new Set(arrays.retained_indices || []), coefficients = normalizeImportance(arrays.coefficients || []), wavelengths = visual.wavelengths || [], width = 980, height = 360, area = plotArea(width, height), positions = wavelengthPositions(wavelengths, area), header = svgHeader(scene, width, height, `CARS 第 ${index + 1} 轮：波长逐步淘汰`, '');
    let body = axes(area, '波长 (nm)', '相对重要性', Math.min.apply(null, wavelengths), Math.max.apply(null, wavelengths), 0, 1);
    const currentSet = new Set(current), t = Math.max(0, Math.min(1, Number(context.progress === undefined ? 1 : context.progress)));
    body += `<g clip-path="url(#${header.id})">`;
    positions.forEach((position) => { const isCurrent = currentSet.has(position.index), keep = retained.has(position.index), coefficientIndex = current.indexOf(position.index), importance = coefficientIndex >= 0 ? coefficients[coefficientIndex] : 0, opacity = isCurrent ? (keep ? 1 : 1 - t) : .12, yTop = area.bottom - (keep ? Math.max(.12, importance) : .035) * area.height; body += `<line class="teaching-wavelength-mark ${keep ? 'keep' : 'remove'}" x1="${position.x}" y1="${area.bottom}" x2="${position.x}" y2="${yTop}" opacity="${opacity}"/>`; });
    if (state.selectedWavelengthNm !== null) { const selected = positions.find((item) => item.wavelength === Number(state.selectedWavelengthNm)); if (selected) body += `<line class="teaching-selected-wavelength" x1="${selected.x}" y1="${area.top}" x2="${selected.x}" y2="${area.bottom}"/>`; }
    body += '</g>';
    const rmsecv = currentState.values && currentState.values.rmsecv;
    const eliminated = Math.max(0, current.length - retained.size);
    const reason = eliminated ? ` · 本轮淘汰 ${eliminated} 个（当前 PLSR 系数绝对值较小，对预测贡献弱）` : '';
    body += `<text class="teaching-callout" x="${area.left}" y="${height - 12}">第 ${index + 1} 轮：保留 ${retained.size} / ${wavelengths.length} 个波长${reason} · 内部 RMSECV ${rmsecv === undefined ? '-' : Number(rmsecv).toFixed(3)}（仅用于筛选）</text>`;
    return header.head + body + header.tail;
  }

  function selectionScene(scene, visual, state) {
    const wavelengths = visual.wavelengths || [], selected = new Set(visual.selected_indices || []), width = 980, height = 330, area = plotArea(width, height), positions = wavelengthPositions(wavelengths, area), header = svgHeader(scene, width, height, '从分析结果形成模型输入', '');
    let body = axes(area, '波长 (nm)', '是否选中', Math.min.apply(null, wavelengths), Math.max.apply(null, wavelengths), 0, 1);
    body += `<g clip-path="url(#${header.id})">`;
    positions.forEach((position) => { const keep = selected.has(position.index), active = Number(state.selectedFeatureIndex) === position.index; body += `<rect x="${position.x - 4}" y="${keep ? area.top + 18 : area.bottom - 18}" width="8" height="${keep ? area.height - 36 : 12}" rx="2" fill="${keep ? (active ? COLORS.orange : COLORS.blue) : COLORS.removed}" opacity="${keep ? 1 : .42}"/>`; });
    body += '</g>';
    body += `<text class="teaching-callout" x="${area.left}" y="${height - 12}">${wavelengths.length} 个波长 → 保留 ${selected.size} 个 · X选取 = X对应列</text>`;
    return header.head + body + header.tail;
  }

  function modelingScene(scene, visual, step, state) {
    const event = step.event, width = 980, height = 470;
    if (event === 'connect_feature_to_prediction') {
      const header = svgHeader(scene, width, height, '特征 → 潜变量 → 预测', '');
      return header.head + `<g class="teaching-flow-boxes"><rect x="80" y="150" width="210" height="100"/><text x="185" y="185">筛选后的光谱</text><text x="185" y="218">${esc(shapeText(scene.input_object.shape))}</text><path d="M300 200 H410"/><polygon points="410,200 395,192 395,208"/><rect x="420" y="150" width="210" height="100"/><text x="525" y="185">潜变量得分</text><text x="525" y="218">${esc(shapeText(matrixShape(visual.scores || [])))}</text><path d="M640 200 H750"/><polygon points="750,200 735,192 735,208"/><rect x="760" y="150" width="150" height="100"/><text x="835" y="185">糖度预测</text><text x="835" y="218">N × 1</text></g><text class="teaching-formula" x="80" y="320">T = XW   →   ŷ = Tq</text><text class="teaching-callout" x="80" y="370">随机选中样本在各步骤持续高亮</text>${header.tail}`;
    }
    const yTrue = visual.y_true || [], yPred = visual.y_pred || [], split = visual.split || [], ids = visual.sample_ids || [], validation = yTrue.map((_, index) => split[index] === 'validation' ? index : -1).filter((index) => index >= 0), values = event === 'show_residual' ? validation.map((index) => yPred[index] - yTrue[index]) : validation.map((index) => yTrue[index]), xRange = event === 'show_residual' ? extent(validation.map((index) => yTrue[index]), 0, 1) : extent(values, 0, 1), yValues = event === 'show_residual' ? values : validation.map((index) => yPred[index]), yRange = event === 'show_residual' ? extent(yValues, -1, 1) : extent(yValues.concat(xRange), 0, 1), area = plotArea(width, height), x = linearScale(xRange[0], xRange[1], area.left, area.right), y = linearScale(yRange[0], yRange[1], area.bottom, area.top), header = svgHeader(scene, width, height, event === 'show_residual' ? '验证集残差' : '验证集：预测值 vs 真实值', event === 'show_residual' ? '残差 = 预测值 − 真实值' : '独立验证集');
    let body = axes(area, '真实糖度 (°Brix)', event === 'show_residual' ? '残差' : '预测糖度 (°Brix)', xRange[0], xRange[1], yRange[0], yRange[1]);
    body += `<g clip-path="url(#${header.id})">`;
    validation.forEach((index) => { const selected = ids[index] === state.selectedSampleId, px = x(yTrue[index]), py = y(event === 'show_residual' ? yPred[index] - yTrue[index] : yPred[index]); body += `<circle class="teaching-prediction-point" data-sample-id="${esc(ids[index])}" cx="${px}" cy="${py}" r="${selected ? 8 : 5}" fill="${selected ? COLORS.orange : COLORS.blue}" stroke="${selected ? COLORS.ink : '#fff'}" stroke-width="${selected ? 2.5 : 1}"/>`; });
    if (event === 'show_residual') body += `<line class="teaching-guide" x1="${area.left}" y1="${y(0)}" x2="${area.right}" y2="${y(0)}"/>`;
    else body += `<line class="teaching-guide" x1="${x(xRange[0])}" y1="${y(xRange[0])}" x2="${x(xRange[1])}" y2="${y(xRange[1])}"/>`;
    body += `</g><text class="teaching-callout" x="${area.left}" y="${height - 16}">验证样本 ${validation.length} 个 · 随机选中样本持续高亮</text>`;
    return header.head + body + header.tail;
  }

  function resultsScene(scene, visual) {
    const metrics = visual.metrics || {}, items = [['RMSE', metrics.rmse], ['MAE', metrics.mae], ['R²', metrics.r2], ['平均偏差', metrics.bias], ['交叉验证 RMSE', metrics.cv_rmse], ['预测变化比', visual.collapse_ratio]];
    const cards = items.map((item, index) => `<div class="teaching-metric-card" data-metric="${esc(item[0])}"><span>${esc(item[0])}</span><strong>${item[1] === undefined || item[1] === null ? '-' : Number(item[1]).toFixed(3)}</strong></div>`).join('');
    return `<div class="teaching-results-scene"><h3>验证结果</h3><p>指标来自合成数据的独立验证集，不代表真实苹果实验表现。</p><div class="teaching-metric-grid">${cards}</div></div>`;
  }

  function render(container, scene, step, state, context) {
    if (!container || !scene) return;
    const visual = scene.stage_run_id && state.bundle ? (function () { const resolved = root.FruitsimP1Teaching.resolveStage(scene.stage_run_id, state.bundle); return resolved && resolved.visual ? resolved.visual : {}; }()) : {};
    let markup;
    if (scene.output_object.type === '验证指标') markup = resultsScene(scene, visual);
    else if (scene.operation.name_en === '标准正态变量变换' || scene.stage_run_id === 'preprocessing') markup = spectrumScene(scene, visual, step, state, context);
    else if (scene.operation.name_en === '主成分分析') markup = step.event === 'show_matrix' || step.event === 'center_matrix' ? matrixScene(scene, visual, step) : pcaScene(scene, visual, step, state);
    else if (scene.operation.name_en === 'CARS 波长筛选') markup = carsScene(scene, visual, step, state, context);
    else if (scene.operation.name_en === '波长筛选') markup = selectionScene(scene, visual, state);
    else if (scene.operation.name_en === '偏最小二乘回归') markup = modelingScene(scene, visual, step, state);
    else markup = spectrumScene(scene, visual, step, state, context);
    container.innerHTML = `<div class="teaching-scene" data-scene-id="${esc(scene.scene_id)}" data-event="${esc(step.event)}"><div class="teaching-scene-contract"><div><span>输入</span><strong>${esc(scene.input_object.type)}</strong><small>${esc(shapeText(scene.input_object.shape))}</small></div><div class="teaching-scene-arrow">↓</div><div><span>方法</span><strong>${esc(scene.operation.name_zh)}</strong><small>${esc(scene.operation.formula || '')}</small></div><div class="teaching-scene-arrow">↓</div><div><span>输出</span><strong>${esc(scene.output_object.type)}</strong><small>${esc(shapeText(scene.output_object.shape))}</small></div></div><div class="teaching-scene-visual">${markup}</div><div class="teaching-scene-next"><strong>下一步：</strong>${esc(scene.explanation.next)}</div></div>`;
  }

  function resolveStage(stageRunId, bundle) {
    const keys = Object.keys(bundle.stages || {});
    for (const key of keys) {
      const values = Array.isArray(bundle.stages[key]) ? bundle.stages[key] : [bundle.stages[key]];
      const found = values.find((item) => item && item.stage_run_id === stageRunId);
      if (found) return found;
    }
    const comparisons = bundle.stages.preprocessing && bundle.stages.preprocessing.comparisons || [];
    return comparisons.find((item) => item.stage_run_id === stageRunId) || null;
  }

  function renderPipeline(container, state, scene) {
    if (!container || !scene) return;
    const active = state.stageKey === 'feature_analysis' ? (scene.operation.name_en.indexOf('CARS') >= 0 ? 'cars' : scene.operation.name_en.indexOf('主成分') >= 0 ? 'pca' : 'feature_analysis') : state.stageKey;
    const items = [['data_inspection', '输入光谱', '样本 × 波长'], ['preprocessing', '光谱预处理', 'SNV'], ['pca', '主成分分析', '观察样本结构'], ['cars', '波长筛选', 'CARS'], ['feature_selection', '筛选结果', '模型输入'], ['modeling', '回归预测', 'PLSR'], ['results', '验证结果', '独立样本']];
    const button = (item) => `<button class="${active === item[0] ? 'active' : ''}" data-teaching-pipeline-key="${item[0]}"><strong>${item[1]}</strong><small>${item[2]}</small></button>`;
    container.innerHTML = `<div class="teaching-pipeline-label">处理链路</div><div class="teaching-pipeline"><div class="teaching-pipeline-main">${button(items[0])}<span class="teaching-pipeline-arrow">→</span>${button(items[1])}<span class="teaching-pipeline-arrow">→</span>${button(items[3])}<span class="teaching-pipeline-arrow">→</span>${button(items[4])}<span class="teaching-pipeline-arrow">→</span>${button(items[5])}<span class="teaching-pipeline-arrow">→</span>${button(items[6])}</div><div class="teaching-pipeline-branch"><span>↳ 结构观察分支</span>${button(items[2])}<small>PCA 结果不进入后续预测</small></div></div>`;
  }

  return { COLORS, plotArea, linearScale, clipPoint, normalizeImportance, wavelengthPositions, matrixShape, shapeText, buildScene, render, renderPipeline, resolveStage };
}));
