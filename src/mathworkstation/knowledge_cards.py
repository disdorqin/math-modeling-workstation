"""C层精华模型卡片检索(config/knowledge) — 确定性知识, 非RAG.

卡片库(config/knowledge/index.json + cards/*.md)与 HMML(做法) / Method
Catalog(能用哪些) 互补: 每张卡片为 32 个 catalog 方法之一提供「适用场景/核心
公式/建模步骤/C题适用性/论文佐证/易错点」, 供 model_plan LLM 在写候选方案
rationale 时参考。

设计约束:
* 确定性: 检索用词汇重叠(含 CJK 二元组), 绝不依赖 embedding/向量检索。
* 按问题/任务类型: ``infer_task_types`` 用关键词表推断 task_type, 先按任务
  类型过滤候选卡片, 再按问题文本相关性排序取 top-k。
* 非阻塞: 索引/卡片缺失或不可读时 ``retrieve`` 返回空列表, ``format_cards``
  返回空串 —— 与 HMML 融合层一致, 永远不中断流水线。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: 确定性 task_type 推断关键词表 (中文关键词为主, 兼收英文)。
_TASK_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "prediction": ("预测", "预报", "趋势", "外推", "未来", "forecast", "predict", "剩余放电"),
    "regression": ("回归", "拟合", "函数关系", "相关关系", "regression", "线性关系"),
    "classification": ("分类", "判别", "识别", "违约", "classif", "判别是否"),
    "optimization": ("优化", "规划", "决策", "最优", "最小化", "最大化", "调度", "安排", "optimi"),
    "evaluation": ("评价", "评估", "排名", "排序", "打分", "优劣", "综合评分", "指标体", "evaluat"),
    "clustering": ("聚类", "分组", "画像", "分群", "cluster"),
    "correlation_analysis": ("关联", "影响因素", "因子", "相关分析", "correlation"),
    "interpolation": ("插值", "interpolat"),
    "simulation": ("模拟", "仿真", "蒙特卡洛", "simulate", "随机模拟"),
    "stochastic_process": ("随机过程", "马尔可夫", "马氏链", "状态转移", "markov", "排队"),
    "graph_optimization": ("图论", "网络", "路径", "连通", "流量", "graph", "网络流", "最短路径"),
    "differential_equation": ("微分方程", "动力系统", "常微分", "ode", "微分"),
    "queueing": ("排队", "队列", "等待时间", "服务台", "queue"),
    "dimension_reduction": ("降维", "主成分", "因子分析", "pca"),
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokenize(text: str) -> set[str]:
    """Tokenise for overlap scoring: latin words + CJK character bigrams.

    CJK bigrams are a light-weight segmentation that keeps Chinese problem
    text scorable without an external tokeniser (consistent with the
    repository's no-RAG, offline-only retrieval stance).
    """
    tokens: set[str] = set(re.findall(r"[a-z0-9]+", text.lower()))
    cjk = "".join(_CJK_RE.findall(text))
    tokens.update(cjk[index : index + 2] for index in range(len(cjk) - 1))
    return tokens


def infer_task_types(problem_text: str) -> list[str]:
    """Deterministically infer likely task_type(s) from problem text."""
    lowered = problem_text.lower()
    hits: list[tuple[int, str]] = []
    for task_type, keywords in _TASK_TYPE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if score:
            hits.append((score, task_type))
    hits.sort(reverse=True)
    return [task_type for _score, task_type in hits]


class KnowledgeCardRetriever:
    """Load ``config/knowledge`` cards and retrieve by task type / relevance.

    Mirrors the HMML ``MethodRetriever`` shape so the model_plan fusion layer
    can treat it uniformly: ``retrieve`` returns ordered card dicts,
    ``format_cards`` renders them for prompt injection.
    """

    def __init__(self, index_path: str | Path | None = None, top_k: int = 4) -> None:
        if index_path is None:
            index_path = Path(__file__).resolve().parents[2] / "config" / "knowledge" / "index.json"
        self.index_path = Path(index_path)
        self.top_k = top_k
        self._cards: list[dict[str, Any]] = []
        self._loaded = False
        self._load()

    def _load(self) -> None:
        """Best-effort load of the card index + markdown bodies (non-blocking)."""
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            cards_root = self.index_path.parent
            entries = raw.get("cards", [])
            for entry in entries:
                card_path = cards_root / str(entry["card_path"])
                content = card_path.read_text(encoding="utf-8") if card_path.is_file() else ""
                self._cards.append(
                    {
                        "model_id": entry.get("model_id", ""),
                        "title": entry.get("title", ""),
                        "family": entry.get("family", ""),
                        "task_types": list(entry.get("task_types", [])),
                        "content": content,
                    }
                )
            self._loaded = True
        except Exception:  # noqa: BLE001 - 卡片层是建议性的, 永远不阻塞流水线
            self._loaded = False

    def _candidate_pool(self, task_types: list[str] | None) -> list[dict[str, Any]]:
        if not task_types:
            return self._cards
        allowed = set(task_types)
        return [card for card in self._cards if allowed & set(card["task_types"])]

    def _score_card(self, card: dict[str, Any], query_tokens: set[str]) -> float:
        """Dice coefficient over (title + family + task_types + content)."""
        text = f"{card['title']} {card['family']} {' '.join(card['task_types'])} {card['content']}"
        card_tokens = _tokenize(text)
        if not query_tokens or not card_tokens:
            return 0.0
        overlap = len(query_tokens & card_tokens)
        return 2.0 * overlap / (len(query_tokens) + len(card_tokens))

    def retrieve(self, problem_text: str, task_types: list[str] | None = None, top_k: int | None = None) -> list[dict[str, Any]]:
        """Return the top-k cards for the problem, ordered by relevance.

        ``task_types`` (optional) restricts the pool before scoring, e.g. the
        output of :func:`infer_task_types`.
        """
        if not self._loaded or not self._cards:
            return []
        query_tokens = _tokenize(problem_text)
        if not query_tokens:
            return []
        pool = self._candidate_pool(task_types)
        scored = sorted(
            ((self._score_card(card, query_tokens), card) for card in pool),
            key=lambda item: item[0],
            reverse=True,
        )
        limit = top_k if top_k is not None else self.top_k
        return [{"score": score, **card} for score, card in scored[:limit] if score > 0]

    def format_cards(self, cards: list[dict[str, Any]]) -> str:
        """Render cards for prompt injection (compact 6-field blocks)."""
        blocks: list[str] = []
        for card in cards:
            sections = _parse_card_sections(card.get("content", ""))
            lines = [f"### {card.get('title', '')} ({card.get('model_id', '')}) — {card.get('family', '')}"]
            for label in ("适用场景", "核心公式", "建模步骤", "C题适用性", "论文佐证", "易错点"):
                body = _compact(sections.get(label, ""))
                if body:
                    lines.append(f"- {label}: {body}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def card_count(self) -> int:
        return len(self._cards) if self._loaded else 0


def _parse_card_sections(content: str) -> dict[str, str]:
    """Split a card markdown body into ``## 章节名 -> 正文`` map."""
    sections: dict[str, str] = {}
    current: str | None = None
    chunks: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(chunks).strip()
            current = line[3:].strip()
            chunks = []
        elif current is not None:
            chunks.append(line)
    if current is not None:
        sections[current] = "\n".join(chunks).strip()
    return sections


def _compact(text: str) -> str:
    return " ".join(text.split())


_global_retriever: KnowledgeCardRetriever | None = None


def get_retriever() -> KnowledgeCardRetriever:
    """Process-lifetime cached retriever (mirrors ``get_library`` / catalog cache)."""
    global _global_retriever
    if _global_retriever is None:
        _global_retriever = KnowledgeCardRetriever()
    return _global_retriever
