"""Create moving-average and exponential-smoothing time series baselines."""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def metrics(actual, pred):
    err = actual - pred
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mape = float(np.mean(np.abs(err / np.where(actual == 0, np.nan, actual))) * 100)
    return {"MAE": mae, "RMSE": rmse, "MAPE": mape}


def run(input_path, output_dir, value_column, window, alpha, test_size):
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")
    df = pd.read_csv(path)
    if value_column not in df.columns:
        raise ValueError(f"missing value column: {value_column}")
    y = pd.to_numeric(df[value_column], errors="coerce").dropna().to_numpy(dtype=float)
    if len(y) < window + 3:
        raise ValueError("time series is too short for the selected window")
    split = max(window + 1, int(len(y) * (1 - test_size)))
    preds_ma, preds_es, actual = [], [], []
    smooth = y[0]
    for i in range(1, len(y)):
        smooth = alpha * y[i-1] + (1 - alpha) * smooth
        if i >= split:
            preds_ma.append(float(np.mean(y[max(0, i-window):i])))
            preds_es.append(float(smooth))
            actual.append(float(y[i]))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame({"actual": actual, "moving_average": preds_ma, "exp_smoothing": preds_es})
    out.to_csv(output / "time_series_predictions.csv", index=False)
    metric_df = pd.DataFrame([
        {"model": "moving_average", **metrics(np.array(actual), np.array(preds_ma))},
        {"model": "exp_smoothing", **metrics(np.array(actual), np.array(preds_es))},
    ])
    metric_df.to_csv(output / "metrics.csv", index=False)
    (output / "summary.md").write_text(f"# Time Series Baseline\n\n- Window: {window}\n- Alpha: {alpha}\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run simple time series baselines.")
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--value-column", default="value", help="Numeric time series column.")
    parser.add_argument("--window", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=0.4)
    parser.add_argument("--test-size", type=float, default=0.25)
    args = parser.parse_args()
    try:
        if args.window < 1:
            raise ValueError("window must be positive")
        if not (0 < args.alpha <= 1):
            raise ValueError("alpha must be in (0, 1]")
        if not (0 < args.test_size < 1):
            raise ValueError("test-size must be between 0 and 1")
        return run(args.input, args.output, args.value_column, args.window, args.alpha, args.test_size)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
