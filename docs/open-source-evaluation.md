# 开源项目评估与融合决策

评估日期：2026-07-21。GitHub 活跃度、Star、License 和仓库状态来自当日 GitHub API；工程适配评分由本项目按控制性、可恢复性、证据链、数据执行、写作能力和融合成本评定。

## 评估结论

| 项目 | 定位 | License | 适配分 | 决策 |
|---|---|---:|---:|---|
| LangGraph | 状态图、Checkpoint、人工介入 | MIT | 91 | 首选可选编排适配器；不替代自研状态与证据内核 |
| PydanticAI | 结构化 Agent、工具约束 | MIT | 85 | 后续 LLM Adapter 首选；按需安装 |
| PaperQA | 科学文档问答与引用 | Apache-2.0 | 84 | 借鉴/适配文献证据层 |
| open_deep_research | 深度研究工作流 | MIT | 82 | 借鉴检索、研究计划和引用工作流 |
| Data Formulator | 交互式数据探索与可视化 | MIT | 80 | 借鉴前端数据探索与图表交互 |
| GPT Researcher | 自动研究报告 | Apache-2.0 | 77 | 借鉴多源研究与报告结构，不作为核心 |
| PocketFlow | 轻量流程框架 | MIT | 72 | 设计简洁，但与现有自研 DAG 重叠，暂不接入 |
| AutoGen | 多 Agent 编排 | CC-BY-4.0 | 64 | 自治性和复杂度偏高，且许可证需单独评估 |
| CrewAI | 多 Agent 协作 | MIT | 62 | 角色协作可参考，不使用其自由循环作为主线 |
| PandasAI | 对话式数据分析 | 未明确 | 57 | 许可与结果控制不满足核心要求，仅参考交互方式 |
| AI-Scientist | 开放式自动科研 | 未明确 | 49 | 开放循环与比赛工作站目标不一致，不接入核心 |

## 选择原则

1. **唯一内核**：当前自研 `Case + Artifact + Dataset + Workflow + Recovery` 是唯一事实源。
2. **LangGraph 作为适配器**：只承接节点编排、暂停恢复或模型工具调用，不拥有案例文件和论文证据的最终状态。
3. **PydanticAI 作为 LLM 边界候选**：负责 Schema、工具白名单和模型供应商切换，不负责直接写正式指标。
4. **PaperQA/open_deep_research 作为研究子系统候选**：所有引用先写 Evidence Plane，再允许进入论文。
5. **Data Formulator 只借 UI/交互**：图表仍由本地 Python 代码和已登记 Dataset 生成。

## 当日仓库元数据

| 仓库 | Stars | License | Archived |
|---|---:|---|---|
| langchain-ai/langgraph | 37,714 | MIT | false |
| pydantic/pydantic-ai | 18,682 | MIT | false |
| microsoft/autogen | 59,856 | CC-BY-4.0 | false |
| crewAIInc/crewAI | 55,868 | MIT | false |
| assafelovic/gpt-researcher | 28,504 | Apache-2.0 | false |
| The-Pocket/PocketFlow | 11,002 | MIT | false |
| Future-House/paper-qa | 8,899 | Apache-2.0 | false |
| SakanaAI/AI-Scientist | 14,259 | 未明确 | false |
| Sinaptik-AI/pandas-ai | 23,664 | 未明确 | false |
| microsoft/data-formulator | 15,969 | MIT | false |
| langchain-ai/open_deep_research | 12,059 | MIT | false |

Star 只用于观察社区规模，不作为技术选型决定因素。

