# Blender 建模备选

这里集中保存当前两种可直接打开的 Blender 建模方案。原始工程文件仍保留在上级目录。

## 01 — Ring Illumination 调试方案

- 工程：[01_ring_illumination_debug.blend](./01_ring_illumination_debug.blend)
- 预览：[01_ring_illumination_debug.png](./01_ring_illumination_debug.png)
- 苹果下半部与环形光源交界；
- 环形光源由 `lightmodel.blend` 的两个源立方体复制组成；
- detector 由 `detector.blend` 保留的玻璃、底座和 aperture 组成；
- 适合检查光源环半径、光源倾角、发光面方向和 detector 相对位置。

## 02 — Detector + Apple 建模方案

- 工程：[02_detector_apple_scene.blend](./02_detector_apple_scene.blend)
- 预览：[02_detector_apple_scene.png](./02_detector_apple_scene.png)
- 来源：`blend003_with_apple.blend`；
- 适合检查苹果、detector、地面和整体场景材质关系；
- 不包含新的环形 Mode B 光源结构。

## 选择建议

调试环形照明、入射方向和传感器空间关系时使用 **01**；检查原有苹果与 detector 建模效果时使用 **02**。两个工程是独立副本，后续修改一个不会覆盖另一个。
