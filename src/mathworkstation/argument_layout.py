from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArgumentBlock:
    kind: str
    item: Any
    lead_zh: str
    lead_en: str
    phase: str
    tail_zh: str = ""
    tail_en: str = ""


def group_question_tables(tables: list[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for table in tables:
        metadata = dict(getattr(table, "metadata", {}) or {})
        subproblem_id = str(metadata.get("subproblem_id") or "")
        if not subproblem_id:
            continue
        grouped.setdefault(subproblem_id, []).append(table)
    return grouped


def plan_argument_blocks(
    node: Any,
    figures: list[dict[str, Any]],
    tables: list[Any],
) -> list[ArgumentBlock]:
    """Order evidence by argumentative role rather than creation order.

    The planner is deterministic and evidence-only. It never creates a chart,
    table, number, or claim; it only decides where already-registered artifacts
    best support the local reasoning chain. Each block may also carry a short
    post-artifact bridge so a figure/table is interpreted and then connected to
    the next argumentative step instead of being dropped into the paper alone.
    """

    blocks: list[ArgumentBlock] = []
    table_by_role: dict[str, list[Any]] = {}
    for table in tables:
        role = str((getattr(table, "metadata", {}) or {}).get("table_role") or "summary_metrics")
        table_by_role.setdefault(role, []).append(table)

    mechanism_kinds = {
        "retail_price_demand_relationship",
        "association_ranking",
        "effect_intervals",
        "market_basket_rule_lift",
        "member_group_profile_heatmap",
        "panel_profile_heatmap",
        "probabilistic_state_transition",
        "state_transition",
        "probabilistic_graphical_model",
    }

    # 1) Model/mechanism evidence belongs immediately after method + validation.
    for figure in figures:
        kind = str((figure.get("parameters") or {}).get("semantic_kind") or "")
        if kind not in mechanism_kinds:
            continue
        blocks.append(
            ArgumentBlock(
                "figure",
                figure,
                "为说明模型为何得到上述关系，先用图形展示主要结构；图中只呈现已经实际计算并检验的证据。",
                "To make the fitted relationship interpretable, the principal structure is shown before the exact numerical table.",
                "model_evidence",
                "这一步先回答“数据中是否确有可利用的结构”；只有这一层证据成立，后续预测或决策才有明确的数据依据。",
                "This block first establishes that a usable empirical structure exists before later prediction or decision steps rely on it.",
            )
        )
    for table in table_by_role.get("relationship_validation", []):
        blocks.append(
            ArgumentBlock(
                "table",
                table,
                "图形用于看结构，表格进一步给出可复核的系数与验证误差，两者承担不同作用。",
                "The figure shows structure; the table gives the exact fitted quantities and validation errors for verification.",
                "model_evidence",
                "精确系数与验证误差用于约束对图形趋势的解释，避免仅凭视觉形态作过度判断。",
                "Exact coefficients and validation errors constrain the visual interpretation and prevent conclusions based on appearance alone.",
            )
        )

    # 2) Decision/results: overview figure first, exact executable schedule second.
    primary_figures: list[dict[str, Any]] = []
    for figure in figures:
        parameters = figure.get("parameters") or {}
        kind = str(parameters.get("semantic_kind") or "")
        role = str(parameters.get("paper_role") or "primary")
        if role == "primary" and kind not in mechanism_kinds:
            primary_figures.append(figure)
    for figure in primary_figures:
        parameters = figure.get("parameters") or {}
        kind = str(parameters.get("semantic_kind") or "")
        family = str(getattr(node, "task_family", "") or "")
        is_decision_figure = family == "optimization" or any(token in kind for token in ("decision", "replenishment", "allocation", "schedule", "optimum", "optimal"))
        if is_decision_figure:
            lead_zh = "在给出完整数值方案前，先用图形概括核心决策的整体形态，便于识别主要差异与趋势。"
            lead_en = "Before listing exact decision values, the primary figure summarizes the overall decision pattern."
            tail_zh = "图形用于把握方案结构；真正实施仍以下方逐项数值和约束审计为准。"
            tail_en = "The figure reveals the decision structure; implementation follows the exact values and constraint audit below."
        elif "probability_validation" in kind or "calibration" in kind or "roc" in kind:
            lead_zh = "核心概率关系建立后，用样本外图形检验其区分能力或校准性，而不以单一准确率替代模型检验。"
            lead_en = "After defining the probabilistic relation, this out-of-sample figure checks discrimination or calibration rather than treating one accuracy score as the model itself."
            tail_zh = "该图只解释当前样本外检验下的概率表现，不能升级为确定性预测或因果结论。"
            tail_en = "The plot is interpreted only under the stated out-of-sample validation design; it does not turn probabilistic warning ability into deterministic or causal claims."
        elif "trajectory" in kind or "flow" in kind:
            lead_zh = "先把随时间变化的状态轨迹画出，使后续统计检验或风险模型对应到可观察的动态过程。"
            lead_en = "The state trajectory is shown first so the later statistical test or risk model remains tied to an observable dynamic process."
            tail_zh = "轨迹用于描述状态如何变化，是否存在持续性或可预测反转仍由后续独立检验决定。"
            tail_en = "The trajectory describes how the state evolves; persistence or predictable reversal is decided by the independent validation evidence, not by visual impression."
        elif "interpret" in kind or "importance" in kind:
            lead_zh = "在主要概率模型通过检验后，再用解释图检查模型实际依赖哪些当前信息。"
            lead_en = "After the primary probabilistic model is validated, this interpretation figure shows which currently available signals the fitted rule relies on."
            tail_zh = "变量重要性只解释预测规则的使用方式，不把重要性排序写成因果效应。"
            tail_en = "Importance describes how the predictor uses information; the ranking is not interpreted as a causal effect."
        else:
            lead_zh = "在报告精确数值前，先用主图呈现本问最关键的结构或结果，使读者能够把数值放回模型语境。"
            lead_en = "Before reporting exact values, the primary figure shows the question's central structure or result so the numbers remain attached to the model argument."
            tail_zh = "正文只解释图中由实际计算支持的证据，并把图形结论连接回本问目标。"
            tail_en = "The prose interprets only evidence supported by the executed calculation and connects the figure back to the question objective."
        blocks.append(
            ArgumentBlock(
                "figure",
                figure,
                lead_zh,
                lead_en,
                "decision" if is_decision_figure else "result",
                tail_zh,
                tail_en,
            )
        )
    for table in table_by_role.get("decision_schedule", []):
        blocks.append(
            ArgumentBlock(
                "table",
                table,
                "图形回答“方案整体长什么样”，下面的表格回答“具体应该怎么执行”，因此保留完整决策值。",
                "The figure summarizes the decision pattern; the following table preserves the exact executable values.",
                "decision",
                "至此，整体趋势与逐项执行值已经对应起来；后续再检查关键参数或场景变化是否会动摇这一方案。",
                "The overview and executable values are now aligned; the next step is to test whether key perturbations or scenarios change the decision.",
            )
        )

    # 3) Compact summaries are useful only when richer tables are absent.  When a
    # relationship table or executable schedule already carries the numbers, a
    # second metrics table merely repeats evidence and makes the paper look like
    # a report dump rather than a modeling argument.
    has_richer_table = bool(table_by_role.get("relationship_validation") or table_by_role.get("decision_schedule"))
    if not has_richer_table:
        for table in table_by_role.get("summary_metrics", []):
            blocks.append(
                ArgumentBlock(
                    "table",
                    table,
                    "最后汇总本问最关键的定量指标，作为结论的数值索引，而不替代前面的完整证据。",
                    "A compact quantitative summary is provided as an index to the conclusion, not as a substitute for detailed evidence.",
                    "summary",
                    "这些指标用于快速回看本问答案，不替代前面的关系证据、完整方案或稳健性检验。",
                    "These metrics provide a compact index to the answer without replacing relationship evidence, detailed decisions, or robustness checks.",
                )
            )

    # 4) Robustness/scenario evidence must come after the main result/decision.
    for figure in figures:
        parameters = figure.get("parameters") or {}
        if str(parameters.get("paper_role") or "primary") != "supplementary_evidence":
            continue
        kind = str(parameters.get("semantic_kind") or "")
        if kind in mechanism_kinds:
            continue
        blocks.append(
            ArgumentBlock(
                "figure",
                figure,
                "核心结果确定后，再检查参数扰动或场景变化是否会改变结论；因此该图放在结果之后作为稳健性证据。",
                "After the main result is established, this figure tests whether perturbations or alternative scenarios materially change it.",
                "robustness",
                "该图承担的是“结论是否依赖某个特定参数或场景”的检验任务；稳健性判断以实际扰动检验结果为边界。",
                "This block tests whether the conclusion depends on a particular parameter or scenario; robustness claims remain bounded by the perturbations actually evaluated.",
            )
        )

    # Generic fallbacks: preserve every registered artifact exactly once.
    known_figure_ids = {
        str(block.item.get("figure_id") or "")
        for block in blocks
        if block.kind == "figure"
    }
    for figure in figures:
        figure_id = str(figure.get("figure_id") or "")
        if figure_id in known_figure_ids:
            continue
        blocks.append(
            ArgumentBlock(
                "figure",
                figure,
                "该图在本问首次需要对应证据的位置展示，用于辅助解释而非装饰。",
                "The figure is placed where its evidence is first needed, rather than appended decoratively.",
                "result",
                "正文只解释该图中由实际计算支持的证据，并将其连接回本问研究目标。",
                "The prose interprets only evidence supported by the executed calculation and connects it back to the question objective.",
            )
        )

    known_table_ids = {
        str(getattr(block.item, "table_id", ""))
        for block in blocks
        if block.kind == "table"
    }
    if has_richer_table:
        known_table_ids.update(
            str(getattr(table, "table_id", ""))
            for table in table_by_role.get("summary_metrics", [])
        )
    for table in tables:
        table_id = str(getattr(table, "table_id", ""))
        if table_id in known_table_ids:
            continue
        blocks.append(
            ArgumentBlock(
                "table",
                table,
                "该表用于给出图形或正文无法精确承载的数值信息。",
                "The table carries exact values that prose or graphics should not be forced to encode.",
                "result",
                "表中数值作为可复核证据使用，不单独脱离模型与图形语境解释。",
                "The table is used as auditable numerical evidence rather than interpreted outside the model and figure context.",
            )
        )
    return blocks
