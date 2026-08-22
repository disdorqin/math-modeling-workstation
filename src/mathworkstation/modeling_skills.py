from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_SKILLS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "ai_skills_extracted"
    / "数学建模全流程AI-Skills出售版"
    / "skills"
)


class ModelingSkillAdvice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    path: str
    relevance: float
    method_hints: list[str] = Field(default_factory=list)
    quality_checks: list[str] = Field(default_factory=list)
    when_not_to_use: list[str] = Field(default_factory=list)


class ModelingSkillRetriever:
    """Read the repository's extracted SKILL.md assets as advisory metadata.

    Skills are never executed as solver code here. They contribute selection
    constraints, method hints and quality checks to the node-level Modeling
    Brain. Actual executability remains the Solver/Feasibility layer's job.
    """

    _FAMILY_SKILLS: dict[str, tuple[str, ...]] = {
        "forecasting": ("mm-model-selector", "mm-prediction-models"),
        "distribution_forecasting": ("mm-model-selector", "mm-prediction-models"),
        "explanatory_inference": ("mm-model-selector", "mm-prediction-models"),
        "classification": ("mm-model-selector", "mm-classification-clustering"),
        "exploratory_analysis": ("mm-model-selector", "mm-classification-clustering", "mm-data-eda-cleaning"),
        "optimization": ("mm-model-selector", "mm-optimization-models"),
        "simulation": ("mm-model-selector", "mm-simulation-models"),
        "ranking": ("mm-model-selector", "mm-evaluation-models"),
        "generic_modeling": ("mm-model-selector",),
    }

    _METHOD_PATTERNS: tuple[tuple[str, str], ...] = (
        (r"\bARIMA\b", "ARIMA"),
        (r"GM\(1,1\)", "GM(1,1)"),
        (r"线性规划", "linear programming"),
        (r"整数规划", "integer programming"),
        (r"非线性规划", "nonlinear programming"),
        (r"多目标优化", "multi-objective optimization"),
        (r"逻辑回归", "logistic regression"),
        (r"随机森林", "random forest"),
        (r"支持向量机|\bSVM\b", "SVM"),
        (r"决策树", "decision tree"),
        (r"K-?means", "K-Means"),
        (r"DBSCAN", "DBSCAN"),
        (r"层次聚类", "hierarchical clustering"),
        (r"主成分|\bPCA\b", "PCA"),
        (r"蒙特卡洛|Monte Carlo", "Monte Carlo"),
        (r"排队模型", "queueing model"),
        (r"离散事件仿真", "discrete-event simulation"),
        (r"回归", "regression baseline"),
        (r"时间序列", "time-series baseline"),
    )

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_SKILLS_ROOT

    @property
    def available(self) -> bool:
        return self.root.is_dir()

    def retrieve(self, task_family: str, query: str = "") -> list[ModelingSkillAdvice]:
        if not self.available:
            return []
        names = self._FAMILY_SKILLS.get(task_family, ())
        values: list[ModelingSkillAdvice] = []
        query_tokens = _tokens(query)
        for order, name in enumerate(names):
            path = self.root / name / "SKILL.md"
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            meta, body = _parse_skill(text)
            description = meta.get("description", "")
            body_tokens = _tokens(f"{description} {body}")
            overlap = len(query_tokens & body_tokens) / max(1, len(query_tokens)) if query_tokens else 0.0
            # Direct task-family routing is the primary signal; lexical overlap
            # only refines ordering among multiple applicable skills.
            relevance = max(0.0, 1.0 - order * 0.08) + overlap * 0.2
            values.append(
                ModelingSkillAdvice(
                    name=meta.get("name", name),
                    description=description,
                    path=path.relative_to(self.root).as_posix(),
                    relevance=float(relevance),
                    method_hints=_method_hints(body),
                    quality_checks=_section_bullets(body, "Quality checks"),
                    when_not_to_use=_section_bullets(body, "When not to use"),
                )
            )
        values.sort(key=lambda item: item.relevance, reverse=True)
        return values


def _parse_skill(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    meta: dict[str, str] = {}
    body_start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            line = lines[index]
            if line.strip() == "---":
                body_start = index + 1
                break
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
    return meta, "\n".join(lines[body_start:])


def _section_bullets(body: str, heading: str) -> list[str]:
    lines = body.splitlines()
    active = False
    values: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if active:
                break
            active = line[3:].strip().lower() == heading.lower()
            continue
        if active and line.strip().startswith("-"):
            value = line.strip()[1:].strip()
            if value:
                values.append(value)
    return values


def _method_hints(body: str) -> list[str]:
    result: list[str] = []
    for pattern, method in ModelingSkillRetriever._METHOD_PATTERNS:
        if re.search(pattern, body, flags=re.IGNORECASE):
            result.append(method)
    return list(dict.fromkeys(result))


def _tokens(text: str) -> set[str]:
    latin = set(re.findall(r"[a-z0-9]+", text.lower()))
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    latin.update(cjk[index : index + 2] for index in range(max(0, len(cjk) - 1)))
    return latin
