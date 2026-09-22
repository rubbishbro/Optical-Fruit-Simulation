/* Small, dependency-free controller contracts used by the real P1 DOM page. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.FruitsimP1Controller = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value)));
  }

  function resolvePreprocessingTeachingStage(activeStage, selectedComparison, pipelinePlayback) {
    return pipelinePlayback ? activeStage : (selectedComparison || activeStage);
  }

  function transitionStartProgress(event, progress, resume) {
    const tween = event === 'morph_curve' || event === 'remove_features' || event === 'show_prediction';
    if (!tween) return 1;
    return resume ? clamp(progress === undefined ? 0 : progress, 0, 1) : 0;
  }

  function resolveStepIndex(stepIndex, stateCount) {
    const lastIndex = Math.max(0, Number(stateCount) - 1);
    const requested = stepIndex === undefined || stepIndex === null ? lastIndex : Number(stepIndex);
    return Math.max(0, Math.min(lastIndex, requested));
  }

  function interpolationAxisRange(start, end, fallbackMin, fallbackMax) {
    const values = [];
    [start, end].forEach((matrix) => {
      (Array.isArray(matrix) ? matrix : []).forEach((row) => {
        (Array.isArray(row) ? row : [row]).forEach((value) => {
          if (Number.isFinite(Number(value))) values.push(Number(value));
        });
      });
    });
    if (!values.length) return [fallbackMin, fallbackMax];
    let min = Math.min.apply(null, values), max = Math.max.apply(null, values);
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.06;
    return [min - pad, max + pad];
  }

  function buildResultsGraphModel(graph) {
    const input = graph || {};
    const sourceNodes = Array.isArray(input.nodes) ? input.nodes : [];
    const nodes = sourceNodes.map((node, index) => Object.assign({ _order: index }, node));
    const byId = new Map(nodes.map((node) => [node.stage_run_id, node]));
    if (byId.size !== nodes.length || nodes.some((node) => !node.stage_run_id)) {
      throw new Error('results_graph nodes must have unique stage_run_id values');
    }
    const edges = (Array.isArray(input.edges) ? input.edges : []).map((edge) => {
      const source = edge.source_stage_run_id;
      const target = edge.target_stage_run_id;
      if (!byId.has(source) || !byId.has(target)) throw new Error(`results_graph edge is unresolved: ${source} → ${target}`);
      return Object.assign({}, edge);
    });
    const outgoing = new Map(nodes.map((node) => [node.stage_run_id, []]));
    const parents = new Map(nodes.map((node) => [node.stage_run_id, []]));
    const children = new Map(nodes.map((node) => [node.stage_run_id, []]));
    const indegree = new Map(nodes.map((node) => [node.stage_run_id, 0]));
    edges.forEach((edge) => {
      const source = edge.source_stage_run_id;
      const target = edge.target_stage_run_id;
      outgoing.get(source).push(target);
      children.get(source).push(target);
      parents.get(target).push(source);
      indegree.set(edge.target_stage_run_id, indegree.get(edge.target_stage_run_id) + 1);
    });
    const queue = nodes.filter((node) => indegree.get(node.stage_run_id) === 0).sort((a, b) => a._order);
    const ordered = [];
    while (queue.length) {
      const node = queue.shift();
      ordered.push(node);
      outgoing.get(node.stage_run_id).forEach((targetId) => {
        indegree.set(targetId, indegree.get(targetId) - 1);
        if (indegree.get(targetId) === 0) {
          queue.push(byId.get(targetId));
          queue.sort((a, b) => a._order - b._order);
        }
      });
    }
    if (ordered.length !== nodes.length) throw new Error('results_graph must be acyclic');
    const levels = new Map(nodes.map((node) => [node.stage_run_id, 0]));
    ordered.forEach((node) => {
      outgoing.get(node.stage_run_id).forEach((targetId) => {
        levels.set(targetId, Math.max(levels.get(targetId), levels.get(node.stage_run_id) + 1));
      });
    });
    const rows = [];
    ordered.forEach((node) => {
      const level = levels.get(node.stage_run_id);
      if (!rows[level]) rows[level] = [];
      rows[level].push(node);
    });
    nodes.forEach((node) => { delete node._order; });
    return { nodes, edges, ordered, levels: rows.filter(Boolean), parents, children };
  }

  function categoricalGroups(values) {
    const labels = (Array.isArray(values) ? values : []).map((value) => String(value));
    const unique = [];
    labels.forEach((label) => { if (!unique.includes(label)) unique.push(label); });
    return { labels, unique, index: new Map(unique.map((label, i) => [label, i])) };
  }

  return {
    clamp,
    resolvePreprocessingTeachingStage,
    transitionStartProgress,
    resolveStepIndex,
    interpolationAxisRange,
    buildResultsGraphModel,
    categoricalGroups
  };
}));
