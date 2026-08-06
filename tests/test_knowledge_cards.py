"""C层精华模型卡片(config/knowledge)校验测试 (task t99126b84).

覆盖验收标准:
1) ≥20 张卡片; 2) 每卡含 6 字段(适用场景/核心公式/建模步骤/C题适用性/论文佐证/易错点);
3) index.json 与 config/model-catalog.json 32 方法对齐; 4) 至少 5 张卡片有真实高教社C题论文佐证;
5) 卡片为确定性知识、不引入 RAG(仅 md + json)。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
KNOW_DIR = PROJECT / "config" / "knowledge"
CARD_DIR = KNOW_DIR / "cards"
INDEX_FILE = KNOW_DIR / "index.json"
CATALOG_FILE = PROJECT / "config" / "model-catalog.json"

REQUIRED_SECTIONS = [
    "## 适用场景",
    "## 核心公式",
    "## 建模步骤",
    "## C题适用性",
    "## 论文佐证",
    "## 易错点",
]


def _load_index() -> dict:
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def _load_catalog() -> dict:
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def test_knowledge_dir_and_index_exist() -> None:
    assert KNOW_DIR.is_dir()
    assert INDEX_FILE.is_file()
    assert CARD_DIR.is_dir()


def test_at_least_20_cards() -> None:
    index = _load_index()
    cards = index["cards"]
    assert len(cards) >= 20, f"卡片数 {len(cards)} < 20"
    md_files = [p.name for p in CARD_DIR.glob("*.md")]
    assert len(md_files) == len(cards)


def test_every_card_has_required_sections() -> None:
    index = _load_index()
    for entry in index["cards"]:
        card_path = CARD_DIR / entry["card_path"].split("/")[-1]
        assert card_path.is_file(), f"卡片文件缺失: {card_path}"
        text = card_path.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{card_path.name} 缺少字段: {section}"


def test_every_card_has_latex_formula() -> None:
    index = _load_index()
    for entry in index["cards"]:
        card_path = CARD_DIR / entry["card_path"].split("/")[-1]
        text = card_path.read_text(encoding="utf-8")
        assert "$$" in text, f"{card_path.name} 核心公式缺少 LaTeX($$...$$)"


def test_index_aligns_with_model_catalog() -> None:
    """index.json 的 model_id 集合与 catalog 32 方法一一对应(无缺失无多余)。"""
    catalog = _load_catalog()
    cat_ids = {m["name"] for m in catalog["methods"]}
    index = _load_index()
    card_ids = {c["model_id"] for c in index["cards"]}
    assert len(cat_ids) == 32
    assert card_ids == cat_ids, (
        f"缺失: {sorted(cat_ids - card_ids)}, 多余: {sorted(card_ids - cat_ids)}"
    )


def test_index_entries_have_required_keys() -> None:
    index = _load_index()
    for entry in index["cards"]:
        for key in ("model_id", "title", "family", "task_types", "card_path", "c_fit"):
            assert key in entry, f"index 条目缺少 {key}: {entry.get('model_id')}"
        assert 0.0 <= entry["c_fit"] <= 1.0


def test_at_least_5_cards_have_real_c_paper_evidence() -> None:
    """论文佐证必须真实: 含「高教社C题」且标注年份与题目。"""
    year_re = re.compile(r"(20\d\d)")
    evid_cards = []
    for entry in _load_index()["cards"]:
        card_path = CARD_DIR / entry["card_path"].split("/")[-1]
        text = card_path.read_text(encoding="utf-8")
        if "高教社" not in text:
            continue
        # 取出「论文佐证」章节, 判断含年份+题目特征
        m = re.search(r"## 论文佐证\n(.*?)\n## 易错点", text, re.S)
        if not m:
            continue
        evidence = m.group(1)
        has_year = bool(year_re.search(evidence))
        has_topic_marker = any(k in evidence for k in ("C题", "C1", "C155", "C050", "C126", "C228", "C235", "C063", "C023", "C-"))
        if has_year and has_topic_marker:
            evid_cards.append(entry["model_id"])
    assert len(evid_cards) >= 5, f"真实佐证卡片仅 {len(evid_cards)} 张: {evid_cards}"


def test_cards_are_deterministic_knowledge_no_rag_marks() -> None:
    """卡片是确定性知识: 不包含 RAG/向量检索标记。"""
    index = _load_index()
    for entry in index["cards"]:
        card_path = CARD_DIR / entry["card_path"].split("/")[-1]
        text = card_path.read_text(encoding="utf-8").lower()
        for mark in ("rag_enabled", "向量检索", "embedding_index", "retrieval_augmented", "vectorstore"):
            assert mark not in text, f"{card_path.name} 含 RAG 标记: {mark}"


def test_every_card_starts_with_model_title_heading() -> None:
    index = _load_index()
    for entry in index["cards"]:
        card_path = CARD_DIR / entry["card_path"].split("/")[-1]
        text = card_path.read_text(encoding="utf-8")
        assert text.startswith("# "), f"{card_path.name} 缺少一级标题"
        assert f"({entry['model_id']})" in text.splitlines()[0]
