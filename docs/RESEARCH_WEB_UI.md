# Fruitsim 科研教学 Web 前台

前台按教学问题而不是组件类型划分为四页：

1. **光学仿真**：显示 Blender 导入的苹果、十二组环形灯具和探测器；支持拖动旋转、滚轮或按钮缩放、视角复位和全屏。
2. **结果图像**：集中浏览吸收热力图、加权光子路径、光谱热力图、PCA、相关热力图、探测器响应、采样深度和能量审计。
3. **ML 链路**：展示数据校验、数据划分、预处理、特征、候选模型与独立验证，并读取真实训练产物生成验证散点和 RMSEP 比较图。
4. **运行与审计**：保留 Gateway 连接、Run 启动、状态推进、事件重放和服务端结果路径。

## Unity 交互接口

网页通过 Unity `SendMessage` 调用：

- `FruitsimOrbitCamera.ZoomIn / ZoomOut / ResetView`
- `FruitsimOpticsExperiment.ApplyWebParameters(json)`

参数 JSON 包含波长、灯环相对半径与高度、光源倾角、光束发散角、总相对功率、探测器相对尺寸与偏移、视场角和方向光线开关。可见光按近似显示颜色绘制；780–1100 nm 使用暗红伪彩，不能解读为人眼实际看到的近红外颜色。

## 图像来源

发布资源位于 `apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/`。运行：

```bash
PYTHONPATH=python MPLCONFIGDIR=.cache/matplotlib \
  /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python \
  scripts/build_web_research_assets.py
```

脚本从既有物理/数学 Run、`pics/` 和 `results/ml_golden_demo/` 提取并生成发布图。`apply_webgl_demo_shell.py` 在构建后将它们复制到 WebGL 根目录的 `static/`。所有 ML 指标均标注为合成教学数据，不构成真实苹果 SSC 精度声明。
