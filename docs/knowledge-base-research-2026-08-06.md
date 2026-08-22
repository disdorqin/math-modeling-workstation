# 知识库路线调研报告(2026-08-06)

> 调研人: claude_code(导师) · 目的: 为工作站"数学建模知识库"选型(轻量卡片 vs 本地RAG)提供依据
> 范围: GitHub 高星数学建模智能体 / 端到端论文生成系统 / RAG 知识库方案

---

## 一、调研对象与星数

| 仓库 | 星数 | 定位 | 知识库做法 |
|---|---|---|---|
| [jihe520/MathModelAgent](https://github.com/jihe520/MathModelAgent) | **3203** | 数学建模 Agent, 建模手/代码手/论文手多智能体 | **RAG 规划中未完成**(ChromaDB+Rerank 标注 `[ ]`), 主要靠 prompt+skills |
| [usail-hkust/LLM-MM-Agent](https://github.com/usail-hkust/LLM-MM-Agent) | 594 (NeurIPS'25) | 数学建模全流程 Agent, MCM 2025 Finalist | **HMML 三级方法库**(5域→子域→97节点, 纯 JSON 树) — 已被工作站融合 |
| [123-qw-as/Beacon](https://github.com/123-qw-as/Beacon) | — | 端到端多agent(LangGraph 14阶段)生成完整论文 | **可选 RAG**(SQLite+embedding), 源类型区分 model_lib / paper |
| [XiaoMaColtAI/math-modeling-skill](https://github.com/XiaoMaColtAI/math-modeling-skill) | 404-580 | Claude Code/Codex 三阶段技能包 | **角色+常见模式+质检清单**(无RAG, 纯结构化 Skill) |
| [yushui2022/MathModel-Skill](https://github.com/yushui2022/MathModel-Skill) | 185 | 三端 Agent-native 技能包, 证据门/格式门 | JSON 契约文件交接, 防漂移 |

**另参考**: [Awesome-LLMs-for-Mathematical-Modeling](https://github.com/DataArcTech/Awesome-LLMs-for-Mathematical-Modeling)(精选列表)

---

## 二、三条知识库技术路线对比

### 路线A: 纯结构化方法库(LLM-MM-Agent HMML 为代表)
- **做法**: 手写 JSON 树, 每方法含 `method/description/core_idea/application`
- **检索**: 无需向量库, 直接按层级打分/关键词匹配(MethodScorer 层级打分)
- **优点**: 确定性、可复现、零成本、易维护; 契合工作站"No Evidence No Claim"
- **缺点**: 检索是精确匹配, 非语义; 需人工维护
- **现状**: **工作站已融合**(config/hmml.json + hmml.py)

### 路线B: 本地 RAG(Beacon 为代表)
- **做法**: corpus 目录(模型md + 获奖论文) → 分块 → 向量化(text-embedding-3-small) → SQLite 存向量 → 节点按需检索
- **源类型区分**: `papers/论文` → paper(写作风格); 其余 → model_lib(建模方法)
- **注入点**: analyst / modeler(检索方法) + writer(检索论文风格, source_type="paper"), 各自 max_chars 上限
- **优点**: 语义检索, 能召回论文精华; 注入写作风格
- **缺点**: 依赖嵌入API(付费/不确定)、检索质量不稳定、违背确定性哲学、376篇PDF需先解析
- **现状**: MathModelAgent 也计划用但**未完成**

### 路线C: 人工提炼精华卡片(Beacon corpus/models 为代表)
- **做法**: 手写 md, 每模型含 `适用场景/判别特征/核心公式/建模步骤`, 另有 `比赛心得.md`
- **优点**: 质量最高、可教(为什么用)、符合"大道至简"
- **缺点**: 需人工/agent 提炼

**关键洞察**: Beacon 是路线B+C结合——corpus 里有**人工提炼的精华 md**(优化模型/回归与预测/微分方程/排队论/比赛心得/如何写论文)**加上**姜启源29章原PDF, 两者一起进 RAG。它的 `corpus/models/*.md` 正是我们要的"知识库结构化提纯"模板。

---

## 三、Beacon 的 RAG 细节(最值得借鉴)

1. **corpus 组成**: `corpus/models/` = 姜启源29章同款 + 人工提炼 md(优化模型/评价模型/回归与预测/微分方程/排队论/十类算法/比赛心得/如何写论文)
2. **检索入口**: `src/math_agent/rag/retrieve.py` 统一 `search()`, 节点只 import 这一个函数
3. **源类型**: `papers/论文` → paper, 其余 → model_lib
4. **注入**: analyst(k方法) + modeler(k方法) + writer(source_type="paper")
5. **容错**: 检索失败 → 返回空, 不阻塞流水线
6. **embedding**: text-embedding-3-small(1536维), SQLite 存向量

---

## 四、对工作站的建议(待与导师讨论确认)

基于调研, 推荐**"路线A(已有) + 路线C(人工提炼) + 可选路线B(RAG)"分层**:

1. **基础层(路线A, 已融合)**: HMML 三级方法库 + model-catalog 32方法 → 已够"模型选择"
2. **精华层(路线C, 新增)**: 仿 Beacon, 把姜启源29章 + 高教社376篇C题优秀论文提炼成**中文精华卡片**(适用场景/判别特征/核心公式/建模步骤/论文佐证/易错点), 存 `config/knowledge/` — 确定性, 可注入 model_plan
3. **增强层(路线B, 可选)**: 若嫌卡片不够, 再把 PDF 库做 RAG(Beacon 同款), 但**默认关闭**(RAG_ENABLED=0), 需时开

**核心原则**: 先做确定性卡片(契合"大道至简"+"可追溯"), RAG 作为可选增强, 不被它主导。

---

## 五、后续动作

- [ ] 与导师确认路线(轻量卡片 vs RAG 增强)
- [ ] 确认 C 题范围(美赛/国赛为主, 格式一致比赛覆盖)
- [ ] 拆任务派给三个徒弟
