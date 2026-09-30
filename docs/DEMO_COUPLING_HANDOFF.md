# 耦合链路与 V4.1 Flash 实施指导

## 0. 执行约束

本文件是交接指导，不是关于现有功能已完成的声明。
用户指定按 [DEMO_FIX_TODO.md](DEMO_FIX_TODO.md) 的顺序修复，**UI 风格最后处理**。
本轮只实施第一至第三批：稳定性、交互正确性、最小 Run 结果衔接。
数据生成算法、ML 调参、CARS 修复和完整物理参数耦合留待第四批。

实施用模型：用户确认使用 OpenCode Go 通道的 DeepSeek V4.1 Flash，
`opencode-go/deepseek-v4.1-flash`。首批已有少量 DeepSeek 直连的后端改动，保留并复核后继续，不丢弃。
本轮主会话审查实现与结果；不要改变项目/全局模型配置，也不要启动嵌套代理。

先读现有文件再编辑，不重写整个前端、不引入新的前端框架；必要 JS helper 可单独提取以便测试。
若新增 Unity `Assets` 文件，遵循已有 `.meta` 约定。
保持页面配色、排版、导航和 ML 教学样式；只允许必要的状态、错误、能力说明、禁用控件与结果入口。

## 1. 文件级链路

### A. 启动与发布

```text
scripts/build_unity.sh webgl
  → Assets/Editor/FruitsimBuild.cs
  → Unity WebGL Build/{loader,framework,wasm,data}
  → scripts/apply_webgl_demo_shell.py
  → WebGLTemplates/FruitsimDemo/index.html + static/

scripts/run_web_demo.sh
  ├─ python -m fruitsim_gateway  (WebSocket :8765)
  └─ scripts/serve_webgl_demo.py (HTTP :8080)
```

- 模板文件不能直接当成真实 Unity 构建；`{{{ LOADER_FILENAME }}}` 等由构建注入脚本替换。
- `serve_webgl_demo.py` 负责 `.gz/.br` 的 Content-Encoding 与原文件 MIME，不要破坏。
- Gateway 输出根由 `FRUITSIM_DEMO_OUTPUT_ROOT` 控制；新增 HTTP 读取必须使用同一根目录。
- 当前脚本硬编码 `python`，本环境只有 `python3`；兼容 `PYTHON_BIN` 而非要求修改系统 PATH。

### B. 网页 → Unity（预览链路）

入口：`apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/index.html`。

```text
光学 input change / 应用按钮
  → applyOptics() → sendUnity()
  → SendMessage('FruitsimOpticsExperiment', 'ApplyWebParameters', json)
  → Optics/IlluminationRigController.ApplyWebParameters()
  → dirty → LateUpdate → RebuildRig()
  → 动态灯具、光线 + OpticalConfiguration（目前没有生产 transport 消费者）

苹果生成
  → GenerateAppleJson / GenerateBatchJson
  → FruitsimAppleGeneratorBridge
  → AppleGenerator 实例化 FruitsimBlenderRig
  → AppleChanged → controller.SetAppleRoot() 与相机复位
  → Plugins/WebGL/FruitsimAppleCallbacks.jslib → 浏览器状态回调

相机按钮 → FruitsimOrbitCamera.ZoomIn / ZoomOut / ResetView
```

关键文件：

- `Assets/Scripts/Optics/FruitsimOpticsBootstrap.cs`：创建装置，使用外部导入探测器视觉。
- `AppleModels.cs`：`AppleGenerationCapabilities` 是当前能力依据。
- `AppleGenerator.cs`：目前仅 scale/pose 改几何，其余三个形状字段只记录。
- `SensorModel.cs`：目前半径实际为 `sensorRadius * appleHeight`，不是 appleRadius；
  参数化传感器视觉被 `UseExternalSensorVisuals()` 隐藏，不代表导入模型跟随了参数。
- `Assets/Scripts/WebGL/FruitsimWebSocketClient.cs` 和 `.jslib` 存在，不代表网页已使用它提交计算；
  当前网页有自己的 WebSocket，不能把两套入口误当成自动同步。

本轮保守策略：无效能力标明/禁用；保留已实现行为，不未经 Unity 验收就改 prefab/传感器尺度。
批量入口可禁用并说明同 pose/最后样本限制，不需开发新样本陈列 UI。

### C. 网页 → Gateway → Run（已运行的数据生成链路）

```text
connect() → WebSocket ws(s)://hostname:8765
  → Gateway/server.py: ProtocolServer 握手与 hello
  → replay(after_seq) / command
  → validate_message() → ProtocolHub.handle()
  → command_id 幂等 ack
  → __main__._demo_handlers()
      ├─ run.start → RunOrchestrator.accept_start()
      │   → _execute() → python -m fruitsim_pipeline generate-math
      │   → RunManager → manifest/status/artifacts/data
      │   → run_completed 或 run_failed
      ├─ run.cancel → accept_cancel()
      └─ viewer.set_wavelength → viewer_state（没有物理计算）
  → EventJournal(seq) → broadcast/replay → 网页 onmessage()
```

