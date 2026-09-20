# Fruitsim 前台与数据链路完整验收（2026-09-20）

## 技术结论

本轮已从真实浏览器学生入口打通 `WebGL → Gateway → Run 编排 → 标准产物`，并独立
重跑数学合成、C++ Monte Carlo、审计和全部图像。最终前台会话 Unity 正常就绪，
新建 Run 到达 `completed/completed`，波长交互与事件重放有效，浏览器控制台错误和
警告均为 0。Python 34/34、干净 Debug C++ CTest 3/3、Unity WebGL Release 构建均通过。

数据链路没有发现主键、波长网格、外键、公式重算、能量守恒或目标边界泄漏。结论的
严格边界仍是“合成方法与教学流程可用”，不是“真实苹果 SSC 模型有效”。当前 Run
没有训练模型，因此只能确认目标未进入特征列表和未伪造 split 声明，不能宣称完成了
训练/验证/测试划分的统计泛化验证。

## 前台证据：学生入口可完成完整操作

- 浏览器入口：`http://127.0.0.1:18080`，Unity 状态从“加载中”变为“已就绪”。
- Gateway：前台按钮连接 `ws://127.0.0.1:8765`，握手与 latest sequence 正常。
- 最终独立 Run：`frontend_release_1036`，事件顺序为
  `run_accepted → queued → generating/running → run_completed`，标准 Run 目录生成。
- 交互：820 nm 波长更新收到 `viewer_state/viewer/updated`；事件重放恢复全部序列。
- 布局：桌面三栏和 720 × 900 窄屏单栏均无横向溢出，控制项在 Unity 视图之前可达。
- 浏览器 QA：最终新会话的 `error`/`warn` 日志数组为空。
- 资源响应：`WebGL.framework.js.gz` 为 `text/javascript + gzip`，`WebGL.wasm.gz` 为
  `application/wasm + gzip`。

前台测试中实际发现并修复了四类阻断问题：重复 `Build/Build/` 资源路径、显式 gzip
资源缺少编码头、运行时 Shader 被裁剪后材质变紫、`CreatePrimitive` 隐式创建已被
裁剪的碰撞体。最终场景改为随构建打包的实体色 Shader，以及不带 Collider 的内置
网格展示对象。

## 数据与指标定义

数学 Run 为 32 个样本 × 51 个波长，共 1632 行光谱；波长范围 500–1000 nm，步长
10 nm。目标只称为 `synthetic_ssc_proxy`。其生成不是“从最终链路结果简单反算后加
高斯噪声”，而是先抽样 latent SSC、含水率、增益和波长漂移，再正向构造吸收系数、
约化散射系数、有效衰减系数和反射率；高斯扰动只作为平滑光谱噪声的一部分。代理目标
由吸收带摘要确定，因此它是受控方法演示目标，不是实验 Brix 标签。

物理 Run 使用 6 个波长、每波长 4096 个光子，共 24576 个光子。`detected_reflectance`
定义为探测权重除以发射光子数；能量残差定义为 `1 − R − T − A − discarded`。当前
几何是半径 40 mm 的双层球、1 mm 表皮、环形光源和有限孔径探测器，参数均为合成假设。

## 结果与图像合理性

- 数学数据：0 个空值、0 个重复 sample ID、0 个重复 sample/wavelength 键；反射率
  范围 0.6447–0.8313，代理目标范围 11.1045–11.3446。
- 公式：保存的 `mu_eff` 可由 `sqrt(3 * mu_a * (mu_a + mu_s_prime))` 在容差内重算。
- 目标边界：没有 `ssc_brix` 数值列；代理目标是样本级常量，不是随波长变化的伪特征；
  审计确认目标不在特征名中。
- 物理结果：每个波长有效命中 5–11 个，探测反射率为 0.000659–0.001538；最大绝对
  能量残差为 1.36e-5，边界失败和最大事件终止均为 0。
- 可视化：数学 Run 输出路径图、光谱热力图、PCA 散点、波长相关热力图和代表光谱；
  物理 Run 输出路径图、探测响应/命中数、穿透深度/组织贡献和能量残差图。全部 PNG
  已逐张人工检查，无空图、裁切、错误色标或不可读重叠。

最初的 64 光子物理演示只有 800 nm 出现一次命中，虽然公式审计通过，但图像会误导
课堂解读。本轮把学生入口默认提高到每波长 4096 个光子，并把不同量纲拆到双轴：
探测反射率配命中数、穿透深度配果肉路径占比。图像现在能同时呈现趋势和统计支持量。

## 方法与复现

验收包含四层：静态语法和压缩响应头；全新浏览器前台交互；标准 Run 数据审计及图像
人工检查；独立 Debug C++ 构建与 Python 全回归。关键复现命令如下：

```bash
bash scripts/build_fruitsim_unity_webgl.sh
bash scripts/run_web_demo.sh
PYTHON_BIN=/home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python \
  bash scripts/run_student_demo.sh
PYTHONPATH=python /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python \
  -m unittest discover -s python/tests -p 'test_*.py' -v
ctest --test-dir build-acceptance-20260920 --output-on-failure
```

旧 `build/` 目录仍包含项目迁移前的 `/home/rubbishbro/桌面/...` 路径，直接运行其中的
CTest 会找不到可执行文件。该缓存不作为验收证据；本轮使用当前路径重新配置的 Debug
目录 `build-acceptance-20260920`，其 3 项测试均实际执行并通过。

## 局限、稳健性与下一步

- 物理探测器即使在 4096 光子/波长下也只有 5–11 个命中，足够教学展示但不足以支持
  精细的波长优劣结论。需要研究级曲线时应增至至少 20000 光子/波长并报告重复种子区间。
- PCA 和相关图是描述性图，不建立因果关系，也不证明真实 SSC 可预测。
- 当前没有真实实验标定、独立批次、训练模型或外部验证集；后续引入 ML 时必须以
  `fruit_id`/批次分组切分，在任何拟合型预处理之前固定 split，并增加 train-only fit 审计。
- Linux 服务器部署仍需在 Ubuntu 22.04 容器/主机做一次最终网络、反向代理、TLS 和并发
  验收；本轮开发机是 Linux x86_64，但并非目标 Ubuntu 22.04 实机。

## 后续问题

1. 课堂默认应优先保持约 10 秒延迟的 4096 光子，还是增加“快速/标准/研究”三级物理档？
2. 真实仪器的探测器半径、NA、表皮厚度与光学系数由哪一批测量数据标定？
3. ML 阶段是否以批次外推、果园外推或品种外推作为主要泛化目标？
