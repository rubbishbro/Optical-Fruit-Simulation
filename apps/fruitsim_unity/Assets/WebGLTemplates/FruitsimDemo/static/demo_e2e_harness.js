/* Real integration harness: drives the actual page against a live Gateway and
 * static server, creating two small math Runs A/B and reading each Run's results
 * over the real /api/runs HTTP endpoints. Loaded only with ?demoe2e=1.
 *
 * The runner injects the Gateway port via ?gateway_port= (no global config) and
 * a unique suffix via ?e2e_suffix= so A/B never collide with existing Runs.
 * Result: window.__demoE2EReport (poll until window.__demoE2EReportDone).
 */
(function () {
  'use strict';

  const params = new URLSearchParams(location.search);
  const suffix = params.get('e2e_suffix') || String(Date.now());
  const report = { pass: false, phase: 'bootstrap', checks: [], error: null };
  window.__demoE2EReport = report;
  window.__demoE2EReportDone = false;

  const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));
  async function waitFor(predicate, timeout, label) {
    const started = performance.now();
    while (performance.now() - started < (timeout || 60000)) {
      if (predicate()) return;
      await sleep(50);
    }
    throw new Error(`timeout waiting for ${label || 'browser state'}`);
  }
  function check(condition, message) { if (!condition) throw new Error(message); }

  async function run() {
    const debug = window.__FruitsimDemoDebug;
    await waitFor(() => debug && window.FruitsimDemo, 10000, 'demo runtime');
    const $ = selector => document.querySelector(selector);

    // Small, fast sample count for integration (min allowed is 6).
    const samples = $('#samples');
    if (!Array.from(samples.options).some(option => option.value === '6')) {
      const option = document.createElement('option');
      option.value = '6';
      option.textContent = '6';
      samples.appendChild(option);
    }

    report.phase = 'connect';
    $('#connect-btn').click();
    await waitFor(() => debug.connectionKind() === 'connected', 15000, 'gateway connection');
    report.checks.push('connected to the live Gateway');

    async function runOne(runId) {
      $('#run-id').value = runId;
      $('#seed').value = '20260920';
      samples.value = '6';
      $('#start-btn').click();
      await waitFor(() => debug.tracker.submittedRunId === runId, 30000, `run ${runId} accepted`);
      await waitFor(() => debug.tracker.state.terminal, 180000, `run ${runId} terminal`);
      const state = Object.assign({}, debug.tracker.state);
      check(state.runId === runId, `tracker run id ${state.runId} != ${runId}`);
      return state;
    }

    async function collectLinks(runId) {
      await waitFor(() => debug.resultsRunId() === runId, 30000, `results ${runId} selected`);
      await waitFor(() => $('#run-results-summary').textContent.includes(runId), 30000, `results ${runId} rendered`);
      return Array.from(document.querySelectorAll('#run-results-artifacts a')).map(link => link.getAttribute('href'));
    }

    report.phase = 'run-a';
    const runA = await runOne(`e2e_a_${suffix}`);
    check(runA.status === 'completed', `run A ended ${runA.status}${runA.message ? ': ' + runA.message : ''}`);
    report.checks.push(`run A ${runA.runId} completed`);
    const linksA = await collectLinks(runA.runId);
    check(linksA.length > 0, 'run A produced no artifact links');
    check(linksA.every(href => href.startsWith(`/api/runs/${runA.runId}/artifacts/`)), 'run A links are not scoped to run A');
    report.checks.push('run A results carry its own identity and same-origin URLs');

    report.phase = 'run-b';
    const runB = await runOne(`e2e_b_${suffix}`);
    check(runB.status === 'completed', `run B ended ${runB.status}`);
    check(runB.runId !== runA.runId, 'run B reused run A identity');
    const linksB = await collectLinks(runB.runId);
    check(linksB.length > 0, 'run B produced no artifact links');
    check(linksB.every(href => href.startsWith(`/api/runs/${runB.runId}/artifacts/`)), 'run B links are not scoped to run B');
    check(!$('#run-results-summary').textContent.includes(runA.runId), 'run A identity leaked into run B results');
    report.checks.push(`run B ${runB.runId} stays independent of run A`);

    // The static preview and ML sources must not be rewritten by a math Run.
    check($('#figures-source-tag').textContent.includes('预计算'), 'figure source tag was not preserved');
    check($('#ml-source-tag').textContent.includes('合成'), 'ML source tag was not preserved');
    report.checks.push('precomputed figure/ML sources stay labeled and untouched');

    report.pass = true;
    report.phase = 'done';
    window.__demoE2EReportDone = true;
  }

  run().catch(error => {
    report.error = error.message;
    window.__demoE2EReportDone = true;
  });
}());
