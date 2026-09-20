# Fruitsim 学生快速入口

普通学生只需要运行：

```bash
bash scripts/run_student_demo.sh
```

这个入口会自动完成：

1. 生成一个小型、可重复的数学合成 Run；
2. 检查样本主键、波长网格、公式输入范围和合成标签边界；
3. 生成数据处理路径图、光谱图、PCA 图和相关性图；
4. 如果本地存在 C++ `build-mesh`，运行一个小型 ring detector Monte Carlo；
5. 检查 C++ 能量残差、detector 权重恒等式和效率定义；
6. 为每个 Run 输出 `qa/audit_report.json`。

物理演示默认每个波长发射 4096 个光子。这个数量在当前 CPU 基线下约需数秒，能避免
64 光子冒烟测试中探测器命中过少、课堂折线图退化为单点尖峰。只做快速连通性检查时
可以显式传入 `--photons 64`，但不应把该低统计结果用于讲解波长趋势。

结果位于 `results/student_demo/`。先打开每个 Run 的：

```text
qa/audit_report.json
visualizations/
manifest.json
status.json
```

如果只想学习 Python 数据链路，不运行 C++：

```bash
bash scripts/run_student_demo.sh --skip-physical
```

所有结果都是合成/仿真演示，不代表真实苹果 SSC 预测。若要做真实实验，必须先替换为
经过校验的 `real_measurement` 数据，并重新进行外部标定和验证。
