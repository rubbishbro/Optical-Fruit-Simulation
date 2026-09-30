# Fruitsim 科研教学 Web 前台

前台按教学问题而不是组件类型划分为四页：

1. **光学仿真**：显示 Blender 导入的苹果、十二组环形灯具和探测器；支持拖动旋转、滚轮或按钮缩放、视角复位和全屏。
2. **结果图像**：集中浏览吸收热力图、加权光子路径、光谱热力图、PCA、相关热力图、探测器响应、采样深度和能量审计。
3. **ML 链路**：展示数据校验、数据划分、预处理、特征、候选模型与独立验证。它读取随仓库提交的预计算合成教学 bundle，不在浏览器内重新训练或调用 C++ transport。
4. **运行与审计**：保留 Gateway 连接、Run 启动、状态推进、事件重放，并新增“本次 Run 数据”面板，
   完成后在同一页面读取/下载该 Run 的已登记产物（samples、spectra 等）。

## Unity 交互接口

网页通过 Unity `SendMessage` 调用：

- `FruitsimOrbitCamera.ZoomIn / ZoomOut / ResetView`
- `FruitsimOpticsExperiment.ApplyWebParameters(json)`

参数 JSON 包含波长、灯环相对半径与高度、光源倾角、光束发散角、总相对功率、探测器相对尺寸与偏移、视场角和方向光线开关。可见光按近似显示颜色绘制；780–1100 nm 使用暗红伪彩，不能解读为人眼实际看到的近红外颜色。

## 交互参数与 Manim 动画

Unity WebGL 的预编译只固定程序代码，页面仍可实时传入光学和苹果参数。Manim 生成的是视频；播放时只能控制进度，视频内的数据、文字和镜头已固定。因此动画参数必须在渲染前确定，不能把每次滑块变化直接当作一次 Manim 渲染。

目前的真实链路是：光学表单 → `ApplyWebParameters` → Unity 场景即时变化；波长另发 `viewer.set_wavelength`。`run.start` 只提交数学数据生成的 `seed` 和 `samples`，不提交光学表单参数。`scripts/research/render_snv_teaching_animation.py` 使用固定的合成光谱，也没有读取 Run 或页面参数。因此当前尚无“页面参数 → 对应计算结果 → Manim 视频”的闭环。

## 三类来源与本次 Run 结果（第三批）

页面明确区分三类来源，互不冒充：

- **实时装置预览（Unity，非计算结果）**：光学表单驱动的 Unity 场景即时变化。
- **预计算教学图（非本次 Run）**：结果图表页的 `static/*.png`；**预计算合成教学数据**：ML 页随仓库提交的五组 bundle。
- **本次 Run 数据**：运行页“本次 Run 数据”面板读取当前 Run 的产物。

运行完成后，静态服务器（由 `run_web_demo.sh` 以 `--runs-root <output_root>` 启用）提供受限同源接口：

```text
GET/HEAD /api/runs/<run_id>                          → manifest 摘要 + 登记产物与相对 URL
GET/HEAD /api/runs/<run_id>/artifacts/<artifact_id>  → 下载已登记且白名单 media_type/role 的文件
```

安全边界：仅服务 `artifacts.json` 登记且媒体类型/role 在白名单内的文件；拒绝路径穿越、单/双 URL 编码穿越、
斜杠/反斜杠、`.`/`..`、目录形态、跨 Run、run 与 file 符号链接逃逸、未登记文件，以及 `request.json`/日志
（含指向它们的符号链接别名）。manifest/status/artifacts 三份 metadata 必须为常规文件（符号链接、schema_version 不符、
`run_id` 与 URL 不一致均返回 503；缺失 status/artifacts 不再凭 manifest 假称完整）。摘要不返回服务器绝对路径或
`request.output_dir`，并给出 `complete/terminal/succeeded` 与 `configuration_hash`。未传 `--runs-root` 时接口整体 404。
gzip/brotli、wasm MIME 与 `/health` 行为不退化。artifact 下载先校验 Run 身份与 metadata，再以流式方式发送；HEAD 不读整文件。

前端对结果请求使用 `run_id` 身份 + generation 计数双重校验：开始新任务即清空旧产物；过期或身份不符的响应被丢弃
（身份不符显示可重试错误）；CSV 预览用独立 token 防止旧响应覆盖；失败显示原因并可重试；链接必须精确等于本 Run 的
`/api/runs/<id>/artifacts/<artifact_id>`；math Run 没有新图表/模型时明确显示“未登记可下载的数据产物”，
不回退到预计算图伪装成功。CSV 预览以 `textContent` 渲染。

**注意**：本闭环是“网页任务 → 数学 Run → 本次数据产物可见”，**不是** Unity 参数 → C++ transport → SSC 模型。

