from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .paper_contracts import SubproblemContract
from .problem_graph import DependencyEdge, ProblemGraph


CUMCM_2023_C_DATA_DIR = Path(
    r"D:\作业\竞赛\大学生数学建模\美赛\备赛\资料\论文\高教社论文"
    r"\I953高教社杯全国大学生数学建模竞赛题目及优秀论文"
    r"\高教社杯全国大学生数学建模竞赛往届题目"
    r"\2023高教社杯全国大学生数学建模竞赛题目\C题"
)


def cumcm_2023_c_contracts() -> list[SubproblemContract]:
    return [
        SubproblemContract(
            subproblem_id="SP1",
            title="蔬菜品类与单品销售分布及关联规律探索",
            objective="基于三年销售流水探索六个蔬菜品类及主要单品日销量的分布、异常、相互关联与阶段变化，为后续需求和经营决策提供数据结构证据",
            inputs=["附件1商品分类信息", "附件2销售流水"],
            outputs=["品类与主要单品日销量画像", "主要 Spearman 关联", "异常率与均值变化候选"],
            constraints=["关联结构只作描述性证据，不解释为因果效应", "不使用2023年6月30日之后的信息"],
            evaluation_metrics=["association strength", "outlier rate", "mean-shift magnitude"],
        ),
        SubproblemContract(
            subproblem_id="SP2",
            title="品类级需求响应、自动定价与未来一周补货优化",
            objective="分析各蔬菜品类销售总量与成本加成定价的关系，并对2023年7月1日至7日联合给出定价与补货策略，使登记模型下的预期收益最大",
            inputs=["SP1销售结构", "附件2品类日销量与售价", "附件3批发价格", "附件4损耗率"],
            outputs=["价格—需求关联与时间留出误差", "未来7日各品类需求", "补货量、售价与预期收益"],
            constraints=["价格搜索不超出历史加价率支持区间", "补货量显式计入损耗率", "需求价格关系只作关联预测而非因果弹性"],
            evaluation_metrics=["temporal demand RMSE", "expected profit", "wholesale-cost sensitivity"],
        ),
        SubproblemContract(
            subproblem_id="SP3",
            title="单品级可售组合、补货量与定价策略优化",
            objective="在2023年6月24日至30日真实可售单品中确定7月1日单品组合、补货量和售价，在尽量满足各品类需求的前提下提高预期收益",
            inputs=["SP2的7月1日品类需求与加价策略", "附件2近期单品销量", "附件3近期批发价", "附件4单品损耗率"],
            outputs=["7月1日可售单品组合", "逐单品补货量与售价", "约束审计与预期收益"],
            constraints=["可售单品总数27-33", "每个入选单品订购量不少于2.5千克", "只从6月24-30日实际销售过的单品选择", "正需求品类至少有一个单品覆盖"],
            evaluation_metrics=["selected item count", "minimum replenishment", "category coverage", "expected profit"],
        ),
        SubproblemContract(
            subproblem_id="SP4",
            title="经营数据补充建议与采集方案报告撰写",
            objective="综合前三问中暴露的数据不确定性和决策边界，提出后续应采集的数据、用途与理由，不新增未经观测支持的定量结论",
            inputs=["SP1关联与分布发现", "SP2品类需求/定价模型局限", "SP3单品选择与损耗约束"],
            outputs=["数据采集建议报告", "每类新增数据对应的模型改进用途"],
            constraints=["建议必须针对前三问实际证据缺口", "交付物不作为新的预测或优化模型"],
            evaluation_metrics=["evidence coverage", "decision relevance"],
        ),
    ]


