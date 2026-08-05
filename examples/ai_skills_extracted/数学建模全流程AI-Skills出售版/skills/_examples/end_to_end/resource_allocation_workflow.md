# 端到端示例：资源分配建模工作流

## 1. 题目

某工厂生产 A、B 两类产品。每件产品消耗不同工时和原料，利润不同。工时和原料有限，要求确定生产数量，使总利润最大，并分析资源变化对方案的影响。

## 2. 拆题结果

| 问题 | 输入 | 输出 | 可能方法 | 难点 |
|---|---|---|---|---|
| 利润最大化 | 单位利润、工时、原料、资源上限 | A/B 生产数量和最大利润 | 线性规划 | 变量是否必须整数 |
| 资源变化分析 | 工时和原料上限扰动 | 最优方案变化 | 灵敏度分析 | 约束影子价格解释 |

## 3. 变量与约束

| 符号 | 含义 | 类型 | 单位 |
|---|---|---|---|
| x_A | 产品 A 生产数量 | 决策变量 | 件 |
| x_B | 产品 B 生产数量 | 决策变量 | 件 |

目标函数示例：

```text
maximize profit = p_A * x_A + p_B * x_B
```

约束示例：

```text
t_A * x_A + t_B * x_B <= total_time
m_A * x_A + m_B * x_B <= total_material
x_A, x_B >= 0
```

如果生产数量必须为整数，应使用整数规划或在连续解基础上做可行性核验。

## 4. 推荐 Skill 调用

1. `$math-modeling-orchestrator` 判断任务路线。
2. `$mm-problem-decomposer` 拆解题目和分问题。
3. `$mm-variable-assumption-builder` 生成变量、假设和约束。
4. `$mm-optimization-models` 建立线性规划或整数规划。
5. `$mm-paper-reviewer` 检查报告是否回答问题、是否存在无支撑结论。

## 5. 可运行脚本

```bash
python3 skills/mm-optimization-models/scripts/linear_programming_template.py --output outputs/lp_demo
```

## 6. 不可直接编造的内容

- 不能编造单位利润、资源上限或产能数据。
- 不能把连续解直接当成整数生产方案。
- 不能声称“最优方案一定适用于实际生产”，必须核验工艺、订单和库存约束。
