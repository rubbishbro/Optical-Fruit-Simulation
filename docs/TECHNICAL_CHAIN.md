# fruitsim 当前技术链路、参考依据与实现方法

更新日期：2026-08-30

本文记录仓库当前实际实现，作为代码、论文数据、验证结果和后续实验接入之间的索引。
`synthetic_golden_delicious_v1` 只用于验证方法和软件流程，不能用于真实苹果 SSC 预测。
构建、运行及 CUDA 环境命令见 [`GUIDE.md`](../GUIDE.md)。

## 1. 当前端到端链路

```text
论文元数据 / 后续逐苹果实验数据
              |
              v
长格式光学数据（sample、batch、tissue、wavelength、mu_a、mu_s'、SSC、来源）
              |
              v
版本化 JSON -> ring/pencil/gaussian launch -> CPU/CUDA 标量蒙特卡罗
                                               |
                                               v
                          skin/flesh 分层传播 -> 苹果表面逃逸
                                               |
                         +---------------------+--------------------+
                         |                                          |
                         v                                          v
             总 R/T/A、径向反射和能量守恒             detector 圆盘/NA 接受筛选
                                                                    |
                                                                    v
                                  detected spectrum、depth、skin/flesh path fraction
                                                                    |
                                                    （后续接入）ML pipeline
                                                              |
                                                              v
                                     MLR / PLSR / RBF-SVR / RF 比较
                                                              |
                                                              v
                                   模型、指标、预测、划分和 provenance
                                                              |
                                                              v
                                     GUI 展示 / 后续仿真—实测残差修正
```

目前物理仿真与 SSC 流水线可以分别运行，但二者尚未形成逐苹果的真实数据闭环：Python demo
中的 `reflectance`、`penetration_depth_mm` 和 `radial_decay` 是显式合成的代理特征，并非
C++ 对每个样本运行后得到的探测器输出。这是接入实验数据时首先要补齐的接口。

## 2. 数据边界与稳定契约

### 2.1 仿真输入

入口类型是 `fruitsim::transport::SimulationProblem`，定义在
[`include/fruitsim/transport/simulation.hpp`](../include/fruitsim/transport/simulation.hpp)。
JSON 由 [`src/io/config_loader.cpp`](../src/io/config_loader.cpp) 解析。当前约束为：

- 长度为 mm，光学系数为 mm^-1，波长为 nm，SSC 为 degree Brix。
- 每个组织和波长必须提供 `mu_a_mm_inv`、`g`、`refractive_index`，以及
  `mu_s_mm_inv` 或 `mu_s_prime_mm_inv` 中的一个；两者不能同时提供。
- 约化散射系数按 `mu_s = mu_s' / (1-g)` 转成输运使用的散射系数。
- `transport_mode` 当前只能为 `scalar`。偏振未来使用独立状态和内核，不扩大标量光子的状态。
- 所有材料参数从配置读取；物理公式中不隐藏苹果专用常数。

当前默认苹果配置 [`configs/golden_delicious_demo.json`](../configs/golden_delicious_demo.json)
和仪器配置 [`configs/ring_sensor_demo.json`](../configs/ring_sensor_demo.json) 使用同心两层解析球：
flesh 外半径 39 mm、skin 外半径 40 mm，外部空气折射率为 1.0。`LayeredSphere` 仍允许配置
core 或更多层，现有折射率验证和测试继续覆盖三层结构。组织的 `g=0.90`、`n=1.36` 和当前
光学曲线均标记为 `synthetic_assumption`。默认总反射 demo 使用 500–1000 nm、50 nm 间隔的
11 个波长，ring instrument demo 为缩短演示时间使用 100 nm 间隔的 6 个波长；ML 合成数据使用
10 nm 间隔的 51 个波长，三个波长轴目前不可直接混用。

### 2.2 数据表

SSC 数据读取和校验位于 [`python/fruitsim_ml/data.py`](../python/fruitsim_ml/data.py)，长表必需字段为：

```text
dataset_id, sample_id, source_type, cultivar, tissue,
wavelength_nm, mu_a_mm_inv, mu_s_prime_mm_inv, g,
refractive_index, ssc_brix, batch_id, source_doi,
measurement_method, uncertainty, notes
```

校验会拒绝缺列、光学/SSC 数值缺失、负光学系数、非法 `g`、重复的
sample/tissue/wavelength 记录、空 sample/batch ID，以及样本间不完整的共同波长轴。
当前只检查各组波长数量相同，后续还应检查波长值本身完全一致及单位/schema 版本。

