#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const contract = require(path.join(__dirname, "../apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_contract.js"));

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

testInterpolation();
testIdentityMappings();
testResizeHitMapping();
testRendererFallbackAndPlaybackPlan();
console.log("P1.1 renderer contract tests passed");
