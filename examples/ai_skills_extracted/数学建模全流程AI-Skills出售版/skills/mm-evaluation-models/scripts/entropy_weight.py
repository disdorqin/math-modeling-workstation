"""Compute entropy weights and weighted scores for multi-indicator evaluation."""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def parse_list(value, name):
    items = [x.strip() for x in value.split(",") if x.strip()]
    if not items:
        raise ValueError(f"{name} cannot be empty")
    return items


def normalize(df, columns, directions):
    normalized = pd.DataFrame(index=df.index)
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
        normalized[col] = scaled + 1e-12
    return normalized


def entropy_weight(normalized):
    matrix = normalized.to_numpy(dtype=float)
    col_sums = matrix.sum(axis=0)
    if np.any(col_sums <= 0):
        raise ValueError("normalized column sum must be positive")
    p = matrix / col_sums
    n = matrix.shape[0]
    if n <= 1:
        raise ValueError("at least two samples are required")
    k = 1.0 / np.log(n)
    entropy = -k * np.sum(p * np.log(p), axis=0)
    diversity = 1 - entropy
    if np.allclose(diversity.sum(), 0):
        weights = np.ones_like(diversity) / len(diversity)
    else:
        weights = diversity / diversity.sum()
    return entropy, diversity, weights


def run(input_path, output_dir, columns_arg, directions_arg):
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("input CSV is empty")
    columns = parse_list(columns_arg, "columns")
    directions = parse_list(directions_arg, "directions")
    if len(columns) != len(directions):
        raise ValueError("columns and directions must have the same length")
    normalized = normalize(df, columns, directions)
    entropy, diversity, weights = entropy_weight(normalized)
    scores = normalized.to_numpy(dtype=float) @ weights

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    weight_df = pd.DataFrame({"column": columns, "direction": directions, "entropy": entropy, "diversity": diversity, "weight": weights})
    weight_df.to_csv(output / "weights.csv", index=False)
    normalized.to_csv(output / "normalized_matrix.csv", index=False)
    score_df = pd.DataFrame({"row": np.arange(len(df)), "score": scores})
    if df.columns[0] not in columns:
        score_df.insert(1, df.columns[0], df.iloc[:, 0].values)
    score_df.to_csv(output / "scores.csv", index=False)
    (output / "summary.md").write_text(
        "# Entropy Weight Summary\n\n" +
        f"- Samples: {len(df)}\n- Indicators: {len(columns)}\n- Weight sum: {weights.sum():.6f}\n",
        encoding="utf-8",
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description="Calculate entropy weights for evaluation indicators.")
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--columns", required=True, help="Comma-separated indicator columns.")
    parser.add_argument("--directions", required=True, help="Comma-separated directions: positive or negative.")
    args = parser.parse_args()
    try:
        return run(args.input, args.output, args.columns, args.directions)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