### 2.3 输出协议

[`src/io/result_writer.cpp`](../src/io/result_writer.cpp) 写出：

| 文件 | 当前含义 |
| --- | --- |
| `summary.csv` | 每波长总 R/T/A、能量残差、全光子深度及新增 instrument 指标 |
| `detectors.csv` | 保留的全部逃逸反射光径向分箱；不等于中央 detector 响应 |
| `instrument.csv` | detector 的总/镜面/漫反射接收权重、效率、接收深度及 skin/flesh 兼容字段 |
| `instrument_regions.csv` | 任意 region 的 detector-weighted 平均路径和路径比例长表 |
| `performance.csv` | 后端、波长数、总光子数、耗时与 photons/s |
| `absorption_grid.csv` | 三维网格内沉积的吸收权重；当前不是严格定义的 fluence |
| `trajectories.csv` | 有上限的调试光子轨迹 |
| `manifest.json` | 配置、后端、运行时、设备、精度和 synthetic/experimental 溯源 |

能量残差使用 `1 - R - T - sum(A_layer) - discarded`。接受的验证算例要求
`boundary_failures` 和 `max_event_terminations` 为零。

`scan-ring --ring-radii 1,2,3,5,8,10,12,15` 会保持同一配置、seed 和波长轴，仅改变
`ring_radius_mm`，输出适合二维 `R(lambda,r)` 分析的长表 `ring_scan.csv`，以及记录配置、seed、
光子数、半径列表和合成假设的 `ring_scan_manifest.json`。扫描只生成正向响应，不判定所谓最优距离。

## 3. 蒙特卡罗物理实现

### 3.1 几何、光源和随机数

- [`src/geometry/layered_sphere.cpp`](../src/geometry/layered_sphere.cpp) 实现由内到外排序的
  同心球组织，查询当前位置组织、相邻界面距离、法线及界面两侧介质。
- [`src/transport/monte_carlo.cpp`](../src/transport/monte_carlo.cpp) 实现 pencil、Gaussian 和正式
  ring source。Gaussian 横向位置由 Box–Muller 采样；零宽 ring 均匀采样方位角；有限宽 ring
  将 `ring_width_mm` 解释为名义半径两侧的总径向宽度，并以
  `r=sqrt(r_inner²+xi(r_outer²-r_inner²))` 在 annulus 面积上均匀采样。ring 可使用固定方向或
  `aim_at` 规则逐光子朝向目标点。
- [`src/core/random.cpp`](../src/core/random.cpp) 实现项目内的 Philox4x32-10 计数型随机流。
  key 由 seed 和波长派生，counter 以 photon ID 为独立流并按抽样次序推进。因此线程调度和
  CPU 线程数不会改变单光子的随机序列。代码采用 Philox 思路和公开常数，没有链接或复制
  Random123 源文件。

### 3.2 单光子事件顺序

CPU 金标准位于 [`src/transport/monte_carlo.cpp`](../src/transport/monte_carlo.cpp)，
CUDA 对应实现在 [`libs/cuda/cuda_backend.cu`](../libs/cuda/cuda_backend.cu)：

1. 从 pencil/Gaussian/ring source 发射，在空气中求与苹果外球的首次交点。
2. 空气—苹果入射面的镜面反射使用确定性权重分裂：`R_specular` 计入反射，其余权重折射入射。
3. 采样无量纲光学深度 `tau=-ln(xi)`，在当前组织内换算距离 `s=tau/(mu_a+mu_s)`。
4. 若先遇到组织界面，则扣除已经走过的光学深度，在新组织中继续使用剩余 `tau`。
5. 碰撞时沉积 `w * mu_a/(mu_a+mu_s)`，其余权重继续传播。
6. 使用 Henyey–Greenstein 相函数采样散射方向；`g` 接近零时退化为各向同性采样。
7. 界面处根据 Snell 定律判断折射/全反射，以非偏振 Fresnel
   `R=(R_s+R_p)/2` 随机选择反射或折射。
8. 权重低于阈值后执行 Russian roulette。事件数达到上限时记入诊断而不静默吞掉光子。
9. 每段实际组织传播距离按 region index 累计；最大深度由 geometry 定义为沿路径各点的
   `outer_radius-|point-center|` 最大值；每条直线传播段会检查离球心最近的段内点，而非只检查
   事件端点，因此无碰撞直穿也不会漏记。该定义与单个 ring photon 的入射方向无关。
10. 光子离开外表面后，按该光子的入射轴分类为反射或透射，并记录原有径向响应。
11. 对反射逃逸分量执行 detector 几何筛选；这一步不消耗随机数且不从 R/T/A 中扣除权重。

