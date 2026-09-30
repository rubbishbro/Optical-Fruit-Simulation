# scripts 目录

面向使用者的构建 / 启动入口保留在本层；辅助工具按用途分组。除非另有说明，所有命令都从
仓库根目录运行。

脚本名统一采用小写 `动作_对象`；长期入口不使用 P0/P1 等阶段编号。测试使用
`test_对象_行为`，研究脚本放在 `research/`，图表脚本放在 `figures/`。

## 正式入口（本层）

- `build_unity.sh linux` / `build_unity.sh webgl`：共用 Unity 构建入口。它会自动在 Unity Hub
  目录中查找 `ProjectSettings/ProjectVersion.txt` 指定的编辑器版本，检查 WebGL Build Support，
  并可用 `UNITY_BIN` 覆盖。`webgl` 会先校验静态资源、构建后注入教学页面并再次校验发布目录。
- `verify_web_teaching_assets.py`：校验目录 JSON、每个数据集 bundle、页面图像与 Unity loader
  的真实引用；`--build-root` 校验发布目录，`--http-base` 校验已服务构建的 HTTP 响应。
- `run_web_demo.sh` / `run_student_demo.sh` / `run_stage_acceptance.sh`：启动与验收。
- `serve_webgl_demo.py`：带 gzip 与跨域头的静态 WebGL 服务。传 `--runs-root <output_root>`
  （`run_web_demo.sh` 已用同一目录）时才开放只读结果接口：
  `GET/HEAD /api/runs/<run_id>` 返回 manifest 摘要与经 `artifacts.json` 登记、白名单媒体类型/role 的产物相对 URL；
  `GET/HEAD /api/runs/<run_id>/artifacts/<artifact_id>` 下载已登记文件。默认不启用；拒绝路径/编码穿越、
  目录形态、跨 Run、符号链接逃逸、未登记文件与 `request.json`/日志，不返回绝对路径或 `request.output_dir`。
- `apply_webgl_demo_shell.py`：构建后确定性注入教学壳，由 WebGL 构建脚本调用。
- `build_web_teaching_assets.py`：生成 WebGL 教学静态资源。输入可用环境变量覆盖：
  `FRUITSIM_RESULTS_ROOT`、`FRUITSIM_MATH_VIS_DIR`、`FRUITSIM_PHYSICAL_VIS_DIR`、
  `FRUITSIM_ML_RUN_DIR`、`FRUITSIM_WEB_ASSET_OUTPUT`、`FRUITSIM_TEACHING_PROFILE`。
- `build_teaching_dataset.py` / `build_ml_teaching_catalog.py`：教学数据与目录生成。
  `build_teaching_dataset` 同时被 `python/tests/test_teaching_dataset.py` 引用，移动时需同步。
- `export_blender_ring_rig_to_unity.py`：Blender → Unity 资产导出。

## figures/

图表与形状演示：`render_simulation_figures.py`、`render_apple_shape.py`、
`render_trajectories_on_shape.py`、`render_detector_obj_under_apple.py`、
`render_blender_detector_apple.py`、`render_blender_ring_mode.py`、`random_apple_3d_demo.py`。
部分脚本默认输出到 `assets/figures/`，其余由 `--output` 指定；
`render_detector_obj_under_apple.py` 需要显式传入 mesh 和 detector OBJ。

## research/

研究 / 探索工具，不属于日常构建入口：`search_joint_controls.py`、
`sweep_optical_controls.py`、`generate_causal_comparisons.py`、
`simulate_guided_photon_paths.py`、`render_snv_teaching_animation.py`。扫描脚本默认输出到
`tmp/`（已被 git 忽略）；其他脚本按各自参数指定输出。

## tests/

前端与端到端检查：`test_ml_teaching.js`、`test_ml_renderer.js`、`test_ml_browser.py`、
`test_demo_browser.py`、`test_demo_e2e.py`、`test_workflow_correctness_e2e.py`。

```bash
node scripts/tests/test_ml_teaching.js
node scripts/tests/test_ml_renderer.js
PYTHONPATH=python python scripts/tests/test_ml_browser.py
PYTHONPATH=python python scripts/tests/test_demo_browser.py
# 真实 Gateway + HTTP 结果接口 + 真实 Chrome A/B（需 google-chrome 与 websocket-client）
PYTHONPATH=python python scripts/tests/test_demo_e2e.py
```

结果接口与脚本级集成测试在 `python/tests/`：
`test_serve_webgl_demo_api.py`（API 安全/HEAD/gzip）、`test_run_web_demo_e2e.py`（真实启动
`run_web_demo.sh` 后 WS 建 Run 并 HTTP 读取同一 Run）。
