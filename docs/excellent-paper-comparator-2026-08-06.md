# 优秀论文对照库 + ExcellentPaperComparator 交付说明(2026-08-06)

> 任务: t9f8d0ae0 · 优秀论文对照库 + 泛化问题定位(执行者: opencode)
> 接口(导师指定): `ExcellentPaperComparator.compare(paper_text, stage_focus) -> list[GeneralizedIssue]`

## 一、交付内容

### 1. 优秀论文对照库 `config/ref_models/excellent_c7/`
- **11 篇**高教社 C 题优秀论文提炼稿(2010/2011/2015/2016/2017/2018/2020/2022/2023/2024/2025),跨 11 个不同年份,每篇含: 结构大纲/摘要写法/建模套路/图表风格/语言特点/评分亮点
- 每篇提炼稿**基于真实论文内容**(OCR 高教社 C 题优秀论文 PDF 后提炼),关键数字均来自原文(如 2016 电池 R²>99%、MRE 0.0035~0.0178、预测误差<0.0007;2015 天文学验证误差最大16分钟最小0分钟;2023 蔬菜最大收益5105.60元;2024 农作物7年收益4530万/6469万等)
- `index.json`: 论文索引(year/file/topic/type/models) + 4 类题型覆盖(回归预测/机理/评价决策/优化决策)
- frontmatter `strong_points`: 共享**规范维度词表**(5 个 focus 维度 × 若干规范短句),每个强点 `"focus|规范短句|关键词1,关键词2"`,供确定性泛化判定

### 2. `src/mathworkstation/excellent_paper_comparator.py`
核心逻辑(全部确定性, 不依赖 LLM):
```
generalized(强点, 当前论文) =
    强点出现在 ≥2 个不同年份优秀论文   (泛化阈值 GENERALIZATION_THRESHOLD=2)
    AND 当前论文缺失该强点             (关键词任一命中即视为具备)
```
- 某强点只出现在 1 个年份(或我们已具备)→ **亮点差异, 不强制改**
- 无关键词的强点(纯特色亮点)→ 天然"保持亮点", 不参与判定
- 对照库缺失/空库 → 返回空列表, **不崩溃**, 打磨循环照常以内部自检推进

### 3. 测试 `tests/test_excellent_paper_comparator.py`(14 项全过)
- 真实对照库: 每 focus 维度对无内容论文产出泛化问题、库规模 ≥10 篇/跨 ≥10 年份/4 类覆盖
- 泛化阈值: 单年份亮点不强改、跨 2 年份触发、已具备不误报
- 健壮性: 空库不崩溃、report()/stats() 接口、非法 focus 回退、无 frontmatter 跳过

## 二、与打磨循环的对接(供注入使用)

`_propose_refinement` 可调用:
```python
from mathworkstation.excellent_paper_comparator import ExcellentPaperComparator
comparator = ExcellentPaperComparator()
report = comparator.report(paper_text, stage_focus)
# report["generalized_issues"] → 注入 prompt: "参照优秀论文, 本 stage focus 维度的泛化问题: ..."
```

## 三、验收核对
| 验收项 | 状态 |
| --- | --- |
| 对照库 ≥10 篇优秀论文提炼稿 | ✅ 11 篇 |
| 泛化问题判定正确(≥2 年份才算泛化) | ✅ 确定性判定 + 单年不强改 |
| 提炼稿基于真实论文(非凭空编造) | ✅ 数字与 OCR 原文一致 |
| 不崩溃/不破坏现有 pipeline | ✅ 全量 pytest 无回归 |
| 保持亮点不强行改 | ✅ 单年份强点不强改 |

## 四、备注
- cline 的 t94f1bd29(泛化问题注入打磨循环)与本文档独立: 本文档提供 `excellent_paper_comparator.py` 及其 `compare/report` 接口, cline 负责在 `refinement._propose_refinement`(auto_pipeline.py:1146)接入
- 提炼稿素材来源: 卡片任务(t99126b84)OCR 的 14 篇 C 题论文文本 + 高教社优秀论文目录
