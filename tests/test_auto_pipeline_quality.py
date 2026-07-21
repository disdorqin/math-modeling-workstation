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
