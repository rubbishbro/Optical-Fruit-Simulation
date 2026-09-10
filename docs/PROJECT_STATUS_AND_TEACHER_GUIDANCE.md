# fruitsim 项目完成情况与教师指导事项

更新日期：2026-09-04

## 1. 文档目的

本文用于总结当前项目已经完成的功能、尚未打通的链路，以及将项目发展为“完整 3D 光学传播与机器学习展示系统”时需要教师确定的技术和科研边界。

当前项目定位为研究型仿真平台和教学演示系统。默认配置中的 Golden Delicious 光学数据、仪器参数和 SSC 数据均带有 synthetic/demo 属性，不能直接作为真实苹果 SSC 预测依据。

## 2. 当前总体链路

目前项目由三条能力链组成：

```text
JSON 配置
  ↓
分层球苹果模型
  ↓
pencil / gaussian / ring 光源
  ↓
CPU / CUDA 标量 Monte Carlo
  ↓
R/T/A、吸收、径向反射、穿透深度
  ↓
圆形 detector 接收筛选
  ↓
CSV / JSON / manifest 结果
```

```text
统计苹果点云
  ↓
平均半径 + PCA 形变模式
  ↓
随机苹果形状 / PLY / 3D 展示
```

```text
长格式光学/SSC CSV
  ↓
数据校验与光谱特征构造
  ↓
预处理与交叉验证
  ↓
MLR / PLSR / RBF-SVR / Random Forest
  ↓
预测、指标、模型和 provenance
```

第一条链路已经可以独立运行；第二条链路已经实现形状建模但尚未成为 Monte Carlo 的真实边界；第三条链路可以独立训练，但当前还没有消费 C++ 对每个苹果实际仿真产生的 detector 特征。

## 3. 已经完成的功能

### 3.1 C++ 仿真框架

- 已建立 C++17 模块化工程和 CMake 构建体系。
- 已拆分 core、geometry、optics、transport、runtime、io 等模块。
- 已提供 CLI 的 `validate`、`run`、`scan-ring` 和 `devices` 命令。
- 已实现版本化 JSON 配置读取和参数校验。
- 已统一单位约定：长度为 mm，光学系数为 mm^-1，波长为 nm，SSC 为 degree Brix。
- 已实现 `mu_s_prime_mm_inv` 到 `mu_s_mm_inv` 的转换。

### 3.2 几何模型

- 已实现同心分层球 `LayeredSphere`。
- 支持内到外递增的多层组织，例如 flesh、skin、core。
- 已实现光线与外球首次交点计算。
- 已实现当前位置所在 region、下一界面、界面法线等查询。
- 已实现沿完整直线段计算最大几何深入深度，避免只检查事件端点造成漏计。

### 3.3 光源

- 已实现 pencil 光源。
- 已实现 Gaussian 光源横向位置采样。
- 已实现零宽 ring 光源。
- 已实现有限宽度 annulus 面积均匀采样。
- 已实现 ring 的 fixed direction 和 aim-at-target 两种方向模式。
- 已提供确定性 source geometry 测试接口。

### 3.4 光学传播

- 已实现标量 Monte Carlo 光子状态。
- 已实现光学深度采样：

  ```text
  tau = -ln(xi)
  s = tau / (mu_a + mu_s)
  ```

- 已实现跨 region 时保留剩余 optical depth。
- 已实现碰撞吸收：

  ```text
  absorbed = weight * mu_a / mu_t
  ```

- 已实现 Henyey-Greenstein 散射。
- 已实现 Snell 折射。
- 已实现非偏振 Fresnel 反射。
- 已实现全反射处理。
- 已实现 Russian roulette。
- 已实现最大事件数和边界失败诊断。
- 已使用确定性计数型随机流，支持按 seed、wavelength 和 photon ID 复现。

### 3.5 Detector 与仪器指标

- 已实现圆形平面 detector。
- 已实现 detector 半径筛选。
- 已实现 acceptance cone 筛选。
- 已支持直接配置 acceptance angle 或通过 NA 换算。
- NA 使用外部介质折射率计算。
- 已区分 entry-surface specular weight 和 bulk-return diffuse weight。
- 已计算 detected weight、detection efficiency、detected reflectance。
- 已计算 detector 接收光子的最大深入深度、平均路径长度和中位数深度。
- 已计算按 region 加权的路径长度和 path fraction。
- 已支持 ring radius 扫描并输出长格式 `ring_scan.csv`。

### 3.6 CPU runtime

