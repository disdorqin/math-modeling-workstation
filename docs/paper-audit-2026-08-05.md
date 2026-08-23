# 论文审核反馈(导师 claude_code,对标 O 奖)

**日期:** 2026-08-05
**审核对象:** 2023 Wordle(opencode)、2018 能源(freebuff)
**原则:** 我们是有理想有要求的,对标 O 奖,标准要严。用户最终审查,现在由导师交付。

---

## 一、做得好的(保留)

两篇论文共同优点:
- ✅ 12 节结构完整(摘要/问题重述/假设/符号/数据/建模/求解/结果/敏感性/优劣/结论/参考文献)
- ✅ 摘要完整:问题/方法/结果/稳健性/关键词齐全
- ✅ 多候选模型比较(6 个)+ 5 折交叉验证 + 敏感性分析
- ✅ 问题重述有深度(讨论建模思路,非复述题目)
- ✅ 自动审批 + 证据门保留(所有数字有 claim 支撑)

## 二、泛化缺陷(必须修,对标 O 奖)

### P1 时间序列切分未生效(最关键,C 题硬伤)
- **问题**:Wordle 是每日时间序列,opencode 用了随机切分(`随机划分策略`),**数据泄漏风险**。O 奖必然用时间顺序切分。
- **影响**:预测未来日期会"看到未来",结果不可信。
- **要求**:`model_plan` 必须识别时间字段 → `time_ordered` 切分 → 模型比较用 `TimeSeriesSplit`。

### P2 学习循环触发不稳定
- **问题**:opencode 2023 未触发(无 lessons),freebuff 2018 触发了(2 lessons)。不稳定。
- **要求**:确保 final_review 后必触发反思,lessons 必沉淀;每篇都有 lessons 可循。

### P3 refinement 稳定性
- **问题**:opencode 2023 refinement 卡住(iteration=0, RUNNING,被 freebuff 误 kill 是诱因,但要确认非 kill 也稳定)。
- **要求**:refinement 必须稳定跑完(多 stage),进入 final_review/export。

### P4 摘要过"模板化"
- **问题**:两篇摘要都出现"研究目的/研究方法/主要结果/稳健性与边界"四段模板(如 `### 摘要核心`),是 `_ensure_abstract_quality` 注入的固定结构,读起来像填充模板而非 O 奖的凝练。
- **要求**:摘要应更像人写的 O 奖风格——自然段落、突出创新点、不机械四段。

### P5 MCM profile 硬编码英文(工具缺陷,freebuff 发现)
- **问题**:`submission` 的 MCM profile 硬编码英文章节名(Abstract/Model/Results/Conclusion),中文论文必误报 REQUIRED_SECTION_MISSING。
- **要求**:`required_sections` 改语言感知(中文论文匹配中文节名)。

### P6 图表说明不足(对标 O 奖)
- **问题**:论文嵌了图(7-8 张),但需要检查每张图是否有充分的分析解读(不是只嵌图)。
- **要求**:每张关键图在正文有对应分析段落。

---

## 三、分工派发

| 缺陷 | 负责人 | 验收标准 |
|---|---|---|
| P1 时间切分 | opencode | Wordle 用 time_ordered,TimeSeriesSplit 验证 |
| P2 学习循环 | opencode | final_review 后必触发,每篇有 lessons |
| P3 refinement | opencode | 稳定跑完多 stage,进 final_review/export |
| P4 摘要 | freebuff | 摘要更自然,非模板四段 |
| P5 MCM profile | freebuff | 中文论文用 CUMCM profile 不误报 |
| P6 图表说明 | 待定 | 每图有分析段落 |

*导师严格审核,标准对标 O 奖。用户最终审查。*