def link_cumcm_2023_c_dependencies(graph: ProblemGraph) -> ProblemGraph:
    sp1 = graph.node("SP1")
    sp1.task_family = "exploratory_analysis"
    sp1.execution_kind = "ANALYSIS"
    sp1.plan.task_family = "exploratory_analysis"
    sp1.plan.execution_kind = "ANALYSIS"
    sp1.plan.candidate_methods = ["Spearman association + IQR outlier + mean-shift scan"]
    sp1.plan.validation_protocol = ["exploratory discovery + pattern audit"]
    sp1.plan.executor_family = "exploratory_analysis"
    sp1.plan.executor_available = True
    sp1.plan.executor_blocker = None
    if sp1.experiments:
        sp1.experiments[0].method = sp1.plan.candidate_methods[0]
        sp1.experiments[0].validation_protocol = list(sp1.plan.validation_protocol)

    for subproblem_id, method in (
        ("SP2", "retail category pricing replenishment"),
        ("SP3", "retail item pricing replenishment"),
    ):
        node = graph.node(subproblem_id)
        node.task_family = "optimization"
        node.execution_kind = "MODEL"
        node.plan.task_family = "optimization"
        node.plan.execution_kind = "MODEL"
        node.plan.candidate_methods = [method]
        node.plan.validation_protocol = ["feasibility + temporal demand validation + scenario sensitivity"]
        node.plan.requires_model_execution = True
        node.plan.executor_family = "optimization"
        node.plan.executor_available = True
        node.plan.executor_blocker = None
        if node.experiments:
            node.experiments[0].method = method
            node.experiments[0].validation_protocol = list(node.plan.validation_protocol)

    sp4 = graph.node("SP4")
    sp4.task_family = "synthesis"
    sp4.execution_kind = "DELIVERABLE"
    sp4.plan.task_family = "synthesis"
    sp4.plan.execution_kind = "DELIVERABLE"
    sp4.plan.candidate_methods = ["evidence synthesis from accepted subproblem answers"]
    sp4.plan.validation_protocol = ["dependency evidence coverage"]
    sp4.plan.requires_model_execution = False
    sp4.plan.executor_family = None
    sp4.plan.executor_available = False
    sp4.plan.executor_blocker = None
    sp4.experiments = []

    sp1.dependencies = []
    graph.node("SP2").dependencies = ["SP1"]
    graph.node("SP3").dependencies = ["SP2"]
    sp4.dependencies = ["SP1", "SP2", "SP3"]
    graph.edges = [
        DependencyEdge(
            source_subproblem_id="SP1",
            target_subproblem_id="SP2",
            relation="DEPENDS_ON",
            rationale="品类级需求和定价建模以前一问识别的销售结构与时间变化为数据诊断依据。",
        ),
        DependencyEdge(
            source_subproblem_id="SP2",
            target_subproblem_id="SP3",
            relation="DEPENDS_ON",
            rationale="单品层决策继承问题2对7月1日各品类需求及加价率的预测结果。",
        ),
        *[
            DependencyEdge(
                source_subproblem_id=source,
                target_subproblem_id="SP4",
                relation="SYNTHESIZES",
                rationale="数据采集建议只针对前三问真实研究证据暴露的限制与不确定性。",
            )
            for source in ("SP1", "SP2", "SP3")
        ],
    ]
    return graph


