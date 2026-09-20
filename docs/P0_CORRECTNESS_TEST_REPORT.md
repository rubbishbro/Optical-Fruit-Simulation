# Fruitsim P0 Correctness 与测试报告

日期：2026-09-20
范围：现有 ML workflow 与 AppleGenerator 的正确性、可追溯性和测试；未新增 P1 算法、动画、模型或材质效果。

## 1. 总体结论

评估：**Ready to share，带明确算法边界说明**。

实验定义现可保存每个方法的显式参数与 resolved parameters；feature selection source 无隐式猜测；cache 纳入 computational metadata；模型选择不读取 final validation；Results 默认只使用 validation view；Apple identity 由完整请求决定且实例参数为生成时快照。

## 2. 修复问题与根因

| 问题 | 根因 | 修复 |
|---|---|---|
| 方法参数不可追溯 | Pipeline 只存字符串，stage 向整条 chain 传一个参数字典 | 引入 `ParameterDefinition`、`MethodSpec`；默认值显式 merge、校验、固化 |
| Selection source 硬编码 | 使用 `analyses.get("cars")` / 首个字典元素 | 引入 `FeatureSelectionSpec.source_analysis_id` 和 method accepted-source contract |
| validation 污染模型选择 | 按 final validation RMSE 选模型 | `select_final_model_by_cv()` 只读取 calibration CV RMSE；validation 仅最终评估 |
| cache 串 groups/source | Spectrum fingerprint 未包含 metadata | 纳入全部 computational metadata；仅 `metadata["display"]` 明确排除 |
| Results 混合 calibration/validation | renderer state 保存全体预测 | 增加 split-aware view API；Results state 默认保存 validation subset |
| CARS 指标语义过强 | 非 nested selection 被描述为 leakage-safe RMSECV | 标记为 `internal_selection_heuristic_not_nested_cv`，更新注释与文档 |
| Apple ID 只取 seed | generation request 其他字段未参与 identity | 固定字段 canonicalization + IEEE-754 float bits + SHA-256；pose 明确参与 |
| AppleInstance 持有可变引用 | 直接保存 request 子对象 | `AppleRequestIdentity.Snapshot()` deep-copy 全部请求字段 |
| 参数生效范围不透明 | 接口字段多于 P0 renderer 实际能力 | `AppleGenerationCapabilities` 明确 active / metadata-only 参数 |
| runtime material 生命周期不清 | `new Material` 未记录 owner | AppleInstance 跟踪 owned materials；Destroy 只清理 owned materials 与实例容器 |

## 3. 修改文件

- `python/fruitsim_ml/workflow.py`
- `python/tests/test_workflow_correctness.py`
- `scripts/run_p0_correctness_e2e.py`
- `apps/fruitsim_unity/Assets/Scripts/Optics/AppleModels.cs`
- `apps/fruitsim_unity/Assets/Scripts/Optics/AppleGenerator.cs`
- `apps/fruitsim_unity/Assets/Scripts/Optics/AppleRequestIdentity.cs`
- `apps/fruitsim_unity/Assets/Editor/AppleCorrectnessChecks.cs`
- `python/tests/test_blender_unity_asset.py`
- `apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_workflow_summary.json`
- `docs/ML_WORKFLOW_P0.md`

## 4. 新数据结构与合同

- `ParameterDefinition(default, type, min, max)`：参数默认值和基础约束。
- `MethodSpec(method_id, parameters, resolved_parameters)`：精确保存显式值和执行值。
- `FeatureSelectionSpec(method, source_analysis_id)`：明确 analysis → selection 边。
- `PredictionSet.view()`、`calibration_view()`、`validation_view()`：split-aware renderer contract。
- `StageRun.computational_fingerprint`：可持久化 cache identity。
- `AppleRequestIdentity`：纯 C# snapshot/canonicalization/hash。
- `AppleGenerationCapabilities`：声明 P0 active 与 metadata-only 字段。

## 5. Backward compatibility

- `PipelineDefinition` 仍接受旧的 method-id 字符串；schema-v1 ExperimentRun/StageRun 仍可加载。
- JSON schema 升级为 v2，同时保留 `method_chain`，C++ GUI 读取合同不变。
- `StageRun.parameters` 现在按 method 分组展示，不再是 stage 共享参数字典；依赖旧参数形状的第三方消费者需要适配。
- Apple `sampleId` 从 seed-only 改为 request hash；旧 sample id 与新规则不兼容，这是为修复追溯冲突而做的必要变更。

## 6. Python tests

命令：

```bash
PYTHONPATH=python MPLCONFIGDIR=.cache/matplotlib \
  /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python \
  -m unittest discover -s python/tests -p 'test_*.py' -v
```

结果：**62 passed，0 failed，0 skipped**，3.205 s。

其中新增/重点 workflow 与 Unity 静态合同测试单独运行结果：**27 passed，0 failed，0 skipped**。

第一次在受限 sandbox 内运行 Gateway E2E 时，因禁止绑定 `127.0.0.1:18766` 出现 1 次环境性失败；在允许 loopback 的相同代码上重跑完整套件后 62/62 通过。该失败未隐藏，也不是应用逻辑回归。

## 7. C++ build/tests

