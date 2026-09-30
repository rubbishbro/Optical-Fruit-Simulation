# 展示仿真：耦合链路、重新渲染与 UI/UX 检查

检查日期：2026-09-30。目标是面向讲解/展示的仿真，而非宣称真实苹果糖度预测精度。

## 1. 结论

现有系统可以作为三个并列的演示模块：Unity 仪器预览、数值仿真图表、合成数据 ML 教学。
**目前不能称为“修改当前苹果/灯具参数后，计算同一实验光谱，再更新 ML 和结果”的闭环系统。**

ML 与物理图表已在本次检查中重新计算、重新渲染；Unity 仅完成代码/接口检查，未运行或重新构建。
当前环境没有 Unity 编辑器、WebGL Build Support 或已有 WebGL 发布构建。
没有覆盖仓库中的现有图片、教学 bundle 或应用代码；本次仓库变更仅为这份报告。

## 2. 当前真实链路

```text
网页光学控件 ── SendMessage / ApplyWebParameters ──> Unity 灯具与光线预览
  └─ 波长 ── viewer.set_wavelength ──> Gateway viewer 事件
     （事件不是 detector 光谱计算）

网页运行按钮 ── run.start(mode=math, seed, samples)
  └─ Gateway ── generate-math ──> Run 目录
     （不会自动训练 ML、生成图表或让页面切换到该 Run）

结果图表页 ──> 固定 static/*.png
ML 教学页 ──> 五组预生成 static/ml_datasets/*/ml_p1_bundle.json

独立 CLI ── C++ Monte Carlo ── physical Run ── visualize-run ──> 物理图表
独立 CLI ── math Run ── run-workflow ──> SNV / PCA / CARS / PLSR / 验证
```

证据入口：

- `apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/index.html`：固定图片列表、参数发送、
  Gateway 事件处理和 `run.start` 请求，尤其第 234、251、260–262 行。
- `python/fruitsim_gateway/orchestrator.py`：仅接受 `mode=math`；启动 `generate-math`，完成后仅返回 Run 路径。
- `apps/fruitsim_unity/Assets/Scripts/Optics/IlluminationRigController.cs`：Unity Light 明确为视觉预览；
  虽有 `GetOpticalConfiguration()`，未发现生产代码将其提交到 C++ transport。
- `apps/fruitsim_unity/Assets/Scripts/RunViewer/RunArtifactLoader.cs`：本地文件读取器，不是浏览器的结果 HTTP 接口；
  `FruitsimRunDebugPanel.cs` 在 WebGL 下禁用。
- `docs/architecture.md`、`docs/web-demo.md`：也明确声明当前 Unity 与 ML 不实时依赖。

## 3. 本次实际验证

| 项目 | 结果 | 边界 |
| --- | --- | --- |
| 静态教学资源 | 40 项检查通过 | 文件存在/引用与合成标签检查，不证明运行参数耦合 |
| Chrome ML DOM 交互 | 17 项通过 | 教学/图表切换、样本选择、波长关联、PCA/CARS 分支、暂停/继续等 |
| Python 回归 | 82 项：80 通过，2 跳过 | 两项物理 Run 测试硬编码 `build-mesh/`，未找到该路径 |
| 新建 Debug C++ 构建与 CTest | 3/3 通过 | CPU；没有验证 CUDA 或 Unity |
| 浏览器 → Gateway → math Run | 实际完成 | `review_browser_seed20260930`，60 样本；不是物理计算或 ML 任务 |
| 独立数学 Run | 120 样本 × 51 波长 | `review_math_seed20260930`，seed=20260930 |
| 独立 ML 流程 | 7 个 StageRun 完成 | SNV → PCA/CARS 并列 → CARS 选波长 → PLSR → 验证 |
| 两条参数化 ML 路线 | 通过重载/缓存隔离检查 | 参数不同不会错误共用 CARS 缓存，重载指标与选波长一致 |
| 独立物理 Run | 6 波长 × 20,000 光子 | `review_physical_seed20260930`，CPU，seed=20260930 |
| 数学/物理 Run 审计 | 均为 pass_with_caveats，0 failures | 合成假设、物理 Run 没有实测 SSC 标签 |
| Unity 运行与重新构建 | 未验证 | 环境缺少编辑器和发布构建，不能凭 C# 源码宣布运行正常 |

物理 Run 的有效命中为 **38–47/波长**，最大绝对能量残差为 **1.20394e-5**。
适合展示数据产生与探测过程，不足以仅凭一次随机种子宣称波长优劣；应增加重复种子区间。

