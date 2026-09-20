# Fruitsim P1 教学实验展示系统交付报告

## 交付范围

P0.1 的唯一 invocation identity 保持不变并作为 P1 的输入合同：页面显示 `method_id`、`invocation_id`、参数和真实 `StageRun` 引用。P1 当前先打通合成教学 Run 的完整 vertical slice：

```text
Data Inspection → Raw/SNV → PCA/CARS → CARS Selection → PLSR → Results
```

前台入口继续使用 vanilla HTML/CSS/JavaScript，不引入 React/Vue/Manim runtime。图表使用 Canvas，结构化数据来自保存的 `ml_p1_bundle.json`，页面切换不会重新执行算法。

## 代码入口

- Web shell：`apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/index.html`
- P1 style：`apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1.css`
- P1 renderer：`apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1.js`
- P1 evidence bundle：`apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_bundle.json`
- Bundle generator：`scripts/build_web_research_assets.py`
- Unity Apple bridge：`apps/fruitsim_unity/Assets/Scripts/Optics/FruitsimAppleGeneratorBridge.cs`
- Apple material shader：`apps/fruitsim_unity/Assets/Resources/FruitsimSolid.shader`
- WebGL callback：`apps/fruitsim_unity/Assets/Plugins/WebGL/FruitsimAppleCallbacks.jslib`

## 已实现能力

六个 Stage 页面均有 StageRun 元数据、方法 invocation、输入引用、解释栏和真实数据图：

- Data Inspection：光谱、sample × wavelength heatmap、target/split/source 信息、selected sample。
- Preprocessing：Raw/SNV/SG(5)/SG(15)/SG(15)→SNV 对比，overlay、difference、heatmap。
- Feature Analysis：PCA 与 CARS 分开的 renderer；PCA score/loading/explained variance；CARS iteration、RMSECV heuristic、保留波长。
- Feature Selection：全部波长与 selected wavelengths 高亮、来源 invocation、数量。
- Modeling：validation-only 默认视图、predicted-vs-true、residual、latent scores、coefficients、collapse ratio。
- Results：validation RMSE/MAE/R²/CV RMSE/bias、selected count、collapse ratio、可点击 pipeline 节点和两个 ExperimentRun 对比表。

Explanation 面板固定回答 What / Why / How / How to read / What happened / Interpretation，并从真实 bundle 数值生成保守描述，不调用 LLM，不把 CARS internal RMSECV 称为无偏泛化性能。

Teaching renderer 采用统一事件名：`show_spectrum`、`highlight_sample`、`show_mean`、`show_std`、`show_formula`、`morph_curve`、`project_points`、`highlight_loading`、`remove_features`、`select_features`、`connect_feature_to_prediction`、`show_prediction`、`show_residual`、`show_metric`。支持 play/pause/previous/next/restart/timeline；全链路播放按 Data → Preprocessing → Feature Analysis → Feature Selection → Modeling → Results 依次进入真实 Stage。

Unity 前台已增加 Apple Generator：Seed、几何、颜色、roughness、spotDensity、normalStrength、SSC/water/absorption/scattering/RI、位置，以及 Generate Apple / Generate Batch / Clear generated。单个生成和批量生成都返回稳定 `sample_id`。roughness、spotDensity、normalStrength 已进入 `FruitsimSolid` shader；physical 参数保持 metadata-only，未与视觉材质混用。

## 验证结果

- Python 全套：**70 passed**。
- Unity Editor batchmode correctness：**29 passed，0 failed**。
- Web shell + P1 bundle：**8 passed**。
- JavaScript：`node --check apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1.js` 通过。
- WebGL：Unity 6000.3.23f1 WebGL/IL2CPP 构建成功；构建报告 complete build size 约 **10.2 MB**，随后 shell apply 成功。
- 前台浏览器：显示 `UNITY READY`；ML 页面显示 32 samples × 51 wavelengths；Generate Apple 返回稳定 sample_id；Generate Batch(3) 返回 3 个不同 sample_id；console error/warning 读取为空。

## 运行命令

```bash
cd /home/rubbishbro/desktop/simulator/fruitsim

# 生成结构化图表数据与静态资源
PYTHONPATH=python /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python scripts/build_web_research_assets.py

# 构建 WebGL 并套入教学 shell
FRUITSIM_BUILD_TIMEOUT=900 bash scripts/build_fruitsim_unity_webgl.sh

# 启动演示服务器
PYTHONPATH=python /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python scripts/serve_webgl_demo.py \
  --root apps/fruitsim_unity/build/WebGL --bind 127.0.0.1 --port 18080

# Python 全回归
PYTHONPATH=python /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python \
  -m unittest discover -s python/tests -p 'test_*.py' -v

# Unity correctness
/home/rubbishbro/.local/bin/unity run apps/fruitsim_unity --timeout 420 -- \
  -executeMethod AppleCorrectnessChecks.RunFromCommandLine -nographics \
  -logFile /tmp/fruitsim-unity-p1-correctness.log
```

## 当前边界与 P2

当前 bundle 的 A/B 对比已经支持选择已有 ExperimentRun、展示 pipeline/参数/metrics/selected count；详细 Canvas 仍以 active teaching bundle 为主，后续可把每个 ExperimentRun 的完整 StageRun visual bundle 做成懒加载。Unity batch 默认保留调用方 pose，因此大量对象放在同一位置时会发生遮挡；P2 可增加可解释的 batch layout、sample-to-Unity 定位和实例化对象池。Manim 导出、真正物理 NIR 材料、更多算法和服务器端动态 Run 查询留到 P2。
