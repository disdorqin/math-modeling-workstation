"""Run the unified time-series analysis on the 2023 (Wordle daily) and 2018
(Texas energy yearly) cases for task tc299a729.

Usage:
    python -m scripts.run_timeseries_analysis <output_root>

It writes one JSON report + one summary markdown per series under
<output_root>/analysis/timeseries/, and prints a compact console summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from mathworkstation import timeseries_analysis as ts

CASES = {
    "2023": {
        "root": "output/mcm-c-2023/v3/20260805-MCM-0001-EUP7",
        "data": "input/data/uploaded/_wordle_data_clean.csv",
        "frequency": "daily",
        "series": [
            ("Number of reported results", "daily_reported_results", 10, 7),
            ("Number in hard mode", "daily_hard_mode", 10, 7),
        ],
    },
    "2018": {
        "root": "output/mcm-c-2018/v2/20260805-MCM-0001-4DH5",
        "data": "input/data/uploaded/_energy2018_tx.csv",
        "frequency": "yearly",
        "series": [
            ("total_production", "yearly_total_production", 10, 5),
            ("total_consumption", "yearly_total_consumption", 10, 5),
            ("renewable_production", "yearly_renewable_production", 8, 5),
            ("consumption_per_capita", "yearly_consumption_per_capita", 8, 5),
        ],
    },
}


def _load_data(root: Path, data: str, frequency: str) -> pd.DataFrame:
    path = root / data
    if not path.exists():
        raise FileNotFoundError(f"data not found: {path}")
    df = pd.read_csv(path)
    # Normalize accidental double/multiple spaces in column headers (the 2023
    # file uses "Number of  reported results" with two spaces).
    df.columns = [str(c).replace("  ", " ").strip() for c in df.columns]
    if frequency == "daily":
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("Date").reset_index(drop=True)
    else:
        df = df.sort_values("Year").reset_index(drop=True)
    return df


def main() -> int:
    base = Path.cwd()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        plt = None
    out = base / "output" / "tasks" / "tc299a729"
    figs_dir = out / "figures"
    figs_dir.mkdir(parents=True, exist_ok=True)
    fig_paths: list[str] = []
    all_reports: dict[str, dict] = {}
    for case, cfg in CASES.items():
        root = base / cfg["root"]
        df = _load_data(root, cfg["data"], cfg["frequency"])
        xcol = "Date" if cfg["frequency"] == "daily" else "Year"
        for col, key, lags, window in cfg["series"]:
            if col not in df.columns:
                print(f"[{case}] skip missing column {col}")
                continue
            series = df[col].astype(float)
            report = ts.analyze_series(
                series, col, frequency=cfg["frequency"], lags=lags, window=window
            )
            d = ts.to_json_dict(report)
            all_reports[f"{case}::{key}"] = d
            print(f"[{case}] {report.summary}")
            # figure: series + rolling trend + change-point markers
            if plt is not None:
                fig, ax = plt.subplots(figsize=(9, 4.5))
                x = df[xcol] if xcol == "Date" else df[xcol].astype(int)
                ax.plot(x, series.to_numpy(), color="#1f77b4", label="observed", lw=1.4)
                ax.plot(
                    x,
                    report.trend.fitted_trend,
                    color="#d62728",
                    lw=2.0,
                    label="rolling trend",
                )
                cps = report.change_points.change_points
                if cps:
                    ids = cps
                    ax.scatter(
                        [x.iloc[i] for i in ids],
                        [series.iloc[i] for i in ids],
                        marker="o",
                        s=60,
                        facecolors="none",
                        edgecolors="green",
                        label="breakpoints",
                    )
                ax.set_title(f"{case} - {col} ({cfg['frequency']})")
                ax.legend(loc="best", fontsize=8)
                ax.grid(alpha=0.3)
                fig.tight_layout()
                fp = figs_dir / f"{case}_{key}.png"
                fig.savefig(fp, dpi=130)
                plt.close(fig)
                fig_paths.append(str(fp))
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "timeseries_reports.json", "w", encoding="utf-8") as f:
        json.dump(all_reports, f, ensure_ascii=False, indent=2)
    # human-readable markdown
    lines = [
        "# 时序分析结果（task tc299a729）\n",
        "由 `src/mathworkstation/timeseries_analysis.py` 生成，"
        "复用 Ljung-Box / ADF / Durbin-Watson / 滑动窗口 / 结构断点方法。\n",
    ]
    for key, d in all_reports.items():
        ac = d["autocorrelation"]
        st = d["stationarity"]
        stt = d["stationarity"] if isinstance(d["stationarity"], dict) else {}
        cp = d["change_points"]
        sw = d["sliding"]
        lines.append(f"## {key}\n")
        lines.append(f"- 序列：{d['series_name']}（{d['frequency']}，n={d['n_points']}）")
        lines.append(f"- Ljung-Box Q({ac['lb_lags']}) = {ac['lb_stat']:.2f}，p = {ac['lb_pvalue']:.4f}，Durbin-Watson = {ac['durbin_watson']:.2f}")
        lines.append(f"- ADF = {st['adf_stat']:.3f}，p = {st['pvalue']:.4f}（{'平稳' if st['is_stationary'] else '非平稳/带趋势'}）")
        lines.append(f"- 结构断点：{len(cp['change_points'])} 个，最大段间相对跳变 {cp['max_relative_jump']:.1%}")
        lines.append(f"- 归一化趋势斜率：{sw['trend_slope']:+.3f}/step")
        lines.append(f"- 结论：{d['summary']}\n")
    (out / "timeseries_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ 结果写入 {out}")
    if fig_paths:
        print(f"   {len(fig_paths)} 张图：{fig_paths[0]} ...")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 失败：{exc}")
        sys.exit(1)
