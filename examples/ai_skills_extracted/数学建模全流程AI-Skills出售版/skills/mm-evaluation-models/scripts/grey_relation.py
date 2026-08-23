"""Compute grey relational coefficients and grades for comparison sequences."""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def parse_cols(value):
    return [x.strip() for x in value.split(",") if x.strip()] if value else []


def minmax(s):
    values = pd.to_numeric(s, errors="coerce")
    if values.isna().any():
        raise ValueError(f"column {s.name} contains non-numeric or missing values")
    span = values.max() - values.min()
    if span == 0:
        return pd.Series(np.ones(len(values)), index=s.index)
    return (values - values.min()) / span


def run(input_path, output_dir, reference_column, columns_arg, rho):
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")
    df = pd.read_csv(path)
    if reference_column not in df.columns:
        raise ValueError(f"missing reference column: {reference_column}")
    columns = parse_cols(columns_arg) or [c for c in df.columns if c != reference_column and pd.api.types.is_numeric_dtype(df[c])]
    if not columns:
        raise ValueError("no comparison columns provided or detected")
    reference = minmax(df[reference_column])
    diffs = {}
    for col in columns:
        if col not in df.columns:
            raise ValueError(f"missing column: {col}")
        diffs[col] = np.abs(reference - minmax(df[col]))
    diff_df = pd.DataFrame(diffs)
    d_min = diff_df.min().min()
    d_max = diff_df.max().max()
    coeff = (d_min + rho * d_max) / (diff_df + rho * d_max)
    grades = coeff.mean(axis=0).sort_values(ascending=False)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    coeff.to_csv(output / "grey_coefficients.csv", index=False)
    grades_df = grades.rename("grade").reset_index()
    grades_df.columns = ["column", "grade"]
    grades_df.to_csv(output / "grey_grades.csv", index=False)
    (output / "summary.md").write_text(f"# Grey Relation Summary\n\n- Reference: {reference_column}\n- rho: {rho}\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Compute grey relational analysis outputs.")
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--reference-column", required=True, help="Reference sequence column.")
    parser.add_argument("--columns", help="Comma-separated comparison columns. Defaults to numeric non-reference columns.")
    parser.add_argument("--rho", type=float, default=0.5, help="Resolution coefficient in (0, 1].")
    args = parser.parse_args()
    try:
        if not (0 < args.rho <= 1):
            raise ValueError("rho must be in (0, 1]")
        return run(args.input, args.output, args.reference_column, args.columns, args.rho)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