- 已实现 batch 化 photon 调度。
- 已实现多线程 CPU 运行。
- 已实现固定 batch 顺序归约。
- 已实现进度回调。
- 已实现取消检查。
- 已实现 R/T 的 batch-level standard error。
- 已支持可选三维 absorption grid。
- 已支持数量受限的调试 trajectories。

### 3.7 CUDA runtime

- 已实现 CUDA 标量输运后端。
- CUDA 与 CPU 共享主要物理生命周期。
- 已支持 ring source、detector acceptance、penetration 和 path statistics。
- 已使用有界 batch，避免一次性提交全部光子。
- 已使用 float photon state、double tally。
- 已实现主机固定顺序归约。
- 已将设备和运行时信息写入 manifest。
- 已具备 CPU/CUDA 统计一致性测试基础。

### 3.8 结果输出

已实现以下输出文件：

- `summary.csv`：R/T/A、能量残差、深度和 detector 汇总。
- `detectors.csv`：全部反射逃逸光的径向反射分箱。
- `instrument.csv`：圆形 detector 的接收指标。
- `instrument_regions.csv`：任意 region 的加权路径统计。
- `performance.csv`：耗时和 photons/s。
- `absorption_grid.csv`：三维吸收权重。
- `trajectories.csv`：有限数量调试路径。
- `manifest.json`：配置、运行参数、设备、指标定义和数据 provenance。

### 3.9 StatisticalFujiShape

- 已实现 Python 和 C++ 两套统计形状模型。
- 已支持平均半径表征。
- 已支持 PCA 形变模式。
- 已支持随机 PCA 系数采样。
- 已支持 sigma clip。
- 已支持 JSON artifact 加载。
- 已支持 PLY 输出和 3D smoke test。
- 已记录来源 DOI、cultivar 状态和模型元数据。

需要注意：源数据没有明确证明 cultivar 为 Fuji，因此当前只能称为统计苹果形状模型，不能直接视为已验证的 Fuji 形状模型。

### 3.10 Python SSC 机器学习

- 已实现 synthetic Golden Delicious 数据生成。
- 已实现数据 schema 和数据质量校验。
- 已实现长表到 sample-by-wavelength 矩阵转换。
- 已实现 `mu_a`、`mu_s_prime`、combined、product、`mu_eff`、reflectance 和 mc_augmented 特征。
- 已实现 raw、StandardScaler、SNV、Savitzky-Golay 和一阶导数预处理。
- 已将预处理、零方差过滤和模型封装到 Pipeline 中，避免验证集泄漏。
- 已实现 MLR、PLSR、RBF-SVR 和 Random Forest。
- 已实现 GridSearchCV。
- 已实现 paper-compatible 和 research 两种验证模式。
- 已输出 predictions、leaderboard、metrics、feature schema、fold assignments 和 joblib pipeline。
- 已对 synthetic 数据持续输出“不可用于真实 SSC 预测”的警告。

### 3.11 GUI

- 已实现 Dear ImGui/ImPlot 研究工作台。
- 已支持启动 CPU 仿真。
- 已支持加载 `summary.csv` 并绘制 R/T/A 光谱。
- 已支持调用 Python ML 任务。
- 已支持读取 `metrics.json` 并展示模型指标。
- 已使用异步任务避免界面完全阻塞。

目前 GUI 仍是结果查看器，不是完整的 3D 实时传播工作台。

## 4. 当前尚未完成或尚未打通的部分

### 4.1 统计苹果形状尚未接入光子输运

当前实际 Monte Carlo 边界仍是 `LayeredSphere`。

```text
StatisticalFujiShape → 可生成 3D 网格
LayeredSphere        → 当前 Monte Carlo 实际边界
```

尚未完成：

- 三角形网格 ray-triangle 求交；
- 网格内部 region 判断；
- 真实非球面 skin/flesh/core 界面；
- 网格法线和折射边界处理；
- 网格 transport 与 LayeredSphere 的一致性验证。

### 4.2 C++ 仿真结果尚未进入 ML 闭环

目前 Python 中的：

```text
reflectance
penetration_depth_mm
radial_decay
```

是显式生成的合成代理特征，不是 C++ 对每个真实或统计苹果运行后的 detector 输出。

需要新增：

```text
sample_id / shape_id
  ↓
C++ 每个样本运行
  ↓
detected spectrum、depth、path、R/T/A
  ↓
转换为 ML 长格式数据
  ↓
Python 特征和 SSC 模型
```

### 4.3 3D 渲染尚未完成

当前 GUI 没有：

- 统计苹果网格显示；
- skin/flesh/core 分层显示；
- 光源和 detector 的 3D 模型；
- 光子路径实时绘制；
- 3D 吸收热图；
- detector 接收路径高亮；
- 单 photon 事件级暂停和单步执行；
- 光学公式与动画状态联动。

