from mathworkstation.auto_pipeline import _polish_section_draft, _scalarize_parameters


def test_scalarize_parameters_reduces_numeric_lists_to_median() -> None:
    value = _scalarize_parameters({"alpha": [0.01, 0.1, 1.0], "nested": {"depth": [2, 4, 8]}})
    assert value == {"alpha": 0.1, "nested": {"depth": 4}}


def test_section_polisher_replaces_empty_model_output_with_claim_grounded_text() -> None:
    context = {
        "allowed_claims": [
            {
                "claim_id": "claim-0123456789ab",
                "text": "Ridge 在交叉验证中排名第一。",
            }
        ]
    }
    content = "本节暂无已登记证据，保留结构性说明，不作外推结论。"
    polished = _polish_section_draft("results", content, context)
    assert "Ridge 在交叉验证中排名第一。 [claim-0123456789ab]" in polished
    assert "暂无已登记证据" not in polished


def test_section_polisher_keeps_no_evidence_scaffold_concise() -> None:
    context = {"allowed_claims": []}
    polished = _polish_section_draft(
        "notation", "本节暂无已登记证据，保留结构性说明，不作外推结论。", context
    )
    assert "$" in polished
    assert polished.count("暂无已登记证据") == 0


def test_section_polisher_removes_boilerplate_from_evidence_rich_draft() -> None:
    context = {
        "allowed_claims": [
            {
                "claim_id": "claim-0123456789ab",
                "text": "数据质量门为 PASS。",
            }
        ]
    }
    content = (
        "本节暂无已登记证据，保留结构性说明，不作外推结论。\n\n"
        "数据质量门为 PASS。[claim-0123456789ab]"
    )
    polished = _polish_section_draft("data_analysis", content, context)
    assert polished.count("暂无已登记证据") == 0
    assert "数据质量门为 PASS。[claim-0123456789ab]" in polished


def test_abstract_quality_appends_natural_prose_not_mechanical_labels() -> None:
    from mathworkstation.auto_pipeline import _ensure_abstract_quality

    context = {
        "allowed_claims": [
            {"claim_id": "claim-aaaa", "claim_type": "problem_analysis", "text": "题目目标已拆解为可追踪的子问题。"},
            {"claim_id": "claim-bbbb", "claim_type": "model_plan", "text": "候选模型经数据审查后进入比较。"},
            {"claim_id": "claim-cccc", "claim_type": "model_result", "text": "Ridge 在交叉验证中排名第一。"},
            {"claim_id": "claim-dddd", "claim_type": "sensitivity", "text": "敏感性门控结果为 PASS。"},
        ]
    }
    out = _ensure_abstract_quality("短摘要。", context)
    assert "研究目的：" not in out
    assert "研究方法：" not in out
    assert "主要结果：" not in out
    assert "稳健性与边界：" not in out
    assert "针对研究问题，" in out
    assert "实验结果表明，" in out
    assert "claim-aaaa" in out and "claim-cccc" in out


def test_abstract_quality_keeps_complete_draft_unchanged() -> None:
    from mathworkstation.auto_pipeline import _ensure_abstract_quality

    content = (
        "本文研究数据驱动的预测问题。方法采用候选模型比较与交叉验证。"
        "主要结果：Ridge 排名第一。结论受数据范围约束。" * 20
    )
    assert len(content) >= 650
    out = _ensure_abstract_quality(content, {"allowed_claims": []})
    assert out == content
