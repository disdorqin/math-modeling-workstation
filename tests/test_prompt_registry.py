from pathlib import Path

import pytest

from mathworkstation.llm.prompts import PromptRegistry


def test_prompt_registry_versions_and_renders() -> None:
    registry = PromptRegistry("prompts")
    prompts = registry.list_prompts()
    assert {item["prompt_id"] for item in prompts} >= {"problem_analysis", "paper_section"}
    prompt = registry.load("problem_analysis")
    messages = prompt.render(
        "problem_analysis",
        {
            "case_id": "case-test",
            "competition_type": "SM",
            "resume_brief": "No prior work.",
        },
    )
    assert messages[0]["role"] == "system"
    assert "case-test" in messages[0]["content"]
    assert len(prompt.digest) == 64


def test_prompt_rejects_wrong_node_and_missing_variables() -> None:
    prompt = PromptRegistry("prompts").load("paper_section")
    with pytest.raises(PermissionError):
        prompt.render("problem_analysis", {})
    with pytest.raises(ValueError, match="missing prompt variables"):
        prompt.render("paper_draft", {"case_id": "x"})


def test_prompt_registry_falls_back_to_project_root_outside_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = PromptRegistry("prompts")
    assert registry.load("problem_analysis").prompt_id == "problem_analysis"
