# 展示仿真修复待办（执行清单）

## 目标与顺序

按用户确认的顺序：**运行稳定性 → 交互正确性 → 结果衔接 → 数据/ML → UI 风格**。
本轮执行前三项；数据/ML 和视觉重设计不在本轮实施范围。
不改 C++ 物理内核，不通过改数据/指标掩盖界面问题。

链路和实施指导见 [DEMO_COUPLING_HANDOFF.md](DEMO_COUPLING_HANDOFF.md)。
既有检查证据见 [DEMO_COUPLING_UX_REVIEW_20260930.md](DEMO_COUPLING_UX_REVIEW_20260930.md)。
清单只能在有测试证据后标为完成；Unity 编辑器不在环境中，不能把源码检查写成 Unity 实机通过。

## 第一批：运行稳定性

- [x] **R1 启动环境一致**：`scripts/run_web_demo.sh` 支持 `PYTHON_BIN`，Gateway/静态服务共用同一解析后的解释器，
  默认解析 `python3`，提前检查可执行文件并给出含覆盖值的报错。证据：`python/tests/test_run_web_demo.py`（2 项）。
- [x] **R2 Unity 加载容错**：`index.html` 的 loader `onerror` 与 `createUnityInstance` reject 统一走 `loaderFailed()`，
  撤去假进度、显示失败原因并给出“重新载入三维场景”重试；未就绪时 `applyOptics` 明确“参数未发送”，ML 页不受影响。
  证据：`static/demo_browser_harness.js` loader-failure 检查。
- [x] **R3 真正取消/超时**：`orchestrator.py` 改用异步子进程，取消/关闭后台 `_ensure_reaper` 有界
  SIGTERM→SIGKILL→回收；`_terminate_and_reap` 返回是否真正退出，不再假称已终止；超时与取消竞态归类正确。
  证据：`test_orchestrator.py` 新增忽略 SIGTERM 的取消/关闭、reap 诚实性、超时测试。
- [x] **R4 任务输入与身份**：严格 `run_id`/seed/samples 校验拒绝 `.`/`..`、类型与越界；
  所有已分配 ID 记入 `_allocated` 永不复用，默认 ID 自动唯一，`close` 后拒绝新任务。
  证据：`test_orchestrator.py` 复用/关闭/范围一致性测试。
- [x] **R5 可恢复的运行反馈**：ack 拒绝原因、断线/连接中/执行中按钮状态、取消使用已提交的 run_id 而非输入框、
  双击连接只开一个 Socket。证据：`demo_browser_harness.js` 连接失败/输入编辑不误取消/表单拒绝检查。

## 第二批：交互正确性（不是视觉改版）

- [x] **I1 状态隔离**：`static/demo_runtime.js` 的 `createRunTracker()` 按 `kind + run_id + seq` 过滤；
  viewer、其他 Run、旧序号与终态后事件均不覆盖当前卡片。证据：harness state-isolation 检查。
- [x] **I2 波长/其他参数校验**：前端 `validateOpticsForm`/`validateStartForm` 拒绝非有限、空白与越界且不发送；
  服务端 `handle_viewer_wavelength` 校验 400–1100 nm；NIR 伪彩说明独立成 `#nir-note`，不被瞬态状态覆盖。
  证据：harness optics-rejection 检查、`test_gateway_viewer.py`。
- [x] **I3 能力诚实**：高宽比/顶部凹凸/不对称度禁用并注明仅记录；种子不生成新几何；
  物理参数注明为元数据、未传入 transport。证据：harness capability-honesty 检查。
- [x] **I4 探测器定义一致**：标签改为“探测器半径 / 果实高度”，新增说明 SensorModel 按果实高度缩放、
  导入模型为固定尺寸不随参数/FOV 实时改变。证据：harness detector-label 检查。
- [x] **I5 批量生成反馈**：禁用“批量生成”入口并解释同 pose 重叠、控制器只跟随最后样本，底层 `GenerateBatchJson` 保留。
  证据：harness capability-honesty 检查。