```bash
cmake --build build-acceptance-20260920 -j2
ctest --test-dir build-acceptance-20260920 --output-on-failure
cmake -S . -B /tmp/fruitsim-p0-gui -DFRUITSIM_BUILD_GUI=ON -DFRUITSIM_BUILD_TESTS=OFF -DFRUITSIM_BUILD_EXAMPLES=OFF
cmake --build /tmp/fruitsim-p0-gui --target fruitsim_gui -j2
```

结果：核心构建成功；CTest **3/3 passed**；ImGui GUI 干净构建成功。第三方 ImPlot 出现 enum deprecation warning，Fruitsim 源码无编译错误。

## 8. Unity tests/build

纯 C# identity/snapshot 逻辑已从 MonoBehaviour 拆出。Editor batchmode harness 命令：

```bash
/home/rubbishbro/.local/bin/unity run apps/fruitsim_unity --timeout 300 -- \
  -executeMethod AppleCorrectnessChecks.RunFromCommandLine \
  -nographics -logFile /tmp/fruitsim-unity-correctness.log
```

结果：**19 passed，0 failed**。覆盖 identity、字段赋值顺序、locale/float 稳定性、四类 snapshot、owned material 清理、5 次连续 Generate/Destroy 和 shared FBX 存活。

项目原先没有自有 Unity EditMode/PlayMode test assembly，因此没有可继承的 NUnit 测试集合；本轮使用真实 Editor batchmode correctness harness，而不是只做文本 smoke test。PlayMode 专项未执行，因为本轮生命周期合同不依赖 frame/update，且未修改运行时交互逻辑。

## 9. WebGL build

```bash
FRUITSIM_BUILD_TIMEOUT=900 bash scripts/build_fruitsim_unity_webgl.sh
```

结果：**成功**，Unity 6000.3.23f1，日志为 `Build Finished, Result: Success`，命令退出码 0。随后 Web shell/server tests **4/4 passed**。Unity wrapper 退出时仍打印既有的 `.NET build-server`/websockify 清理噪声，但不影响 Unity build result。

## 10. E2E 测试

数据集：`math_seed20260919`，synthetic math，32 samples × 51 wavelengths；fit 24，validation 8。

Pipeline A：

```text
Data Inspection → SG(15,3) → SNV → PCA(5) + CARS(8, decay=.72)
→ CARS selection → PLSR(3) → Results
```

Validation：RMSE 0.0718741，MAE 0.0531369，R² -0.317535，bias 0.00275858，CV RMSE 0.0672501，11 selected features。

Pipeline B：

```text
Data Inspection → SNV → PCA(3) + CARS(5, decay=.60)
→ CARS selection → PLSR(2) → Results
```

Validation：RMSE 0.0889715，MAE 0.0673041，R² -1.018919，bias 0.00849106，CV RMSE 0.0535290，8 selected features。

两个 ExperimentRun 均完成 save/reload，metrics 与 selected indices 完全一致。负 R² 是 8 个 validation synthetic samples 上的真实结果；本测试验证流程正确性，不宣称模型性能。

## 11. Cache correctness

- 同数据/同参数/同 seed：命中。
- deterministic SNV 改 seed：仍命中，seed 不污染无随机算法的 cache key。
- seed-sensitive CARS 改 seed：不命中。
- 同 X/y、不同 groups：不命中。
- 只改变 `metadata["display"]`：按设计命中。
- SG 参数、preprocessing chain、CARS 参数不同：不命中。
- StageRun save/load 后重新放入 cache：身份保持且命中。
- 两条 E2E CARS cache key 不同，Pipeline B CARS `cache_hit=false`。

## 12. Leakage correctness

- PCA spy：fit 行数严格为 20 个指定 calibration rows。
- CARS/PLSR spy：将 validation X 设置为 1,000,000 后，所有 estimator `.fit()` 输入均未出现 validation 值。
- `fit_indices` 与 `validation_indices` 重叠会明确报错。
- 多模型选择测试：改变 validation RMSE 不改变选择；改变 calibration CV RMSE 可以改变选择。
- final RMSE/MAE/R²/bias 与 validation view 手算一致。
- Results intermediate state 数量与 validation subset 一致，不含 calibration rows。

## 13. Apple identity/snapshot/lifecycle

- 相同完整 request：相同 sample id。
- seed、geometry、physical、visual、pose 任一改变：sample id 改变。
- 字段赋值顺序和进程 locale 不影响 canonical hash。
- float 使用 IEEE-754 bit hex，不依赖小数点文化设置。
- Generate 后修改原 geometry/physical/visual/pose：AppleInstance snapshot 不变。
- Destroy 后 owned runtime material 数量回到 baseline。
- 连续 5 次 Generate/Destroy 不增长 owned material count。
- `Resources/FruitsimBlenderRig` shared asset 未被销毁。

## 14. 仍未解决的问题与必须保留的 caveat

- CARS `best_rmsecv` 是 internal selection heuristic，不是 nested-CV 无偏泛化误差。
- geometry 的 `heightRatio/crownRatio/asymmetry`、visual 的 `roughness/spotDensity/normalStrength`、全部 physical fields 仍是 metadata-only；能力对象已明确暴露这一点。
- 标准 Unity Test Runner 的项目自有 EditMode/PlayMode test assembly 尚未建立；当前 19 项由真实 Editor batchmode harness 执行。
- Web 页面读取构建时 workflow summary；实时 Gateway 回灌属于 P1，本轮未实现。
- synthetic 32-sample E2E 只证明合同、重放、cache 和 split 语义，不代表真实苹果数据上的外部有效性。
