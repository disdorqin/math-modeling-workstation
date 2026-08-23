from __future__ import annotations

from typing import Any

from .paper_contracts import SubproblemContract
from .problem_graph import DependencyEdge, ProblemGraph


CUMCM_2010_C_REFERENCE = {
    "a_km": 5.0,
    "b_km": 8.0,
    "boundary_x_km": 15.0,
    "factory_b_x_km": 20.0,
    "pipeline_unit_cost_q2": 7.2,
    "consulting_estimates": [21.0, 24.0, 20.0],
    "consulting_weights": [0.5, 0.25, 0.25],
    "a_unit_cost_q3": 5.6,
    "b_unit_cost_q3": 6.0,
    "shared_unit_cost_q3": 7.2,
}


def cumcm_2010_c_contracts() -> list[SubproblemContract]:
    return [
        SubproblemContract(
            subproblem_id="SP1",
            title="建立输油管通用几何费用模型",
            objective="针对有无共用管线、单位费用相同或不同等情形，建立可参数化的总费用最小布局模型",
            inputs=["两炼油厂到铁路线距离", "两厂相对位置", "各类管线单位费用"],
            outputs=["通用坐标模型", "有/无共用管线的方案比较规则"],
            constraints=["铁路线视为直线", "管线沿设计直线段铺设", "费用按线长和区域费用计算"],
            evaluation_metrics=["constraint feasibility", "objective value"],
        ),
        SubproblemContract(
            subproblem_id="SP2",
            title="考虑城区附加费用的具体最优布局",
            objective="在 a=5、b=8、城郊分界 x=15、两厂水平间距20千米及城区附加费用下求总费用最小的交接点和车站位置",
            inputs=["SP1通用几何模型", "三家咨询公司附加费估计", "统一管线费用7.2万元/千米"],
            outputs=["最小总费用", "E/F/G点坐标", "分段管线长度"],
            constraints=["E 位于郊区矩形内", "F 位于城郊分界线上", "G 位于铁路线"],
            evaluation_metrics=["objective value", "surcharge sensitivity"],
        ),
        SubproblemContract(
            subproblem_id="SP3",
            title="不同管线单价下的最优布局与无共用方案比较",
            objective="在A厂5.6、B厂6.0、共用管线7.2万元/千米的条件下重新优化，并比较取消短共用管线的长期方案",
            inputs=["SP2几何布局", "A/B/共用管线差异化单价", "城区附加费用"],
            outputs=["最小总费用", "E/F/G点坐标", "有/无共用管线成本差"],
            constraints=["保持题面几何边界", "无共用方案令EG=0"],
            evaluation_metrics=["objective value", "scenario comparison", "surcharge sensitivity"],
        ),
    ]


def weighted_urban_surcharge() -> float:
    estimates = CUMCM_2010_C_REFERENCE["consulting_estimates"]
    weights = CUMCM_2010_C_REFERENCE["consulting_weights"]
    return float(sum(float(value) * float(weight) for value, weight in zip(estimates, weights)))


def prepare_cumcm_2010_c_plans() -> dict[str, dict[str, Any]]:
    common = {
        "solver_method": "pipeline_layout_continuous",
        "factory_a_height": CUMCM_2010_C_REFERENCE["a_km"],
        "factory_b_height": CUMCM_2010_C_REFERENCE["b_km"],
        "factory_b_x": CUMCM_2010_C_REFERENCE["factory_b_x_km"],
        "urban_boundary_x": CUMCM_2010_C_REFERENCE["boundary_x_km"],
    }
    return {
        "SP1": {
            **common,
            "a_nonshared_cost": 1.0,
            "b_nonshared_cost": 1.0,
            "shared_cost": 1.0,
            "urban_surcharge": 0.0,
            "purpose": "parameterized geometry sanity execution for the general model; coefficients are symbolic in the paper equation schema",
        },
        "SP2": {
            **common,
            "a_nonshared_cost": CUMCM_2010_C_REFERENCE["pipeline_unit_cost_q2"],
            "b_nonshared_cost": CUMCM_2010_C_REFERENCE["pipeline_unit_cost_q2"],
            "shared_cost": CUMCM_2010_C_REFERENCE["pipeline_unit_cost_q2"],
            "urban_surcharge": weighted_urban_surcharge(),
        },
        "SP3": {
            **common,
            "a_nonshared_cost": CUMCM_2010_C_REFERENCE["a_unit_cost_q3"],
            "b_nonshared_cost": CUMCM_2010_C_REFERENCE["b_unit_cost_q3"],
            "shared_cost": CUMCM_2010_C_REFERENCE["shared_unit_cost_q3"],
            "urban_surcharge": weighted_urban_surcharge(),
            "compare_no_shared": True,
        },
    }


def link_cumcm_2010_c_dependencies(graph: ProblemGraph) -> ProblemGraph:
    """Register the real multi-stage dependency chain SP1 -> SP2 -> SP3."""

    for node in graph.nodes:
        node.plan.candidate_methods = ["pipeline layout continuous optimization"]
        if node.experiments:
            node.experiments[0].method = "pipeline layout continuous optimization"
    graph.node("SP2").dependencies = ["SP1"]
    graph.node("SP3").dependencies = ["SP2"]
    graph.edges = [
        DependencyEdge(
            source_subproblem_id="SP1",
            target_subproblem_id="SP2",
            relation="DEPENDS_ON",
            rationale="问题2在问题1通用几何费用模型上加入具体城乡费用与位置参数。",
        ),
        DependencyEdge(
            source_subproblem_id="SP2",
            target_subproblem_id="SP3",
            relation="DEPENDS_ON",
            rationale="问题3保持问题2几何结构，仅细化不同管线单价并增加长期方案比较。",
        ),
    ]
    return graph


def answer_texts() -> dict[str, tuple[str, str]]:
    return {
        "SP1": (
            "以铁路线为 x 轴，令 A=(0,a)、B=(d,b)、城郊分界 x=c、共享交接点 E=(x,y)、边界交点 F=(c,z)、车站 G=(x,0)。总费用由 A-E、E-F、E-G、F-B 四段按各自单位费用加权；无共用管线是 y=0 的边界情形。实际方案应在费用参数与几何边界下分别求解并比较，而不是固定使用某一个图形模板。",
            "问题1给出的是参数化设计规则；具体最优坐标依赖 a、b、d、c 以及各类管线单位费用。",
        ),
        "SP2": (
            "三家咨询公司的资质权重取 0.5、0.25、0.25 时，城区附加费为21.5万元/千米。连续几何优化得到总费用约282.6973万元，E≈(5.449,1.854)，F≈(15,7.368)，车站G≈(5.449,0)。",
            "附加费用的咨询权重具有主观性，因此结论同时报告±10%城区附加费扰动下的敏感性。",
        ),
        "SP3": (
            "采用A厂5.6、B厂6.0、共用管线7.2万元/千米重新优化，最小总费用约251.9685万元，E≈(6.734,0.139)，F≈(15,7.279)，G≈(6.734,0)。强制取消共用段后最优费用约251.9755万元，仅高约0.007万元，因此短共用段的长期工程取舍应结合混油等题面外工程代价另行判断。",
            "数值模型只计入题面铺设费和城区附加费；混油、安全和运维代价没有可量化数据，不能被伪造成成本项。",
        ),
    }