- [x] **I6 前端回归**：新增真实 DOM harness `static/demo_browser_harness.js` + runner `scripts/tests/test_demo_browser.py`
  （实际 24 项）；原 17 项 ML DOM 检查保持通过。证据：两个 runner 均 exit 0。

## 第三批：结果衔接（最小真实闭环）

- [x] **C1 三类来源清楚**：`index.html` 增 `#unity-source-tag`（实时装置预览（Unity，非计算结果））、
  `#figures-source-tag`（预计算教学图（非本次 Run））、运行页“本次 Run 数据”面板；删除“可在图表页面查看”不实文案。
  证据：`test_demo_browser.py` + `test_demo_e2e.py` 来源标签断言。
- [x] **C2 同一 Run 可读取**：`scripts/serve_webgl_demo.py` opt-in `--runs-root` 提供
  `GET/HEAD /api/runs/<run_id>`（manifest 摘要 + 登记产物相对 URL）与
  `GET/HEAD /api/runs/<id>/artifacts/<artifact_id>`；不返回绝对路径/`request.output_dir`。
  证据：`python/tests/test_serve_webgl_demo_api.py`、`test_run_web_demo_e2e.py`。
- [x] **C3 结果入口可用**：完成后自动加载并可点击“查看本次数据产物”，列出 samples/spectra 等下载链接与
  可选 CSV 文本预览；无新图/模型时明确“未登记可下载的数据产物（没有生成新的图表或 ML 模型）”。
  证据：`test_demo_browser.py` results-identity、`test_demo_e2e.py`。
- [x] **C4 防旧结果/请求竞态**：新任务 `clearResults()`；`loadResults` 带 identity + generation 双守卫，
  身份不符或过期响应丢弃（身份不符显示可重试错误，不再永久“正在读取”）；预览使用独立 token；
  失败可重试并显示原因；摘要含 run_id/state/complete/terminal/succeeded/seed/来源/时间/configuration_hash。
  证据：`test_demo_browser.py` results-identity（stub fetch、preview 竞态、跨 Run 链接拒绝）。
- [x] **C5 文件读取安全**：路径穿越/单双编码/斜杠反斜杠/`.`/`..`/目录形态/跨 Run/run 与 file 符号链接逃逸/
  未登记/媒体类型与 role 不在白名单/`request.json`、`logs` 及 **resolve 后别名**（symlink→request.json/logs）均被拒绝；
  manifest/status/artifacts 三份 metadata 为符号链接、schema_version 不符或 run_id 与 URL 不一致一律 503；
  status/artifacts 缺失返回 503 而非凭 manifest 假称完整；默认不启用；gzip/wasm MIME 与 health 保持。
  证据：`test_serve_webgl_demo_api.py`（19 项，含 raw 未规范化穿越、别名、metadata 完整性）。
- [x] **C6 集成验收**：`run_web_demo.sh` 把同一 `output_root` 传给 Gateway 与静态服务；
  真实脚本启动后 WS 建 Run 并 HTTP 读取同 Run（`test_run_web_demo_e2e.py`）；
  真实浏览器 A/B 两个小样本 Run 各自身份/URL 独立，静态图与 ML bundle 来源不被污染
  （`scripts/tests/test_demo_e2e.py`）。

> 本批的“闭环”是网页任务 → 数学 Run → 本次数据产物可见。
> **不是** Unity 参数 → C++ transport → SSC 模型。后者仍需另立实现任务。

## 第四批：数据与 ML（本轮延期）

- [ ] **M1 CARS 数值缺陷**：交叉验证必须评估本轮 `current` 特征子集，补语义测试。
- [ ] **M2 默认配置**：在训练集内部的分组 CV 比较预处理、全谱/选波长和 PLS 成分数；
  独立测试，不用已反复查看的验证集宣布最终效果。