def load_cumcm_2023_c_frames(data_dir: str | Path = CUMCM_2023_C_DATA_DIR) -> dict[str, pd.DataFrame]:
    root = Path(data_dir)
    required = [root / f"附件{index}.xlsx" for index in range(1, 5)]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("CUMCM_2023_C_ATTACHMENTS_MISSING:" + ";".join(missing))

    info = pd.read_excel(required[0], dtype={"单品编码": str, "分类编码": str})
    sales = pd.read_excel(required[1], usecols=["销售日期", "单品编码", "销量(千克)", "销售单价(元/千克)", "销售类型"], dtype={"单品编码": str})
    wholesale = pd.read_excel(required[2], dtype={"单品编码": str})
    loss = pd.read_excel(required[3], sheet_name="Sheet1", dtype={"单品编码": str})

    info["单品编码"] = info["单品编码"].map(_code)
    sales["单品编码"] = sales["单品编码"].map(_code)
    wholesale["单品编码"] = wholesale["单品编码"].map(_code)
    loss["单品编码"] = loss["单品编码"].map(_code)
    sales["销售日期"] = pd.to_datetime(sales["销售日期"], errors="raise").dt.normalize()
    wholesale["日期"] = pd.to_datetime(wholesale["日期"], errors="raise").dt.normalize()
    sales["销量(千克)"] = pd.to_numeric(sales["销量(千克)"], errors="coerce")
    sales["销售单价(元/千克)"] = pd.to_numeric(sales["销售单价(元/千克)"], errors="coerce")
    wholesale["批发价格(元/千克)"] = pd.to_numeric(wholesale["批发价格(元/千克)"], errors="coerce")
    loss["损耗率(%)"] = pd.to_numeric(loss["损耗率(%)"], errors="coerce")
    sales = sales[
        sales["销售类型"].astype(str).str.contains("销售", na=False)
        & (sales["销量(千克)"] > 0)
        & (sales["销售单价(元/千克)"] > 0)
    ].copy()
    sales = sales.merge(info[["单品编码", "单品名称", "分类编码", "分类名称"]], on="单品编码", how="inner")

    # Question 1 uses observed sales irrespective of whether a same-day wholesale
    # quote is available.  Keep six category series plus the 12 highest-volume
    # individual items so the exploratory solver sees both scales without a
    # 251-column correlation explosion.
    category_qty = sales.pivot_table(index="销售日期", columns="分类名称", values="销量(千克)", aggfunc="sum", fill_value=0.0)
    category_qty.columns = [f"品类::{value}" for value in category_qty.columns]
    top_items = (
        sales.groupby(["单品编码", "单品名称"], as_index=False)["销量(千克)"].sum()
        .sort_values("销量(千克)", ascending=False)
        .head(12)
    )
    top_codes = set(top_items["单品编码"].astype(str))
    item_qty = (
        sales[sales["单品编码"].isin(top_codes)]
        .pivot_table(index="销售日期", columns="单品名称", values="销量(千克)", aggfunc="sum", fill_value=0.0)
    )
    item_qty.columns = [f"单品::{value}" for value in item_qty.columns]
    q1 = category_qty.join(item_qty, how="outer").fillna(0.0).sort_index().reset_index().rename(columns={"销售日期": "date"})

    # Pricing/replenishment needs same-day wholesale cost.  Drop only transaction
    # rows for which no registered cost quote exists instead of fabricating a cost.
    priced = sales.merge(
        wholesale.rename(columns={"日期": "销售日期"}),
        on=["销售日期", "单品编码"],
        how="inner",
    ).merge(loss[["单品编码", "损耗率(%)"]], on="单品编码", how="left")
    priced["损耗率(%)"] = priced["损耗率(%)"].fillna(priced.groupby("分类名称")["损耗率(%)"].transform("median"))
    priced["损耗率(%)"] = priced["损耗率(%)"].fillna(priced["损耗率(%)"].median())

    item_daily = _daily_panel(
        priced,
        group_columns=["销售日期", "单品编码", "单品名称", "分类名称"],
    ).rename(
        columns={
            "销售日期": "date",
            "单品编码": "item_code",
            "单品名称": "item_name",
            "分类名称": "category",
            "销量(千克)": "quantity",
            "销售单价(元/千克)": "sale_price",
            "批发价格(元/千克)": "wholesale_cost",
            "损耗率(%)": "loss_rate",
        }
    )
    category_daily = _daily_panel(
        priced,
        group_columns=["销售日期", "分类名称"],
    ).rename(
        columns={
            "销售日期": "date",
            "分类名称": "category",
            "销量(千克)": "quantity",
            "销售单价(元/千克)": "sale_price",
            "批发价格(元/千克)": "wholesale_cost",
            "损耗率(%)": "loss_rate",
        }
    )
    return {
        "q1": q1,
        "category_daily": category_daily,
        "item_daily": item_daily,
        "metadata": info,
    }


