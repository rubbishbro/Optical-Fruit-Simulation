# WebGL 可行性验证记录

目标环境：Ubuntu 22.04 目标、x86_64、服务器无 GPU、Docker 可用。当前开发主机实际运行的是 Linux x86_64，Unity 项目版本为 `6000.3.23f1`。

## 已验证

- Unity Editor 入口已增加 `Fruitsim.Editor.FruitsimBuild.BuildWebGL`；
- `scripts/build_fruitsim_unity_webgl.sh` 能正确把项目切换到 WebGL 目标并提交构建；
- WebGL JavaScript bridge 已加入 Unity 项目；
- bridge 使用浏览器 WebSocket，不调用原生 IP socket；
- Ubuntu 静态服务器可返回 `/health`；
- `.gz` / `.br` 资源可以按原始 MIME 类型和 `Content-Encoding` 返回；
- 浏览器安全响应头已加入；
- C# 参考编译：0 errors，3 个已有字段警告；
- Python 协议集成测试：4/4 通过；
- 完整 Python 回归：34/34 通过；
- C++ CTest：3/3 通过；
- Python wheel 包含 `fruitsim_protocol`、`fruitsim_gateway` 和 `fruitsim-gateway` 入口。

## 当前状态

Unity Personal License 和 WebGL Build Support 已验证，实际 WebGL Release 构建已成功
生成 `Build/WebGL.loader.js`、压缩的 `.data.gz/.framework.js.gz/.wasm.gz` 产物。教学壳
源文件 `FruitsimDemo/index.html` 已在构建后确定性注入，包含浏览器控制台、Gateway
状态和事件时间线；这样规避 Unity 6 Linux 编辑器对项目本地模板的路径兼容差异。
真实浏览器前台还验证了桌面与 720 px 窄屏布局、Gateway 连接、Run 生成、事件重放、
波长交互和 Unity 加载；最终独立会话的浏览器错误/警告为 0。

## 构建成功后的验证命令

```bash
bash scripts/build_fruitsim_unity_webgl.sh
bash scripts/run_web_demo.sh
```

然后在浏览器打开：

```text
http://服务器地址:8080
```

浏览器入口默认位于 `http://服务器地址:8080`，WebSocket 网关配置为：

```text
ws://服务器地址:8765
```

## 结论

WebGL 方案已完成本轮可交付验收：服务器不需要承担 Unity 图形渲染，Gateway 负责
低延迟控制事件，Run 生成和 C++ 物理仿真仍在服务器端执行。后续重点是教师课件流程、
浏览器实际交互美化，以及将更多真实物理 Run 状态映射到 Unity 视图。