`boundary_epsilon` 用于判断几何相等，`boundary_nudge` 用于跨界面后将位置轻推入目标介质，二者
分离以避免薄层中自相交或跳层。GPU 还使用与浮点 ULP 相容的界面处理。

### 3.3 计分与统计

- 每层吸收、R/T、径向响应、穿透深度直方图及可选三维吸收网格均累计光子权重。
- 深度 P50/P90 是直方图分箱中点近似，不是保存全部光子深度后的精确分位数。
- 标准误来自固定 photon batch 的 R/T 样本；只有一个 batch 时无法估计 batch 间方差，当前返回 0。
- 抽样轨迹只用于诊断和 GUI，不应参与统计推断。

中央 detector 是一个平面圆盘，`axis` 从 detector 指向样品。逃逸光线首先与 detector 平面
求交，交点必须在 `radius_mm` 内，同时传播方向必须落在 `-axis` 周围的 acceptance cone 中。
配置可给 `acceptance_half_angle_deg`，或给 exterior medium 中的 `numerical_aperture`，后者按
`theta=asin(NA/n_exterior)` 转换。当前不模拟 detector 对照明的遮挡。

`detected_weight` 是通过筛选的 packet 权重原始和；其中入射外表面 Fresnel 权重记为
`detected_specular_weight`，进入组织后再从入射侧逃逸的权重记为 `detected_diffuse_weight`，且三者满足
`detected_weight = detected_specular_weight + detected_diffuse_weight`。这里的 diffuse 是 transport
分类名，表示 bulk-return 分量，并不额外要求至少发生一次散射。`detected_photon_count` 是被接受的 packet
贡献数量，仅作辅助。单位权重发射下：

```text
detection_efficiency = detected_weight / launched_photons
detected_reflectance = detected_weight / launched_photons
```

两者当前数值相等，分别保留“仪器效率”和“收集反射率”语义。接收深度均值按 detector-arrival
packet weight 加权，中位数由权重直方图估计。`weighted_mean_path_by_region_mm` 的分母是全部
detected weight（包含零组织路径的 specular 分量）；`path_fraction_by_region` 的分母是各 region 的
加权路径总和。`skin_path_fraction` / `flesh_path_fraction` 及对应平均路径只是按 layer 名称从通用数组
派生的兼容字段；有可选 core 时两者之和可以小于 1。

全部光子与 detector 光子的最大深度都使用 geometry 的外表面 inward depth，取值为 `[0,R]`。
必须区分 `penetration_q50/q90` 与 `detected_penetration_*`：前者按 packet count 统计全部发射 packet，后者按
被当前 detector 几何接收的光。只有后者能回答该 source-detector 结构的实际 sampling depth。

### 3.4 CPU 并行

[`src/runtime/cpu_backend.cpp`](../src/runtime/cpu_backend.cpp) 把固定编号的 photon batch
动态分配给线程。每个 batch 独立计分，完成后按 batch ID 固定顺序归约。随机数又由 photon ID
确定，所以相同 seed、光子数和配置在不同 CPU 线程数下得到相同结果。取消和进度更新发生在
batch 边界。

### 3.5 CUDA 并行

[`libs/cuda/cuda_backend.cu`](../libs/cuda/cuda_backend.cu) 当前使用每个 CUDA 线程处理一个光子，
以有界 batch 启动：

- 光子传播状态和光学参数使用 `float`，每光子标量 tally 及主机归约使用 `double`。
- 三维吸收网格使用 double `atomicAdd`；轨迹使用受限原子槽，回传后按 photon/event 排序。
- batch 回传后在主机固定顺序归约，因此同一 GPU、seed 和配置可重复；CPU/GPU 因浮点路径不同，
  只要求统计一致，不要求逐光子一致。
- 设备名称、compute capability、驱动/runtime/toolkit、block size、精度和边界 nudge 会写入 manifest。
- CUDA 实现同样执行 ring sampling、圆盘/acceptance 筛选和接收路径累计；不会静默忽略 detector。

当前性能瓶颈是每光子的标量结果需要 device-to-host 回传；尚未实现 block/device 两级归约、
CUDA stream 重叠和多 GPU 调度。

## 4. SSC 建模实现

### 4.1 合成数据

`generate-demo` 位于 [`python/fruitsim_ml/data.py`](../python/fruitsim_ml/data.py)，固定 seed 可复现。
SSC 从截断到 8–17 °Brix 的分布生成；吸收谱使用基线、约 675 nm 的叶绿素峰和约 970 nm 的
水吸收峰，`mu_s'` 随波长缓慢下降，再叠加显式的样本差异和噪声。代理量使用：

