# 数据证据层规范

## 数据集分类

- `OBSERVED`：用户上传、公开数据库、API 或网页采集的真实观测数据；
- `DERIVED`：由已登记 Dataset 计算产生，必须声明 `derived_from`；
- `SYNTHETIC`：模拟或生成数据，禁止伪装为真实观测数据。

Dataset Registry 与 Artifact Registry 分工：Artifact 记录文件、哈希、路径、Run 和上游文件；Dataset 记录语义类型、来源、许可、数据血缘和质量状态。

## 来源采集

`collect-url` 只允许 HTTP/HTTPS，设置超时与体积上限，并保存：请求 URL、最终 URL、采集时间、HTTP 状态、Content-Type、SHA-256 和原始响应文件。采集文件先作为 Evidence Artifact，确认语义后再登记为 Dataset。

## 质量画像

当前支持 CSV、Excel、JSON 和 Parquet。画像由本地 Python 计算：

- 行列数、重复行、缺失单元格；
- 字段类型、缺失比例、唯一值、常量列；
- 数值字段的最小值、最大值、均值、中位数和标准差；
- 目标变量是否存在、是否全空、是否为常量。

质量门：

- `PASS`：自动完成 `data_quality`；
- `REVIEW`：进入人工复核，可接受局限后继续；
- `BLOCK`：节点失败并阻断 EDA/建模，必须修复数据后重跑。

画像 JSON 和中文报告都注册为 Artifact，并绑定原始数据 Artifact ID。大模型无权手工写入质量指标。

