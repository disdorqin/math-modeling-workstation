from __future__ import annotations

from mathworkstation.judge_validity import (
    CalibrationPaper,
    JudgeVote,
    aggregate_judge_validity,
    anonymize_paper_text,
    blind_pair_rows,
    identity_leakage_findings,
    make_swapped_pair,
)


def _papers() -> list[CalibrationPaper]:
    return [
        CalibrationPaper(
            blind_id="paper-a",
            origin="REAL_EXCELLENT",
            competition="MCM",
            year=2024,
            problem_letter="C",
            problem_key="mcm-2024-c",
            source_path="external/2409404.pdf",
            award="O",
        ),
        CalibrationPaper(
            blind_id="paper-b",
            origin="WORKSTATION_CURRENT",
            competition="MCM",
            year=2024,
            problem_letter="C",
            problem_key="mcm-2024-c",
            source_path="generated/current.pdf",
            case_id="current",
        ),
        CalibrationPaper(
            blind_id="paper-c",
            origin="WORKSTATION_OLDER",
            competition="MCM",
            year=2024,
            problem_letter="C",
            problem_key="mcm-2024-c",
            source_path="generated/old.pdf",
            case_id="old",
        ),
    ]


def test_anonymizer_masks_award_and_team_identity_without_erasing_results() -> None:
    source = """Outstanding Winner\nTeam # 2409404\nUniversity: Example U\nO Award paper models momentum.\nAUC = 0.681 and cost = 2409404.25.\n"""
    value = anonymize_paper_text(source)

    assert "Outstanding" not in value
    assert "Team # 2409404" not in value
    assert "Example U" not in value
    assert "O Award" not in value
    assert "models momentum" in value
    assert "0.681" in value
    assert "2409404.25" in value


def test_swapped_pair_changes_position_but_preserves_identity() -> None:
    ab, ba = make_swapped_pair(
        swap_group="mcm24-real-current",
        left_id="paper-a",
        right_id="paper-b",
        kind="REAL_VS_CURRENT",
    )

    assert ab.left_id == ba.right_id == "paper-a"
    assert ab.right_id == ba.left_id == "paper-b"
    assert ab.swap_group == ba.swap_group


def test_blind_pair_rows_never_expose_private_pair_kind() -> None:
    ab, _ = make_swapped_pair(
        swap_group="mcm24-real-current",
        left_id="paper-a",
        right_id="paper-b",
        kind="REAL_VS_CURRENT",
    )

    row = blind_pair_rows([ab])[0]

    assert row == {
        "pair_id": "mcm24-real-current-ab",
        "swap_group": "mcm24-real-current",
        "left_id": "paper-a",
        "right_id": "paper-b",
    }
    assert "kind" not in row


def test_identity_leakage_scanner_flags_provenance_but_not_normal_numbers() -> None:
    text = "Outstanding Award\nTeam Control Number: 2409404\ncase 20260823-MCM-0004-D97D\nAUC=0.681"
    findings = identity_leakage_findings(text, forbidden_literals=["2409404"])

    assert "award_label" in findings
    assert "team_control_label" in findings
    assert "case_id" in findings
    assert "forbidden_literal:2409404" in findings
    assert not any("0.681" in item for item in findings)


def test_chinese_anonymizer_masks_award_team_and_school_metadata() -> None:
    source = """全国大学生数学建模竞赛一等奖\n参赛队号：C050\n学校：示例大学\n本文建立补货优化模型。\n"""
    value = anonymize_paper_text(source)

    assert "一等奖" not in value
    assert "参赛队号" not in value
    assert "示例大学" not in value
    assert "补货优化模型" in value
    assert identity_leakage_findings(value) == []


def test_no_blind_human_anchor_forces_inconclusive_h1() -> None:
    papers = _papers()
    ab, ba = make_swapped_pair(
        swap_group="mcm24-real-current",
        left_id="paper-a",
        right_id="paper-b",
        kind="REAL_VS_CURRENT",
    )
    votes = [
        JudgeVote("internal-auditor", "INTERNAL", ab.pair_id, "RIGHT", 0.8),
        JudgeVote("internal-auditor", "INTERNAL", ba.pair_id, "LEFT", 0.8),
    ]

    aggregate = aggregate_judge_validity(papers, [ab, ba], votes)

    assert aggregate["position_swap_consistency"] == 1.0
    assert aggregate["discrimination"]["internal-auditor"]["accuracy_vs_provenance_prior"] == 0.0
    assert aggregate["h1_judge_validity_bottleneck"] == "INCONCLUSIVE"
    assert aggregate["human_vote_count"] == 0


