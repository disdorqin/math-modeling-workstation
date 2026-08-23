# Elastic Net (elastic_net)

> 卡片来源: 姜启源《数学模型》方法论 + 高教社C题优秀论文真实佐证 · 家族: 回归族 · 关联 task_type: regression

## 适用场景

特征强相关且希望稀疏、Lasso 解不稳定。关键词: L1+L2/弹性网络/正则组合。

## 核心公式

$$\min_w \|y-Xw\|^2 + \alpha l_1\|w\|_1 + \alpha(1-l_1)\|w\|^2$$

## 建模步骤

1. 标准化特征
2. 用 ElasticNetCV 联合调 $\alpha, l_1\_ratio$
3. 拟合, 检查稀疏性与系数稳定性
4. 与 Lasso/Ridge 对比选优
5. 解读保留特征

## C题适用性

C题强相关指标众多、需在稀疏选择与稳定性间平衡时(信贷指标/经营指标筛选)。

## 论文佐证

未在高教社C题获奖论文中作为独立模型出现; 该卡为 catalog 32 方法补齐项, 可作为 Lasso/Ridge 的稳健性对比方案。

## 易错点

l1_ratio 调过头退化为纯Lasso/Ridge; 未标准化; 与lasso对比意义不明。
