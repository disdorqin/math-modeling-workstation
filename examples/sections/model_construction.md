# 模型建立

## 基本框架

设第 $i$ 例患者的标准化基线特征为 $\tilde{\mathbf{x}}_i$，一年后的病情进展指数为 $y_i$。本文以线性主效应模型为基本框架：

$$\hat{y}_i = \beta_0 + \tilde{\mathbf{x}}_i^{\top}\boldsymbol{\beta}$$

标准化是必要的前置步骤：血清学指标与体格指标的量纲相差数量级，若不消除尺度差异，正则化惩罚会不成比例地压缩数值较大的特征。

## 目标函数

由于数据分析已诊断出结构性多重共线性，普通最小二乘的损失函数

$$\mathcal{L}_{\text{OLS}}(\boldsymbol{\beta}) = \sum_{i} \left(y_i - \beta_0 - \tilde{\mathbf{x}}_i^{\top}\boldsymbol{\beta}\right)^{2}$$

在设计矩阵接近奇异时解不稳定。为此引入带惩罚项的目标函数，构成本文的候选模型族：

$$\mathcal{L}_{\text{Ridge}}(\boldsymbol{\beta}) = \frac{1}{2n}\sum_{i}\left(y_i - \beta_0 - \tilde{\mathbf{x}}_i^{\top}\boldsymbol{\beta}\right)^{2} + \alpha\lVert\boldsymbol{\beta}\rVert_{2}^{2}$$

$$\mathcal{L}_{\text{Lasso}}(\boldsymbol{\beta}) = \frac{1}{2n}\sum_{i}\left(y_i - \beta_0 - \tilde{\mathbf{x}}_i^{\top}\boldsymbol{\beta}\right)^{2} + \alpha\lVert\boldsymbol{\beta}\rVert_{1}$$

$L_2$ 惩罚沿共线性方向收缩系数、降低估计方差；$L_1$ 惩罚在共线特征组内只保留代表性特征、将其余系数精确置零，因而同时承担特征筛选职能，直接服务于子问题一。

## 非线性对照

为检验"线性主效应足够"这一假设是否成立，本文引入两类基于决策树的集成模型作为对照：随机森林通过对样本与特征的双重随机化降低方差，梯度提升通过逐轮拟合残差降低偏差。二者都能自动捕捉交互作用与非线性关系，其形式可统一写为

$$\hat{y}_i = \sum_{m} \gamma_m h_m(\mathbf{x}_i)$$

其中 $h_m$ 为基学习器。若集成模型显著优于线性模型，则说明存在被线性形式忽略的结构；若不优于，则线性假设得到实证支持。这一对照设计使假设四成为可检验命题，而非无根据的断言。

## 评价与选择准则

所有候选模型在同一份数据、同一套折划分下评估，以均方根误差为主指标，平均绝对误差与决定系数为辅助指标。选择准则为：主指标的折间均值最优者胜出；若均值接近，则取折间标准差更小者，即偏好在不同数据划分下更稳定的模型。