def test_one_blind_human_logical_pair_is_not_enough_to_decide_h1() -> None:
    papers = _papers()
    ab, ba = make_swapped_pair(
        swap_group="mcm24-real-current",
        left_id="paper-a",
        right_id="paper-b",
        kind="REAL_VS_CURRENT",
    )
    votes = [
        JudgeVote("internal-auditor", "INTERNAL", ab.pair_id, "RIGHT", 0.8),
        JudgeVote("internal-auditor", "INTERNAL", ba.pair_id, "LEFT", 0.8),
        JudgeVote("human-1", "HUMAN", ab.pair_id, "LEFT", 0.9, blind_verified=True),
        JudgeVote("human-1", "HUMAN", ba.pair_id, "RIGHT", 0.9, blind_verified=True),
    ]

    aggregate = aggregate_judge_validity(papers, [ab, ba], votes)

    assert aggregate["position_swap_consistency"] == 1.0
    assert aggregate["cross_judge_agreement"] == 0.0
    assert aggregate["blind_human_vote_count"] == 2
    assert aggregate["blind_human_anchor_group_count"] == 1
    assert aggregate["h1_judge_validity_bottleneck"] == "INCONCLUSIVE"


def test_two_blind_human_logical_pairs_can_support_h1_from_actual_human_agreement() -> None:
    papers = _papers()
    real_ab, real_ba = make_swapped_pair(
        swap_group="mcm24-real-current",
        left_id="paper-a",
        right_id="paper-b",
        kind="REAL_VS_CURRENT",
    )
    old_ab, old_ba = make_swapped_pair(
        swap_group="mcm24-current-old",
        left_id="paper-b",
        right_id="paper-c",
        kind="CURRENT_VS_OLDER",
    )
    votes = [
        JudgeVote("internal-auditor", "INTERNAL", real_ab.pair_id, "RIGHT", 0.8),
        JudgeVote("internal-auditor", "INTERNAL", real_ba.pair_id, "LEFT", 0.8),
        JudgeVote("internal-auditor", "INTERNAL", old_ab.pair_id, "LEFT", 0.8),
        JudgeVote("internal-auditor", "INTERNAL", old_ba.pair_id, "RIGHT", 0.8),
        JudgeVote("human-1", "HUMAN", real_ab.pair_id, "LEFT", 0.9, blind_verified=True),
        JudgeVote("human-1", "HUMAN", real_ba.pair_id, "RIGHT", 0.9, blind_verified=True),
        JudgeVote("human-1", "HUMAN", old_ab.pair_id, "LEFT", 0.9, blind_verified=True),
        JudgeVote("human-1", "HUMAN", old_ba.pair_id, "RIGHT", 0.9, blind_verified=True),
    ]

    aggregate = aggregate_judge_validity(papers, [real_ab, real_ba, old_ab, old_ba], votes)

    assert aggregate["blind_human_anchor_group_count"] == 2
    assert aggregate["internal_checked_vs_blind_human"] == 2
    assert aggregate["internal_accuracy_vs_blind_human"] == 0.5
    assert aggregate["h1_judge_validity_bottleneck"] == "SUPPORTED"


def test_nonblind_human_vote_does_not_unlock_h1() -> None:
    papers = _papers()
    ab, ba = make_swapped_pair(
        swap_group="mcm24-real-current",
        left_id="paper-a",
        right_id="paper-b",
        kind="REAL_VS_CURRENT",
    )
    votes = [
        JudgeVote("internal-auditor", "INTERNAL", ab.pair_id, "RIGHT", 0.8),
        JudgeVote("internal-auditor", "INTERNAL", ba.pair_id, "LEFT", 0.8),
        JudgeVote("human-known-source", "HUMAN", ab.pair_id, "LEFT", 0.9),
    ]

    aggregate = aggregate_judge_validity(papers, [ab, ba], votes)

    assert aggregate["human_vote_count"] == 1
    assert aggregate["blind_human_vote_count"] == 0
    assert aggregate["h1_judge_validity_bottleneck"] == "INCONCLUSIVE"


def test_current_vs_older_uses_current_as_provenance_prior() -> None:
    papers = _papers()
    ab, ba = make_swapped_pair(
        swap_group="mcm24-current-old",
        left_id="paper-b",
        right_id="paper-c",
        kind="CURRENT_VS_OLDER",
    )
    votes = [
        JudgeVote("internal-auditor", "INTERNAL", ab.pair_id, "LEFT", 0.7),
        JudgeVote("internal-auditor", "INTERNAL", ba.pair_id, "RIGHT", 0.7),
    ]

    aggregate = aggregate_judge_validity(papers, [ab, ba], votes)

    assert aggregate["discrimination"]["internal-auditor"]["accuracy_vs_provenance_prior"] == 1.0
