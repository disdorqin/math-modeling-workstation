"""Tests for the unified time-series analysis module (task tc299a729)."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from mathworkstation.timeseries_analysis import (
    analyze_series,
    autocorrelation,
    change_points,
    decompose_trend,
    sliding_stats,
    stationarity,
    to_json_dict,
)

from test_auto_pipeline_e2e import DeterministicStructuredLLM


@pytest.fixture
def trending_series():
    """A clean upward-trending series with mild noise (non-stationary, trending)."""
    rng = np.random.default_rng(7)
    x = np.arange(80, dtype=float)
    y = 10.0 + 0.3 * x + rng.normal(0, 1.5, size=80)
    return pd.Series(y)


@pytest.fixture
def random_series():
    """A stationary white-noise series."""
    rng = np.random.default_rng(11)
    return pd.Series(rng.normal(0, 1.0, size=200))


def test_decompose_trend_shapes(trending_series):
    td = decompose_trend(trending_series, "trend", method="rolling", window=7)
    assert td.n_points == 80
    assert len(td.fitted_trend) == 80
    assert len(td.detrended) == 80
    assert td.series_name == "trend"
    # detrended should be much smaller than original spread
    original_std = float(np.std(trending_series))
    assert td.residual_std < original_std


def test_decompose_trend_poly_preserves_slope(trending_series):
    td = decompose_trend(trending_series, "t", method="poly", window=7)
    # slope ~ 0.3 -> fitted trend endpoints reflect it
    assert td.fitted_trend[-1] > td.fitted_trend[0]


def test_autocorrelation_white_noise(random_series):
    ac = autocorrelation(random_series, "wn", lags=10)
    assert ac.lb_lags == 10
    assert len(ac.acf) == 10
    # white noise: should NOT reject independence
    assert ac.has_serial_correlation is False


def test_autocorrelation_trend_has_serial_corr(trending_series):
    ac = autocorrelation(trending_series, "trend", lags=10)
    assert ac.has_serial_correlation is True


def test_stationarity_trending_series_has_unit_root(trending_series):
    st = stationarity(trending_series, "trend")
    assert st.is_stationary is False  # trending => ADF can't reject unit root


def test_stationarity_white_noise_is_stationary(random_series):
    st = stationarity(random_series, "wn")
    assert st.is_stationary is True


def test_change_points_runs(trending_series):
    cp = change_points(trending_series, "trend", window=5)
    assert isinstance(cp.change_points, list)
    assert cp.window == 5
    assert len(cp.segment_means) >= 1


def test_sliding_stats(trending_series):
    sw = sliding_stats(trending_series, "trend", window=7)
    assert sw.overall_mean > 0
    assert sw.max_value >= sw.min_value
    assert sw.trend_slope > 0  # upward series -> positive normalized slope


def test_analyze_series_composite(trending_series):
    report = analyze_series(trending_series, "synth", frequency="daily", lags=8, window=7)
    assert report.n_points == 80
    assert report.frequency == "daily"
    assert len(report.summary) > 0
    assert report.autocorrelation.has_serial_correlation is True
    assert report.stationarity.is_stationary is False


def test_to_json_dict_clean_types(trending_series):
    report = analyze_series(trending_series, "synth", lags=6, window=5)
    d = to_json_dict(report)
    import json
    roundtripped = json.loads(json.dumps(d))  # must serialize
    assert roundtripped["series_name"] == "synth"
    assert isinstance(roundtripped["autocorrelation"]["lb_pvalue"], float)
    assert isinstance(roundtripped["n_points"], int)


class TimeseriesAwareLLM(DeterministicStructuredLLM):
    """Deterministic proposer that reflects the injected timeseries report in
    the timeseries_analysis section draft (proves the injection plumbing)."""

    def markdown_call(
        self,
        case_id: str,
        session_id: str,
        node_id: str,
        _prompt_name: str,
        variables: dict[str, Any],
        _input_artifact_ids: list[str],
        **_kwargs: Any,
    ) -> tuple[str, dict[str, str]]:
        section_id = variables["section_id"]
        context = variables["context_json"]
        if section_id == "timeseries_analysis":
            injected = context.get("timeseries_analysis_data") or ""
            body = f"序列 {context.get('series_name', '')} 的时序诊断如下：\n\n{injected}"
        elif section_id == "momentum_analysis":
            body = "动量机制评估汇总：定义、假设检验与滑动窗口结论见本节。"
        else:
            return super().markdown_call(
                case_id, session_id, node_id, _prompt_name, variables, _input_artifact_ids, **_kwargs
            )
        content = f"## {context['title']}\n\n{body}"
        response = self._response(case_id, session_id, node_id, {"section_id": section_id})
        return content + "\n", response


def test_c_type_pipeline_lands_timeseries_section(tmp_path: Path) -> None:
    """C-type papers must contain a substantive 时序分析 section (te7b24ff3).

    Regression guard for the A-plan "落地 2023/2018 时序分析章节" task: the
    outline already adds timeseries_analysis for C-type problems, but the
    pipeline-level data injection (auto_pipeline._generate_sections) must reach
    the section draft and the assembled final.md — otherwise the section is a
    shell with no trend/ADF/Ljung-Box content.
    """
    from mathworkstation.auto_pipeline import AutoPipelineService
    from mathworkstation.case_manager import CaseManager
    from mathworkstation.datasets import DatasetKind
    from mathworkstation.refinement import RefinementConfig

    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "C 题 时序章节", problem_type="c", year=2023, version=1)
    service = AutoPipelineService(cases, None, coherence=False)  # type: ignore[arg-type]
    service.llm = TimeseriesAwareLLM(service)  # type: ignore[assignment]
    session = service.sessions.create_session(case["case_id"])

    problem = tmp_path / "problem.md"
    problem.write_text(
        "# C 题\n\n根据逐年观测数据建模并预测未来走势，比较候选方法并分析时序特征。\n",
        encoding="utf-8",
    )
    data = tmp_path / "series.csv"
    rows = list(range(40))
    pd.DataFrame(
        {
            "feature_a": [10.0 + 0.4 * r for r in rows],
            "feature_b": [5.0 + (r % 5) for r in rows],
            "target": [12.0 + 0.5 * r + (r % 3) for r in rows],
        }
    ).to_csv(data, index=False)

    result = service.run(
        case["case_id"],
        session["session_id"],
        problem,
        data,
        "逐年观测序列",
        "target",
        "e2e-human",
        "MCM-C",
        data_kind=DatasetKind.OBSERVED,
        source_uri="https://example.org/datasets/c-series",
        license_name="CC BY 4.0",
        data_description="固定 C 题时序验收数据",
        refinement_config=RefinementConfig(max_stages=1, min_stages=0, max_changed_ratio=0.5),
    )

    root = cases.case_root(case["case_id"])
    final_text = (root / "paper" / "final.md").read_text(encoding="utf-8")

    # outline carries the C-type section
    outline = json.loads((root / "paper" / "outline" / "auto-outline.json").read_text(encoding="utf-8"))
    assert any(s["section_id"] == "timeseries_analysis" for s in outline["sections"])

    # the assembled paper has a substantive 时序分析 section (trend / ADF /
    # Ljung-Box / stationarity markers come from the injected report)
    assert "## 时序分析" in final_text
    for marker in ("ADF", "Ljung-Box", "平稳性", "趋势"):
        assert marker in final_text, f"timeseries marker {marker!r} missing from final.md"

    # the raw report artifact is also written for the review trail
    assert (root / "analysis" / "timeseries_analysis.md").is_file()
    assert result.get("paper_artifact_id")
