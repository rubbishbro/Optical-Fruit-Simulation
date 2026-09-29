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

## 交互参数与 Manim 动画

Unity WebGL 的预编译只固定程序代码，页面仍可实时传入光学和苹果参数。Manim 生成的是视频；播放时只能控制进度，视频内的数据、文字和镜头已固定。因此动画参数必须在渲染前确定，不能把每次滑块变化直接当作一次 Manim 渲染。

目前的真实链路是：光学表单 → `ApplyWebParameters` → Unity 场景即时变化；波长另发 `viewer.set_wavelength`。`run.start` 只提交数学数据生成的 `seed` 和 `samples`，不提交光学表单参数。`scripts/research/render_snv_teaching_animation.py` 使用固定的合成光谱，也没有读取 Run 或页面参数。因此当前尚无“页面参数 → 对应计算结果 → Manim 视频”的闭环。

拟采用一份不可变的参数快照作为计算和动画的共同依据：

1. 页面把用户选定的实验参数、随机种子和单位整理为 `experiment_spec`。拖动滑块时只更新 Unity/浏览器图表；用户确认后才提交一次计算。
2. 计算服务校验 `experiment_spec` 并保存到 Run；结果清单记录 `run_id`、输入数据摘要、输出数据路径和实际采用的参数。页面通过 `run_id` 展示计算结果。
3. 用户在某个 Run 上选择“生成讲解动画”及场景、样本、教学步骤。服务从该 Run 的结果生成 `animation_spec`；动画数值必须读取同一 Run 的数据，不能重新随机生成。
4. 将规范化的 `animation_spec`、输入数据摘要、Manim 场景版本及画质预设合成缓存键。命中已完成的 MP4 就直接播放；未命中则加入后台渲染队列，页面显示排队/渲染/完成/失败状态。完成后记录 MP4、封面、规格和缓存键，供相同请求复用。

`animation_spec` 的最小内容可表示为：

```json
{
  "scene": "snv",
  "run_id": "example_run",
  "sample_id": "sample_001",
  "steps": ["raw", "mean", "standard_deviation", "transform"],
  "render_preset": "preview"
}
```

计算参数属于 `experiment_spec`；动画只引用 Run，并补充镜头/教学步骤/画质参数。画质预设由渲染服务定义，避免浏览器传入任意分辨率或帧率。动画清单必须显示关联的 `run_id` 和参数摘要；若播放的是通用概念动画，明确标为“示意”，不标成当前实验结果。

为控制渲染量，固定知识点（例如 SNV 公式讲解）可以预渲染少量通用片段；连续参数变化仍由 Unity 或 Canvas 即时展示。只有用户明确选定 Run 和场景时才按需渲染与该结果精确对应的 Manim 动画。可以先生成低画质预览，再对需要交付的片段生成高画质版本。上述计算参数存档、动画任务、缓存与播放器联动是待实现的接口约定，不是现有功能。

## 图像来源

发布资源位于 `apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/`。运行：

```bash
PYTHONPATH=python MPLCONFIGDIR=.cache/matplotlib \
  /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python \
  scripts/build_web_teaching_assets.py
```

脚本从既有物理/数学 Run、`assets/figures/` 和 `results/ml_golden_demo/` 提取并生成发布图。`apply_webgl_demo_shell.py` 在构建后将它们复制到 WebGL 根目录的 `static/`。所有 ML 指标均标注为合成教学数据，不构成真实苹果 SSC 精度声明。
