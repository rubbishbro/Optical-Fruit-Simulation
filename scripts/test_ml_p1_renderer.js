#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const contract = require(path.join(__dirname, "../apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_contract.js"));
const controller = require(path.join(__dirname, "../apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_controller.js"));

function testInterpolation() {
  assert.deepStrictEqual(contract.interpolateArray([0, 2], [10, 6], 0), [0, 2]);
  assert.deepStrictEqual(contract.interpolateArray([0, 2], [10, 6], 1), [10, 6]);
  assert.deepStrictEqual(contract.interpolateArray([0, 2], [10, 6], 0.5), [5, 4]);
  assert.deepStrictEqual(contract.interpolateMatrix([[0, 1]], [[2, 5]], 0.5), [[1, 3]]);
}

function testIdentityMappings() {
  assert.strictEqual(contract.mapCarsCoefficient([1, 4, 7], [0.2, 0.9, 0.1], 4), 0.9);
  assert.strictEqual(contract.mapCarsCoefficient([1, 4, 7], [0.2, 0.9, 0.1], 2), null);
  assert.deepStrictEqual(
    contract.mapModelCoefficientToWavelength([0.3, -0.8], [4, 7], [500, 510, 520, 530, 540, 550, 560, 570], 1),
    { coefficientIndex: 1, coefficient: -0.8, originalFeatureIndex: 7, wavelengthNm: 570 },
  );
}

function testResizeHitMapping() {
  [640, 980, 1280].forEach((width) => {
    const point = contract.mapPointerToCanvas(
      { clientX: 20 + width * 0.25, clientY: 30 + 520 * 0.75 },
      { left: 20, top: 30, width, height: 520 },
      width,
      520,
    );
    assert(Math.abs(point.x - width * 0.25) < 1e-9);
    assert(Math.abs(point.y - 520 * 0.75) < 1e-9);
  });
}

function testRendererFallbackAndPlaybackPlan() {
  const fallback = () => "fallback";
  assert.strictEqual(contract.resolveRenderer("morph_curve", { morph_curve: () => "known" }, fallback)(), "known");
  assert.strictEqual(contract.resolveRenderer("future_unknown_event", {}, fallback)(), "fallback");
  assert.strictEqual(contract.ANIMATION_EVENTS.length, 14);
  const bundle = JSON.parse(fs.readFileSync(path.join(__dirname, "../apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_bundle.json"), "utf8"));
  const plan = contract.buildPlaybackPlan(bundle);
  assert(plan.some((item) => item.stage_run_id === "feature-analysis-pca"));
  assert(plan.some((item) => item.stage_run_id === "feature-analysis-cars"));
  assert(plan.findIndex((item) => item.stage_run_id === "feature-analysis-cars") < plan.findIndex((item) => item.stage_run_id === "feature-selection-cars.select"));
  assert.strictEqual(contract.fadeOpacity(true, 0), 1);
  assert.strictEqual(contract.fadeOpacity(true, 1), 0);
}

function testControllerBehavior() {
  const active = { stage_run_id: "experiment-pre", states: [{ event: "show_formula" }] };
  const comparison = { stage_run_id: "comparison-sg15", states: [{ event: "show_formula" }] };
  assert.strictEqual(controller.resolvePreprocessingTeachingStage(active, comparison, false), comparison);
  assert.strictEqual(controller.resolvePreprocessingTeachingStage(active, comparison, true), active);
  assert.strictEqual(controller.resolveStepIndex(0, 6), 0);
  assert.strictEqual(controller.resolveStepIndex(undefined, 6), 5);
  assert.strictEqual(controller.transitionStartProgress("morph_curve", 0.5, false), 0);
  assert.strictEqual(controller.transitionStartProgress("morph_curve", 0.5, true), 0.5);
  assert.strictEqual(controller.transitionStartProgress("show_mean", 0.5, true), 1);
  const axisRange = controller.interpolationAxisRange([[0, 10]], [[5, 15]], -1, 1);
  assert(Math.abs(axisRange[0] + 0.9) < 1e-12);
  assert(Math.abs(axisRange[1] - 15.9) < 1e-12);
  const graph = controller.buildResultsGraphModel({
    nodes: [
      { stage_run_id: "raw-stage-x", method_id: "raw", invocation_id: "raw_x" },
      { stage_run_id: "prep-stage-y", method_id: "sg", invocation_id: "sg15_teacher" },
      { stage_run_id: "model-stage-z", method_id: "plsr", invocation_id: "plsr_stable" },
    ],
    edges: [
      { source_stage_run_id: "raw-stage-x", target_stage_run_id: "prep-stage-y", input_ref: "stage:raw-stage-x" },
      { source_stage_run_id: "prep-stage-y", target_stage_run_id: "model-stage-z", input_ref: "stage:prep-stage-y" },
    ],
  });
  assert.deepStrictEqual(graph.levels.map((level) => level.map((node) => node.invocation_id)), [
    ["raw_x"], ["sg15_teacher"], ["plsr_stable"],
  ]);
  assert.strictEqual(graph.edges[1].target_stage_run_id, "model-stage-z");
  const branchedGraph = controller.buildResultsGraphModel({
    nodes: [
      { stage_run_id: "raw-stage-renamed", method_id: "raw", invocation_id: "raw_demo" },
      { stage_run_id: "prep-stage-renamed", method_id: "sg", invocation_id: "sg15_teacher" },
      { stage_run_id: "pca-stage-renamed", method_id: "pca", invocation_id: "pca_explainer" },
      { stage_run_id: "cars-stage-renamed", method_id: "cars", invocation_id: "cars_stable" },
      { stage_run_id: "selection-stage-renamed", method_id: "cars.select", invocation_id: "selection_final" },
    ],
    edges: [
      { source_stage_run_id: "raw-stage-renamed", target_stage_run_id: "prep-stage-renamed" },
      { source_stage_run_id: "prep-stage-renamed", target_stage_run_id: "pca-stage-renamed" },
      { source_stage_run_id: "prep-stage-renamed", target_stage_run_id: "cars-stage-renamed" },
      { source_stage_run_id: "cars-stage-renamed", target_stage_run_id: "selection-stage-renamed" },
    ],
  });
  assert.deepStrictEqual(branchedGraph.parents.get("pca-stage-renamed"), ["prep-stage-renamed"]);
  assert.deepStrictEqual(branchedGraph.parents.get("cars-stage-renamed"), ["prep-stage-renamed"]);
  assert.deepStrictEqual(branchedGraph.children.get("prep-stage-renamed"), ["pca-stage-renamed", "cars-stage-renamed"]);
  assert.deepStrictEqual(branchedGraph.parents.get("selection-stage-renamed"), ["cars-stage-renamed"]);
  assert(!branchedGraph.children.get("pca-stage-renamed").includes("cars-stage-renamed"));
  assert.deepStrictEqual(branchedGraph.levels.map((level) => level.map((node) => node.stage_run_id)), [
    ["raw-stage-renamed"], ["prep-stage-renamed"], ["pca-stage-renamed", "cars-stage-renamed"], ["selection-stage-renamed"],
  ]);
  const groups = controller.categoricalGroups(["batch-b", "batch-a", "batch-b"]);
  assert.deepStrictEqual(groups.unique, ["batch-b", "batch-a"]);
  assert.strictEqual(groups.index.get("batch-a"), 1);
}

testInterpolation();
testIdentityMappings();
testResizeHitMapping();
testRendererFallbackAndPlaybackPlan();
testControllerBehavior();
console.log("P1.1 renderer contract tests passed");
