# 论文学习循环设计(Paper Learning Loop, Hermes/KEPA 启发)

**灵感:** Hermes Agent 的 KEPA(Knowledge-Enhanced Prompt Adaptation)——"提示词的梯度下降"。不更新模型权重,而是更新**如何用模型**:提示词模板、工具调用序列、skill 定义。核心:每次完成任务 → 后台 review → 提炼 skill → 下次渐进加载。

**性质:** 设计定稿 v1.0 — 用户已确认 4 项决策(2026-08-05)。
**目标:** 让工作站"每完成一篇论文就学习",越用越强。

---

## 0. 已确认的设计决策(用户拍板)

| # | 决策 | 选择 |
|---|---|---|
| 1 | lessons 存储 | **JSON + 导出人读**(machine-readable for progressive loading, markdown export for humans) |
| 2 | 反思把关 | **测试阶段由 claude_code 把关;正式写入阶段由用户确认** |
| 3 | 触发时机 | **final_review 通过后触发反思** |
| 4 | 跨竞赛隔离 | **C 题优先**(C 题 lessons 优先加载,其他题共存不干扰) |

---

## 1. 核心循环(论文级学习)

```
[论文完成] → [后台反思] → [提炼泛化教训] → [存 lessons] → [下一篇加载应用]
```

对比 Hermes:我们的"任务"= 完成一篇论文,"skill"= 论文写作 lessons。

### 1.1 后台反思(每篇论文后触发)
一个轻量 review 步骤(不打断用户),从三视角提炼:
- **本论文做得好** → 值得固化的写法/流程
- **本论文做得差/卡住** → 待改进
- **O 奖论文对比** → O 奖怎么做、我们缺什么

### 1.2 泛化教训(核心:不针对单一题目)
写"**怎么做**"的教训,可跨年份/跨 C 题适用。例如:
- ❌ 特例:"2024 网球题要处理 elapsed_time"
- ✅ 泛化:"C 题时间序列数据默认用时间顺序切分防泄漏"

### 1.3 存储:分层 lessons(`memory/paper_lessons.md`)
Hermes 用 SKILL.md 分层。我们用:
- **Always 层**(每篇都加载):泛化的 C 题最佳实践(时间切分、图表晋升、统计检验)
- **Pitfalls 层**(踩坑记录):"上次卡在 X,下次先做 Y"
- **Recent 层**(最近教训):最新学到、可能还有用

### 1.4 渐进加载
下一篇论文开始时,只加载相关 lessons(不是全部):
- 按竞赛类型(mcm-c)筛选
- 按 Pitfalls 优先级(先避坑)
- 注入到 model_plan / paper_section 的提示词上下文

---

## 2. 与现有机制的关系

| 现有机制 | 本设计 |
|---|---|
| `memory/frozen_facts.json` | 证据级冻结(不冲突) |
| `refinement/hidden_state.json` | **单篇内**跨 Stage 记忆(论文级) |
| `D:\AI_Memory\memory-general.jsonl` | 舰队级共享记忆(跨 agent) |
| **本设计 `paper_lessons.md`** | **跨论文**写作经验(新增,跨篇学习) |

三者是**不同粒度**:证据冻结(篇内事实) < 隐藏状态(篇内打磨) < **论文 lessons(跨篇成长)**。

---

## 3. Hermes 机制映射表

| Hermes 机制 | 我们的实现 |
|---|---|
| KEPA(改提示词) | lessons 注入 model_plan/paper_section 提示词 |
| 后台 review agent | 论文后置 review 步骤(提炼 lessons) |
| SKILL.md 分层 | paper_lessons.md(Always/Pitfalls/Recent) |
| 渐进加载 | 按竞赛+优先级筛选 lessons 注入 |
| Pitfalls 增长 | 每篇踩坑 → 追加 lessons |
| periodic nudge | 可选:每 N 篇强制 review |
| security gates | 不需要(纯文本,无代码执行) |

---

## 4. 实施步骤

1. **lessons 存储**:`memory/paper_lessons.md`(或 `paper_lessons.json` 结构化)
2. **反思提炼**:论文完成后,对比 O 奖,提炼泛化教训(LLM 辅助 + 人工确认)
3. **渐进加载**:新论文开始时,筛选相关 lessons 注入提示词上下文
4. **Pitfalls 闭环**:卡住点 → 记 Pitfalls → 下次先避

## 5. 待确认

1. lessons 用 markdown(人可读)还是 JSON(机器可载)?我倾向 JSON + 人读导出。
2. 反思是纯 LLM 自动,还是我(Claude)每篇人工把关 lessons?
3. 何时算"一篇完成"触发反思?(paper_ready 后?final_review 后?导出后?)
4. 跨竞赛(C 题 vs 其他)是否隔离 lessons?(我倾向 C 题优先,其他共存)

---

*设计者: claude_code, 启发自 Hermes Agent KEPA(self-improving loop)。参考: NousResearch/Hermes-Agent, alibabacloud 源码深挖。*