本次数学数据的默认 PLSR：80 个拟合样本、40 个分组留出验证样本、11 个特征，
验证 RMSE=0.06440（合成代理值单位），R²=−0.30137。
这说明软件流程执行成功，**不说明该配置有良好的预测能力**；不能把小 RMSE 单独包装为高精度，
也不能将代理值指标写成真实测量 °Brix 精度。

## 4. 展示前应优先解决的问题

### P0：结果身份与状态反馈

1. **新 Run 完成后仍显示旧图片、旧 ML 数据。** 浏览器实测完成后 `figure-image.src`
   仍为 `static/absorption_heatmap.png`，ML dataset 仍为 `synthetic_teaching_clean_signal_v1`。
   运行页“可在图表页面查看”的文案不符合实际链路。
   - 先明确标为“预计算教学图”和“服务端已保存，尚未绑定当前图表”；实现结果读取后才提供“查看本次结果”。
   - 每张图/每次分析显示 `run_id`、`dataset_id`、参数摘要和数据来源；不允许静默回退旧数据。

2. **viewer 事件覆盖计算状态。** 完成 Run 后点击应用光学参数，状态从“已完成”变为
   `updated`，步骤变为 `viewer`。`onmessage` 对所有事件无差别更新运行卡片。
   - 分离 `viewer_state` 和 `run_state`；按事件 kind 和当前 run_id 过滤，历史重放也不能覆盖正在查看的任务。

3. **部分几何控件没有可见效果。** `AppleModels.cs` 的能力声明只把 `scale` 列为有效几何参数；
   `heightRatio`、`crownRatio`、`asymmetry` 仅作元数据。`AppleGenerator.cs` 实际只设置等比例缩放与姿态。
   - 未实现的参数隐藏或禁用，明确“仅记录”；不能让观众把“修改成功”理解为网格已经变形。
   - 当前“随机生成”也不是统计形状模型采样；种子参与身份/纹理，不代表随机苹果几何。

4. **Unity loader 失败没有兜底。** 页面只处理 `createUnityInstance` 的 reject，没有处理 loader
   `<script>` 的 `onerror`。本次直接访问无构建模板时实际一直显示“载入中”。
   - 区分未发布、下载失败、运行失败，提供重试、静态装置图和继续查看 ML 的入口。
   - 这是缺失资源时的容错问题，不是一次真实 WebGL 运行失败的证据。

5. **探测器参数的视觉与定义不一致。** UI 标为“探测器半径 / 果实半径”，而
   `SensorModel.Configure()` 用 `sensorRadius * appleHeight`；有约两倍的量纲解释差异（近球形时）。
   Bootstrap 调用 `UseExternalSensorVisuals()` 后隐藏程序化探测器，未发现将新尺寸/偏移同步给
   Blender 导入的 `DetectorHousing`/`DetectorGlass` 的代码。
   - 统一比例基准并测试；给实际接收孔径/FOV 增加可视轮廓，让展示模型与光学定义一致。
   - 这一项为源码定位，仍需 Unity 实机确认表现。

### P1：交互和演示可靠性

- 批量生成复用相同 pose，没有样本网格/错位陈列；多实例会重叠，控制器仅跟随最后一个样本。
  建议改为单个主样本 + 缩略图列表，而不是默认叠放多个完整仪器 prefab。
- `cancel` 取消的是等待 `asyncio.to_thread(subprocess.run)` 的任务，不显式终止子进程；
  取消提示不能保证计算已停止。建议管理子进程句柄，确认退出后发布取消完成。本次未做取消压测。
- 同名 Run 会被不可变目录规则拒绝，但页面没有自动生成新 ID，错误确认也只显示通用提示。
  默认生成唯一 ID，显示具体错误并提供恢复操作。
- 输入只有 HTML min/max，不等于 JS 提交时已校验。建议拒绝空值/非有限值/越界值，
  与 Unity 和服务端采用一致的范围，不要悄悄转为 0 或单边 clamp。
- `queued/generating/completed/viewer/updated` 等标签未完整中文化；连接按钮也不显示当前可执行动作。
  展示默认应显示简单的中文步骤与错误卡片，调试日志放到折叠面板。
- 1440、720、390 像素宽度未发现页面级横向溢出；窄屏 ML 流程轨道使用局部横向滚动。
  390 像素首屏被来源说明、样本卡和工具栏占满，主要图表还不可见，属于阅读优先级问题。

## 5. 面向展示的 UI/UX 方案

