from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .c_problem_benchmark import CProblemBenchmarkRegistry, load_c_problem_benchmark
from .problem_graph import ProblemGraph, SubproblemNode


class CProblemModelingPriorAssessment(BaseModel):
    """Advisory C-problem research obligations derived from excellent-paper corpora.

    These priors may shape research questions and validation obligations, but
    they deliberately contain no solver-feasibility decision and never select a
    concrete algorithm by corpus frequency.
    """

    model_config = ConfigDict(extra="forbid")

    scope: str = "C_PROBLEM_ONLY"
    source_registry: str
    prior_names: list[str] = Field(default_factory=list)
    research_obligations: list[str] = Field(default_factory=list)
    validation_obligations: list[str] = Field(default_factory=list)
    forbidden_shortcuts: list[str] = Field(default_factory=list)
    evidence_note: str = ""


class CProblemModelingPriorService:
    def __init__(self, registry: CProblemBenchmarkRegistry, *, source_registry: str) -> None:
        registry.validate_primary_gate()
        self.registry = registry
        self.source_registry = source_registry

    @classmethod
    def from_default_registry(cls) -> "CProblemModelingPriorService":
        repo_root = Path(__file__).resolve().parents[2]
        relative = Path("config/ref_models/c_problem_excellent_benchmark_v1.json")
        registry = load_c_problem_benchmark(repo_root / relative, repo_root=repo_root)
        return cls(registry, source_registry=relative.as_posix())

    def assess(self, node: SubproblemNode, graph: ProblemGraph) -> CProblemModelingPriorAssessment:
        prior_names = [item.name for item in self.registry.shared_c_problem_priors]
        research: list[str] = [
            "先定义与该子问题题意直接对应的变量、状态、指标、几何对象或领域构造，再比较通用算法。",
            "模型选择理由必须来自数据特征、领域机理或约束结构；优秀论文中的算法频率只能提供候选线索。",
        ]
        if node.dependencies:
            research.append(
                "该节点存在上游依赖：优先复用、扩展或质疑已接受的上游 Research State，不得把后续小问重置成独立模型演示。"
            )
        elif any(edge.target_subproblem_id == node.subproblem_id for edge in graph.edges):
            research.append("该节点应显式说明它如何使用上游研究证据。")

        if node.execution_kind == "DELIVERABLE":
            research.append("交付物只能综合依赖节点的 accepted evidence，不得在写作层补造模型、数字或政策目标。")

        validation = _validation_obligations(node.task_family)
        shortcuts = [
            "禁止因为某方法在优秀论文中出现频率高，就把它标记为 PASS 或 selected；SolverRegistry 仍是可执行性的唯一真源。",
            "禁止用一个通用 RMSE/准确率段落替代 family-specific validation。",
            "禁止为了显得模型丰富而增加没有真实实验与证据支持的对照模型。",
        ]
        return CProblemModelingPriorAssessment(
            source_registry=self.source_registry,
            prior_names=prior_names,
            research_obligations=list(dict.fromkeys(research)),
            validation_obligations=validation,
            forbidden_shortcuts=shortcuts,
            evidence_note=(
                f"Derived from {len(self.registry.corpora)} C-problem corpora / "
                f"{self.registry.total_reference_papers} excellent papers; advisory only."
            ),
        )


def _validation_obligations(task_family: str) -> list[str]:
    mapping: dict[str, list[str]] = {
        "forecasting": [
            "必须采用时间顺序验证，禁止随机切分造成未来信息泄漏。",
            "预测结论应在证据允许时报告误差与区间/不确定性，而不是只给点预测。",
        ],
        "distribution_forecasting": [
            "必须验证时间外推误差以及分布约束（如非负、总和/单纯形约束）。",
            "分布预测应给不确定性或稳定性证据。",
        ],
        "classification": [
            "必须检查类别层面的召回/平衡表现，并在有概率输出时检查概率质量。",
        ],
        "explanatory_inference": [
            "必须区分关联与因果，并给系数/效应稳定性或区间证据。",
        ],
        "exploratory_analysis": [
            "探索性发现必须做稳定性检查，不能把一次相关/聚类图直接升级为结论。",
        ],
        "ranking": [
            "综合评价/排序必须检查权重或指标扰动下的排名稳定性，并区分 MCDM 与信息检索 ranking。",
        ],
        "optimization": [
            "必须验证约束可行性、目标值与决策变量语义；有关键参数时检查敏感性/稳健性。",
        ],
        "simulation": [
            "必须报告重复仿真、随机种子/分布假设与结果不确定性。",
        ],
        "synthesis": [
            "所有建议、memo/letter/策略必须能回溯到已接受结果与限制。",
        ],
        "generic_modeling": [
            "在未知 family 下先完成题意分类与验证协议选择，不能直接落入通用监督学习。",
        ],
    }
    return list(mapping.get(task_family, []))
