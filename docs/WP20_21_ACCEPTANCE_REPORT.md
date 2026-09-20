# WP20/21 验收报告

## 结论

WP20 已完成；WP21 已完成本轮 Linux/无 GPU 基线验收。Release 构建、Development
构建和 WebGL 构建均通过，未发现 Shader 缺失异常、托管异常或残留 Unity/Bee 构建进程。

## WP20 变更

- `RunViewer` 先读取 `status.json` 的修改时间和文件长度，只有指纹变化时才重新读取
  manifest/status/artifacts 并统计 CSV 行数。
- 缺失目录或尚未生成 `status.json` 显示 `Empty`，不在每次轮询中重复输出 Warning。
- 契约版本不支持、Run ID 不一致和空契约显示 `BlockingError`；文件暂不可用显示
  `RecoverableError`；成功加载显示 `Ready`。
- 调试面板增加 FPS、CPU、RSS、GC、Unity 分配、Mono 内存、对象数量、探测次数和完整
  加载次数，便于教师演示和性能定位。
- 支持 `FRUITSIM_RUN_DIR=/absolute/path` 或 `-fruitsim-run /absolute/path` 指定 Run。
- 无 GPU (`NullGfxDevice`) 时跳过灯光、射线、材质、传感器外观对象创建，但仍保留
  光学配置计算和 RunViewer 状态页面。

## WP21 测试记录

| 项目 | 结果 |
|---|---|
| Linux Release 构建 | 通过，默认产物位于 `apps/fruitsim_unity/build` |
| Linux Development 构建 | 通过，独立产物位于 `/tmp/fruitsim-wp21-development` |
| Release 无图形运行 20 秒 | 通过；退出码 124 为人为超时；RSS 115576 kB，约 112.9 MiB |
| Release 有效 Run 运行 15 秒 | 通过；退出码 124 为人为超时；RSS 116684 kB，约 114.0 MiB |
| Development 无图形运行 12 秒 | 通过；退出码 124 为人为超时；RSS 227648 kB，约 222.3 MiB |
| WebGL Release 构建 | 通过；压缩产物约 10.5 MB |
| WebGL 静态入口 | `/health`、`index.html`、loader 均 HTTP 200 |
| 1 秒构建超时 | 按预期返回非零码并报告超时；2 秒后无 Unity/Bee 残留进程 |

Release 运行日志未出现 `ArgumentNullException`、Shader 错误、`MemoryLeaks` 或
Profiler 警告。Development 运行出现 Profiler 内存阈值和 MemoryLeaks 诊断行，这是
Development/Profiler 构建的预期诊断输出，不属于 Release 演示路径故障。

## 复现命令

```bash
FRUITSIM_BUILD_TIMEOUT=300 bash scripts/build_fruitsim_unity_linux.sh
FRUITSIM_BUILD_MODE=development \
FRUITSIM_BUILD_OUTPUT=/tmp/fruitsim-wp21-development/Fruitsim.x86_64 \
FRUITSIM_BUILD_TIMEOUT=300 bash scripts/build_fruitsim_unity_linux.sh
FRUITSIM_BUILD_TIMEOUT=900 bash scripts/build_fruitsim_unity_webgl.sh
```

RunViewer 指定数据示例：

```bash
FRUITSIM_RUN_DIR=/absolute/path/to/results/runs/<run_id> \
  apps/fruitsim_unity/build/Fruitsim.x86_64 -batchmode -nographics
```

## 后续边界

包清理、浏览器端真实 WebSocket 联调和教师演示流程仍属于 WP19/WP22 的后续工作，
本验收不将它们混入运行时稳定性结论。
