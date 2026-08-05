"""Rank alternatives with a weighted-sum multi-objective template."""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def split(value):
    return [x.strip() for x in value.split(",") if x.strip()]


def run(input_path, output_dir, columns_arg, weights_arg, directions_arg):
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(f"input file not found: {p}")
    df = pd.read_csv(p)
    cols = split(columns_arg)
    weights = np.array([float(x) for x in split(weights_arg)], dtype=float)
    dirs = split(directions_arg)
    if not (len(cols) == len(weights) == len(dirs)):
        raise ValueError("columns, weights, and directions must have the same length")
    weights = weights / weights.sum()
    norm = pd.DataFrame(index=df.index)
    for c, d in zip(cols, dirs):
        v = pd.to_numeric(df[c], errors="coerce")
        if v.isna().any():
            raise ValueError(f"column {c} contains invalid numeric values")
        span = v.max() - v.min()
        if span == 0:
            norm[c] = 1.0
        elif d == "positive":
            norm[c] = (v - v.min()) / span
        elif d == "negative":
            norm[c] = (v.max() - v) / span
        else:
            raise ValueError("directions must be positive or negative")
    score = norm.to_numpy(dtype=float) @ weights
    result = df.copy()
    result["weighted_score"] = score
    result["rank"] = pd.Series(score).rank(ascending=False, method="min").astype(int)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result.sort_values("rank").to_csv(output / "multi_objective_ranking.csv", index=False)
    (output / "summary.md").write_text("# Multi-objective Weighted Sum\n\nPareto analysis is recommended when rankings change strongly under weight perturbation.\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run weighted-sum multi-objective ranking.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--columns", required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--directions", required=True)
    args = parser.parse_args()
    try:
        return run(args.input, args.output, args.columns, args.weights, args.directions)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
