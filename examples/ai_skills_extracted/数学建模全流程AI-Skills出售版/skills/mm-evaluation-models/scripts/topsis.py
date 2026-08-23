"""Run a TOPSIS ranking workflow for multi-indicator evaluation data."""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def items(value, name):
    out = [x.strip() for x in value.split(",") if x.strip()]
    if not out:
        raise ValueError(f"{name} cannot be empty")
    return out


def prepare(df, columns, directions):
    data = pd.DataFrame(index=df.index)
    for col, direction in zip(columns, directions):
        if col not in df.columns:
            raise ValueError(f"missing column: {col}")
        values = pd.to_numeric(df[col], errors="coerce")
        if values.isna().any():
            raise ValueError(f"column {col} contains non-numeric or missing values")
        min_v, max_v = values.min(), values.max()
        if max_v == min_v:
            scaled = pd.Series(np.ones(len(values)), index=df.index)
        elif direction == "positive":
            scaled = (values - min_v) / (max_v - min_v)
        elif direction == "negative":
            scaled = (max_v - values) / (max_v - min_v)
        else:
            raise ValueError("directions must be positive or negative")
        data[col] = scaled
    norm = np.sqrt((data ** 2).sum(axis=0))
    norm = norm.replace(0, 1)
    return data / norm


def run(input_path, output_dir, columns_arg, weights_arg, directions_arg):
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("input CSV is empty")
    columns = items(columns_arg, "columns")
    directions = items(directions_arg, "directions")
    if len(columns) != len(directions):
        raise ValueError("columns and directions must have the same length")
    weights = np.array([float(x) for x in items(weights_arg, "weights")], dtype=float)
    if len(weights) != len(columns):
        raise ValueError("weights and columns must have the same length")
    if np.any(weights < 0) or np.isclose(weights.sum(), 0):
        raise ValueError("weights must be non-negative and have positive sum")
    weights = weights / weights.sum()

    normalized = prepare(df, columns, directions)
    weighted = normalized.to_numpy(dtype=float) * weights
    positive_ideal = weighted.max(axis=0)
    negative_ideal = weighted.min(axis=0)
    d_positive = np.sqrt(((weighted - positive_ideal) ** 2).sum(axis=1))
    d_negative = np.sqrt(((weighted - negative_ideal) ** 2).sum(axis=1))
    denom = d_positive + d_negative
    closeness = np.divide(d_negative, denom, out=np.zeros_like(d_negative), where=denom != 0)
    ranking = pd.Series(closeness).rank(ascending=False, method="min").astype(int)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame({"row": np.arange(len(df)), "d_positive": d_positive, "d_negative": d_negative, "closeness": closeness, "rank": ranking})
    if df.columns[0] not in columns:
        result.insert(1, df.columns[0], df.iloc[:, 0].values)
    result.sort_values("rank").to_csv(output / "topsis_result.csv", index=False)
    normalized.to_csv(output / "normalized_matrix.csv", index=False)
    pd.DataFrame({"column": columns, "weight": weights, "positive_ideal": positive_ideal, "negative_ideal": negative_ideal}).to_csv(output / "ideal_solutions.csv", index=False)
    (output / "summary.md").write_text(f"# TOPSIS Summary\n\n- Samples: {len(df)}\n- Indicators: {len(columns)}\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run TOPSIS ranking.")
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--columns", required=True, help="Comma-separated indicator columns.")
    parser.add_argument("--weights", required=True, help="Comma-separated non-negative weights.")
    parser.add_argument("--directions", required=True, help="Comma-separated directions: positive or negative.")
    args = parser.parse_args()
    try:
        return run(args.input, args.output, args.columns, args.weights, args.directions)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
