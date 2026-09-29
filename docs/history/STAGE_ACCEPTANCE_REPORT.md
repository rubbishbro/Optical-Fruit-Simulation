# Fruitsim 阶段验收报告

验收对象：工作包 0–8 的当前数据、仿真、审计、可视化和学生入口链路。

验收结论：当前阶段可以交付为“可重复的合成/仿真方法演示与调试基线”，不能交付为“真实苹果 SSC 预测系统”。所有 Run 都保留这个边界。

## 实际执行结果

入口：

```bash
bash scripts/run_stage_acceptance.sh
```

结果：

| 检查项 | 结果 | 证据 |
|---|---:|---|
| C++ 测试 | 3/3 通过 | `build-mesh` 的 CTest |
| Python 测试 | 25/25 通过 | 合同、数据加载、公式审计、可视化、物理适配与重复性 |
| 数学小流程 | 通过，有 2 个明确 caveat | `results/stage_acceptance/math_seed20260919/qa/audit_report.json` |
| C++ 物理小流程 | 通过，有 2 个明确 caveat | `results/stage_acceptance/physical_seed20260919/qa/audit_report.json` |
| 数学可视化 | 5 类图生成 | 热力图、散点图、相关性热力图、光谱图、路径图 |
| 物理可视化 | 4 类图生成 | 探测光谱、路径统计、能量残差、路径图 |

物理小流程的最大能量残差为 `5.61697e-05`，小于当前审计阈值 `1e-3`。相同 C++ 配置、线程数和随机种子重复运行时，`summary.csv`、`instrument.csv` 和 `instrument_regions.csv` 字节一致。

## 公式合理性边界

数学合成链路当前审计：

- `mu_s' = 0.44 * (lambda / 700)^(-0.72)`：在当前波长域内为有限正值；
- `mu_a`：由基线、吸收带、含水代理和合成 SSC 代理构造，输出保持非负；
- `mu_eff = sqrt(3 * mu_a * (mu_a + mu_s'))`：结果字段被保存，并由审计逐点重算比对；
- `reflectance = gain * exp(-0.55 * optical_depth) * noise`：结果被限制在 `[0, 1]`，但系数仍是方法演示参数；
- `synthetic_ssc_proxy` 是演示目标，不是 `ssc_brix`，不能用来宣称真实预测能力。

C++ Monte Carlo 链路当前审计：

- `energy_residual = 1 - R - T - A - discarded`；
- `detected_weight = detected_specular_weight + detected_diffuse_weight`；
- `detection_efficiency = detected_weight / launched_photons`，并与 `detected_reflectance` 对齐；
- 当前物理 Run 没有实测 SSC，不能进入真实标签训练或真实精度结论。

## 泄漏与可信性检查

已执行并通过：

- sample 主键唯一；
- `(sample_id, wavelength_nm)` 光谱键唯一；
- 光谱记录的外键都能回到样本表；
- 每个样本的波长网格完整且一致；
- Run 内没有把 `ssc_brix` 伪造为数值；
- 合成 proxy 在样本内保持常量，不作为波长级特征；
- 有 ML split/feature schema 时，审计会检查 calibration/validation 样本交集、样本分配唯一性和 target 不在 feature 名称中；
- 没有 ML split artifact 时，报告明确写为“未声明 ML split”，不会误报为已验证。

因此，当前能确认的是“数据处理边界和结构没有发现泄漏”。还不能确认真实实验数据接入后的标签质量、批次外推能力或跨设备泛化能力；这些必须在 `real_measurement` / `hybrid_calibrated` 阶段重新审计。

## 可视化与 Unity 转化可行性

当前可转化的量已经足够支撑阶段演示：样本 ID、批次、波长、反射率、吸收/约化散射/有效衰减系数、探测权重、效率、路径深度、皮层/果肉路径比例，以及 C++ 配置、性能和能量审计结果均有明确来源。

每一张图都写入 `visualization_manifest.json`，并从已校验的 Run 产物生成。因此可以稳定转化为：

- Unity 调试面板中的单次 Run、波长滑条、探测器指标和能量残差；
- 学生查看的流程图、散点图、热力图和光谱图；
- 后续 Web/Notebook 端的静态或交互式复现。

当前不足是物理 Run 仍是单样本、小规模演示，且没有真实标签；所以图像适合解释和调试，不适合做统计结论。PCA 颜色使用合成 proxy 只用于演示可视化，不等于模型输入，也不应被解释为真实 SSC 分离效果。

## 普通学生入口

```bash
bash scripts/run_student_demo.sh
```

学生只需要查看每个输出 Run 下的 `qa/audit_report.json`、`visualizations/`、`manifest.json` 和 `status.json`。如果只学习 Python 链路：

```bash
bash scripts/run_student_demo.sh --skip-physical
```

这条路径不会要求学生理解 Unity、C++ 或模型训练；它先生成小数据，再显示检查结果，最后打开图像目录即可。

## 下一阶段准入条件

进入真实测量或训练模型前，必须补齐：真实 SSC 与测量时间/设备/批次、外部校准集、跨批次或按果实分组的正式 split、仪器噪声与缺失机制、实测数据的单位/波长/元数据审计，以及真实数据上的不确定性和误差报告。
