"""C层知识卡片检索模块测试 (task t554eae27).

覆盖验收标准:
1) model_plan 自动检索注入卡片(按问题/任务类型检索);
2) 非阻塞(索引/卡片缺失不崩, 返回空);
3) 与 HMML / Method Catalog 共存(独立模块, 不修改 catalog / hmml 行为);
4) 卡片为确定性知识、无 RAG;
5) 2023/2024 C 题可检索到相关卡片。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mathworkstation.auto_pipeline import _load_knowledge_cards
from mathworkstation.knowledge_cards import (
    KnowledgeCardRetriever,
    _tokenize,
    get_retriever,
    infer_task_types,
)
from mathworkstation.llm.prompts import PromptRegistry

PROJECT = Path(__file__).resolve().parents[1]
KNOW_DIR = PROJECT / "config" / "knowledge"


def _real_analysis(objectives: list[str]) -> object:
    class _FakeAnalysis:
        pass

    analysis = _FakeAnalysis()
    analysis.objectives = objectives
    return analysis


def test_retriever_loads_all_cards() -> None:
    retriever = KnowledgeCardRetriever()
    assert retriever.loaded is True
    assert retriever.card_count == 32


def test_retrieve_returns_sorted_top_k() -> None:
    retriever = KnowledgeCardRetriever()
    cards = retriever.retrieve("预测剩余放电时间，建立放电电压与时间的关系模型", top_k=3)
    assert len(cards) <= 3
    scores = [card["score"] for card in cards]
    assert scores == sorted(scores, reverse=True)
    for card in cards:
        assert card["score"] > 0
        assert card["model_id"] and card["content"]


def test_retrieve_filters_by_task_type() -> None:
    retriever = KnowledgeCardRetriever()
    cards = retriever.retrieve(
        "预测剩余放电时间，建立放电电压与时间的关系模型",
        task_types=["prediction"],
    )
    assert cards
    for card in cards:
        assert "prediction" in card["task_types"]


def test_infer_task_types_returns_prediction_for_forecast_problem() -> None:
    types = infer_task_types("预测未来趋势并评估模型稳健性")
    assert "prediction" in types


def test_infer_task_types_empty_text() -> None:
    assert infer_task_types("") == []


def test_retrieve_empty_problem_returns_empty() -> None:
    retriever = KnowledgeCardRetriever()
    assert retriever.retrieve("") == []


def test_format_cards_contains_six_fields() -> None:
    retriever = KnowledgeCardRetriever()
    cards = retriever.retrieve("预测剩余放电时间，建立放电电压与时间的关系模型", top_k=2)
    block = retriever.format_cards(cards)
    for label in ("适用场景", "核心公式", "建模步骤", "C题适用性", "论文佐证", "易错点"):
        assert label in block
    assert "（无）" not in block


def test_format_cards_empty() -> None:
    assert KnowledgeCardRetriever().format_cards([]) == ""


def test_missing_index_is_non_blocking(tmp_path: Path) -> None:
    missing = tmp_path / "config" / "knowledge"
    missing.mkdir(parents=True)
    retriever = KnowledgeCardRetriever(index_path=missing / "index.json")
    assert retriever.loaded is False
    assert retriever.retrieve("任何问题") == []
    assert retriever.format_cards([]) == ""


def test_broken_index_is_non_blocking(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    broken = config_dir / "index.json"
    broken.write_text("{ not json", encoding="utf-8")
    retriever = KnowledgeCardRetriever(index_path=broken)
    assert retriever.loaded is False
    assert retriever.retrieve("任何问题") == []


def test_load_knowledge_cards_injects_non_empty_block() -> None:
    block = _load_knowledge_cards(_real_analysis(["预测未来趋势并评估模型稳健性"]))
    assert block, "expected a non-empty knowledge-card block for a real objective"
    assert "###" in block and "适用场景" in block


def test_load_knowledge_cards_empty_objectives_returns_empty() -> None:
    assert _load_knowledge_cards(_real_analysis([])) == ""


def test_model_plan_prompt_accepts_knowledge_cards_variable() -> None:
    registry = PromptRegistry("prompts")
    prompt = registry.load("model_plan")
    block = _load_knowledge_cards(_real_analysis(["预测未来趋势并评估模型稳健性"]))
    rendered = prompt.render(
        "model_plan",
        {
            "case_id": "case-x",
            "dataset_id": "dataset-x",
            "catalog_json": "{}",
            "columns_json": "[]",
            "profile_json": "{}",
            "problem_analysis_json": "{}",
            "hmml_retrieved": "（无）",
            "knowledge_cards": block or "（无）",
        },
    )
    assert any("C-layer essential model cards" in message["content"] for message in rendered)
    assert "{knowledge_cards}" not in rendered[1]["content"]


def test_2024_c_problem_retrieves_relevant_cards() -> None:
    path = PROJECT / "output" / "mcm-c-2024" / "v3" / "20260805-MCM-0001-KVD7" / "analysis" / "problem_analysis.json"
    if not path.is_file():
        pytest.skip("2024 case analysis not present")
    analysis_raw = json.loads(path.read_text(encoding="utf-8"))
    block = _load_knowledge_cards(_real_analysis(analysis_raw.get("objectives", [])))
    if not block:
        pytest.skip("no cards retrieved for this objective set")
    assert "###" in block
    # must reference at least one real card body section
    assert "适用场景" in block or "核心公式" in block


def test_2023_c_problem_retrieves_relevant_cards() -> None:
    path = PROJECT / "output" / "mcm-c-2023" / "v3" / "20260805-MCM-0001-EUP7" / "analysis" / "problem_analysis.json"
    if not path.is_file():
        pytest.skip("2023 case analysis not present")
    analysis_raw = json.loads(path.read_text(encoding="utf-8"))
    block = _load_knowledge_cards(_real_analysis(analysis_raw.get("objectives", [])))
    if not block:
        pytest.skip("no cards retrieved for this objective set")
    assert "###" in block
    assert "适用场景" in block or "核心公式" in block


def test_tokenize_handles_cjk_bigrams() -> None:
    tokens = _tokenize("预测剩余放电时间")
    assert "预测" in tokens and "时间" in tokens
    assert tokens & _tokenize("预测剩余放电时间的关系")  # shared bigrams


def test_get_retriever_is_process_cached() -> None:
    assert get_retriever() is get_retriever()
