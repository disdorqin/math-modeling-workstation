"""Solve a linear programming template with scipy.optimize.linprog."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from scipy.optimize import linprog


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load_problem(path):
    if path is None:
        return {"c": [-3, -2], "A_ub": [[2, 1], [1, 1]], "b_ub": [100, 80], "bounds": [[0, None], [0, None]]}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"input file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def run(input_path, output_dir):
    problem = load_problem(input_path)
    res = linprog(
        c=problem["c"],
        A_ub=problem.get("A_ub"),
        b_ub=problem.get("b_ub"),
        A_eq=problem.get("A_eq"),
        b_eq=problem.get("b_eq"),
        bounds=problem.get("bounds"),
        method="highs",
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    solution_x = list(res.x) if res.success and res.x is not None else []
    pd.DataFrame({"variable": [f"x{i+1}" for i in range(len(solution_x))], "value": solution_x}).to_csv(output / "solution.csv", index=False)
    (output / "summary.md").write_text(f"# Linear Programming Result\n\n- Success: {res.success}\n- Status: {res.message}\n- Objective: {res.fun if res.success else 'NA'}\n", encoding="utf-8")
    return 0 if res.success else 2


def main():
    parser = argparse.ArgumentParser(description="Solve a linear programming JSON problem. If --input is omitted, a demo is used.")
    parser.add_argument("--input", help="Input JSON path.")
    parser.add_argument("--output", required=True, help="Output directory.")
    args = parser.parse_args()
    try:
        return run(args.input, args.output)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
