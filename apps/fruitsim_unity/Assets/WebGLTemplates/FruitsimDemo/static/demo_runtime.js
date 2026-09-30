/* Framework-free runtime for the Fruitsim web demo.
 *
 * Kept separate from the DOM wiring in index.html so the same validation,
 * event-routing and label logic can be exercised by the headless Chrome DOM
 * harness (static/demo_browser_harness.js).  It deliberately contains no
 * dependency on Unity, the Gateway socket, or any rendering code.
 */
(function (global) {
  'use strict';

  // Mirrors fruitsim_gateway.orchestrator: seed 0..2^31-1, samples 6..5000.
  // MIN_SAMPLES equals fruitsim_pipeline MathSyntheticConfig.batch_count.
  const LIMITS = Object.freeze({
    SEED_MIN: 0,
    SEED_MAX: 2147483647,
    SAMPLES_MIN: 6,
    SAMPLES_MAX: 5000,
    WAVELENGTH_MIN_NM: 400,
    WAVELENGTH_MAX_NM: 1100,
  });

  // field id -> { key: applied payload key, min, max, integer, label }
  const OPTICS_FIELDS = Object.freeze({
    'light-count': { key: 'light_count', label: '环形光源数量', min: 1, max: 64, integer: true },
    wavelength: { key: 'wavelength_nm', label: '波长', min: LIMITS.WAVELENGTH_MIN_NM, max: LIMITS.WAVELENGTH_MAX_NM },
    'ring-radius': { key: 'ring_radius_ratio', label: '灯环半径 / 果实半径', min: 0.5, max: 1.5 },
    'ring-height': { key: 'ring_height_ratio', label: '灯环高度 / 果实高度', min: -1, max: 0.25 },
    'incident-angle': { key: 'incident_angle_deg', label: '光源倾角', min: 0, max: 89 },
    divergence: { key: 'beam_divergence_deg', label: '光束发散半角', min: 0, max: 90 },
    'optical-power': { key: 'optical_power', label: '相对光功率', min: 0, max: 10 },
    'sensor-radius': { key: 'sensor_radius_ratio', label: '探测器半径', min: 0.01, max: 0.5 },
    'sensor-offset': { key: 'sensor_offset_ratio', label: '探测器偏移', min: 0.01, max: 0.75 },
    'sensor-fov': { key: 'sensor_fov_deg', label: '探测器视场角', min: 1, max: 180 },
  });

  // The orchestrator rejects anything that is not a safe identifier.
  const RUN_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$/;

  const STAGE_LABELS = Object.freeze({
    queued: '排队',
    generating: '生成数据',
    completed: '完成',
    control: '控制',
    orchestrator: '任务管理',
    viewer: '预览参数',
    failed: '失败',
  });
  // Honest status vocabulary from the Gateway: queued/generating/completed/
  // control/cancelling.  There is no "光传输模拟" stage in this data pipeline.
  const STATUS_LABELS = Object.freeze({
    idle: '待机',
    queued: '排队中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    cancelling: '取消中',
    updated: '已更新',
    accepted: '已接收',
  });

  const TERMINAL_STATUS = Object.freeze({
    run_completed: 'completed',
    run_failed: 'failed',
    run_cancelled: 'cancelled',
  });

  function parseNumber(raw) {
    if (raw === null || raw === undefined) return { ok: false, reason: '不能为空' };
    if (typeof raw === 'boolean') return { ok: false, reason: '必须是数值' };
    const text = String(raw).trim();
    if (text === '') return { ok: false, reason: '不能为空' };
    const value = Number(text);
    if (!Number.isFinite(value)) return { ok: false, reason: '必须是有限数值' };
    return { ok: true, value };
  }

  function validateInteger(raw, options) {
    const parsed = parseNumber(raw);
    if (!parsed.ok) return parsed;
    if (!Number.isInteger(parsed.value)) return { ok: false, reason: `${options.label}必须是整数` };
    if (parsed.value < options.min || parsed.value > options.max) {
      return { ok: false, reason: `${options.label}必须在 ${options.min} 到 ${options.max} 之间` };
    }
    return { ok: true, value: parsed.value };
  }

  function validateRange(raw, options) {
    const parsed = parseNumber(raw);
    if (!parsed.ok) return parsed;
    if (parsed.value < options.min || parsed.value > options.max) {
      return { ok: false, reason: `${options.label}必须在 ${options.min} 到 ${options.max} 之间` };
    }
    return { ok: true, value: parsed.value };
  }

  function validateOpticsValue(fieldId, raw) {
    const spec = OPTICS_FIELDS[fieldId];
    if (!spec) return { ok: false, reason: '未知参数' };
    return spec.integer ? validateInteger(raw, spec) : validateRange(raw, spec);
  }

  function validateOpticsForm(values) {
    const payload = {};
    const errors = {};
    for (const fieldId of Object.keys(OPTICS_FIELDS)) {
      const result = validateOpticsValue(fieldId, values[fieldId]);
      if (!result.ok) {
        errors[fieldId] = result.reason;
        continue;
      }
      payload[OPTICS_FIELDS[fieldId].key] = result.value;
    }
    payload.show_rays = !!values['show-rays'];
    return { ok: Object.keys(errors).length === 0, payload, errors };
  }

  function validateStartForm(seedRaw, samplesRaw, runIdRaw) {
    const errors = {};
    const seed = validateInteger(seedRaw, { label: '随机种子', min: LIMITS.SEED_MIN, max: LIMITS.SEED_MAX });
    if (!seed.ok) errors.seed = seed.reason;
    const samples = validateInteger(samplesRaw, { label: '样本数量', min: LIMITS.SAMPLES_MIN, max: LIMITS.SAMPLES_MAX });
    if (!samples.ok) errors.samples = samples.reason;

    let runId = null;
    const runText = runIdRaw === null || runIdRaw === undefined ? '' : String(runIdRaw).trim();
    if (runText !== '') {
      if (runText === '.' || runText === '..' || !RUN_ID_RE.test(runText)) {
        errors.runId = '任务名称只能包含字母、数字、下划线、点和连字符，且以字母或数字开头（最长 120 字符）';
      } else {
        runId = runText;
      }
    }
    return {
      ok: Object.keys(errors).length === 0,
      errors,
      runId,
      payload: {
        seed: seed.ok ? seed.value : null,
        samples: samples.ok ? samples.value : null,
      },
    };
  }

  function formatStage(value) {
    if (value === null || value === undefined || value === '') return '-';
    return STAGE_LABELS[value] || String(value).replaceAll('_', ' ');
  }

  function formatStatus(value) {
    if (value === null || value === undefined || value === '') return STATUS_LABELS.idle;
    return STATUS_LABELS[value] || String(value);
  }

  // Active (geometry/visual/pose) apple inputs that are actually applied. The
  // metadata-only fields (height/crown/asymmetry/physical) are intentionally not
  // validated here; empty active fields must be rejected, never silently 0.
  const APPLE_ACTIVE_FIELDS = Object.freeze({
    'apple-scale': { label: '整体大小', min: 0.01, max: null },
    'apple-roughness': { label: '表面粗糙度', min: 0, max: 1 },
    'apple-metallic': { label: '金属感', min: 0, max: 1 },
    'apple-specular-ior': { label: '表面反射', min: 0, max: 1 },
    'apple-ior': { label: '外观折射率', min: 1, max: 3 },
    'apple-spot-density': { label: '斑点密度', min: 0, max: 1 },
    'apple-normal-strength': { label: '表面纹理强度', min: 0, max: 1 },
    'apple-skin-transmission': { label: '表皮透光度', min: 0, max: 1 },
    'apple-pos-x': { label: '位置 X', min: null, max: null },
    'apple-pos-y': { label: '位置 Y', min: null, max: null },
    'apple-pos-z': { label: '位置 Z', min: null, max: null },
  });

  function validateAppleGeneration(values) {
    const errors = {};
    const out = {};
    const seed = validateInteger(values['apple-seed'], {
      label: '随机种子',
      min: LIMITS.SEED_MIN,
      max: LIMITS.SEED_MAX,
    });
    if (!seed.ok) {
      errors['apple-seed'] = `随机种子${seed.reason}`;
    } else {
      out['apple-seed'] = seed.value;
    }
    for (const fieldId of Object.keys(APPLE_ACTIVE_FIELDS)) {
      const spec = APPLE_ACTIVE_FIELDS[fieldId];
      const parsed = parseNumber(values[fieldId]);
      if (!parsed.ok) {
        errors[fieldId] = `${spec.label}${parsed.reason}`;
        continue;
      }
      if (spec.min !== null && parsed.value < spec.min) {
        errors[fieldId] = `${spec.label}必须不小于 ${spec.min}`;
        continue;
      }
      if (spec.max !== null && parsed.value > spec.max) {
        errors[fieldId] = `${spec.label}必须在 ${spec.min} 到 ${spec.max} 之间`;
        continue;
      }
      out[fieldId] = parsed.value;
    }
    return { ok: Object.keys(errors).length === 0, errors, values: out };
  }

  /* Routes broadcast events into the single visible run card.
   *
   * Rules:
   *  - an accepted run is claimed only by the ``run_accepted`` event whose
   *    ``payload.command_id`` matches the command_id this client actually sent
   *    (ProtocolHub copies command_id into the event payload). A matching
   *    ``expectedRunId`` must also agree; an empty requested id lets the server
   *    assign one.
   *  - only ``run_*`` kinds with a run_id may change the run card; viewer and
   *    id-less run events never do;
   *  - seq is tracked per current Run. Replayed/duplicate events for this run
   *    never overwrite newer state, while another Run's higher seq never blocks
   *    this Run's still-missing terminal.
   */
  function createRunTracker() {
    let lastReceivedSeq = 0; // highest seq seen (any kind) -> replay cursor
    let appliedRunSeq = 0; // highest seq applied to the current Run
    let submittedRunId = null;
    let pending = null; // { commandId, expectedRunId } for an in-flight run.start
    const state = {
      status: 'idle',
      stage: '-',
      runId: null,
      runDir: '-',
      terminal: false,
      errorCode: null,
      message: null,
    };

    function reset() {
      state.status = 'idle';
      state.stage = '-';
      state.runId = null;
      state.runDir = '-';
      state.terminal = false;
      state.errorCode = null;
      state.message = null;
    }

    function beginSubmit(commandId, expectedRunId) {
      // Remember the received-seq at submit time so a pending start can be
      // replayed from before its run_accepted even if other runs advance seq.
      pending = {
        commandId: String(commandId),
        expectedRunId: expectedRunId || null,
        replayFrom: lastReceivedSeq,
      };
      submittedRunId = null;
      appliedRunSeq = 0;
      reset();
      state.status = 'queued';
      state.stage = 'queued';
    }

    function rejectSubmit(message) {
      pending = null;
      submittedRunId = null;
      appliedRunSeq = 0;
      reset();
      state.message = message || null;
    }

    // A dropped socket before the server confirmed a start: keep the pending
    // start so reconnect can resend the same command_id (idempotent ack) and
    // replay from the submit-time cursor. Only an explicit rejection unlocks.
    function markDisconnected() {
      if (!submittedRunId && pending) {
        state.status = 'queued';
        state.stage = 'queued';
        state.message = '连接中断，等待重连确认（同一任务标识，不会重复创建）';
      }
    }

    function isActive() {
      return ['queued', 'running', 'cancelling'].includes(state.status) && !state.terminal;
    }

    // Replay cursor: a confirmed run resumes from its own applied seq with a
    // run_id filter, so another run's higher seq cannot hide a missing terminal.
    // A pending start resumes from the seq captured at submit time.
    function replayRequest() {
      if (submittedRunId !== null) {
        return { after_seq: appliedRunSeq, run_id: submittedRunId };
      }
      if (pending) {
        return { after_seq: pending.replayFrom, run_id: null };
      }
      return { after_seq: lastReceivedSeq, run_id: null };
    }

    function ingest(event) {
      if (!event || typeof event !== 'object') return { applied: false, reason: 'not-event' };
      const seq = Number(event.seq);
      if (Number.isFinite(seq) && seq > lastReceivedSeq) lastReceivedSeq = seq;

      const kind = String(event.kind || '');
      if (!kind.startsWith('run_')) return { applied: false, reason: 'not-run' };
      const payload = event.payload || {};
      const eventRunId = payload.run_id || event.run_id || null;

      if (pending && kind === 'run_accepted' && payload.command_id === pending.commandId) {
        if (!eventRunId) return { applied: false, reason: 'missing-run-id' };
        if (pending.expectedRunId && eventRunId !== pending.expectedRunId) {
          return { applied: false, reason: 'run-id-mismatch' };
        }
        submittedRunId = eventRunId;
        pending = null;
        appliedRunSeq = 0;
      }
      if (submittedRunId === null) return { applied: false, reason: 'no-submitted-run' };
      // Strict identity: an id-less run event never touches the run card.
      if (!eventRunId || eventRunId !== submittedRunId) return { applied: false, reason: 'run-id-mismatch' };
      if (!Number.isFinite(seq) || seq <= appliedRunSeq) return { applied: false, reason: 'stale' };
      if (state.terminal) return { applied: false, reason: 'terminal-locked' };

      state.runId = submittedRunId;
      state.stage = String(event.stage || state.stage);
      if (kind === 'run_accepted') {
        state.status = 'queued';
        state.stage = 'queued';
      } else if (kind === 'run_progress') {
        state.status = String(event.status || 'running');
      } else if (kind === 'run_cancel_requested') {
        state.status = 'cancelling';
        state.stage = 'control';
      } else if (Object.prototype.hasOwnProperty.call(TERMINAL_STATUS, kind)) {
        state.status = TERMINAL_STATUS[kind];
        state.stage = String(event.stage || state.stage);
        state.terminal = true;
        state.errorCode = payload.error_code || null;
        state.message = payload.message || null;
      } else {
        state.status = String(event.status || state.status);
      }
      if (payload.run_dir) state.runDir = String(payload.run_dir);
      appliedRunSeq = seq;
      return { applied: true, state: Object.assign({}, state) };
    }

    return {
      state,
      beginSubmit,
      rejectSubmit,
      markDisconnected,
      ingest,
      isActive,
      replayRequest,
      reset,
      get lastReceivedSeq() { return lastReceivedSeq; },
      get appliedRunSeq() { return appliedRunSeq; },
      get pendingCommandId() { return pending ? pending.commandId : null; },
      get pendingExpectedRunId() { return pending ? pending.expectedRunId : null; },
      get pendingReplayFrom() { return pending ? pending.replayFrom : null; },
      get submittedRunId() { return submittedRunId; },
    };
  }

  const debug = {
    sentCommands: [],
    socketCount: 0,
    recordCommand(entry) {
      debug.sentCommands.push(entry);
    },
    lastCommand(name) {
      for (let index = debug.sentCommands.length - 1; index >= 0; index -= 1) {
        if (debug.sentCommands[index].name === name) return debug.sentCommands[index];
      }
      return null;
    },
  };

  global.FruitsimDemo = {
    LIMITS,
    OPTICS_FIELDS,
    RUN_ID_RE,
    parseNumber,
    validateInteger,
    validateRange,
    validateOpticsValue,
    validateOpticsForm,
    validateStartForm,
    validateAppleGeneration,
    APPLE_ACTIVE_FIELDS,
    formatStage,
    formatStatus,
    createRunTracker,
    debug,
  };
})(typeof window !== 'undefined' ? window : globalThis);