- [ ] **M3 合成教学数据**：调整信号/噪声/目标范围与教学预设，保留清晰合成边界。
- [ ] **M4 完整物理耦合**：定义 experiment_spec、坐标/单位、离散灯具与连续环形源适配，
  多样本谱矩阵及标签来源；未实现参数显式拒绝，不擅自声称真实 SSC 预测。

## 第五批：UI 风格（最后处理，本轮延期）

- [ ] **V1** 配色、字体、间距、组件、布局与投屏视觉统一。
- [ ] **V2** 3D 灯光/材质/背景与外观、截面、轨迹视图。
- [ ] **V3** 讲解预设、主图优先、小屏阅读顺序与展示模式。

## 执行记录

| 批次 | 执行者 | 状态 | 验收证据/阻塞 |
| --- | --- | --- | --- |
| 1 | OpenCode Go 代理（DeepSeek V4.1 Flash）；主会话复核 | 已验收（当前可验证范围） | 主会话独立重跑 Python 135 项：133 通过 / 2 跳过；含真实脚本 E2E |
| 2 | OpenCode Go 代理（DeepSeek V4.1 Flash）；主会话复核 | 已验收（Unity 实机待验收） | 主会话独立重跑 demo DOM 24 项、ML DOM 17 项；原 inline CSS 未变，未改物理/ML/数据源码 |
| 3 | OpenCode Go 代理（DeepSeek V4.1 Flash）；主会话复核 | 已验收（本地数学 Run 闭环） | Runs API 安全 20 项、真实脚本 E2E（含幂等重发）、主会话独立重跑真实浏览器 A/B E2E |
| 4 | 待安排 | 延期 | 本轮不改 ML 和数据 |
| 5 | 待安排 | 延期 | 用户要求 UI 风格最后处理 |

复核修订轮（主会话 9 条）：按 command_id+expectedRunId 认领本客户端 run_accepted；start 被拒可恢复重试、viewer 拒绝不影响 Run；
断线重放改用 appliedRunSeq + run_id filter 专门游标、pending 保留提交时游标并在重连时同 command_id 重发（幂等 ack + journal 重放），
hello 不设游标；cancel 需联网且已确认；始终刷新 runPath；未真正回收不伪报 cancelled（发 cancellation_failed）；
partial Run 终态原子同步且 completed 不被迟到取消覆盖；loader 同步失败入口；默认名留空由服务端生成唯一 ID。
末轮补强（A–F）：metadata 三文件禁止符号链接/校验 schema 与 run_id、缺失即 503；artifact 别名（symlink→request.json/logs）拒绝；
artifact_id 白名单与去重抽出单一 helper；summary 增 terminal/succeeded/configuration_hash；HEAD 不整读 body；
结果身份不符可重试、preview 独立 token、链接严格同 Run；苹果 active 字段空/非有限拒绝而非静默 0。
主会话末轮额外补验：manifest/status 的 run_id 缺失也返回 503，摘要和下载均拒绝；批量说明改为“控制器只跟随最后样本”，不误称其余实例已删除。
证据：`test_orchestrator.py`（28 项）、`test_demo_browser.py`（24 项）、`test_serve_webgl_demo_api.py`（20 项）、
`test_run_web_demo_e2e.py`（1 项，含幂等重发）、`scripts/tests/test_demo_e2e.py`（真实浏览器 A/B）。
主会话同时重跑静态资源 44/44、C++ CTest 3/3，`git diff --check` 通过。
完整 Python 验收日志：`/tmp/opencode/fruitsim-review/fix-verified-python-tests.log`（临时证据）。

## 统一完成条件

- 不改 `src/transport/`、`src/cuda/`、物理配置和教学数据指标来解决前端问题。
- 不覆盖用户已有改动/结果，不提交 git commit，不修改 OpenCode 全局模型配置。
- 新增问题对应的回归测试；Python、静态资源、ML DOM 检查通过，跳过项如实记录。
- Unity 专属表现记录为待实机验收，不伪造截图/帧率/构建成功。
- 清单完成项带文件与测试证据，不用“已修改代码”替代验证。
