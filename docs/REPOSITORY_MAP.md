# fruitsim 仓库地图

本文是进入项目的导航页。它描述当前代码实际边界，不把计划中的 mesh transport、偏振或
Unity 前端写成已经完成的功能。

## 1. 从哪里开始

按下面顺序阅读最容易建立全局概念：

1. [`README.md`](../README.md)：构建、启动命令和 demo 入口。
2. [`GUIDE.md`](../GUIDE.md)：工程约束、单位、验证方法、CUDA/ML 环境和限制。
3. [`docs/TECHNICAL_CHAIN.md`](TECHNICAL_CHAIN.md)：从配置到光子事件、计分和输出的逐文件说明。
4. [`include/fruitsim/transport/simulation.hpp`](../include/fruitsim/transport/simulation.hpp)：核心问题定义、光子状态和结果结构。
5. [`src/transport/monte_carlo.cpp`](../src/transport/monte_carlo.cpp)：CPU 单光子生命周期。
6. [`libs/cuda/cuda_backend.cu`](../libs/cuda/cuda_backend.cu)：CUDA 对应实现。
7. [`python/fruitsim_ml/train.py`](../python/fruitsim_ml/train.py)：SSC 模型比较入口。

## 2. 顶层目录职责

```text
include/fruitsim/       C++ 稳定公共接口
src/                    C++ CPU/解析几何/IO 实现
libs/                   CMake 库目标；CUDA 源码位于 libs/cuda
apps/fruitsim_cli/      无界面、可复现的仿真和扫描入口
apps/fruitsim_gui/      当前 Dear ImGui/ImPlot 研究工作台（CPU 优先）
python/fruitsim_ml/     数据校验、特征、预处理和 SSC 回归
python/fruitsim_shape/  点云训练、PCA 苹果采样和网格导出前的形状层
python/tests/           Python 形状和端到端 smoke 测试
tests/                  C++ 单元、物理、shape loader、CUDA 测试
configs/                版本化仿真/ML/benchmark 配置
data/                   文献表、schema、shape artifact、合成数据
docs/                   技术链、形状说明和本仓库地图
prac-raytracing/        独立学习练习，不是 fruitsim 生产代码
results/                本地运行输出，不作为源码接口
build*/                 本地 CMake 构建产物，不提交
```

## 3. C++ 依赖方向

```text
core
  ↓
geometry   optics
  ↓         ↓
transport
  ↓
runtime ──→ io
  ↓
fruitsim_cli / fruitsim_gui
```

- `core`：`Vec3`、`Ray`、单位基础类型、Philox 计数型随机数。
- `geometry`：当前生产 transport 使用 `LayeredSphere`；`StatisticalFujiShape` 目前是形状数据和
  网格表示，不是三角网格求交后端。
- `optics`：光学参数校验、HG、Snell 和非偏振 Fresnel。
- `transport`：不可变 `SimulationProblem`、`PhotonState`、MC 生命周期、R/T/A、detector 和路径统计。
- `runtime`：CPU batch 调度和可选 CUDA backend 的运行适配。
- `io`：JSON 配置加载、CSV 结果和 manifest 写出。

不要在 GUI 中复制物理公式；不要在 transport 中写死 GUI 或 SSC 逻辑。

## 4. 当前两个几何世界

当前必须明确区分：

```text
LayeredSphere
  └── 当前 CPU/CUDA photon boundary 和 Fresnel 的实际几何

StatisticalFujiShape
  └── Zenodo 点云学习的平均径向形状/PCA 随机网格
      └── 当前可采样、验证、导出和显示
      └── 尚未用于 Monte Carlo 三角网格求交
```

因此任何展示界面都应同时显示 `display_geometry` 和 `transport_geometry`，避免用户把随机
苹果网格误认为光子已经在其内部传播。

## 5. 配置到结果的入口

仿真：

```text
configs/*.json
  → load_simulation_config()
  → SimulationProblem::validate()
  → ITransportBackend::run()
  → write_simulation_results()
  → summary.csv / instrument.csv / trajectories.csv / manifest.json
```

当前主要配置：

- `golden_delicious_demo.json`：总反射/透射基础 demo。
- `ring_sensor_demo.json`：环形光源 + 中央圆形 detector。
- `ring_sensor_benchmark.json`：20k/100k/1M 光子吞吐测试。
- `refractive_mismatch_validation.json`：界面 Fresnel 验证。
- `ml_*.json`：Python SSC 组合实验。

ML：

```text
long CSV
  → validate_dataset()
  → feature builder
  → preprocessing Pipeline
  → MLR/PLSR/SVR/RF
  → metrics.json / predictions.csv / pipeline.joblib
```

目前 ML 合成数据中的 reflectance、penetration 和 radial_decay 是代理特征，并非逐苹果
C++ detector 输出；`SimulationResult → ML dataset` 适配器尚未完成。

## 6. GUI 当前边界

当前 [apps/fruitsim_gui/main.cpp](../apps/fruitsim_gui/main.cpp) 是轻量研究面板：

- 可以加载配置、启动 CPU 仿真、读取 R/T/A 和 ML 指标。
- CUDA 可由 CLI 使用，但主 GUI 尚未提供完整 backend 选择和 CUDA 任务控制。
- 尚未实现 OpenGL 3D viewport、网格导入、ring/detector 场景、路径重放和 fluence 体绘制。
- StatisticalFujiShape 的 Matplotlib 查看器是独立 Python 工具，不是主 GUI。

计划中的 Unity/Blender 前端不属于当前仓库已完成组件。若加入，应通过版本化 job、scene
manifest 和 trajectory 协议调用 CLI，而不是复制 C++ transport。

## 7. 修改代码时的边界

常见修改位置：

| 需求 | 首选位置 |
| --- | --- |
| 新增光学公式 | `include/fruitsim/optics/` + `src/optics/` + physics tests |
| 新增几何类型 | `geometry`，先做 CPU reference，再接 runtime |
| 改变 photon lifecycle | `src/transport/monte_carlo.cpp`，同步 CUDA 和物理测试 |
| 新增输出字段 | result structs、`src/io/result_writer.cpp`、schema/docs |
| 新增 source/detector 参数 | `simulation.hpp`、config loader、JSON schema、CPU/CUDA |
| 新增 ML 特征 | `python/fruitsim_ml/features.py` + schema/训练测试 |
| 改 GUI | `apps/fruitsim_gui/`，不要把展示逻辑放进 transport |
| 点云/PCA 形状 | `python/fruitsim_shape/` 和 `include/src/...statistical_fuji_shape` |

## 8. 推荐验证顺序

```bash
cmake --build build-cuda --parallel
ctest --test-dir build-cuda --output-on-failure

mamba run -n mamba-torch311 \
  env PYTHONPATH=python python -m unittest discover \
  -s python/tests -p 'test_*.py' -v

mamba run -n mamba-torch311 \
  env PYTHONPATH=python python -m fruitsim_ml train \
  --config configs/ml_smoke_test.json
```

CUDA 测试在没有可见设备时应报告 skip，而不是伪造 GPU 结果。合成 ML 结果只能验证软件
流程，不能作为真实 SSC 精度结论。

