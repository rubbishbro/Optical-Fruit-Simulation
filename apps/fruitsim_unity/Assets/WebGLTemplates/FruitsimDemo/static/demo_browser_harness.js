/* Real-browser DOM checks for the Fruitsim demo page.
 *
 * Loaded only with ?demoharness=1.  It drives the actual index.html DOM and the
 * shared validation/event-routing code.  Server events and the Gateway socket
 * are stubbed in-page (no real WebSocket E2E here); Unity is absent, so the
 * loader-failure path is the real one.  A passing result means the DOM/state
 * behaviour is correct, not that a real Gateway round-trip succeeded.
 */
(function () {
  'use strict';

  const report = document.createElement('pre');
  report.id = 'demo-harness-result';
  report.style.cssText = 'position:fixed;z-index:99999;left:4px;bottom:4px;max-width:95vw;max-height:45vh;overflow:auto;background:#111;color:#d7f7d7;padding:8px;font:11px monospace;white-space:pre-wrap';
  document.body.appendChild(report);

  const runtimeErrors = [];
  window.addEventListener('error', event => runtimeErrors.push(`${String(event.message || event.error || 'window error')} @ ${event.filename || '-'}:${event.lineno || '-'}`));
  window.addEventListener('unhandledrejection', event => runtimeErrors.push(String(event.reason || 'unhandled rejection')));

  const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));
  async function waitFor(predicate, timeout) {
    const started = performance.now();
    while (performance.now() - started < (timeout || 6000)) {
      if (predicate()) return;
      await sleep(25);
    }
    throw new Error('timeout waiting for browser state');
  }
  function check(condition, message) { if (!condition) throw new Error(message); }
  function evt(seq, kind, status, stage, payload) {
    payload = payload || {};
    return { protocol: 1, type: 'event', seq, event_id: `evt-${seq}`, run_id: payload.run_id || null, kind, stage, status, server_ts: '2026-09-30T00:00:00Z', payload };
  }

  let phase = 'bootstrap';
  const results = [];
  const pass = name => results.push({ name, pass: true });

  async function run() {
    await waitFor(() => window.__FruitsimDemoDebug && window.FruitsimDemo, 8000);
    const debug = window.__FruitsimDemoDebug;
    const tracker = debug.tracker;
    const $ = selector => document.querySelector(selector);

    phase = 'loader-failure';
    await waitFor(() => $('#unity-state').textContent === '载入失败', 15000);
    check(debug.loaderFailed(), 'loader failure was not routed through the shared error entry');
    check($('#unity-retry'), 'no retry control after loader failure');
    check(!$('#loading #progress'), 'fake progress bar was not removed after loader failure');
    pass('loader failure shows a real error and retry without fake progress');

    phase = 'loader-sync-failure';
    const beforeStubFail = debug.loaderFailed();
    debug.simulateLoaderLoad(); // createUnityInstance is absent in the template
    check(debug.loaderFailed() !== beforeStubFail && /未提供/.test(debug.loaderFailed()), 'missing createUnityInstance did not fail cleanly');
    window.createUnityInstance = () => { throw new Error('boom-loader'); };
    debug.simulateLoaderLoad();
    check(/boom-loader/.test(debug.loaderFailed()), 'synchronous createUnityInstance throw did not fail cleanly');
    delete window.createUnityInstance;
    check($('#unity-state').textContent === '载入失败', 'synchronous loader failure did not update the Unity state');
    pass('missing or synchronously throwing createUnityInstance enters loader failure');

    phase = 'capability-honesty';
    check($('#apple-height-ratio').disabled, 'height ratio must be disabled (metadata only)');
    check($('#apple-crown-ratio').disabled, 'crown ratio must be disabled (metadata only)');
    check($('#apple-asymmetry').disabled, 'asymmetry must be disabled (metadata only)');
    check($('#apple-capability-note').textContent.includes('仅记录'), 'capability note does not state geometry params are metadata only');
    check($('#apple-capability-note').textContent.includes('不生成新的果实形状'), 'seed effect boundary is not stated');
    check($('#apple-physical-note').textContent.includes('元数据') && $('#apple-physical-note').textContent.includes('光传输计算'), 'physical metadata is not marked as not transported');
    check($('#generate-batch').disabled, 'batch entry must be disabled while same-pose overlap is unresolved');
    check($('#apple-batch-note').textContent.includes('重叠'), 'batch limitation note is missing');
    pass('capability controls are disabled and explained honestly');

    phase = 'detector-label';
    check($('label[for="sensor-radius"]').textContent.includes('果实高度'), 'sensor radius label must reference apple height');
    check($('#detector-note').textContent.includes('果实高度') && $('#detector-note').textContent.includes('固定尺寸'), 'detector note must explain height scaling and fixed imported model');
    pass('detector definition matches SensorModel height scaling');

    phase = 'optics-rejection';
    const wavelength = $('#wavelength');
    const nirBefore = $('#nir-note').textContent;
    const beforeOpticsCommands = debug.sentCommands.length;
    wavelength.value = '9999';
    $('#apply-optics').click();
    check($('#parameter-status').textContent.includes('参数未应用'), 'invalid wavelength was not rejected in the status line');
    check(/400/.test($('#parameter-status').textContent), 'rejection reason does not state the valid range');
    check(debug.sentCommands.length === beforeOpticsCommands, 'an invalid optics form still sent a command');
    check(wavelength.getAttribute('aria-invalid') === 'true', 'invalid wavelength field was not marked');
    wavelength.value = '700';
    $('#apply-optics').click();
    check(debug.sentCommands.length === beforeOpticsCommands, 'apply while Unity is not ready must not send a viewer command');
    check($('#parameter-status').textContent.includes('尚未就绪'), 'not-ready state was not reported for a valid form');
    check($('#nir-note').textContent === nirBefore, 'NIR note was overwritten by transient status');
    pass('optics validation rejects bad input, marks fields, and never edits the NIR note');

    phase = 'stub-connected';
    const stub = { readyState: 1, sent: [], send(message) { this.sent.push(JSON.parse(message)); } };
    debug.setGatewayStub(stub, 'connected');
    const seed = $('#seed');
    const samples = $('#samples');
    const runIdInput = $('#run-id');
    const startButton = $('#start-btn');
    const cancelButton = $('#cancel-btn');
    function beginRun(runId) {
      debug.resetTracker();
      runIdInput.value = runId === undefined ? '' : runId;
      stub.sent.length = 0;
      startButton.click();
      return stub.sent.find(message => message.name === 'run.start');
    }
    function claimRun(message, runId, seq) {
      debug.inject(evt(seq, 'run_accepted', 'accepted', 'queued', { run_id: runId, command_id: message.command_id }));
      return message.command_id;
    }

    phase = 'run-form-rejection';
    const originalSeed = seed.value;
    const originalSamples = samples.value;
    tracker.rejectSubmit('test-reset');
    seed.value = '1.5';
    startButton.click();
    check(!stub.sent.some(message => message.name === 'run.start'), 'non-integer seed still started a run');
    check($('#run-feedback').textContent.includes('参数错误'), 'seed rejection was not reported');
    seed.value = originalSeed;
    const tempOption = document.createElement('option');
    tempOption.value = '3';
    tempOption.textContent = '3';
    samples.appendChild(tempOption);
    samples.value = '3';
    startButton.click();
    check(!stub.sent.some(message => message.name === 'run.start'), 'out-of-range samples still started a run');
    check(/6/.test($('#run-feedback').textContent), 'samples rejection does not state the valid minimum');
    samples.removeChild(tempOption);
    samples.value = originalSamples;
    runIdInput.value = '..';
    startButton.click();
    check(!stub.sent.some(message => message.name === 'run.start'), 'unsafe run id still started a run');
    pass('run form rejects bad seed/samples/run_id without sending');

    phase = 'submit-with-command-id';
    let startMessage = beginRun('my-run');
    check(startMessage, 'valid run.start was not sent');
    check(startMessage.run_id === 'my-run' && startMessage.payload.seed === 20260920 && startMessage.payload.samples === 120, 'submitted identity/params were not forwarded');
    check(startMessage.command_id, 'run.start command_id was not recorded');
    pass('valid run form submits the actual run id, params and command_id');

    phase = 'default-unique-id';
    const defaultMessage = beginRun('');
    check(defaultMessage && defaultMessage.run_id === null, 'blank run name should let the server assign an id');
    debug.inject(evt(1, 'run_accepted', 'accepted', 'queued', { run_id: 'web_demo_seed20260920', command_id: defaultMessage.command_id }));
    check(tracker.submittedRunId === 'web_demo_seed20260920', 'server-assigned id was not claimed');
    check(runIdInput.value === '', 'the name input should stay blank so the next default run is unique again');
    pass('blank name lets the server assign a unique id without pinning the input');

    phase = 'foreign-accepted-not-claimed';
    const mine = beginRun('mine');
    check(tracker.pendingCommandId === mine.command_id, 'pending start was not tracked by command_id');
    debug.inject(evt(2, 'run_accepted', 'accepted', 'queued', { run_id: 'someone-else', command_id: 'other-client-command' }));
    check(tracker.submittedRunId === null, "another client's run_accepted claimed this client's card");
    check($('#run-state').textContent === '排队中', 'foreign accepted changed the run card');
    claimRun(mine, 'mine', 3);
    check(tracker.submittedRunId === 'mine', 'our run_accepted did not claim the card');
    pass("another client's run_accepted cannot claim our card; ours can");

    phase = 'rejected-start-recovery';
    const rejected = beginRun('dup-id');
    debug.inject({ protocol: 1, type: 'command_ack', command_id: rejected.command_id, accepted: false, server_ts: 'x', error: { code: 'handler_error', message: '任务标识 dup-id 已被使用' } });
    check(tracker.pendingCommandId === null, 'a rejected run.start left the tracker pending');
    check(!startButton.disabled, 'start button stayed disabled after a rejected start');
    check($('#run-feedback').textContent.includes('已被使用'), 'rejection reason was not surfaced');
    const retry = beginRun('dup-id-2');
    check(retry && retry.command_id !== rejected.command_id, 'retry did not send a fresh run.start');
    claimRun(retry, 'dup-id-2', 4);
    check(tracker.submittedRunId === 'dup-id-2', 'retry after rejection did not proceed');
    pass('a rejected run.start recovers and an immediate retry succeeds');

    phase = 'viewer-ack-keeps-run';
    debug.inject(evt(5, 'run_progress', 'running', 'generating', { run_id: 'dup-id-2' }));
    const activeStatus = tracker.state.status;
    debug.inject({ protocol: 1, type: 'command_ack', command_id: 'viewer-command-1', accepted: false, server_ts: 'x', error: { code: 'handler_error', message: 'wave length bad' } });
    check(tracker.state.status === activeStatus, 'a rejected viewer ack cleared the active run status');
    check(tracker.isActive(), 'a rejected viewer ack ended the active run');
    pass('a rejected viewer ack does not disturb the active run');

    phase = 'state-isolation';
    debug.inject(evt(6, 'run_progress', 'running', 'generating', {}));
    check($('#run-state').textContent === '运行中', 'an id-less run event was accepted');
    debug.inject(evt(7, 'viewer_state', 'updated', 'viewer', { wavelength_nm: 700 }));
    check($('#run-state').textContent === '运行中', 'viewer event polluted the run card');
    debug.inject(evt(8, 'run_progress', 'running', 'generating', { run_id: 'other-run' }));
    check($('#run-state').textContent === '运行中', 'another run polluted the current run card');
    debug.inject(evt(9, 'run_completed', 'completed', 'completed', { run_id: 'dup-id-2', run_dir: '/srv/results/dup-id-2' }));
    check($('#run-state').textContent === '已完成', 'completion did not reach the run card');
    check($('#run-path').textContent === 'Run dup-id-2', 'run identity was not displayed without an absolute path');
    debug.inject(evt(10, 'run_failed', 'failed', 'generating', { run_id: 'dup-id-2' }));
    check($('#run-state').textContent === '已完成', 'a later event overwrote the terminal state');
    pass('viewer/other-run/id-less/late events never overwrite the current terminal state');

    phase = 'run-path-reset';
    const fresh = beginRun('reset-path');
    check($('#run-path').textContent === '-', 'a new run kept the previous run path');
    claimRun(fresh, 'reset-path', 12);
    pass('the run path resets for a new run instead of showing the old one');

    phase = 'input-edit-no-cancel';
    const cancelTarget = beginRun('cancel-target');
    claimRun(cancelTarget, 'cancel-target', 20);
    debug.inject(evt(21, 'run_progress', 'running', 'generating', { run_id: 'cancel-target' }));
    check(!cancelButton.disabled, 'cancel is unavailable for a confirmed active run');
    runIdInput.value = 'edited-name';
    stub.sent.length = 0;
    cancelButton.click();
    const cancelMessage = stub.sent.find(message => message.name === 'run.cancel');
    check(cancelMessage, 'cancel did not send a run.cancel command');
    check(cancelMessage.run_id === 'cancel-target', `cancel targeted ${cancelMessage.run_id} instead of the active run`);
    check(!stub.sent.some(message => message.run_id === 'edited-name'), 'editing the name input redirected the cancel');
    pass('editing the task-name input cannot cancel or retarget the active run');

    phase = 'cancel-send-failure';
    const failingStub = { readyState: 1, send() { throw new Error('boom-send'); }, sent: [] };
    debug.setGatewayStub(failingStub, 'connected');
    check(!cancelButton.disabled, 'cancel should be enabled while a confirmed run is active');
    cancelButton.click();
    check($('#run-feedback').textContent.includes('发送失败') && !$('#run-feedback').textContent.includes('等待子进程'), 'a failed cancel send was reported as a successful request');
    pass('a failed cancel send is reported honestly, not as a request');

    phase = 'pending-cancel-guard';
    debug.setGatewayStub(stub, 'connected');
    const pendingStart = beginRun('pending-run');
    check(cancelButton.disabled, 'cancel button should be disabled while the run is unconfirmed');
    stub.sent.length = 0;
    debug.cancelRun();
    check(!stub.sent.some(message => message.name === 'run.cancel'), 'cancel was sent before the run was confirmed');
    check($('#run-feedback').textContent.includes('已确认'), 'pending cancel did not explain it needs confirmation');
    claimRun(pendingStart, 'pending-run', 40);
    debug.inject(evt(41, 'run_progress', 'running', 'generating', { run_id: 'pending-run' }));
    check(!cancelButton.disabled, 'cancel should be enabled once the run is confirmed');
    debug.setGatewayStub(null, 'offline');
    check(cancelButton.disabled, 'cancel button must be disabled when disconnected');
    debug.cancelRun();
    check($('#run-feedback').textContent.includes('未连接'), 'disconnected cancel did not explain the connection problem');
    pass('cancel needs a live connection and a confirmed run id');

    phase = 'disconnect-recovery';
    debug.setGatewayStub(stub, 'connected');
    const recoverStart = beginRun('recover-run');
    claimRun(recoverStart, 'recover-run', 1000);
    debug.inject(evt(1001, 'run_progress', 'running', 'generating', { run_id: 'recover-run' }));
    // Another run's higher seq arrives before we reconnect: the replay cursor
    // must not jump to it, or our lower-seq terminal would be skipped.
    debug.inject(evt(2000, 'run_progress', 'running', 'generating', { run_id: 'noise-run' }));
    check(tracker.lastReceivedSeq === 2000, 'noise run did not advance the received watermark');
    tracker.markDisconnected();
    stub.sent.length = 0;
    const replay = debug.simulateReconnect();
    check(replay && replay.after_seq === 1001, `replay must resume from appliedRunSeq, got ${replay && replay.after_seq}`);
    check(replay.run_id === 'recover-run', 'replay must filter to the current run id');
    check(stub.sent.some(message => message.type === 'replay' && message.after_seq === 1001 && message.run_id === 'recover-run'), 'replay request did not use the per-run cursor and filter');
    // hello carries the server watermark but must not claim received history.
    debug.inject({ protocol: 1, type: 'hello', latest_seq: 9999, server_ts: 'x' });
    check(tracker.lastReceivedSeq === 2000, 'hello.latest_seq was treated as received events');
    // Our missed terminal (seq 1002, lower than the noise run's 2000) still applies.
    debug.inject(evt(1002, 'run_completed', 'completed', 'completed', { run_id: 'recover-run' }));
    check($('#run-state').textContent === '已完成', 'the missed terminal was not applied from replay');
    debug.inject(evt(2001, 'run_progress', 'running', 'generating', { run_id: 'noise-run' }));
    debug.inject(evt(2002, 'viewer_state', 'updated', 'viewer', { wavelength_nm: 700 }));
    check($('#run-state').textContent === '已完成', 'later other-run/viewer events overwrote the recovered terminal');
    debug.inject(evt(1002, 'run_completed', 'completed', 'completed', { run_id: 'recover-run' }));
    check($('#run-state').textContent === '已完成' && tracker.lastReceivedSeq === 2002, 'a duplicate seq changed the card');
    pass('reconnect replays from the per-run cursor so other-run high seq cannot hide our terminal');

    phase = 'pending-replay-cursor';
    const cursorAtSubmit = tracker.lastReceivedSeq;
    const pendingForReplay = beginRun('pending-replay');
    check(tracker.pendingReplayFrom === cursorAtSubmit, 'a pending start did not remember its submit-time cursor');
    const pendingReplay = tracker.replayRequest();
    check(pendingReplay.after_seq === cursorAtSubmit && pendingReplay.run_id === null, 'pending replay request did not use the submit-time cursor');
    claimRun(pendingForReplay, 'pending-replay', 5000);
    pass('a pending start keeps its submit-time replay cursor');

    phase = 'pending-reconnect';
    debug.setGatewayStub(stub, 'connected');
    const pendingNet = beginRun('pending-net');
    tracker.markDisconnected();
    check(tracker.pendingCommandId === pendingNet.command_id, 'a pending start was cleared on disconnect');
    check(tracker.submittedRunId === null, 'a pending start pretended to be confirmed');
    check(cancelButton.disabled, 'cancel should stay disabled while unconfirmed');
    stub.sent.length = 0;
    const replayPending = debug.simulateReconnect();
    const resent = stub.sent.find(message => message.name === 'run.start');
    check(resent && resent.command_id === pendingNet.command_id, 'pending start was not resent with the same command_id');
    check(stub.sent.some(message => message.type === 'replay' && message.run_id === null && message.after_seq === replayPending.after_seq), 'pending replay request was not sent');
    // The hub acknowledges idempotently and the journal replays the accepted event.
    debug.inject({ protocol: 1, type: 'command_ack', command_id: pendingNet.command_id, accepted: true, server_ts: 'x', error: null });
    debug.inject(evt(7000, 'run_accepted', 'accepted', 'queued', { run_id: 'pending-net', command_id: pendingNet.command_id }));
    check(tracker.submittedRunId === 'pending-net', 'the replayed accepted event did not claim the run');
    pass('a dropped socket keeps the pending start and reconnects it idempotently');

    phase = 'pending-reconnect-rejected';
    const pendingRej = beginRun('pending-rej');
    tracker.markDisconnected();
    debug.simulateReconnect();
    debug.inject({ protocol: 1, type: 'command_ack', command_id: pendingRej.command_id, accepted: false, server_ts: 'x', error: { code: 'handler_error', message: '任务标识 pending-rej 已被使用' } });
    check(tracker.pendingCommandId === null, 'a rejected reconnect did not unlock the pending start');
    check(!startButton.disabled, 'start did not re-enable after a rejected reconnect');
    pass('only an explicit rejection unlocks a new task after reconnect');

    phase = 'results-identity';
    const originalFetch = window.fetch;
    const pendingFetches = [];
    window.fetch = url => {
      const record = { url: String(url), resolve: null, reject: null };
      record.promise = new Promise((resolve, reject) => { record.resolve = resolve; record.reject = reject; });
      pendingFetches.push(record);
      return record.promise;
    };
    try {
      const aStart = beginRun('results-a');
      claimRun(aStart, 'results-a', 6000);
      debug.inject(evt(6001, 'run_completed', 'completed', 'completed', { run_id: 'results-a' }));
      check(pendingFetches.length === 1 && pendingFetches[0].url === '/api/runs/results-a', 'completed run did not request its results');
      // Starting a new task must invalidate the in-flight response.
      const bStart = beginRun('results-b');
      pendingFetches[0].resolve({ ok: true, status: 200, json: () => Promise.resolve({ run_id: 'results-a', state: 'completed', complete: true, artifacts: [] }) });
      await sleep(30);
      check(debug.resultsRunId() !== 'results-a', 'a stale response rendered after a new task started');
      check(!$('#run-results-summary').textContent.includes('results-a'), 'stale results leaked into the panel');
      claimRun(bStart, 'results-b', 6002);
      debug.inject(evt(6003, 'run_completed', 'completed', 'completed', { run_id: 'results-b' }));
      const bFetch = pendingFetches.find(item => item.url === '/api/runs/results-b');
      check(bFetch, 'second run did not request its own results');
      bFetch.resolve({ ok: true, status: 200, json: () => Promise.resolve({ run_id: 'results-b', state: 'completed', complete: true, terminal: true, succeeded: true, source_type: 'synthetic_math', seed: 7, configuration_hash: 'abcdef0123456789', artifacts: [
        { artifact_id: 'samples', role: 'sample_table', media_type: 'text/csv', size: 12, previewable: true, url: '/api/runs/results-b/artifacts/samples' },
        { artifact_id: 'spectra', role: 'spectral_table', media_type: 'text/csv', size: 24, previewable: true, url: '/api/runs/results-b/artifacts/spectra' },
      ] }) });
      await sleep(30);
      check($('#run-results-summary').textContent.includes('results-b'), 'current run results were not rendered');
      check($('#run-results-summary').textContent.includes('配置摘要'), 'configuration summary was not shown');
      check($('#run-results-artifacts').textContent.includes('samples'), 'artifact link was not rendered');
      check($('#run-results-artifacts').querySelector('a').getAttribute('href') === '/api/runs/results-b/artifacts/samples', 'artifact link is not the same-origin API URL');
      // Strict URL: a link pointing at another Run must never be rendered.
      debug.loadResults('results-b');
      const crossLinkFetch = pendingFetches[pendingFetches.length - 1];
      crossLinkFetch.resolve({ ok: true, status: 200, json: () => Promise.resolve({ run_id: 'results-b', state: 'completed', succeeded: true, artifacts: [{ artifact_id: 'samples', role: 'sample_table', media_type: 'text/csv', size: 1, previewable: false, url: '/api/runs/results-a/artifacts/samples' }] }) });
      await sleep(30);
      check($('#run-results-artifacts').querySelectorAll('a').length === 0, 'a cross-Run artifact URL was rendered');
      // Identity mismatch stays retryable (not a permanent spinner).
      debug.loadResults('results-b');
      const mismatchFetch = pendingFetches[pendingFetches.length - 1];
      mismatchFetch.resolve({ ok: true, status: 200, json: () => Promise.resolve({ run_id: 'someone-else', state: 'completed', succeeded: true, artifacts: [] }) });
      await sleep(30);
      check(!$('#run-results-summary').textContent.includes('someone-else'), 'a mismatched run_id response was rendered');
      check($('#run-results-note').textContent.includes('失败') || $('#run-results-artifacts').textContent.includes('身份不符'), 'identity mismatch was not reported');
      check(!$('#load-results-btn').disabled, 'identity mismatch did not stay retryable');
      // Preview race: a later preview must not be overwritten by an earlier one.
      debug.loadResults('results-b');
      const previewBase = pendingFetches[pendingFetches.length - 1];
      previewBase.resolve({ ok: true, status: 200, json: () => Promise.resolve({ run_id: 'results-b', state: 'completed', succeeded: true, artifacts: [
        { artifact_id: 'samples', role: 'sample_table', media_type: 'text/csv', size: 12, previewable: true, url: '/api/runs/results-b/artifacts/samples' },
        { artifact_id: 'spectra', role: 'spectral_table', media_type: 'text/csv', size: 24, previewable: true, url: '/api/runs/results-b/artifacts/spectra' },
      ] }) });
      await sleep(30);
      const previewButtons = Array.from($('#run-results-artifacts').querySelectorAll('button'));
      check(previewButtons.length === 2, 'expected two preview buttons');
      previewButtons[0].click();
      previewButtons[1].click();
      const previewFetches = pendingFetches.filter(item => item.url.includes('/artifacts/samples') || item.url.includes('/artifacts/spectra'));
      const spectraFetch = previewFetches.find(item => item.url.endsWith('/spectra'));
      const samplesFetch = previewFetches.find(item => item.url.endsWith('/samples'));
      spectraFetch.resolve({ ok: true, status: 200, text: () => Promise.resolve('spectra,1,2') });
      samplesFetch.resolve({ ok: true, status: 200, text: () => Promise.resolve('samples,9,9') });
      await sleep(30);
      check($('#run-results-preview').textContent.includes('spectra'), 'an earlier preview response overwrote the later one');
      // A failed fetch surfaces an error and stays retryable.
      debug.loadResults('results-b');
      const errorFetch = pendingFetches[pendingFetches.length - 1];
      errorFetch.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) });
      await sleep(30);
      check($('#run-results-note').textContent.includes('失败'), 'failed results fetch was not reported');
      check(!$('#load-results-btn').disabled, 'results fetch failure did not stay retryable');
      // Terminal-but-failed run must not be described as completed.
      debug.clearResults('');
      debug.loadResults('results-failed');
      const failedFetch = pendingFetches[pendingFetches.length - 1];
      failedFetch.resolve({ ok: true, status: 200, json: () => Promise.resolve({ run_id: 'results-failed', state: 'failed', complete: true, terminal: true, succeeded: false, artifacts: [] }) });
      await sleep(30);
      check($('#run-results-artifacts').textContent.includes('failed'), 'a failed run was not reported with its real state');
      check(!$('#run-results-note').textContent.includes('已完成'), 'a failed run was labeled as completed');
      // Empty completed run is reported honestly.
      debug.clearResults('');
      debug.loadResults('results-empty');
      const emptyFetch = pendingFetches[pendingFetches.length - 1];
      emptyFetch.resolve({ ok: true, status: 200, json: () => Promise.resolve({ run_id: 'results-empty', state: 'completed', complete: true, terminal: true, succeeded: true, artifacts: [] }) });
      await sleep(30);
      check($('#run-results-artifacts').textContent.includes('未登记'), 'empty run did not state that no artifacts were produced');
      pass('results requests use identity+generation guards, survive errors, and show empty runs honestly');
    } finally {
      window.fetch = originalFetch;
    }

    phase = 'apple-input-validation';
    const appleScale = $('#apple-scale');
    const appleSeed = $('#apple-seed');
    const appleOriginalScale = appleScale.value;
    const appleOriginalSeed = appleSeed.value;
    appleScale.value = '';
    $('#generate-apple').click();
    check($('#apple-status').textContent.includes('参数错误') && $('#apple-status').textContent.includes('整体大小'), 'empty scale was silently accepted');
    check(appleScale.getAttribute('aria-invalid') === 'true', 'empty scale was not marked invalid');
    appleScale.value = appleOriginalScale;
    appleSeed.value = 'abc';
    $('#generate-apple').click();
    check($('#apple-status').textContent.includes('随机种子'), 'non-numeric seed was not rejected');
    appleSeed.value = appleOriginalSeed;
    $('#generate-apple').click();
    check($('#apple-status').textContent.includes('尚未就绪'), 'a valid apple form should report that Unity is not ready');
    check(!appleScale.hasAttribute('aria-invalid') && !appleSeed.hasAttribute('aria-invalid'), 'a valid apple form kept invalid marks');
    pass('apple generation rejects empty/non-finite active inputs instead of clamping to 0');

    phase = 'connection-failure';
    debug.resetTracker();
    debug.setGatewayStub(null, 'offline');
    const socketsBefore = debug.socketCount();
    $('#connect-btn').click();
    $('#connect-btn').click();
    await waitFor(() => debug.connectionKind() === 'error', 10000);
    await sleep(100);
    check(debug.socketCount() === socketsBefore + 1, 'duplicate connect opened more than one socket');
    check($('#gateway-state').textContent === '连接失败', `gateway state was ${$('#gateway-state').textContent}`);
    check($('#connect-btn').textContent.includes('重试'), 'connect button does not offer retry after failure');
    check(!$('#connect-btn').disabled, 'connect button stayed disabled after a failed connection');
    pass('connection failure is reported with a retry and no duplicate sockets');

    phase = 'runtime-errors';
    check(runtimeErrors.length === 0, runtimeErrors.join(' | '));
    pass('browser runtime has no uncaught errors');

    report.textContent = JSON.stringify({ pass: true, checks: results }, null, 2);
    document.body.dataset.demoHarness = 'pass';
  }

  run().catch(error => {
    report.textContent = JSON.stringify({
      pass: false,
      phase,
      error: error.message,
      state: window.__FruitsimDemoDebug && {
        connectionKind: window.__FruitsimDemoDebug.connectionKind(),
        trackState: Object.assign({}, window.__FruitsimDemoDebug.tracker.state),
        submittedRunId: window.__FruitsimDemoDebug.tracker.submittedRunId,
        pendingCommandId: window.__FruitsimDemoDebug.tracker.pendingCommandId,
        lastReceivedSeq: window.__FruitsimDemoDebug.tracker.lastReceivedSeq,
        appliedRunSeq: window.__FruitsimDemoDebug.tracker.appliedRunSeq,
        loaderFailed: window.__FruitsimDemoDebug.loaderFailed(),
      },
    }, null, 2);
    document.body.dataset.demoHarness = 'fail';
  });
}());
