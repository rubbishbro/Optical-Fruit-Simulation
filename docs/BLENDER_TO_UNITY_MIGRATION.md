# Blender 场景到 Unity WebGL 的迁移基线

Unity 仿真视图的视觉权威源是：

`assets/blender/alternatives/01_ring_illumination_debug.blend`

它不是参考图，而是运行时装置资产的来源。Unity 中原先由球体等 Primitive 临时拼出的苹果已经移除；缺少导出的 FBX 时，运行时会明确报错，不再静默退回程序球体。

## 迁移范围

- `Apple_ModeB_Debug` → `BlenderApple`：保留 Blender 中的不规则果形与顶部凹陷，2048 个顶点。
- `DetectorHousing`、`DetectorGlass`：迁移底部探测器外壳与玻璃面。
- 12 组 `LightModel_XX`：每组拆成 `RingLampHousing_XX` 与 `RingLampEmitter_XX`，共 24 个灯具网格。
- Blender Z-up 转换为 Unity Y-up。
- 原场景采用毫米量级尺寸，导出根节点使用 `0.03` 展示比例。

地面、Blender 相机、Blender 灯光以及静态曲线没有重复导入。Unity 继续根据实际苹果包围盒和教学参数动态计算灯环、射线与光源，因此果形来自 Blender，光学路径仍可交互和解释。

## 再生成命令

在项目根目录执行：

```bash
blender -b assets/blender/alternatives/01_ring_illumination_debug.blend \
  -noaudio --python scripts/export_blender_ring_rig_to_unity.py -- \
  apps/fruitsim_unity/Assets/Resources/FruitsimBlenderRig.fbx
```

随后构建 WebGL：

```bash
FRUITSIM_BUILD_TIMEOUT=900 bash scripts/build_fruitsim_unity_webgl.sh
```

## 防回退检查

`python/tests/test_blender_unity_asset.py` 会检查 FBX 中是否存在苹果、探测器和全部 12 组双部件灯具，并检查 Unity 启动代码必须加载该 FBX、不得恢复 Primitive 球体回退。

最终验收还必须从浏览器前台完成：画面应同时看见凹顶苹果、完整灯环和底部探测器；连接 Gateway 后启动 Run，应推进至 `completed/completed`，浏览器控制台不得出现 warning 或 error。
