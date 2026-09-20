# Fruitsim 待办工作包

## 当前阶段：Unity 封装、性能与可运行性

### WP18 — Unity 运行时性能优化（已完成第一轮）

- [x] 参数没有变化时不触发重建
- [x] 复用灯光、射线和传感器可视对象
- [x] 复用调试材质，避免每次重建创建 Material
- [x] 缓存苹果 Bounds，避免每个光源重复遍历 Renderer
- [x] 对 `Shader.Find` 失败提供无图形降级路径
- [x] 运行时显示重建次数、对象数量和最近一次重建耗时

本轮已完成脏标记修正、灯光/射线/材质复用、同轴模式延迟创建环形对象、
Bounds 缓存、运行时指标和无图形 Shader 降级。

### WP19 — 构建与资源配置优化（核心项已完成）

- [x] 区分 Debug/Development 构建与 Release 演示构建
- [x] 限制 Unity Job Worker 数量和构建 CPU 范围
- [x] 降低服务器/学生演示默认质量档位
- [ ] 清理不参与演示的运行时包和资源
- [x] 验证 WebGL Build Support 并完成真实 WebGL 构建

构建默认使用 Release 选项；设置 `FRUITSIM_BUILD_MODE=development` 可恢复
Development/Profiler 构建。Linux/WebGL 构建脚本支持 `FRUITSIM_JOB_WORKERS`、
`FRUITSIM_CPU_LIST`、`FRUITSIM_BUILD_TIMEOUT`；Linux 还支持
`FRUITSIM_BUILD_OUTPUT` 以隔离 Debug/Release 产物。本轮已实际完成 Linux Release、
Linux Development 和 WebGL Release 构建；WebGL 静态服务的 `/health`、入口页和
loader 资源也已通过冒烟检查。包清理仍保留为后续独立变更，避免未经验证移除编辑器
或运行时依赖。

### WP20 — 运行时健壮性与演示数据（已完成）

- [x] 无图形模式下不因 Shader 缺失抛异常
- [x] Run 目录不存在时显示一次性状态，而不是持续告警
- [x] 提供明确空状态页面，并支持命令行/环境变量选择 Run
- [x] 将文件轮询改为低开销的状态文件检测
- [x] 区分警告、可恢复错误和阻断错误

### WP21 — 性能与稳定性验收（已完成本轮基线）

- [x] Linux Debug 运行测试
- [x] Linux Release 运行测试
- [x] CPU、RSS、GC、对象数量和帧率基线入口
- [x] 无 GPU/无显示器服务器测试
- [x] Unity 构建异常、超时和残留进程清理测试

### WP22 — WebGL 演示交付（已完成本轮核心项）

- [x] 安装并验证 WebGL Build Support
- [x] 完成 WebGL 构建
- [x] 连接 Gateway 和 Unity WebSocket 客户端
- [x] 完成浏览器端学生入口测试
- [x] 完成教师演示流程和故障提示

### WP23 — Run 编排与端到端联调（已完成本轮核心项）

- [x] `run.start` 连接真实数学合成 Run 生成器
- [x] 推送 queued/running/completed/failed/cancelled 事件
- [x] 保持标准 Run 契约和 append-only journal
- [x] 提供 WebGL + Gateway 一键启动入口
- [x] 完成协议、编排器、静态资源和运行结果端到端测试

## 本轮执行边界

本轮执行 WP22/23 的 WebGL 教学交付、Gateway 联调和 Run 编排；不修改既有
Run 数据契约或 C++ 计算边界。
