# 图表改进计划 (Figure Improvement Plan)

**版本:** v1.0 · **日期:** 2026-08-05  
**起草:** freebuff (执行) · **导师验收:** Claude Code  
**融合协议版本:** docs/open-source-integration-protocol.md v1.0  
**方向:** 图表说明/分析段落 · 图表编号映射一致性 · figure_id 追踪

---

## 一、问题陈述

当前工作站在各年论文(2018/2023/2024 MCM)中的图表处理存在以下不足:

| 问题 | 影响 | 目标 |
|------|------|------|
| 图表仅嵌入,缺少分析段落 | 无法达到 O 奖标准(O 奖论文每张图都有充分文字解读) | 每张图配≥80字的分析段落 |
| 编号一致性仅靠事后检查 | 正文引用与图题编号不同步风险 | 编号映射写入 context 并纳入一致性门 |
| figure_id 只在 check 时验证 | writing 阶段可能引用不存在的图 | 写入 draft 前验证 figure_id |
| 分析段落缺乏量化标准 | 评审无法判断"充分性" | 定义每节的图表分析段落模板和最小要求 |

## 二、对标 O 奖标准

O 奖(MCM/ICM Outstanding Winner)论文中,每张图表不仅有图题,还有:

1. **引导句**("As shown in Figure N,...")
2. **观察描述**(图中呈现了什么)
3. **数据解读**(数值含义/趋势/异常)
4. **结论导向**(支持了论文的什么论点)

```
【O奖标准示例】
图1: Total Energy Use by Sector
正文段落: "Figure 1 illustrates the total energy consumption across four
sectors from 1960 to 2009. The industrial sector consistently dominates,
accounting for approximately 33% of total consumption. A notable inflection
point occurs around 2000, where transportation begins a steady decline while
commercial use rises — suggesting a structural shift toward service-oriented
energy demand. This observation supports our assumption that the commercial
sector will continue to expand relative to industrial use."
```

## 三、融合设计(开源项目对照)

### 3.1 已融合的开源项目

| 开源项目 | License | 融合内容 | 对应模块 | 状态 |
|----------|---------|----------|----------|------|
| Sphinx numfig | BSD-2-Clause | 图表编号机制 | `src/mathworkstation/figure_numbering.py` | 已完成 |
| SciencePlots | MIT | 学术图表渲染约定 | `src/mathworkstation/figure_numbering.py` + `src/mathworkstation/plot_style.py` | 已完成 |

### 3.2 本次融合的开源项目(3 个)

经过遵照融合协议的检索→确认→复刻/融合流程:

| # | 开源项目 | 仓库 | License | 融合内容 | 对应文件 |
|---|----------|------|---------|----------|----------|
| 1 | **SciencePlots** | github.com/garrettj403/SciencePlots | MIT | 学术图表布局规范: label/legend/unit 完整性标准、caption 结构约定、附录对照图表分离 | `src/mathworkstation/figure_analysis.py` |
| 2 | **Data Formulator** | github.com/microsoft/data-formulator | MIT | 图表类型分类方法: 标题关键词→图表类型→描述模式映射,语义 chart spec 到 Vega-Lite 的路由 | `src/mathworkstation/figure_analysis.py` |
| 3 | **Chart-to-text benchmark** | github.com/vis-nlp/Chart-to-text | CC BY-NC-SA 4.0 | 设计模式(非代码): 图表标题质量评估维度、caption 充分性打分标准、O奖级别描述段落的结构化模板 | `src/mathworkstation/figure_analysis.py` |

**许可声明:**
- SciencePlots (MIT): 用于风格约定和布局标准的参考,不复制代码
- Data Formulator (MIT): 用于图表分类方法的模式参考,仅学习分类关键词映射逻辑
- Chart-to-text: 仅参考评估方法论(设计模式),不复制代码/数据集/模型

### 3.3 融合功能与开源项目一一对应关系

