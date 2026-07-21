# EDA、图表与实验规范

## EDA

EDA 只能读取状态为 `PROFILED` 或 `VERIFIED` 的 Dataset。输出包括确定性统计 JSON、中文报告以及注册图表。宽表绘图设上限：分布图最多 12 个数值字段，相关图最多 20 个字段，防止无限画布和运行阻塞。

## 图表证据

每张图登记：Figure ID、Artifact ID、标题、源 Artifact、生成函数、参数、Run ID 和状态。EDA/Baseline 初始图片均为 `DRAFT`，不能直接进入最终论文。后续图表审查通过后才能转为 `FINAL`。

## 实验隔离

每个实验位于 `experiments/{experiment_id}/`：

- `experiment.json`：实验状态和主要产物；
- `input_manifest.json`：Dataset、源 Artifact、SHA-256；
- `config.json`：任务、字段、拆分和随机种子；
- `code_snapshot/`：执行代码快照；
- `results/metrics.json`：程序计算的指标；
- `results/predictions.csv`：逐行实际值和预测值；
- `model/best_model.joblib`：序列化模型；
- `stdout.log`、`stderr.log`：执行记录。

指标、预测和模型 Artifact 的上游必须同时包含原始数据、实验配置和代码快照。实验成功不等于可以写入论文，初始 `paper_eligible=false`。

## Baseline

回归候选：Dummy Mean、Linear Regression、Ridge、Random Forest。分类候选：Dummy Prior、Logistic Regression、Random Forest。统一处理数值/类别缺失、标准化和 OneHot。

回归使用 MAE、RMSE、R²；分类使用 Accuracy、Macro-F1。固定随机种子、记录测试集比例。Baseline 仅建立可复现下限，不是最终模型结论。