协议文件：`python/fruitsim_protocol/messages.py`、`journal.py` 和 `data/schemas/*`。
不要修改 protocol=1 的字段要求或移除 command_id 幂等机制。

当前严重问题：网页对所有 `event` 都更新同一 run-state，viewer 与其他 Run 会污染卡片。
修复须以 `kind + run_id` 判定，不仅凭 `stage` 或 `status` 字符串。
前端需区分编辑中的任务名、实际已提交任务 ID 和正在查看结果的任务 ID，避免编辑框变化误取消旧任务。
重放/历史事件可以保留日志，但不得覆盖较新序号的状态或当前任务；序号水位与状态更新分开管理。

### D. Run 合同与产物

```text
Run 根/<run_id>/
  ├─ request.json
  ├─ manifest.json  (run_id/source_type/seed/configuration_hash/status)
  ├─ status.json
  ├─ artifacts.json → artifacts[].{artifact_id,relative_path,role,media_type,sha256}
  ├─ data/samples.csv, spectra.csv, spectra.npz, synthetic_math_manifest.json
  └─ ml/input_long.csv
```

- `RunManager.create()` 拒绝覆盖已有目录；不要为了重试删除历史结果。
- `_RUN_ID_RE` 当前会允许 `.`/`..`，必须额外拒绝路径特殊名/目录逃逸。
- seed/samples 用 `int()` 和 clamp 会容忍不合适的输入；前后端应严格拒绝而不是误报已采用原始输入。
- Run 文件是原子 JSON 写入，目录可能处于生成中，HTTP 不应据目录存在就宣称任务完成。

### E. 独立物理/ML 与静态展示（当前不自动耦合）

```text
configs/sphere_ring_detector.json → C++ CLI → summary/instrument/trajectories
  → fruitsim_pipeline simulate-physical → synthetic_physics Run
  → fruitsim_ml visualize-run → visualizations/*.png

math Run → fruitsim_ml run-workflow
  → PipelineEngine → SNV / PCA 与 CARS 并列 / CARS.select / PLSR / 验证
  → experiment.json + stages/*.json

结果页 → 固定 static/*.png
ML 页 → static/ml_p1_datasets.json → 五组 bundle
```

`Assets/Scripts/RunViewer/RunArtifactLoader.cs` 是本地文件读取器，WebGL 下的 debug panel 禁用。
它不是远端 HTTP 结果 API；不能把后端 `/home/.../run_dir` 传给浏览器就认为能读取。

## 2. 第一批关键设计：取消、超时与状态

建议替换 `asyncio.to_thread(subprocess.run)` 为 `asyncio.create_subprocess_exec()`：

- 保存每个 Run 的任务/进程句柄；cancel 的请求确认与进程退出后的终态事件分开。
- 捕获 stdout/stderr；等待采用超时；超时/取消先 terminate，再有限时间等待，必要时 kill，再 await 回收。
- 处理取消发生在进程句柄登记之前；不要留下未等待的后台进程。
- `close()` 应清理活动任务/进程；终态只发一次；关闭失败必须如实报告。
- 如需取消时同步部分 Run 状态，使用受限原子写入且不得修改已 completed/failed 的 Run；
  不重写 `RunManager` 合同来掩盖进程仍在工作。
- 日志/事件最大尺寸合理，用户输入不拼接 shell 命令；保留 `cwd/env/PYTHONPATH` 的现有语义。

测试使用受控长任务/失败任务，而不是靠快 math Run 碰运气：断言进程实际退出、无后续完成事件、
超时归类正确、服务 close 后不存活、立即取消竞态安全、正常成功路径不退化。

## 3. 第二批关键设计：功能反馈，不改风格

- 输入采用 `checkValidity()/reportValidity()` 配合有限/整数检查；先验证再发送，不发送错误的 viewer 命令。
- 波长服务端也校验 400–1100 nm；`viewer_state` 只更新 viewer 信息，不更新 Run 卡片。
- 不以 SendMessage 返回 true 宣称 Unity 已经完成 rebuild；至多表示请求已发出/预览参数已提交。
- loader 的 `onerror` 与实例初始化 reject 用统一错误入口；失败时撤去假进度并给重试。
- 翻译实际 Gateway 的 queued/generating/completed/control/cancelling 等标签，不编造未执行的“光传输模拟”。
- 高宽比/顶部凹凸/不对称度、物理参数、随机种子的效果边界根据能力声明写清楚。
- 避免重复开 Socket，旧 Socket 回调不能污染新连接；断线/重连不冒认历史已完成任务为当前提交。