拟采用一份不可变的参数快照作为计算和动画的共同依据：

1. 页面把用户选定的实验参数、随机种子和单位整理为 `experiment_spec`。拖动滑块时只更新 Unity/浏览器图表；用户确认后才提交一次计算。
2. 计算服务校验 `experiment_spec` 并保存到 Run；结果清单记录 `run_id`、输入数据摘要、输出数据路径和实际采用的参数。页面通过 `run_id` 展示计算结果。
3. 用户在某个 Run 上选择“生成讲解动画”及场景、样本、教学步骤。服务从该 Run 的结果生成 `animation_spec`；动画数值必须读取同一 Run 的数据，不能重新随机生成。
4. 将规范化的 `animation_spec`、输入数据摘要、Manim 场景版本及画质预设合成缓存键。命中已完成的 MP4 就直接播放；未命中则加入后台渲染队列，页面显示排队/渲染/完成/失败状态。完成后记录 MP4、封面、规格和缓存键，供相同请求复用。

`animation_spec` 的最小内容可表示为：

```json
{
  "scene": "snv",
  "run_id": "example_run",
  "sample_id": "sample_001",
  "steps": ["raw", "mean", "standard_deviation", "transform"],
  "render_preset": "preview"
}
```

计算参数属于 `experiment_spec`；动画只引用 Run，并补充镜头/教学步骤/画质参数。画质预设由渲染服务定义，避免浏览器传入任意分辨率或帧率。动画清单必须显示关联的 `run_id` 和参数摘要；若播放的是通用概念动画，明确标为“示意”，不标成当前实验结果。

为控制渲染量，固定知识点（例如 SNV 公式讲解）可以预渲染少量通用片段；连续参数变化仍由 Unity 或 Canvas 即时展示。只有用户明确选定 Run 和场景时才按需渲染与该结果精确对应的 Manim 动画。可以先生成低画质预览，再对需要交付的片段生成高画质版本。上述计算参数存档、动画任务、缓存与播放器联动是待实现的接口约定，不是现有功能。

## 构建与校验入口

五组合成教学数据集 bundle（`static/ml_datasets/*/ml_p1_bundle.json`）随仓库提交，因此在干净检出上
无需先跑数据生成即可构建。完整流程：

```bash
# 1. 校验静态资源引用（目录 JSON、每个 bundle、页面图像）
python scripts/verify_web_teaching_assets.py --require-catalog

# 2. 查找 Unity 6000.3.23f1、检查 WebGL Build Support，构建、注入教学页面并校验发布目录
bash scripts/build_unity.sh webgl

# 3. 启动静态服务与 Gateway，浏览器打开 http://<host>:8080
bash scripts/run_web_demo.sh
```

`run_web_demo.sh` 会把同一个输出根目录传给 Gateway 与静态服务（`--runs-root`），因此运行页能读取刚创建的 Run。
验证入口：

```bash
# Python 契约/编排/Runs API/脚本级集成
PYTHONPATH=python python -m unittest discover -s python/tests -p 'test_*.py' -v

# 前端真实 DOM（状态隔离/输入拒绝/连接失败/结果竞态，stub 事件）
PYTHONPATH=python python scripts/tests/test_demo_browser.py

# 真实 Gateway + HTTP 结果接口 + 真实 Chrome A/B 集成
PYTHONPATH=python python scripts/tests/test_demo_e2e.py
```

浏览器 A/B runner 会临时启动 Gateway 与静态服务，并通过 URL 参数注入 Gateway 端口（无全局配置）。
本环境无 Unity 编辑器，浏览器中 Unity 场景仍处于“载入失败”，数学 Run 与 ML/DOM 页面可用；Unity 实机表现待验收。

`build_unity.sh` 读取 `apps/fruitsim_unity/ProjectSettings/ProjectVersion.txt`（当前
`6000.3.23f1`），优先在 Unity Hub 安装目录中查找同版本编辑器，可用 `UNITY_BIN` 覆盖；
找不到 WebGL Build Support 时给出提示，设置 `FRUITSIM_REQUIRE_WEBGL_MODULE=1` 可改为硬失败。

发布资源位于 `apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/`；
`apply_webgl_demo_shell.py` 在构建后将 `static/` 复制到 WebGL 根目录的 `static/`。
如需重新生成 bundle（例如修改教学数据），运行 `python scripts/build_ml_teaching_catalog.py`，
它通过 `FRUITSIM_RESULTS_ROOT` 等环境变量读取输入 Run。所有 ML 指标均标注为合成教学数据，
不构成真实苹果 SSC 精度声明，页面光学参数也不会驱动这些 ML 结果。
