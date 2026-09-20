# Work Packages 22–23 — WebGL 教学交付与 Run 编排

## WP22：WebGL 演示交付

- 采用 `Assets/WebGLTemplates/FruitsimDemo/index.html` 作为可维护的教学壳源文件；由于
  Unity 6 Linux 编辑器对项目本地模板的解析存在兼容性差异，正式构建保持 Unity
  `Default` 模板稳定产出，再由 `scripts/apply_webgl_demo_shell.py` 确定性注入教学壳。
  页面包含教学控制台、Unity Canvas、Gateway 连接状态、Run 状态和事件时间线。
- 浏览器控制台支持连接 Gateway、生成 Demo Run、请求取消、重放事件和发送波长变化。
- `scripts/run_web_demo.sh` 一键启动静态 WebGL 服务和 Gateway。
- 静态服务器继续提供压缩资源、`/health` 和浏览器安全响应头。

## WP23：真实 Run 编排与端到端联调

- `run.start` 不再只返回演示事件，而是启动 `fruitsim_pipeline generate-math`。
- Gateway 推送 `queued`、`generating/running`、`completed`、`failed` 或 `cancelled` 事件。
- Run 仍写入标准 `manifest.json`、`status.json`、`artifacts.json`，不改变既有数据契约。
- `run_id`、seed、样本数和 pipeline 超时均有边界控制；事件写入 append-only journal。
- 保留 WebGL 作为浏览器控制/可视化端，Python pipeline 作为服务器端执行端，C++ 物理
  仿真不在浏览器中运行。

## 启动

```bash
bash scripts/run_web_demo.sh
```

默认入口：`http://服务器地址:8080`。默认 Gateway：`ws://服务器地址:8765`。

可以通过以下环境变量调整部署：

```bash
FRUITSIM_DEMO_BIND=0.0.0.0 \
FRUITSIM_WEB_PORT=8080 \
FRUITSIM_GATEWAY_PORT=8765 \
FRUITSIM_DEMO_OUTPUT_ROOT=results/web_demo/runs \
bash scripts/run_web_demo.sh
```

## 验收边界

本包验证静态资源、WebSocket 协议、Run 生成和事件链路；教师讲述中的物理模型、合成
数据边界和 `synthetic_ssc_proxy` 限制仍必须按 `STAGE_ACCEPTANCE_REPORT.md` 说明。

## 本轮实测结果

- Unity 6000.3.23f1 / WebGL Release 构建：`Build Finished, Result: Success`。
- 构建产物包含 `Build/WebGL.loader.js`、`.data.gz`、`.framework.js.gz`、`.wasm.gz`，
  教学壳无未替换宏，静态入口和压缩资源 HTTP 均返回 200。
- Gateway CLI WebSocket E2E：命令确认成功，事件序列为
  `run_accepted → run_progress → run_progress → run_completed`；`manifest.json` 和
  `status.json(state=completed)` 均生成。
- 端口、输出目录和日志均可通过环境变量覆盖，构建和演示结束后无残留 Unity/Bee 进程。
- 真实浏览器入口已修正并验证 Unity 资源只拼接一次 `Build/`，显式 `.gz` 请求返回正确
  `Content-Encoding` 与原始 MIME；最终前台控制台错误/警告为 0。
- WebGL 场景使用无碰撞体的纯展示网格构造苹果、叶片、底座和传感器，避免裁剪后的
  `SphereCollider`/`CapsuleCollider` 在浏览器运行时被隐式创建。