## 4. 第三批关键设计：受限 HTTP 结果接口

使用现有静态服务器，增加显式 opt-in `--runs-root`，由 `run_web_demo.sh` 传同一 output_root。
建议接口（实施时记录最终路径）：

```text
GET /api/runs/<run_id>                      → Run 摘要 + 产物条目与相对 URL
GET /api/runs/<run_id>/artifacts/<artifact_id> → 下载已登记、允许类型的文件
```

安全约束：

- 校验 URL 解码后的 run_id/artifact_id，拒绝点目录、斜杠/反斜杠、编码穿越、非法 Unicode 路径；
  不能直接 `translate_path()` 到任意结果目录。
- 先 resolve Run 再确认在 runs_root 内；resolve 产物路径后确认在同一 Run 内，拒绝 symlink 逃逸。
- 仅允许 artifacts.json 登记且允许的媒体类型/role；不开放任意文件、执行模型、日志目录、目录列表。
- 返回摘要不能暴露机器绝对路径/任意 request 内容；相对 path/URL 用安全编码。
- 失效登记/损坏 JSON/文件不存在/未完成状态返回明确错误或非完成摘要，不悄悄回退 static 图片。
- 不做反序列化 joblib/pickle；不把 CSV 单元格通过 innerHTML 渲染；异常消息不暴露完整服务器路径。
- GET/HEAD 行为一致；保留静态压缩头与健康检查；未启用 runs_root 时 API 不暴露目录。

前端完成态提供“查看本次数据产物”入口、Run 摘要和下载列表即可。
本轮不自动生成模型/新图片、不修改 immutable Run 的产物索引；没有新图/ML 时明确说明未生成。
静态图和五组 ML bundle 继续工作且标为预计算示例，不让 run.start 自动改它们。

> 实施记录（C1–C6）：最终接口为 `GET/HEAD /api/runs/<safe_run_id>` 与
> `GET/HEAD /api/runs/<run_id>/artifacts/<artifact_id>`；仅 `--runs-root` 启用，
> 允许媒体类型 `text/csv`、`text/plain`、`application/json`、`application/octet-stream`
> 且 role 在白名单内。metadata 三文件禁止符号链接并校验 schema_version 与 run_id，
> 缺失/损坏返回 503；artifact 符号链接别名（→request.json/logs）拒绝；摘要含
> `complete/terminal/succeeded` 与 `configuration_hash`。run_web_demo.sh 传同一 output_root。
> 测试见 `python/tests/test_serve_webgl_demo_api.py`、`test_run_web_demo_e2e.py`、
> `scripts/tests/test_demo_browser.py`、`scripts/tests/test_demo_e2e.py`。

## 5. 验证与环境

已创建的隔离 Python：`/tmp/opencode/fruitsim-review-venv/bin/python`，含 NumPy/pandas/SciPy/sklearn/Matplotlib。
系统 Python `python3` 不含这些依赖；`python` 命令不存在。Node 未安装；Chrome 命令可用。
Unity 编辑器不存在，desktop browser 工具未连接；可用 headless Chrome 做实际 DOM 验证，不模拟 Unity 已运行。
C++ 验证构建：`/tmp/opencode/fruitsim-review-build/`，本轮不需改动其源代码。

```bash
PYTHONPATH=python /tmp/opencode/fruitsim-review-venv/bin/python \
  -m unittest discover -s python/tests -p 'test_*.py' -v
python3 scripts/verify_web_teaching_assets.py --require-catalog
PYTHONPATH=python /tmp/opencode/fruitsim-review-venv/bin/python scripts/tests/test_ml_browser.py
ctest --test-dir /tmp/opencode/fruitsim-review-build --output-on-failure
```

新增测试至少覆盖：

1. viewer/其他 Run/旧事件不污染当前任务；拒绝无效输入和 loader 失败的实际 DOM 行为。
2. 任务取消/超时/关闭/失败/重复 ID/正常成功，验证实际进程生命期。
3. HTTP 读取正常 CSV/JSON、404、穿越/编码/符号链接/未登记文件/HEAD，以及原 gzip MIME。
4. 浏览器与真实 Gateway/HTTP 的小规模集成；来源标签和当前产物身份一致。

前端测试若仅用静态源码字符串断言，不能替代 DOM 行为测试。
所有服务/长任务测试结束清理进程；输出写临时/忽略目录，不覆盖当前报告证据。

## 6. 交付要求

每批完成后返回：改动文件、实现要点、测试命令/结果、仍被环境阻塞的项目。
按测试证据更新待办清单；主会话复核后再标“已验收”。
未经测试不要写“全部修复”，不要 commit/push，不改待延期的第四/第五批。