| 融合功能 | 来源项目 | 开源源功能 | 对应代码行 |
|----------|----------|------------|------------|
| 图表类型检测与描述模式 | Data Formulator | `classify_figure()` 中关键字→章节路由 | `figure_analysis.py` `_detect_chart_type()` |
| 学术图表标注完整性检查 | SciencePlots | mplstyle 中的 label/title/legend 约定 | `figure_analysis.py` `check_figure_annotations()` |
| 分析段落结构化模板 | Chart-to-text | 标题质量评估维度的模板映射 | `figure_analysis.py` `SECTION_FIGURE_REQUIREMENTS` |
| 图表引用完整性门 | Sphinx numfig | numref 跨引用一致性 | `figure_numbering.py` `check_figure_numbering()` |

## 四、实现模块: figure_analysis.py

### 4.1 新增文件

```
src/mathworkstation/figure_analysis.py   # 图表分析段落引擎
tests/test_figure_analysis.py            # 测试
```

### 4.2 核心功能

1. **`check_figure_analysis_paragraphs()`**: 检查每张图在论文中是否有充分的分析段落
   - 分析段落最小长度: ≥80 字(data_analysis/sensitivity) / ≥100 字(results)
   - 必须有引导句("图N" / "Figure N"引用)
   - 必须有数据解读(数值/趋势/比较)
   - 必须有结论导向(支持哪个论点)

2. **`generate_figure_analysis_template()`**: 生成结构化分析段落模板
   - 根据图表类型和数据来源自动生成引导框架
   - 标记需人工填充的 `[TODO]` 块
   - 确保模板覆盖 O 奖标准的 4 个要素

3. **`check_figure_annotations()`**: 检查图表标注完整性
   - 轴标签完整性(轴名+单位)
   - 图例完整性
   - 图表标题是否描述性强(非 "Figure" 占位)

4. **`report_figure_coverage()`**: 生成图表覆盖度报告
   - 哪些图有分析段落,哪些缺少
   - 分析段落字数统计
   - 覆盖度百分比

### 4.3 与现有模块集成

```
PaperCoherenceChecker
  └── _figures_cited()          # 已有: 检查图是否被引用
  +── figure_analysis.check()   # [新增] 检查分析段落质量

PaperConsistencyChecker
  └── check()                   # 已有: figure_id 一致性
  +── figure_analysis            # 联合: 分析段落也验证 figure_id

PaperSectionWorkspace
  └── initialize()              # 已有: 创建 context.json
  +── write analysis_report      # [新增] 标题分析报告写入 context
```

## 五、验收标准

| # | 标准 | 验证方法 |
|---|------|----------|
| 1 | 上网检索了 3 个开源项目(有来源 URL/License) | 检查 Figure 分析文档的来源章节 |
| 2 | 融合的功能与开源项目一一对应 | 检查对应表 3.3 |
| 3 | 测试通过(新模块 + 不破坏既有) | `pytest tests/test_figure_analysis.py -v` |
| 4 | 自动上报(task_submit) | 本任务 agent=freebuff, task_id=t8859f1f6 |

## 六、测试用例

| 测试 | 内容 |
|------|------|
| `test_check_analysis_paragraphs_all_sections` | 各节分析段落检查(正常/缺少/过短) |
| `test_check_figure_annotations_complete` | 标注完整性检查(全/缺轴标签/缺图例) |
| `test_generate_template_for_sections` | 为各节生成分析模板 |
| `test_report_figure_coverage` | 图表覆盖度报告 |
| `test_figure_id_tracking_in_analysis` | 分析段落中的 figure_id 追踪 |
| `test_o_award_standard_compliance` | O 奖标准四要素检查 |
| `test_integration_with_paper_coherence` | 与现有连贯性检查器的集成 |
| `test_integration_existing_tests_unbroken` | 不破坏既有测试 |

---

*本文件是 figure-improvement-plan-2026-08-05.md,按照 open-source-integration-protocol.md 的要求编写。*