**建议保留科学边界，但把“工程实验台”改成“可讲解的单条故事线”。**

### 展示首页

- 约 65%–70% 空间给 3D 装置，右侧放 3–5 个主要控制：波长、照明几何、样本、显示路径。
- 高级材质、元数据、连接端口、seed 和原始日志默认折叠。当前 20 多项样本输入不宜默认展开。
- 三个明确的状态/来源标签：`实时装置预览`、`预计算教学数据`、`本次计算结果`。
- 常驻一条流程：**装置 → 光谱 → 预处理 → 选波长 → 回归 → 验证**。
  PCA 保持诊断分支，不绘制成所有后续步骤都经过的强制节点。
- 增加“开始讲解”“暂停”“复位”，预设三个故事：认识装置、比较预处理、查看验证结果。
  展示预设必须可复现，不靠随机挑出最好看的模型指标。

### Unity 重新渲染方向

- 使用中性背景、稳定主视角、柔和主光/补光、适度轮廓光，优先看清苹果、灯环与接收孔径，
  不必先追求高成本写实效果。导入材质/玻璃/实际光学参数保持解耦。
- 支持“外观 / 截面 / 采样路径”三种视图；光子路径仅在有对应 Run 数据时标为计算结果。
- 方向光线和 Monte Carlo 轨迹采用不同线型/图例；NIR 伪彩标记常驻，不能只出现在会被替换的状态文本中。
- Unity 展示几何和 transport 几何同时说明。当前 Blender 苹果外观、双层球计算和统计网格计算
  不是同一个对象，不能用画面相似替代几何一致性。
- 展示交互目标：普通参数预览尽量在 100 ms 内反馈；该数值是设计目标，不是本次 Unity 性能实测。

### 数据和 ML 展示

- 统一颜色含义：原始蓝、处理后橙、当前样本高亮、未选特征灰；不要把全体光谱画得比主样本更醒目。
- 默认一个大图、一个比较操作、一句结论，详细说明与矩阵契约按需展开。
- SNV 原始/处理后对照；CARS 保留真实波长顺序；PLSR 散点、1:1 线与残差联合展示。
- 验证面板同时显示 R²、RMSE、目标单位、验证样本数、分组方式和基线对照，负 R² 也应如实可见。
- 物理曲线附有效命中数与统计区间；检测光子的穿透深度不要当成全体光子的深度。
- 投屏默认字号建议 18–20 px 正文、28–32 px 标题；低对比的小字仅保留在高级模式。
- 小屏先呈现“当前步骤 + 主图 + 下一步”，再展开来源、样本和方法说明；支持键盘、可见焦点与减少动效。

## 6. 真正耦合的最小实现顺序

1. **先做来源诚实与状态隔离**：上面的 P0 文案、事件过滤、无效控件与加载兜底，不改物理模型。
2. **以一个实验快照为主键**：确认后冻结 `experiment_spec`，包括 mm 单位、坐标变换、波长、
   source/detector 定义、transport 几何、种子；`visual_style` 单独保存。
   Unity 离散灯具与 C++ 连续环形源并不自动等价，必须定义适配规则和不支持参数的明确拒绝。
3. **打通 Run 结果读取**：安全的 HTTP artifact URL/白名单替代服务端绝对路径；
   完成后页面按 run_id 加载结果，参数改变则标记当前结果过期。
4. **再加入物理任务与数据集适配**：一份物理 Run 当前只有一个样本和 6 个波长，且没有 SSC 标签，
   不能直接接入监督训练。需定义多样本扫描、统一波长网格及可信的教学代理标签/实测标签来源。
5. **最后统一 ML 与演示播放**：从同一 dataset_id 运行 ML，UI 读取真实 StageRun 与验证结果；
   所有动画/缓存关联输入摘要与版本。滑动参数只更新预览，明确确认才排队计算。

对于近期展示交付，更经济的方案是先保留三模块独立结构，清晰标注数据来源，增加故事预设和
可重播的结果。不要为了画面连贯伪造“实时光谱/实时训练”，也不要让每次滑块变化启动重计算。

## 7. 本次重新渲染产物与复现

临时检查产物位于 `/tmp/opencode/fruitsim-review/`，不是随仓库交付的稳定发布资源：