### 4.4 结果动画和统计动画尚未明确

需要决定是展示：

- 真实每个 photon 的路径；
- 代表性 photon 的路径；
- 大量 photon 的统计云；
- batch 级统计结果；
- 还是上述模式的组合。

不建议在前台实时绘制百万条完整路径。推荐后台统计大量 photon，前台展示有限代表性路径和统计热图。

### 4.5 真实仪器校准尚未完成

当前 detector 只是几何接收模型，尚未包含：

- dark reference；
- white reference；
- detector 响应曲线；
- 光源功率谱；
- 探头窗口和封装；
- 真实 NA 标定；
- 位置误差和角度误差；
- 温度和样品状态修正。

### 4.6 科研验证仍需扩展

尚需补充：

- 多层折射率不匹配的 CPU/CUDA 等价性；
- Gaussian source 的 CPU/CUDA 等价性；
- 三维吸收网格相似性；
- roulette 极端参数；
- 光子数量收敛性；
- Beer-Lambert 和 Fresnel 基准算例；
- MCML 风格参考结果；
- 真实实验批次的外部验证。

## 5. 需要教师确定的关键边界

### 5.1 系统定位

请确认系统最终是：

1. 教学演示系统；
2. 工程仿真工具；
3. 论文验证平台；
4. 真实 SSC 预测系统。

推荐先确定为“教学演示 + 工程验证平台”，暂不宣称真实 SSC 预测系统。

### 5.2 3D 几何边界

需要确定：

- 是否必须使用 StatisticalFujiShape 作为输运边界；
- 是否需要 skin、flesh、core 三层；
- 是否允许先采用径向内缩的近似内层；
- 是否需要保留局部凹陷和果梗区域；
- 是否支持用户导入 PLY/OBJ/STL；
- 允许的网格面数和渲染精度；
- 是否需要切面、透明组织和体渲染。

推荐 MVP：统计苹果外表面 + 径向内缩 skin/flesh/core，多边形网格实际参与光线求交。

### 5.3 光学模型边界

需要确认第一版是否固定为：

```text
标量 Monte Carlo
吸收 + 散射
Henyey–Greenstein
Fresnel + Snell
全反射
Russian roulette
```

建议第一版暂不加入偏振、荧光、时间飞行、波动光学和温度耦合。

### 5.4 光源和 detector 边界

需要确定：

- 是否必须支持 pencil、Gaussian、ring 三种光源；
- ring 是否采用有限宽 annulus；
- detector 是否固定同轴；
- 是否模拟 detector 对光源的遮挡；
- 是否支持多个 detector；
- 是否支持扫描 ring radius、detector distance 和 NA。

推荐 MVP：一个 ring source、一个 circular detector、可调 ring radius、NA 和波长。

### 5.5 动画边界

需要确定：

- 是否需要单 photon 单步模式；
- 是否需要多 photon 并行路径；
- 是否需要吸收热图；
- 是否需要显示 photon weight；
- 是否需要按事件暂停；
- 是否需要速度控制；
- 是否需要录制 GIF/MP4；
- 是否需要保存每一步的状态用于复盘。

推荐 MVP：

```text
单 photon 事件级动画
+ 100～1000 条代表性路径
+ 大量 photon 的统计热图
```

### 5.6 公式展示边界

需要确定公式是：

- 仅显示公式文本；
- 实时显示当前 photon 的公式参数；
- 还是显示公式计算过程和数值变化。

推荐实时展示：

```text
tau = -ln(xi)
s = tau / mu_t
absorbed = w * mu_a / mu_t
R = (Rs + Rp) / 2
R + T + A + discarded ≈ 1
```

ML 部分展示：

```text
mu_eff = sqrt(3 * mu_a * (mu_a + mu_s_prime))
SNV(x) = (x - mean(x)) / std(x)
y = beta_0 + beta_1 x_1 + ... + beta_n x_n
K(x, x') = exp(-gamma ||x - x'||^2)
```

### 5.7 ML 边界

需要确认：

- 第一阶段是否继续使用 synthetic 数据；
- 是否必须接入 C++ detector 输出；
- 是否需要展示每个 preprocessing 中间结果；
- 是否需要展示 GridSearchCV 的参数搜索；
- 是否需要显示 calibration/validation 划分；
- 是否要求按 batch 做独立验证；
- 是否允许界面显示“SSC prediction”；
- 是否必须使用真实实验数据才能出现 calibrated 标签。

推荐将模型状态分为：

```text
method_demo
experimental_pending_validation
experiment_calibrated
```

