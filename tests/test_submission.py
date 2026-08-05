from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.submission import SubmissionService, SubmissionProfile, markdown_to_latex


def test_markdown_to_latex_preserves_math_and_escapes_text() -> None:
    output = markdown_to_latex("# 标题\n\n## 模型建立\n\n目标 $L= y-x$，误差率 10%\n", SubmissionProfile("SM"))
    assert "\\section{模型建立}" in output
    assert "$L= y-x$" in output
    assert "10\\%" in output


def test_submission_sanitizes_internal_markers_before_preflight(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "cases")
    case = cases.create_case("SM", "投稿预检")
    root = cases.case_root(case["case_id"])
    (root / "paper" / "final.md").write_text("# 标题\n\n## 摘要\n\n## 模型建立\n[CLAIM-001]\n\n## 结果分析\n\n## 结论\n", encoding="utf-8")
    service = SubmissionService(cases, ArtifactRegistry(cases))
    result = service.prepare(case["case_id"])
    codes = {item["code"] for item in result["preflight"]["findings"]}
    assert result["preflight"]["gate"] == "PASS"
    assert "INTERNAL_REFERENCE_LEAK" not in codes
    assert "[CLAIM-001]" not in (root / "paper" / "markdown" / "submission.md").read_text(encoding="utf-8")


def test_submission_preflight_passes_complete_text(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "cases")
    case = cases.create_case("SM", "投稿通过")
    root = cases.case_root(case["case_id"])
    (root / "paper" / "final.md").write_text("# 标题\n\n## 摘要\n完整摘要。\n\n## 模型建立\n设 $x$。\n\n## 结果分析\n结果明确。\n\n## 结论\n结论明确。\n", encoding="utf-8")
    result = SubmissionService(cases, ArtifactRegistry(cases)).prepare(case["case_id"])
    assert result["preflight"]["gate"] == "PASS"
    assert (root / "paper" / "latex" / "main.tex").is_file()


def test_mcm_profile_accepts_chinese_paper_sections(tmp_path: Path) -> None:
    """MCM/ICM profile must not false-report missing sections on Chinese papers."""
    cases = CaseManager(tmp_path / "cases")
    case = cases.create_case("MCM", "中文 MCM 论文")
    root = cases.case_root(case["case_id"])
    (root / "paper" / "final.md").write_text(
        "# 标题\n\n## 摘要\n完整摘要。\n\n## 模型建立\n设 $x$。\n\n## 结果分析\n结果明确。\n\n## 结论\n结论明确。\n",
        encoding="utf-8",
    )
    result = SubmissionService(cases, ArtifactRegistry(cases)).prepare(case["case_id"], "MCM")
    codes = {item["code"] for item in result["preflight"]["findings"]}
    assert result["preflight"]["gate"] == "PASS"
    assert "REQUIRED_SECTION_MISSING" not in codes


def test_mcm_profile_accepts_english_paper_sections(tmp_path: Path) -> None:
    """English MCM papers still pass with English section headings."""
    cases = CaseManager(tmp_path / "cases")
    case = cases.create_case("MCM", "English MCM paper")
    root = cases.case_root(case["case_id"])
    (root / "paper" / "final.md").write_text(
        "# Title\n\n## Abstract\nFull abstract.\n\n## Model\nModel details.\n\n## Results\nClear results.\n\n## Conclusion\nClear conclusion.\n",
        encoding="utf-8",
    )
    result = SubmissionService(cases, ArtifactRegistry(cases)).prepare(case["case_id"], "MCM")
    assert result["preflight"]["gate"] == "PASS"


def test_mcm_profile_still_blocks_when_sections_missing(tmp_path: Path) -> None:
    """Missing sections must still be reported even with language-aware aliases."""
    cases = CaseManager(tmp_path / "cases")
    case = cases.create_case("MCM", "缺节论文")
    root = cases.case_root(case["case_id"])
    (root / "paper" / "final.md").write_text("# 标题\n\n## 摘要\n完整摘要。\n\n## 模型建立\n设 $x$。\n", encoding="utf-8")
    result = SubmissionService(cases, ArtifactRegistry(cases)).prepare(case["case_id"], "MCM")
    codes = {item["code"] for item in result["preflight"]["findings"]}
    assert result["preflight"]["gate"] == "BLOCK"
    assert "REQUIRED_SECTION_MISSING" in codes
