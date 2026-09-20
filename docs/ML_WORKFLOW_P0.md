# Fruitsim ML 可视化重构 P0

## 1. 原架构诊断

旧入口集中在 `python/fruitsim_ml/train.py`：通过配置文件展开“特征集 × 预处理 × 模型”的组合，直接保存 `metrics.json`、`predictions.csv` 和 `cv_folds.csv`。其中的 SNV、Savitzky–Golay、PLSR 和现有交叉验证逻辑可以复用，但算法之间没有统一的输入/输出类型。

`features.py` 负责把 CSV 透视成裸 `numpy.ndarray`，`visualize.py` 主要从 Run 目录直接生成 PNG。这样最终图可以保存，却无法可靠重载预处理、PCA 投影、CARS 变量淘汰或 PLSR 预测的中间状态。

现有 `fruitsim_pipeline` 已经有 RunManager、manifest、随机种子、审计和 artifact 契约，因此新的 ML 实验结构放在 `fruitsim_ml.workflow`，不破坏旧训练入口。C++ GUI 已经使用 ImGui/ImPlot，WebGL 页面已经存在，因此两端都通过 `experiment.json` 的结构化摘要读取，不各自复制算法状态。

## 2. 新架构

核心对象关系如下：

```text
SpectrumSet
  -> Method.execute()
  -> MethodExecutionResult
  -> StageRun
  -> ExperimentRun.stage_runs[]
  -> structured intermediate states / renderer / UI
```

`Method` 描述单一算法，带有 `stage`、`input_type`、`output_type`、参数 schema 和执行函数。`MethodRegistry` 负责注册和解析算法，`PipelineDefinition.validate()` 根据类型和阶段校验组合，不允许把 PLSR 接到预处理阶段，也不允许把 Prediction/ModelResult 接到 PCA。

`StageRun` 保存一次阶段执行的输入引用、输出引用、方法链、参数、随机种子、统计量、执行元数据和 `IntermediateState`。它可以独立保存为 JSON，并从 JSON 重载。

`ExperimentRun` 保存完整 pipeline definition、dataset id、阶段列表、最终模型、最终指标、配置快照和 artifact 引用。它不是单纯的 RMSE 记录。

统一数据对象包括：

- `SpectrumSet`：光谱矩阵、波长、sample id、目标值、batch metadata。
- `LatentFeatureSet`：PCA 等潜变量矩阵、组件名、loadings。
- `FeatureAnalysisResult`：PCA/CARS 分析结果、选中特征、统计量和原始输入引用。
- `SelectedFeatureSet`：真正交给模型的矩阵、选中特征索引和波长名。
- `PredictionSet`：sample id、真实值、预测值、残差、split 和 fold id。
- `EvaluationResult`：RMSE、MAE、R²、CV RMSE、bias、样本数和特征数。

## 3. 已实现的固定 Stage Pipeline

默认教学路线为：

```text
Data Inspection
  -> SNV
  -> Feature Analysis[PCA, CARS]
  -> Feature Selection[CARS selected wavelengths]
  -> Modeling[PLSR]
  -> Experiment Results
```

同一阶段比较通过 `run_preprocessing_comparison()` 实现，支持：

```text
Raw
SNV
Savitzky–Golay -> SNV
```

这些路线共享同一个 `SpectrumSet`、sample id 和 wavelength axis，并由 `StageCache` 缓存；切换时不重复计算。

分组数据会在 PCA、CARS 和 PLSR 拟合前先划分 calibration/validation。PCA、CARS 只在 calibration rows 上拟合，PLSR 只在 calibration rows 上训练，validation rows 只用于最终评估。随机种子和 split 索引写入 ExperimentRun。

## 4. 已接入算法与中间状态

- Raw passthrough：保留原始曲线，生成 `morph_curve` 状态。
- SNV：保存 raw spectrum、sample mean、sample std、normalized spectrum。
- Savitzky–Golay：保存 raw/smoothed spectrum、window 和 polyorder。
- PCA：保存 centered matrix、scores、loadings、explained variance ratio。
- CARS：保存每一轮 retained indices、absolute coefficients、RMSECV progression；后续动画可以直接使用 `remove_features` 事件。
- CARS selection：保存最终 selected indices 和 selected feature names。
- PLSR：保存 latent scores、coefficients、predictions、residuals 和评估指标。