只有真实实验数据并完成外部验证后，才允许使用 `experiment_calibrated`。

### 5.8 性能边界

需要确定：

- 目标平台是 CPU、单 GPU 还是多 GPU；
- 交互动画需要多少 photon/s；
- 科研统计运行需要多少 photon；
- 是否接受后台计算和前台低数量可视化分离；
- 是否需要保存完整 photon history。

推荐：

```text
动画：少量代表性 photon，优先交互
统计：后台批量运行，优先结果稳定
GPU：用于大规模统计，不要求逐 photon 与 CPU 一致
```

## 6. 建议的完整 3D 系统形态

```text
3D View
 ├── 苹果网格
 ├── skin/flesh/core 图层
 ├── 光源和 detector
 ├── photon path
 ├── absorption heatmap
 └── detector accepted path

Physics Panel
 ├── wavelength
 ├── mu_a / mu_s' / g / n
 ├── Fresnel / Snell
 ├── current weight
 ├── current region
 └── energy conservation

Animation Panel
 ├── play / pause / step
 ├── speed
 ├── photon ID
 ├── event ID
 └── path filters

ML Panel
 ├── raw data
 ├── feature construction
 ├── preprocessing
 ├── train/validation split
 ├── model training
 ├── prediction
 └── metrics and residuals
```

## 7. 建议的阶段性验收标准

### 阶段一：现有能力验收

- CPU CLI 可以完成 validate/run。
- CPU 测试通过。
- R/T/A 能量残差合理。
- boundary failures 和 max event terminations 为零。
- ring sensor 和 ring scan 可以输出完整结果。
- Python 数据校验和 ML smoke test 可以运行。

### 阶段二：3D 展示验收

- 可以加载统计苹果形状。
- 可以显示至少两层组织。
- 可以显示 ring source 和 circular detector。
- 可以播放代表性 photon 路径。
- 可以显示吸收位置和 detector 接收路径。
- 可以实时显示 photon weight、region、event 和深度。

### 阶段三：3D 输运验收

- photon 可以与三角形苹果网格求交。
- 网格边界支持折射、反射和全反射。
- 网格结果与 LayeredSphere 基准在球形测试中统计一致。
- 统计苹果形状可以产生稳定的 R/T/A 和 detector 结果。

### 阶段四：ML 教学展示验收

- 可视化显示长表到光谱矩阵的转换。
- 可视化显示特征公式和预处理公式。
- 可视化显示 calibration/validation 划分。
- 可视化显示模型训练和参数搜索。
- 可视化显示预测散点、残差和模型指标。
- synthetic 数据和模型状态始终有清晰警告。

### 阶段五：仿真—ML 闭环验收

- 每个样本具有唯一 sample_id 和 shape_id。
- C++ 仿真输出可以转换成 ML 输入长表。
- ML 特征能够追溯到具体 shape、wavelength、source 和 detector 配置。
- manifest 能记录完整参数和版本。
- 真实实验数据具备独立批次验证后，才考虑 calibrated 状态。

## 8. 建议教师最终确认的最小决策清单

如果希望尽快进入开发，教师至少需要确认以下 10 项：

1. 系统是否定位为教学/工程演示，而不是当前阶段的真实 SSC 产品。
2. 是否必须让 StatisticalFujiShape 参与实际光线求交。
3. 组织层数采用两层还是 skin/flesh/core 三层。
4. 第一版是否只支持 ring source 和 circular detector。
5. 是否采用标量 Monte Carlo，不加入偏振和荧光。
6. 是否采用“少量路径动画 + 大量统计热图”的展示方式。
7. 公式是否需要实时数值化展示。
8. ML 是否必须接入 C++ 真实 detector 输出。
9. 第一阶段是否继续使用 synthetic 数据。
10. 最终验收优先级是视觉效果、物理正确性、性能还是 ML 闭环。

## 9. 结论

项目已经完成了较完整的 C++ 标量光子输运基础、CPU/CUDA 后端、环形光源与 detector 指标、结果协议、统计苹果形状建模和 SSC 机器学习实验框架。

项目距离完整 3D 展示系统的主要差距不在基础 Monte Carlo 公式，而在三个接口：

```text
统计苹果网格 → 实际光线边界
Monte Carlo 结果 → 3D 渲染状态
C++ detector 输出 → ML 特征输入
```

教师需要优先确定系统定位、3D 几何精度、物理模型范围、动画深度、ML 是否真实闭环以及数据是否允许进入 calibrated 状态。边界确定后，后续开发可以按照“3D 网格输运 → 渲染与动画 → 公式面板 → 仿真结果接入 ML → 验收验证”的顺序推进。