def prepare_cumcm_2023_c_plans(frames: dict[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    q1_columns = [column for column in frames["q1"].columns if column != "date"]
    common = {
        "date_column": "date",
        "quantity_column": "quantity",
        "sale_price_column": "sale_price",
        "wholesale_cost_column": "wholesale_cost",
        "loss_rate_column": "loss_rate",
    }
    return {
        "SP1": {
            "solver_method": "default",
            "numeric_columns": q1_columns,
        },
        "SP2": {
            "solver_method": "retail_category_pricing_replenishment",
            "mode": "category",
            "entity_column": "category",
            **common,
            "future_dates": [f"2023-07-{day:02d}" for day in range(1, 8)],
            "test_size": 0.2,
            "minimum_demand_rows": 90,
            "markup_grid_points": 21,
            "recent_cost_days": 14,
            "demand_ridge_alpha": 1.0,
        },
    }


def q2_targets_for_july1(result: dict[str, Any]) -> dict[str, dict[str, float]]:
    targets: dict[str, dict[str, float]] = {}
    for row in result.get("strategy", []):
        if str(row.get("date")) != "2023-07-01":
            continue
        targets[str(row["entity"])] = {
            "demand_forecast": float(row["demand_forecast"]),
            "markup_rate": float(row["markup_rate"]),
        }
    if not targets:
        raise ValueError("CUMCM_2023_Q2_JULY1_TARGETS_MISSING")
    return targets


def prepare_q3_plan(q2_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "solver_method": "retail_item_pricing_replenishment",
        "mode": "item",
        "date_column": "date",
        "entity_column": "item_code",
        "category_column": "category",
        "quantity_column": "quantity",
        "sale_price_column": "sale_price",
        "wholesale_cost_column": "wholesale_cost",
        "loss_rate_column": "loss_rate",
        "future_date": "2023-07-01",
        "category_targets": q2_targets_for_july1(q2_result),
        "availability_days": 7,
        "selection_count": 30,
        "min_items": 27,
        "max_items": 33,
        "minimum_order": 2.5,
    }


def q1_answer(result: dict[str, Any]) -> tuple[str, str]:
    discoveries = result.get("discoveries", {})
    pairs = list(discoveries.get("strongest_associations") or [])
    shifts = list(discoveries.get("largest_mean_shift_candidates") or [])
    strongest = pairs[0] if pairs else None
    shift = shifts[0] if shifts else None
    pieces = ["将6个品类与总销量最高的12个单品统一到日尺度后进行分布与关联探索。"]
    if strongest:
        pieces.append(
            f"最强 Spearman 关联出现在{strongest['left']}与{strongest['right']}之间，r={float(strongest['spearman_r']):.3f}。"
        )
    if shift:
        pieces.append(
            f"均值变化扫描中，{shift['column']}的标准化变化幅度最高，为{float(shift['standardized_mean_shift']):.3f}。"
        )
    return (
        "".join(pieces),
        "相关、异常与变化点结果是描述性/假设生成证据；它们不能单独证明价格、品类或单品之间存在因果作用。",
    )


def q2_answer(result: dict[str, Any]) -> tuple[str, str]:
    strategy = list(result.get("strategy") or [])
    profit = float(result.get("objective_value", 0.0))
    relationships = list(result.get("price_demand_relationship") or [])
    mean_rmse = float(result.get("metrics", {}).get("demand_validation_rmse_mean", np.nan))
    return (
        f"在逐品类时间留出验证后，仅在历史加价率支持范围内搜索定价。2023年7月1-7日共形成{len(strategy)}条品类-日期策略，登记模型下7日预期总收益约{profit:.2f}元；品类需求模型平均时间留出RMSE为{mean_rmse:.3f}千克。",
        f"价格—需求系数只解释为关联预测，不能作因果弹性；未来批发价以最近14日观测成本估计，并用±10%批发成本情景检验。有效品类关系数={len(relationships)}。",
    )


def q3_answer(result: dict[str, Any]) -> tuple[str, str]:
    count = int(result.get("selected_item_count", 0))
    minimum = float(result.get("metrics", {}).get("minimum_order_quantity", 0.0))
    profit = float(result.get("objective_value", 0.0))
    return (
        f"7月1日方案从6月24-30日实际可售集合中选择{count}个单品，各入选单品补货量均不低于{minimum:.2f}千克，并覆盖问题2中具有正需求的全部品类；登记策略下预期收益约{profit:.2f}元。",
        "单品选择采用近期销量与损耗后单位毛利形成的可解释筛选分数，价格继承品类层最优加价率；这是受约束经营基线，不宣称穷举得到全局最优单品组合。",
    )


def q4_answer() -> str:
    return (
        "建议优先补充六类数据：①实时库存、到货量与缺货时刻，用于区分真实需求与缺货截断销量；"
        "②逐批次进货报价、供应商可供量与交货可靠性，用于替代未来批发成本的简单历史估计；"
        "③温度、湿度、天气与节假日/客流，用于提高短期需求预测；"
        "④促销、陈列位置和折扣执行记录，用于分离价格与促销混杂；"
        "⑤逐日/逐批次鲜度、报损与临期折价数据，用于建立动态损耗模型；"
        "⑥竞争门店价格与替代品价格，用于识别跨品类替代和更可靠的价格响应。"
        "这些数据分别对应前三问中缺货不可见、成本未知、外生需求变化、价格混杂、损耗静态化和替代效应缺失等实际证据边界。"
    )


def _daily_panel(frame: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    quantity = "销量(千克)"
    sale_price = "销售单价(元/千克)"
    cost = "批发价格(元/千克)"
    loss = "损耗率(%)"
    values = frame[group_columns + [quantity, sale_price, cost, loss]].copy()
    values["__sale_value"] = values[quantity] * values[sale_price]
    values["__cost_value"] = values[quantity] * values[cost]
    grouped = values.groupby(group_columns, as_index=False).agg(
        **{
            quantity: (quantity, "sum"),
            "__sale_value": ("__sale_value", "sum"),
            "__cost_value": ("__cost_value", "sum"),
            loss: (loss, "median"),
        }
    )
    denominator = grouped[quantity].replace(0.0, np.nan)
    grouped[sale_price] = grouped["__sale_value"] / denominator
    grouped[cost] = grouped["__cost_value"] / denominator
    return grouped.drop(columns=["__sale_value", "__cost_value"]).dropna(subset=[sale_price, cost])


def _code(value: Any) -> str:
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text
