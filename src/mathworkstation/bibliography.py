from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VerifiedReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    citation: str
    category: str = "method"
    supports: list[str] = Field(default_factory=list)
    available_year: int
    verification_url: str
    verification_note: str


# Minimal seed for methods already executed by the current Gold Solver set.
# These are bibliographic metadata records, not evidence of competition quality.
# Each entry was re-checked against an author/publisher page on 2026-08-19.
VERIFIED_METHOD_REFERENCES: tuple[VerifiedReference, ...] = (
    VerifiedReference(
        key="ljung_box_1978",
        citation=(
            "Ljung, G. M., & Box, G. E. P. (1978). On a Measure of Lack of Fit in Time Series Models. "
            "Biometrika, 65(2), 297–303. https://doi.org/10.1093/biomet/65.2.297."
        ),
        supports=["ljung", "ljung box", "residual persistence"],
        available_year=1978,
        verification_url="https://doi.org/10.1093/biomet/65.2.297",
        verification_note="Oxford Academic bibliographic metadata re-checked on 2026-08-23; used for the residual serial-dependence diagnostic actually executed in the momentum analysis",
    ),
    VerifiedReference(
        key="breiman_2001_random_forests",
        citation=(
            "Breiman, L. (2001). Random Forests. Machine Learning, 45(1), 5–32. "
            "https://doi.org/10.1023/A:1010933404324."
        ),
        supports=["random forest", "random forests", "nonlinear comparator"],
        available_year=2001,
        verification_url="https://doi.org/10.1023/A:1010933404324",
        verification_note="Springer bibliographic metadata re-checked on 2026-08-23; cited only for the Random Forest comparator actually executed under the same grouped validation protocol",
    ),
    VerifiedReference(
        key="brier_1950_probability_score",
        citation=(
            "Brier, G. W. (1950). Verification of Forecasts Expressed in Terms of Probability. "
            "Monthly Weather Review, 78(1), 1–3. https://doi.org/10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2."
        ),
        supports=["calibration", "brier", "probability verification"],
        available_year=1950,
        verification_url="https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2",
        verification_note="NOAA/AMS bibliographic DOI cross-checked via Springer reference metadata on 2026-08-23; used for the probabilistic calibration score reported by the executed hazard model",
    ),
    VerifiedReference(
        key="luettinger_clark_2005_pipeline_route",
        citation=(
            "Luettinger, J., & Clark, T. (2005). Geographic Information System-based Pipeline "
            "Route Selection Process. Journal of Water Resources Planning and Management, "
            "131(3), 193–200. https://doi.org/10.1061/(ASCE)0733-9496(2005)131:3(193)."
        ),
        category="domain",
        supports=["pipeline", "pipeline route", "route selection", "管线", "输油管", "路线", "布局"],
        available_year=2005,
        verification_url="https://doi.org/10.1061/(ASCE)0733-9496(2005)131:3(193)",
        verification_note="ASCE journal metadata verified on 2026-08-21; pre-2010 route-selection background, not evidence for contest-specific numerical results",
    ),
    VerifiedReference(
        key="yildirim_aydinoglu_yomralioglu_2007_pipeline_route",
        citation=(
            "Yildirim, V., Aydinoglu, A. C., & Yomralioglu, T. (2007). GIS Based Pipeline "
            "Route Selection by ArcGIS in Turkey. 27th Annual ESRI International User Conference."
        ),
        category="domain",
        supports=["pipeline", "pipeline route", "route selection", "管线", "输油管", "路线", "布局"],
        available_year=2007,
        verification_url="https://proceedings.esri.com/library/userconf/proc07/papers/abstracts/a2015.html",
        verification_note="ESRI conference proceedings metadata verified on 2026-08-21; pre-2010 pipeline-routing context only",
    ),
    VerifiedReference(
        key="byrd_lu_nocedal_zhu_1995",
        citation=(
            "Byrd, R. H., Lu, P., Nocedal, J., & Zhu, C. (1995). A Limited Memory Algorithm "
            "for Bound Constrained Optimization. SIAM Journal on Scientific Computing, "
            "16(5), 1190–1208. https://doi.org/10.1137/0916069."
        ),
        supports=["pipeline layout", "continuous optimization", "bound constrained", "lbfgsb", "l bfgs b"],
        available_year=1995,
        verification_url="https://doi.org/10.1137/0916069",
        verification_note="SIAM Journal on Scientific Computing article metadata; published in 1995 and available before the 2010 CUMCM contest",
    ),
    VerifiedReference(
        key="nocedal_wright_2006",
        citation=(
            "Nocedal, J., & Wright, S. J. (2006). Numerical Optimization (2nd ed.). "
            "Springer. https://doi.org/10.1007/978-0-387-40065-5."
        ),
        supports=["pipeline layout", "continuous optimization", "nonlinear optimization", "bound constrained"],
        available_year=2006,
        verification_url="https://doi.org/10.1007/978-0-387-40065-5",
        verification_note="Springer second-edition bibliographic record; published in 2006 and available before the 2010 CUMCM contest",
    ),
    VerifiedReference(
        key="bazaraa_sherali_shetty_2006",
        citation=(
            "Bazaraa, M. S., Sherali, H. D., & Shetty, C. M. (2006). Nonlinear Programming: "
            "Theory and Algorithms (3rd ed.). Wiley. https://doi.org/10.1002/0471787779."
        ),
        supports=["pipeline layout", "continuous optimization", "nonlinear programming", "nonlinear optimization"],
        available_year=2006,
        verification_url="https://doi.org/10.1002/0471787779",
        verification_note="Wiley third-edition bibliographic record; first published online in 2005 and available before the 2010 CUMCM contest",
    ),
    VerifiedReference(
        key="eia_seds_state_energy",
        citation=(
            "U.S. Energy Information Administration. State Energy Data System (SEDS): "
            "comprehensive state energy statistics and historical series."
        ),
        category="domain",
        supports=["energy", "state energy", "energy profile", "renewable energy", "energy compact"],
        available_year=2009,
        verification_url="https://www.eia.gov/state/seds/",
        verification_note="Official EIA SEDS landing page; the 2018 contest attachment is the historical through-2009 SEDS extract supplied with the problem.",
    ),
    VerifiedReference(
        key="lopez_nrel_2012",
        citation=(
            "Lopez, A., Roberts, B., Heimiller, D., Blair, N., & Porro, G. (2012). "
            "U.S. Renewable Energy Technical Potentials: A GIS-Based Analysis. "
            "NREL/TP-6A20-51946. National Renewable Energy Laboratory."
        ),
        category="domain",
        supports=["renewable energy", "energy compact", "energy profile"],
        available_year=2012,
        verification_url="https://www.nrel.gov/docs/fy12osti/51946.pdf",
        verification_note="Official NREL report metadata, also indexed in NREL's archived Annual Technology Baseline references.",
    ),
    VerifiedReference(
        key="holt_2004_reprint",
        citation=(
            "Holt, C. C. (2004). Forecasting seasonals and trends by exponentially weighted "
            "moving averages. International Journal of Forecasting, 20(1), 5–10. "
            "https://doi.org/10.1016/j.ijforecast.2003.09.015."
        ),
        supports=["holt", "exponential smoothing", "panel forecast", "panel trend"],
        available_year=2004,
        verification_url="https://doi.org/10.1016/j.ijforecast.2003.09.015",
        verification_note="Elsevier International Journal of Forecasting article page; reprint of Holt's 1957 ONR report",
    ),
    VerifiedReference(
        key="hwang_yoon_1981",
        citation=(
            "Hwang, C.-L., & Yoon, K. (1981). Multiple Attribute Decision Making: Methods "
            "and Applications—A State-of-the-Art Survey. Springer. "
            "https://doi.org/10.1007/978-3-642-48318-9."
        ),
        supports=["topsis", "multi criteria", "multi-criteria", "mcdm", "multiple attribute decision"],
        available_year=1981,
        verification_url="https://doi.org/10.1007/978-3-642-48318-9",
        verification_note="Springer bibliographic page for the 1981 Multiple Attribute Decision Making monograph",
    ),
    VerifiedReference(
        key="shannon_1948",
        citation=(
            "Shannon, C. E. (1948). A Mathematical Theory of Communication. "
            "The Bell System Technical Journal, 27(3), 379–423. "
            "https://doi.org/10.1002/j.1538-7305.1948.tb01338.x."
        ),
        supports=["entropy", "information entropy"],
        available_year=1948,
        verification_url="https://doi.org/10.1002/j.1538-7305.1948.tb01338.x",
        verification_note="Wiley / Bell System Technical Journal article metadata",
    ),
    VerifiedReference(
        key="dantzig_1963",
        citation=(
            "Dantzig, G. B. (1963). Linear Programming and Extensions. "
            "Princeton University Press."
        ),
        supports=["linear programming", "linear_programming", "simplex", "lp"],
        available_year=1963,
        verification_url="https://books.google.com/books/about/Linear_Programming_and_Extensions.html?id=c8YSAQAAMAAJ",
        verification_note="Princeton University Press bibliographic record surfaced through Google Books",
    ),
    VerifiedReference(
        key="seber_lee_2003",
        citation=(
            "Seber, G. A. F., & Lee, A. J. (2003). Linear Regression Analysis (2nd ed.). "
            "Wiley. https://doi.org/10.1002/9780471722199."
        ),
        supports=["linear trend", "panel linear trend", "linear regression", "least squares"],
        available_year=2003,
        verification_url="https://doi.org/10.1002/9780471722199",
        verification_note="Wiley book page and straight-line regression chapter metadata",
    ),
    VerifiedReference(
        key="hoerl_kennard_1970",
        citation=(
            "Hoerl, A. E., & Kennard, R. W. (1970). Ridge Regression: Biased Estimation "
            "for Nonorthogonal Problems. Technometrics, 12(1), 55–67. "
            "https://doi.org/10.1080/00401706.1970.10488634."
        ),
        supports=["ridge", "regularization", "linear regression"],
        available_year=1970,
        verification_url="https://www.tandfonline.com/doi/abs/10.1080/00401706.1970.10488634",
        verification_note="Taylor & Francis / Technometrics article page",
    ),
    VerifiedReference(
        key="hyndman_athanasopoulos_2021",
        citation=(
            "Hyndman, R. J., & Athanasopoulos, G. (2021). Forecasting: Principles and "
            "Practice (3rd ed.). OTexts, Melbourne."
        ),
        supports=["forecast", "forecasting", "time series", "temporal holdout", "exponential smoothing", "holt"],
        available_year=2021,
        verification_url="https://otexts.com/fpp3/",
        verification_note="Official author-hosted OTexts edition and citation metadata",
    ),
    VerifiedReference(
        key="efron_tibshirani_1993",
        citation=(
            "Efron, B., & Tibshirani, R. J. (1993). An Introduction to the Bootstrap. "
            "Chapman & Hall."
        ),
        supports=["bootstrap", "resampling", "confidence interval", "uncertainty"],
        available_year=1993,
        verification_url="https://doi.org/10.1201/9780429246593",
        verification_note="Publisher DOI metadata cross-checked through Springer bibliographic records",
    ),
    VerifiedReference(
        key="james_witten_hastie_tibshirani_2021",
        citation=(
            "James, G., Witten, D., Hastie, T., & Tibshirani, R. (2021). An Introduction "
            "to Statistical Learning: with Applications in R (2nd ed.). Springer. "
            "https://doi.org/10.1007/978-1-0716-1418-1."
        ),
        supports=["classification", "logistic", "statistical learning", "resampling", "clustering"],
        available_year=2021,
        verification_url="https://link.springer.com/book/10.1007/978-1-0716-1418-1",
        verification_note="Springer Nature bibliographic page",
    ),
    VerifiedReference(
        key="talluri_van_ryzin_2004_revenue_management",
        citation=(
            "Talluri, K. T., & van Ryzin, G. J. (2004). The Theory and Practice of Revenue "
            "Management. Springer. https://doi.org/10.1007/b139000."
        ),
        supports=[
            "retail category pricing replenishment",
            "retail item pricing replenishment",
            "demand aware pricing replenishment",
            "perishable retail pricing optimization",
            "dynamic pricing",
            "revenue management",
        ],
        available_year=2004,
        verification_url="https://doi.org/10.1007/b139000",
        verification_note="Springer bibliographic record verified on 2026-08-22; covers price-based revenue management, market-response models, estimation and forecasting, and is used only for method semantics",
    ),
    VerifiedReference(
        key="nahmias_1982_perishable_inventory",
        citation=(
            "Nahmias, S. (1982). Perishable Inventory Theory: A Review. Operations Research, "
            "30(4), 680–708. https://doi.org/10.1287/opre.30.4.680."
        ),
        supports=[
            "retail category pricing replenishment",
            "retail item pricing replenishment",
            "demand aware pricing replenishment",
            "perishable retail pricing optimization",
            "perishable inventory",
            "replenishment",
        ],
        available_year=1982,
        verification_url="https://doi.org/10.1287/opre.30.4.680",
        verification_note="INFORMS Operations Research article metadata verified on 2026-08-22; review of ordering policies for fixed-life and decaying perishable inventory",
    ),
    VerifiedReference(
        key="spearman_1904",
        citation=(
            "Spearman, C. (1904). The Proof and Measurement of Association between Two Things. "
            "The American Journal of Psychology, 15(1), 72–101. https://doi.org/10.2307/1412159."
        ),
        supports=["spearman", "rank correlation", "rank association"],
        available_year=1904,
        verification_url="https://doi.org/10.2307/1412159",
        verification_note="Original journal article bibliographic DOI metadata",
    ),
    VerifiedReference(
        key="liu_wordle_2022",
        citation=(
            "Liu, C.-L. (2022). Using Wordle for Learning to Design and Compare Strategies. "
            "arXiv:2205.11225."
        ),
        category="domain",
        supports=["wordle", "hard mode", "word game"],
        available_year=2022,
        verification_url="https://arxiv.org/abs/2205.11225",
        verification_note="Original author preprint on arXiv; available before the 2023 MCM contest",
    ),
    VerifiedReference(
        key="rosenbaum_wordle_2022",
        citation=(
            "Rosenbaum, W. (2022). Finding a Winning Strategy for Wordle is NP-complete. "
            "arXiv:2204.04104."
        ),
        category="domain",
        supports=["wordle", "word game"],
        available_year=2022,
        verification_url="https://arxiv.org/abs/2204.04104",
        verification_note="Original author preprint on arXiv; available before the 2023 MCM contest",
    ),
    VerifiedReference(
        key="bonthron_wordle_2022",
        citation=(
            "Bonthron, M. (2022). Rank One Approximation as a Strategy for Wordle. "
            "arXiv:2204.06324."
        ),
        category="domain",
        supports=["wordle", "word game"],
        available_year=2022,
        verification_url="https://arxiv.org/abs/2204.06324",
        verification_note="Original author preprint on arXiv; available before the 2023 MCM contest",
    ),
)