```text
mu_eff = sqrt(3 * mu_a * (mu_a + mu_s'))
reflectance_proxy = exp(-2.6 * mu_eff) * noise
penetration_proxy = 1 / mu_eff
radial_decay_proxy = mu_eff / mu_s'
```

这些公式是软件和建模链路的合成假设，不是论文公开的逐苹果数据，也不是经过仪器标定的物理
传递函数。生成数据、manifest、模型和 GUI 必须持续显示不可用于真实预测的警告。

### 4.2 特征和预处理

[`python/fruitsim_ml/features.py`](../python/fruitsim_ml/features.py) 将每个 sample 的长表转换成：

- `mu_a`、`mu_s_prime`；
- 两者拼接、逐波长乘积；
- `mu_eff=sqrt(3*mu_a*(mu_a+mu_s'))`；
- 合成/未来 MC 探测反射谱；
- 反射谱加穿透深度和径向衰减的 augmented 特征。

[`python/fruitsim_ml/preprocessing.py`](../python/fruitsim_ml/preprocessing.py) 和
[`python/fruitsim_ml/train.py`](../python/fruitsim_ml/train.py) 提供 raw、StandardScaler、SNV、
Savitzky–Golay 平滑及一阶导数。预处理、零方差剔除和模型封装在 scikit-learn `Pipeline` 中，
只在训练折拟合，避免把验证集统计量泄漏到训练过程。

### 4.3 模型、验证和产物

当前并行比较 MLR、PLSR、RBF-SVR 和 Random Forest。PLSR 成分数、SVR 的 C/gamma/epsilon、
RF 树数/深度由内层 `GridSearchCV` 选择。

- `paper_compatible`：固定 seed 的 75/25 calibration/validation 划分，训练集内使用随机 5-fold CV。
- `research`：以 `batch_id` 做 75/25 GroupShuffleSplit，训练批次内使用 GroupKFold。

训练输出 `R²`、Pearson `r_p`、RMSEC、RMSECV、RMSEP、MAE、bias 和 RPD，并写出
`model_manifest.json`、`pipeline.joblib`、`metrics.json`、`predictions.csv`、`cv_folds.csv` 和
`feature_schema.json`。当前 `cv_folds.csv` 实际记录外层 calibration/validation 分配，并未保存
GridSearchCV 的每个内层折；文件名保留是为了接口兼容，后续需补充完整折记录。

代码会拒绝把非纯实验数据或未确认外部验证的模型标记为 `experiment_calibrated`。当前还没有
独立的 prediction/inference 命令，也没有在加载 artifact 时完整执行 schema、单位、波长轴、
特征顺序和软件版本兼容性检查。

## 5. GUI 与任务编排

[`apps/fruitsim_gui/main.cpp`](../apps/fruitsim_gui/main.cpp) 是 Dear ImGui/ImPlot/GLFW/OpenGL 的
初始研究工作台：C++ 仿真在后台任务运行；Python 通过 `python -m fruitsim_ml train` 子进程启动；
界面可显示基本 R/T/A 和 ML 指标。

当前尚缺完整 JSONL 进度解析、可靠取消/失败日志、历史缓存、组织/光源/探测器编辑器、吸收热图、
穿透深度和轨迹视图。GUI 不是物理或 ML 实现的唯一入口；CLI 和版本化文件协议是稳定边界。

## 6. 代码导航

| 模块 | 主要文件 | 职责 |
| --- | --- | --- |
| core | `include/fruitsim/{vec3,ray,random}.hpp`、`src/core/random.cpp` | 数学原语、射线、Philox RNG |
| geometry | `include/fruitsim/geometry/layered_sphere.hpp`、`src/geometry/` | 同心分层球及界面查询 |
| optics | `include/fruitsim/optics/optics.hpp`、`src/optics/` | 参数校验、HG、Snell/Fresnel |
| transport | `include/fruitsim/transport/`、`src/transport/` | 稳定问题/结果类型及 CPU 金标准 |
| runtime | `include/fruitsim/runtime/`、`src/runtime/cpu_backend.cpp` | batch、线程、进度、取消、确定性归约 |
| CUDA | `libs/cuda/cuda_backend.cu` | GPU 标量光子传输和 tally |
| IO | `include/fruitsim/io/`、`src/io/` | JSON 配置、CSV/JSON 结果和溯源 |
| CLI | `apps/fruitsim_cli/main.cpp` | validate、run、scan-ring、devices 命令 |
| GUI | `apps/fruitsim_gui/main.cpp` | 可选研究工作台 |
| ML | `python/fruitsim_ml/` | 数据、特征、预处理、训练、模型比较 |
| schema | `data/schemas/` | 配置和数据契约 |
| tests | `tests/` | core、物理、CPU/CUDA 统计一致性测试 |

