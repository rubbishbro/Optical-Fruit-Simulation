你是一个资深 C++17 科学计算/光学仿真平台工程师。我要开发一个名为 fruitsim 的 C++ 光学仿真平台，用于模拟果品等强散射介质中的光传播，最终服务于近红外/可见光无损检测研究。

总体目标：
1. 构建一个模块化 C++17 工程。
2. 支持基础 ray tracing 结构，但最终核心是 Monte Carlo photon transport。
3. 支持果品三层介质模型：skin、flesh、core。
4. 支持光学参数：mu_a、mu_s、g、refractive_index。
5. 支持单波长和多波长仿真。
6. 支持 JSON 配置输入和 CSV 结果输出。
7. 支持命令行运行。
8. 后续可扩展 GUI 和 GPU 加速，但当前只做 CPU MVP。

工程要求：
1. 使用 CMake。
2. 使用 C++17。
3. 模块拆分清晰：
   - core: Vec3, Ray, Random
   - geometry: Sphere, LayeredSphere
   - optics: OpticalProperty, Medium
   - source: LightSource, PencilBeamSource
   - detector: Detector, ReflectanceDetector, TransmittanceDetector
   - solver: Solver, RayTracingSolver, MonteCarloSolver
   - io: ConfigLoader, CsvWriter
   - app: fruitsim_cli
4. 避免全局变量。
5. 避免裸指针，优先使用值语义、std::unique_ptr、std::shared_ptr。
6. 所有随机过程支持 seed。
7. 每个阶段都要能编译运行。
8. 给出完整文件树、CMakeLists.txt、关键源码和运行命令。

请先实现阶段 0：
创建 C++17 + CMake 项目骨架，实现 Vec3、Ray、Random，并提供 fruitsim_cli 示例程序。
不要一次性实现所有功能。