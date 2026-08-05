# 购买者使用指南

## 产品定位

这套包是数学建模 AI Skills 工作流，不是代写论文、代赛、保奖或伪造结果工具。它适合把现实问题拆成变量、数据、模型、代码模板、验证清单和报告结构。

## 极简结构

购买者打开后只需要关注：

```text
数学建模全流程AI-Skills出售版/
├── 数学建模全流程AI-Skills包介绍.md
└── skills/
```

`skills/` 里包含 13 个真实 Skill。以下划线开头的目录是共享资料、样例和发布辅助材料。

## 使用方式

### 调用 Skill

```text
请使用 $math-modeling-orchestrator 判断这个建模任务应该怎么推进：……
```

```text
请使用 $mm-problem-decomposer 分析下面的题目：……
```

```text
请使用 $mm-model-selector 根据题目拆解和数据条件推荐模型：……
```

### 运行脚本

先在出售版根目录安装依赖：

```bash
python3 -m pip install -r skills/_release/requirements.txt
```

然后参考：

```text
skills/_release/docs/SCRIPT_INDEX.md
```

## 验证包是否完整

在出售版根目录运行：

```bash
python3 skills/_release/scripts/validate_public_package.py
```

通过后会输出：

```text
Public package validation passed.
```

## 使用边界

- 可以用于学习、训练、科研建模辅助、业务分析、工程决策支持、代码模板和报告审查。
- 不应输出可直接提交的完整论文。
- 不应伪造数据、图表、实验结果或参考文献。
- 用户必须自行核验数据、模型、结果和最终结论。

