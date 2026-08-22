# 论文对标优秀论文打磨机制设计(2026-08-06)

> 导师: claude_code · 依据用户指示: 让产出论文朝着优秀论文对标, 通过跨年份泛化问题定位修正
> 现状: 工作站已有 M-stage 打磨(refinement.py, FOCUS_CURRICULUM 恰好5个stage), 但仅靠内部自检, 无外部优秀论文对照

---

## 一、现有打磨机制(已理解)

### M-stage 循环(refinement.py)
- `RefinementConfig(max_stages=10, min_stages=2)`
- 每 stage 一个 focus, 循环旋转:
  ```
  FOCUS_CURRICULUM = [
    "coherence",           # stage1: 完整性/子问题闭环
    "humanize",            # stage2: 自然语言
    "figures_and_tables",  # stage3: 图表嵌入+说明
    "notation_and_latex",  # stage4: 符号/公式/LaTeX
    "final_polish",        # stage5: 严谨性/去AI痕迹
  ]
  ```
  → 恰好 = 用户说的"M=5打磨"(草稿→充实→图表→语言→排版风格), 且 max_stages=10 循环2轮

### 当前打磨的输入(缺口所在)
`_propose_refinement` 用 LLM 生成建议, 输入为:
- `audit_scope / quality_vector / issues / controller / sections / failures`
- **全部是论文内部自检**(coherence/consistency findings)
- **没有外部优秀论文对照**

---

## 二、用户核心要求(对标优秀论文)

1. 每篇论文经历 M stage 打磨, 逐步朝优秀论文靠近
2. **对照优秀论文**: 把我们的论文 vs 高教社C题优秀论文对照, 找出问题
3. **找泛化问题**: 跨不同年份反复出现的问题(非某一年特有)→ 才值得修
4. **保持亮点**: 各自亮点不同不强行改, 只朝优秀论文方向推进
5. M=5 合适(与现有 curriculum 吻合), 可商量

---

## 三、设计方案: 优秀论文对照层(新增)

### 核心: 给打磨循环注入"外部优秀论文对照"信号

```
┌────────────────────────────────────────────────────┐
│  现有打磨循环(refinement.py, M=5)                 │
│  stage_i:  focus_i + 内部自检findings             │
│    ↓ (新增注入)                                    │
│  ExcellentPaperComparator:                         │
│    1. 检索优秀论文对照库(高教社C题精选)           │
│    2. 按 stage focus 抽取优秀论文对应维度         │
│    3. 对照找"泛化问题"(跨年份, 不是某年特有)     │
│    4. 产出: 泛化问题清单(generalized_issues)      │
│    → 注入 _propose_refinement 输入               │
└────────────────────────────────────────────────────┘
```

### 关键组件

**1. 优秀论文对照库(数据)**
- 复用 config/knowledge/cards/(32张卡片已含论文佐证)
- 新增 config/ref_models/excellent_c7/ 精选高教社C题优秀论文的提炼稿(每篇: 结构/语言/图表/建模套路/评分点)

**2. ExcellentPaperComparator(对照器)**
- 输入: 当前论文全文 + 当前stage focus + 优秀论文提炼稿
- 输出: `generalized_issues[]`(泛化问题, 带"哪几年论文出现"佐证)
- 判定逻辑:
  - 某问题在≥2个不同年份优秀论文中反复出现, 而我们的论文没有 → **泛化问题, 值得修**
  - 某问题只在我们论文或某一年出现, 优秀论文各有做法 → **不强制改**(保持亮点)

**3. 注入点**
- 修改 `_propose_refinement`: 输入增加 `excellent_ref_json`(优秀论文对照结果)
- 每 stage 的 prompt 增加: "参照优秀论文, 本 stage focus 维度的泛化问题: ..."

### 4. 泛化问题判定(核心逻辑)
```
generalized(issue, ref_papers) =
    count(p in ref_papers where p表现更好) ≥ 2 个不同年份
    AND 我们论文确实缺失该点
```
→ 只有满足才进入打磨建议, 否则记录为"亮点差异, 不改"

---

## 四、落地步骤(派给徒弟)

### 步骤1: 构建优秀论文提炼稿库(数据准备)
- 从高教社C题优秀论文精选 ~10篇(不同年份/不同C题类型)
- 每篇提炼: 结构大纲/摘要写法/建模套路/图表风格/语言特点/评分亮点
- 存 `config/ref_models/excellent_c7/<year>-<topic>.md`

### 步骤2: ExcellentPaperComparator(核心逻辑)
- 实现"对照 + 泛化问题判定"函数
- 输入论文全文 + 优秀论文提炼稿, 输出 generalized_issues

### 步骤3: 注入打磨循环
- `_propose_refinement` 增加 excellent_ref 输入
- prompt 增加泛化问题参照

### 步骤4: 验证
- 用 2023/2024 C题论文跑一轮, 看泛化问题是否被正确识别/修正

---

## 五、验收标准
- 对照库 ≥10篇优秀论文提炼稿
- 泛化问题判定逻辑正确(≥2年份才算泛化)
- 打磨循环注入生效, 论文朝优秀论文方向改进
- 保持亮点不强行改

---

*设计稿, 待与用户确认 M=5 / 泛化阈值后派单*