当前没有重新实现 MSC、VIP、SVR 或 Random Forest；它们作为后续新增 Registry Method 的扩展点，避免为了凑算法数量修改现有数学行为。

## 5. UI 入口

WebGL 研究工作台的 ML 页面增加了结构化 Stage Navigator：

- Data
- Preprocessing
- Feature Analysis · PCA
- Feature Analysis · CARS
- Feature Selection
- Modeling
- Results

每页显示 StageRun id、方法链、input reference、output kind/reference、参数、统计量、中间状态数量和未来动画事件名。CARS 和 Results 已通过浏览器前台实测。

C++ ImGui GUI 增加 `ML Stage Navigator` 窗口：可以从当前 Run 目录执行 `fruitsim_ml run-workflow`，也可以加载 `experiment.json`，用 ImGui Tab 查看各个 StageRun。原有 C++ 模拟、旧 ML 比较和 ImPlot 图表保持兼容。

## 6. Unity AppleGenerator

Unity 新增：

- `AppleModels.cs`
- `AppleGenerator.cs`

接口示例：

```csharp
AppleInstance instance = generator.GenerateApple(
    seed,
    geometryParameters,
    visualMaterial,
    physicalProperties,
    pose);
```

`AppleInstance` 返回稳定的 `sampleId`、seed、参数快照、Unity object reference 和容器 object reference。当前 sample id 规则为 `unity-apple-{seed:D10}`，同一 seed 可重现同一单颗样本标识。

`ApplePhysicalProperties` 与 `AppleVisualMaterial` 是独立对象。SSC、水分、吸收和散射参数只作为物理 metadata，不直接决定视觉材质；颜色、粗糙度、斑点密度和法线强度只属于视觉层。

当前生成器复用已导入的 Blender rig，未重新制作视觉材质，也未提前扩展批量生成 UI。

## 7. 调用方法

从已有 Run 执行结构化实验：

```bash
PYTHONPATH=python python -m fruitsim_ml run-workflow \
  --run-dir results/frontend_acceptance_20260920/student_demo_final/math_seed20260919 \
  --output results/ml_workflow_demo
```

生成：

- `results/ml_workflow_demo/experiment.json`
- `results/ml_workflow_demo/stages/*.json`

重新读取：

```python
from fruitsim_ml.workflow import ExperimentRun
experiment = ExperimentRun.load("results/ml_workflow_demo/experiment.json")
```

## 8. 测试结果

- 新增工作流测试：4/4 通过。
- 验证 StageRun 保存/重载、阶段类型校验、Raw/SNV/SG 比较缓存和 CARS 中间状态。
- ImGui GUI 当前源码构建成功。
- Unity WebGL 构建成功，新增 C# 脚本通过 Unity 脚本编译。
- 浏览器前台确认 Unity READY、六阶段 ML 页面、CARS 中间状态、Results 指标和 Web 控制台无错误。

## 9. 尚未解决的问题

- 当前 CARS 是面向教学和架构验证的稳定实现，不是最终论文级参数寻优版本。
- Web 静态图集仍是发布时打包的 source-backed bundle；新实验的动态图表尚未通过 Gateway 实时刷新。
- ImGui 当前展示 StageRun 摘要，尚未绘制所有中间矩阵和 residual 图。
- Unity `AppleInstance` 已与视觉场景连接，但 sample metadata 尚未通过 WebSocket 自动写入服务端 Run manifest。
- 真实实验数据仍需通过已有 experimental dataset v2 校验后再进入 calibrated workflow。

## 10. P1 建议顺序

1. 把 StageRun 中间数组导出为轻量 NPZ/Arrow artifact，并由 Web/ImPlot 读取，而不是把大数组长期内嵌 JSON。
2. 增加 Gateway 的 `experiment.start`、`stage.replay` 和 `artifact.get` 命令，让新 Run 可以实时刷新 Stage 页面。
3. 为每个 Method 增加 chart contract 和统一的静态/交互 renderer。
4. 增加 MSC、VIP、SVR、Random Forest Registry Method，并补充同一 FeatureSet 的模型比较。
5. 将 Unity `AppleInstance.sampleId`、物理参数快照和光谱 artifact 写入统一 Run manifest。
6. 最后再接入教学动画 keyframe，不提前让动画层承担算法执行职责。
