# StatisticalFujiShape 数据、方法与使用边界

## 数据来源

统计形状模型使用 Zenodo 记录
[3D high-resolution point cloud of apple shapes and UAV videos in apple orchards](https://doi.org/10.5281/zenodo.15635995)
中的 `LabDataset.zip`。记录由 Wang、Jia、Cao、Kooistra、Lau Sarmiento、Wang 和 Valente 发布，
许可为 CC BY 4.0。压缩包 MD5 为 `dee3f690c983fdceb0332000eb9d1ed2`，包含
`apple2.ply` 至 `apple101.ply` 共 100 个已对齐的实验室扫描点云。

Zenodo 记录没有声明 cultivar。`StatisticalFujiShape` 是项目要求的建模层名称，不代表该数据已经
被证实为 Fuji。所有模型 artifact 写入：

```text
cultivar_label_requested: Fuji
cultivar_status: unverified_in_source_record
```

获得论文补充材料、实验记录或作者确认前，不得将输出描述为经过验证的 Fuji 统计形状。

## 为什么不能直接对 PLY 顶点做 PCA

各 PLY 文件的顶点数量不同，点的数组索引也不是解剖学 correspondence。直接补齐数组或按索引
拼接后做 PCA 会把扫描采样顺序当成果实形变，物理意义错误。当前流程将每个点云转换到共同的
Fibonacci 球面方向网格：

1. 读取 binary little-endian 或 ASCII PLY 的 `x/y/z`。
2. 使用各坐标轴 robust quantile bounds 的中点进行平移对齐，不做尺寸归一化，因此实际尺寸变化
   保留在 PCA 中。
3. 将原始坐标从 m 转成 mm。
4. 对每个共同方向查询点云单位方向上的近邻，以逆角距离加权得到 radial surface。
5. 所有样本得到相同长度、相同方向语义的 radius vector。
6. 对 sample-by-direction 矩阵做 SVD/PCA。
7. 每个保存的 deformation mode 表示该主成分的一个标准差形变，随机系数采用标准正态分布并
   默认截断到正负 3 sigma。
8. 对共同方向做凸包三角化，平均形状和所有随机实例共享封闭网格拓扑。

该方法假设苹果表面相对于所选中心是 star-shaped。深凹、遮挡、离群点及扫描不完整会影响 radial
重建；模型 manifest 保存训练参数以便复现和比较。

## 下载与训练

原始数据约 4.77 GB，不纳入 Git。下载、校验并解压：

```bash
mkdir -p data/external/zenodo_15635995
curl -L --continue-at - \
  --output data/external/zenodo_15635995/LabDataset.zip \
  https://zenodo.org/api/records/15635995/files/LabDataset.zip/content

echo "dee3f690c983fdceb0332000eb9d1ed2  data/external/zenodo_15635995/LabDataset.zip" \
  | md5sum --check

unzip data/external/zenodo_15635995/LabDataset.zip \
  -d data/external/zenodo_15635995
```

使用 Python 3.11 环境训练 2048 个表面方向和 8 个 PCA modes：

```bash
cd /home/rubbishbro/desktop/simulator

env PYTHONNOUSERSITE=1 PYTHONPATH=python \
  /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python \
  -m fruitsim_shape train \
  --input-dir data/external/zenodo_15635995/LabDataset \
  --output data/shape_models/generated/statistical_fuji_shape_v1.json \
  --input-unit m --directions 2048 --modes 8 \
  --neighbors 12 --max-points 300000
```

模型 JSON 包含数据 DOI、许可、archive checksum、实际样本文件、中心、共同 directions、平均半径、
PCA eigenvalues/deformations、explained variance 和三角形 topology。

## 产生随机苹果

仓库已经包含由上述 100 个点云和参数训练得到的约 0.55 MB artifact：
`data/shape_models/statistical_fuji_shape_zenodo_v1.json`。它使用 2048 个表面方向、4092 个三角形和
8 个 PCA modes，累计解释训练集中约 88.31% 的 radial-shape variance。

```bash
env PYTHONNOUSERSITE=1 PYTHONPATH=python \
  /home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python \
  -m fruitsim_shape sample \
  --model data/shape_models/statistical_fuji_shape_zenodo_v1.json \
  --output results/shapes/random_apple_seed_42.ply \
  --seed 42 --modes 8 --sigma-clip 3
```

相同模型、seed、mode count 和 sigma clip 会产生相同网格。Python API 还提供
`ShapeInstance.inset_vertices_mm(thickness)`，可生成简单径向内缩的 skin/flesh 分界面。

## 与 Monte Carlo 和 GUI 的关系

当前 `StatisticalFujiShape` 已在 Python 与 C++ geometry 层实现，C++ 可加载 artifact，并使用项目
Philox RNG 可复现采样。但现有 Monte Carlo transport 仍使用解析 `LayeredSphere`：

- 尚未实现 triangle mesh BVH/射线求交。
- 尚未实现 mesh 内外判定和多层 offset surface 的稳健拓扑检查。
- 尚未验证凹面、薄皮层、自相交和界面 nudge。
- 当前 GUI 尚未渲染该 PLY/triangle mesh。

因此统计形状目前是可验证的“形状生成层”，不是已经启用的非球形光子 transport backend。后续应
先增加静态三角网格可视化，再实现 CPU mesh reference transport，最后做 CUDA parity。