## 7. 论文与参考项目

完整元数据索引见
[`data/literature/golden_delicious_sources.csv`](../data/literature/golden_delicious_sources.csv)。

| 参考 | 本项目采用的内容 | 使用边界 |
| --- | --- | --- |
| [Qin & Lu, 2009, Computers and Electronics in Agriculture](https://doi.org/10.1016/j.compag.2009.04.002) | Golden Delicious 光传播特征与蒙特卡罗研究设计 | 用于研究范围和传播特征参考；仓库没有论文逐样本数据 |
| [Qin, Lu & Peng, 2009, Transactions of the ASABE](https://doi.org/10.13031/2013.26807) | 600 个 Golden Delicious、500–1000 nm 的吸收/散射谱趋势与 SSC 建模基线 | 用于谱形和 SSC 方法对照，不把摘要指标当作当前模型验证 |
| [Cen, Lu & Mendoza, 2012, Acta Horticulturae](https://doi.org/10.17660/ActaHortic.2012.945.24) | 1039 个 Golden Delicious 的吸收/散射特征组合、PLS–SSC 对照 | 无公开逐样本表，因此仅作方法和指标参考 |
| [Askoura, Vaudelle & L'Huillier, 2016, Photonics](https://doi.org/10.3390/photonics3010002) | 球形 apple skin/flesh 分层模型及果皮影响 | 当前 1 mm skin 是合成演示设置，不宣称复现论文皮厚 |
| [MCML / OMLC](https://omlc.org/software/mc/) | 稳态分层浑浊介质的事件定义、R/T/A 和验证思路 | 作为独立物理基准；当前解析球不是平板 MCML 几何 |
| [Random123](https://github.com/DEShawResearch/random123) | counter-based RNG 和 Philox 设计参考 | 项目内自行实现所需 Philox 接口，未引入其源码依赖 |
| [MCX](https://github.com/fangq/mcx) | GPU/体素光子输运、数据布局和性能设计参考 | GPLv3；MIT 仓库不复制实现 |
| [MMC](https://github.com/fangq/mmc) | 未来四面体网格与复杂几何参考 | GPLv3；MIT 仓库不复制实现 |
| [CUDA C++ Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/) | kernel、内存层级、原子操作和并行归约依据 | 用于 CUDA 工程实现，不构成苹果光学参数来源 |

## 8. 当前验证状态和技术缺口

当前 CPU core/physics 测试通过；CUDA 在 RTX 4060 Laptop GPU 上完成了固定 seed 可重复性和
12,000 光子的三层球 ring/detector CPU/GPU 统计一致性测试。测试还覆盖 annulus 面积采样、
detector radius/acceptance 单调性、理想大孔径 detector、关闭 detector 后 R/T/A 完全不变、CPU
线程数确定性及 detector 不影响能量残差。这些结果证明当前软件路径能运行，不证明 synthetic
参数代表真实 Golden Delicious 或任何真实仪器。

当前需要优先改进：

1. 用可精确提取且带不确定度的分层 Golden Delicious 实测参数替换合成曲线。
2. 建立逐苹果的 C++ 仿真输出到 Python 样本特征转换器，统一仿真和仪器波长轴。
3. 在现有圆盘/NA 基础上加入光源与 detector 机械遮挡、透镜/光纤传递函数、光谱仪响应、暗/白
   参考校正和与真实探头坐标的标定。
4. 建立 MCML/Beer–Lambert/Fresnel 独立回归语料及更广的 CPU/CUDA 置信区间测试。
5. 实现 CUDA block/device 归约、stream、多 GPU、GPU CI 和可重复性能基准。
6. 增加 artifact inference、严格兼容性/OOD 检查、预测不确定度和完整 CV 折记录。
7. 用独立果园/采收批次外部测试建立 literature prior、少样本校准、残差修正和实测重训练对照。
8. 完成 GUI 任务生命周期和所有 provenance 展示；再扩展体素/网格、时间分辨、偏振与荧光。

更详细的优先级和启动命令统一维护在 [`GUIDE.md`](../GUIDE.md)，避免两处命令随版本漂移。