- `rerender_overview.png`：原始光谱、SNV、分组验证预测和独立物理探测响应的四联图。
- `rerender_summary.json`：结果摘要；`browser_review.json`：布局与浏览器 Run 实测记录。
- `runs/review_math_seed20260930/visualizations/`：数学 Run 重新渲染图表。
- `runs/review_physical_seed20260930/visualizations/`：物理响应、路径统计、能量审计图表。
- `ml/experiment.json`、`ml/stages/`：实际重新计算的 ML 阶段与数组。
- `ui_*_1440.png`、`ui_ml_390.png`：当前页面截图，**不是新的 UI 设计稿，也不包含已运行的 Unity 场景**。
- `python-tests.log`：完整回归结果。

本次隔离 Python 环境为 `/tmp/opencode/fruitsim-review-venv/`，新 C++ 构建为
`/tmp/opencode/fruitsim-review-build/`。在装有项目依赖的 Python 环境中可用标准 CLI 重新生成：

```bash
cmake -S . -B build-review -DFRUITSIM_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build build-review --parallel 4
ctest --test-dir build-review --output-on-failure

PYTHONPATH=python python -m fruitsim_pipeline generate-math \
  --output-root results/review/runs --run-id review_math_seed20260930 \
  --samples 120 --seed 20260930
PYTHONPATH=python python -m fruitsim_ml run-workflow \
  --run-dir results/review/runs/review_math_seed20260930 \
  --output results/review/ml --seed 20260930
PYTHONPATH=python python -m fruitsim_ml visualize-run \
  --run-dir results/review/runs/review_math_seed20260930

PYTHONPATH=python python -m fruitsim_pipeline simulate-physical \
  --binary build-review/apps/fruitsim_cli/fruitsim_cli \
  --config configs/sphere_ring_detector.json \
  --output-root results/review/runs --run-id review_physical_seed20260930 \
  --photons 20000 --threads 4 --seed 20260930
PYTHONPATH=python python -m fruitsim_ml visualize-run \
  --run-dir results/review/runs/review_physical_seed20260930
```

Run 是不可变目录，复跑应换新 run_id/输出目录，不覆盖既有结果。
Unity 后续需安装项目指定的 `6000.3.23f1` 和 WebGL Build Support，再运行
`bash scripts/build_unity.sh webgl`；完成后仍应实际检查材质、控件反馈、移动端和帧率。

## 8. R² 为负的补充诊断

用户追问后，使用同一 Run、同一拟合/验证划分进行了对照，不改变应用代码。
本节是诊断性比较，不应据此挑选配置后继续把该验证集当作未见过的最终测试集。

| 配置 | 验证 R² | 验证 RMSE（代理值单位） |
| --- | ---: | ---: |
| 统一预测训练集目标均值 | −0.01196 | 0.05679 |
| 原始全光谱 + PLSR，2 成分 | 0.26219 | 0.04849 |
| SNV 全光谱 + PLSR，1 成分 | 0.01537 | 0.05602 |
| SNV 全光谱 + PLSR，5 成分 | −0.68893 | 0.07337 |
| 默认 SNV + CARS 11 特征 + PLSR，5 成分 | −0.30137 | 0.06440 |

验证目标范围仅 11.08120–11.35127，标准差为 0.05646；默认误差大于目标自然波动。
默认模型拟合集 R²=0.32796、验证 R²=−0.30137，存在泛化不足。
SNV 改变光谱的均值/尺度，可能同时消除本数据生成公式中的目标相关信息；更多 PLS 成分也不一定更好。
这组比较支持“默认链路不适合该数学合成 Run”，不支持“SNV 对所有数据都不适合”。

还确认了 CARS 的特征子集评分实现错误：`python/fruitsim_ml/workflow.py` 的 `_cars()`
在 fold 的 fit/predict 中使用 `X_fit[...][:, :]`，没有使用本轮 `current` 特征子集。
因此 51、37、27、20、15、11 个特征对应的 RMSECV 全部为 0.0857410。
用内存中的函数副本改为 `[:, current]` 后，评分随子集变化，但这次仍选中同一 11 特征，
默认验证 R² 也没有变化。**这是应修复的真实缺陷，但不能宣称它单独造成了本次负 R²。**
现有回归检查覆盖执行、分组边界和缓存等，不足以发现这一数值语义问题，应补专门的特征子集 CV 测试。

建议先修复 CARS 评分与测试，再在训练集内部的分组 CV 比较原始/SG/SNV、全谱/选波长、PLS 成分数，
选定路线后使用新的独立测试数据验证；不能为了展示修改指标或反复挑最好的验证集结果。
诊断记录：`/tmp/opencode/fruitsim-review/ml_diagnosis.json`、`cars_subset_diagnosis.json`。
