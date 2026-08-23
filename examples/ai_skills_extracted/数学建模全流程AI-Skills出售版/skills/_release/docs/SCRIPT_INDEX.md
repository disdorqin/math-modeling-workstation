# Python 脚本索引

以下命令都从出售版根目录运行，也就是包含 `数学建模全流程AI-Skills包介绍.md` 和 `skills/` 的目录。

## 数据分析

```bash
python3 skills/mm-data-eda-cleaning/scripts/eda_report.py --input skills/_examples/sample_data_prediction.csv --output outputs/eda
```

## 综合评价

```bash
python3 skills/mm-evaluation-models/scripts/entropy_weight.py --input skills/_examples/sample_data_evaluation.csv --output outputs/entropy --columns x1,x2,x3 --directions positive,negative,positive
python3 skills/mm-evaluation-models/scripts/topsis.py --input skills/_examples/sample_data_evaluation.csv --output outputs/topsis --columns x1,x2,x3 --weights 0.3,0.4,0.3 --directions positive,negative,positive
python3 skills/mm-evaluation-models/scripts/ahp_consistency.py --output outputs/ahp
python3 skills/mm-evaluation-models/scripts/grey_relation.py --input skills/_examples/sample_data_prediction.csv --output outputs/grey --reference-column usage --columns temperature,rainfall
```

## 预测模型

```bash
python3 skills/mm-prediction-models/scripts/gm11.py --input skills/_examples/sample_data_prediction.csv --output outputs/gm11 --column usage --periods 3
python3 skills/mm-prediction-models/scripts/regression_baseline.py --input skills/_examples/sample_data_prediction.csv --output outputs/regression --target usage --features month,temperature,rainfall
python3 skills/mm-prediction-models/scripts/time_series_baseline.py --input skills/_examples/sample_data_prediction.csv --output outputs/time_series --value-column usage
```

## 优化模型

```bash
python3 skills/mm-optimization-models/scripts/linear_programming_template.py --output outputs/lp
python3 skills/mm-optimization-models/scripts/integer_programming_template.py --output outputs/ip
python3 skills/mm-optimization-models/scripts/multi_objective_template.py --input skills/_examples/sample_data_evaluation.csv --output outputs/multi_objective --columns x1,x2,x3 --weights 0.3,0.4,0.3 --directions positive,negative,positive
```

## 分类聚类

```bash
python3 skills/mm-classification-clustering/scripts/clustering_baseline.py --input skills/_examples/sample_data_evaluation.csv --output outputs/clustering --columns x1,x2,x3
python3 skills/mm-classification-clustering/scripts/classification_baseline.py --input skills/_examples/classification_sample.csv --output outputs/classification --target label --features x1,x2,x3 --model random_forest
```

## 仿真模拟

```bash
python3 skills/mm-simulation-models/scripts/monte_carlo_template.py --output outputs/monte_carlo --iterations 1000 --seed 42
python3 skills/mm-simulation-models/scripts/queue_simulation_template.py --output outputs/queue --customers 1000 --seed 42
```

