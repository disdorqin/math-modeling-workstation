from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelNarrative:
    variables_zh: str
    construction_zh: str
    solution_zh: str
    motivation_zh: str = ""


def narrative_for_method(method: str, task_family: str) -> ModelNarrative:
    """Return evidence-safe model-construction prose for an actually executed method.

    The narrative explains the mathematical role of variables, model structure and
    solution procedure.  It never invents coefficients, hyperparameters or results;
    those remain sourced from the accepted solver result and equations registry.
    """

    value = method.lower().replace("-", "_").replace(" ", "_").replace(".", "_")
    if "retail_category_pricing_replenishment" in value:
        return ModelNarrative(
            variables_zh=(
                "设品类为 $c$、日期为 $t$；$p_{c,t}$ 与 $w_{c,t}$ 分别表示售价和批发成本，"
                "$m_{c,t}=p_{c,t}/w_{c,t}-1$ 为成本加成率，$\\lambda_c$ 为损耗率，"
                "$\\hat q_{c,t}$ 为预测销量，$Q_{c,t}$ 为补货量，$\\Pi_{c,t}$ 为预期收益。"
            ),
            construction_zh=(
                "先按品类建立销量需求响应模型，并从最简形式开始：第一层只用加价率解释销量；若时间留出误差有实质下降，再加入周周期、年周期和缓慢趋势；"
                "只有在此基础上二次加价项仍能带来足够的样本外改进时才继续升阶。各候选采用相同岭回归惩罚和时间顺序留出集，使复杂度增加必须由真实验证收益来证明。"
                "选定需求模型后，再把需求预测、损耗修正和成本加成定价统一写入收益函数。为避免无依据外推，加价率只在该品类历史实际支持区间内搜索。"
            ),
            solution_zh=(
                "先按“简约加价响应→时间校正线性响应→时间校正二次响应”的顺序比较时间留出误差，仅在更复杂候选达到规定相对改进幅度时升级，并在完整历史样本上重新估计入选模型。"
                "对未来每个品类—日期组合，在历史加价率区间上离散搜索：逐一计算需求预测、损耗修正补货量、售价与预期收益，取收益最大的候选作为当日决策；"
                "最后对批发成本进行扰动检验，考察策略对成本估计误差的敏感程度。"
            ),
            motivation_zh=(
                "问题1已经用于识别销量序列中的稳定关联、异常和阶段变化；问题2需要进一步把这些数据结构落实为经营决策。"
                "因此本问不把售价和补货量分开处理，而是先刻画价格加成与销量的预测关系，再把需求、损耗和采购成本统一到收益优化中。"
            ),
        )
    if "retail_item_pricing_replenishment" in value:
        return ModelNarrative(
            variables_zh=(
                "设候选单品为 $i$，其所属品类记为 $c(i)$；$x_i$ 表示是否选入经营组合，$\\bar q_i$ 为近期日均销量，"
                "$p_i,w_i,\\lambda_i$ 分别表示售价、批发成本和损耗率，$Q_i$ 为补货量，$\\hat q_i$ 为预计销量。"
            ),
            construction_zh=(
                "问题3不是重新独立预测需求，而是继承问题2得到的品类需求和最优加价率。首先在题目规定的近期真实可售集合中，"
                "依据近期销量与损耗修正后的单位毛利筛选候选单品；随后按近期销量份额将品类需求分配到入选单品，"
                "并同时施加单品数量、品类覆盖和最小陈列量约束。"
            ),
            solution_zh=(
                "先根据各品类需求规模与可售单品数量确定品类配额，再按经营价值指标排序选取单品；对入选单品计算需求份额、"
                "损耗修正补货量和售价，并逐项检查27—33个单品、每个单品不少于2.5 kg以及需求品类全覆盖等硬约束。"
            ),
            motivation_zh=(
                "问题2给出了品类层的需求预测和定价结果，但门店最终执行的是具体单品的采购与陈列。"
                "因此问题3将上游品类决策下沉到真实可售单品，在继承品类需求和加价率的同时加入单品数量、品类覆盖和最低陈列量约束。"
            ),
        )
    if "spearman_iqr_mean_shift_scan" in value:
        return ModelNarrative(
            variables_zh=(
                "以每日销量序列为研究对象，记任意两个序列为 $X$ 与 $Y$，用 $\\rho_s$ 表示 Spearman 秩相关系数；"
                "同时以四分位距和分段均值变化刻画异常波动与阶段性变化。"
            ),
            construction_zh=(
                "该小问首先回答数据中是否存在稳定的同步变化、异常点和阶段性结构，因此采用对分布形态要求较弱的秩相关与稳健统计量，"
                "避免把少数极端销量直接放大为线性相关。"
            ),
            solution_zh=(
                "计算各主要销量序列之间的秩相关强度，并结合四分位距异常扫描与均值变化检查识别重点关系；"
                "相关方向通过重抽样稳定性检验后才进入后续建模依据。"
            ),
            motivation_zh=(
                "后续定价与补货模型必须建立在对销量结构的可靠认识之上。"
                "因此问题1先回答“哪些品类和单品存在稳定同步变化、哪里出现异常或阶段变化”，再决定哪些结构值得进入后续决策模型。"
            ),
        )

    family = str(task_family or "")
    if family == "optimization":
        return ModelNarrative(
            variables_zh="决策变量、目标函数和约束均直接取自该小问实际登记的优化问题；未登记的变量不在论文中补造。",
            construction_zh="将题目目标转化为可计算目标函数，并把业务、几何或资源限制写成显式约束，再在可行域内求解。",
            solution_zh="按照实际求解器给出的可行方案求解，并通过约束可行性和关键参数扰动检查结果稳定性。",
        )
    if family == "forecasting":
        return ModelNarrative(
            variables_zh="以时间索引、目标序列和实际登记的解释变量构成预测变量体系，并保持训练—验证的时间顺序。",
            construction_zh="模型只使用预测时点能够获得的信息建立时间外推关系，避免随机切分造成未来信息泄漏。",
            solution_zh="在时间留出集上评估预测误差，并在证据允许时给出预测区间或残差稳定性结果。",
        )
    if family == "exploratory_analysis":
        return ModelNarrative(
            variables_zh="以实际登记的数据字段构成探索对象，所有统计量均可回溯到原始观测或其确定性变换。",
            construction_zh="先用稳健统计和关系度量识别数据结构，再把经稳定性检查的发现作为后续模型选择依据。",
            solution_zh="探索结果只用于描述和筛选，不把单次图形或相关系数直接升级为因果结论。",
        )
    return ModelNarrative(
        variables_zh="变量、参数和状态均沿用该小问实际求解计划中的定义。",
        construction_zh="模型结构由题意、数据和约束共同决定，不为了增加复杂度而引入与求解过程无关的模块。",
        solution_zh="按照已登记的求解与验证协议获得结果，并仅报告可以由证据链回溯的结论。",
    )