def bibliography_coverage(
    methods_by_subproblem: dict[str, str],
    references: list[VerifiedReference],
) -> dict[str, object]:
    method_refs = [item for item in references if item.category == "method"]
    coverage: dict[str, list[str]] = {}
    gaps: list[str] = []
    citation_optional_methods = {
        "panel profile summary",
        "group profile summary",
        "multi entity profile",
    }
    for subproblem_id, method in methods_by_subproblem.items():
        lowered = method.lower().replace("_", " ").replace("-", " ")
        matched = [
            item.key
            for item in method_refs
            if any(token.lower().replace("_", " ").replace("-", " ") in lowered for token in item.supports)
        ]
        coverage[subproblem_id] = matched
        citation_optional = any(value in lowered for value in citation_optional_methods)
        if not matched and not citation_optional:
            gaps.append(subproblem_id)
    return {
        "method_reference_keys": coverage,
        "method_gaps": gaps,
        "domain_reference_keys": [item.key for item in references if item.category == "domain"],
        "method_reference_count": len(method_refs),
        "domain_reference_count": sum(item.category == "domain" for item in references),
        "gate": "PASS" if not gaps else "REVIEW",
    }


def select_verified_references(
    methods: list[str],
    *,
    domain_text: str = "",
    cutoff_year: int | None = None,
) -> list[VerifiedReference]:
    method_text = " ".join(methods).lower().replace("_", " ").replace("-", " ")
    domain_value = domain_text.lower()
    selected = []
    for item in VERIFIED_METHOD_REFERENCES:
        if cutoff_year is not None and item.available_year > cutoff_year:
            continue
        target = method_text if item.category == "method" else domain_value
        if any(token.lower().replace("_", " ").replace("-", " ") in target for token in item.supports):
            selected.append(item)
    return selected
