"""Solve a small integer programming template when scipy.optimize.milp is available."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load_problem(path):
    if path is None:
        return {"c": [-5, -4], "A": [[2, 1], [1, 2]], "lb": [-np.inf, -np.inf], "ub": [8, 8], "integrality": [1, 1], "bounds": [[0, 10], [0, 10]]}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"input file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def run(input_path, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    try:
        from scipy.optimize import Bounds, LinearConstraint, milp
    except Exception:
        (output / "summary.md").write_text("# Integer Programming\n\nThis SciPy version does not provide scipy.optimize.milp. Consider PuLP or OR-Tools if allowed by your environment.\n", encoding="utf-8")
        return 0
    p = load_problem(input_path)
    bounds = Bounds([b[0] for b in p["bounds"]], [b[1] for b in p["bounds"]])
    constraints = LinearConstraint(np.array(p["A"], dtype=float), np.array(p["lb"], dtype=float), np.array(p["ub"], dtype=float))
    res = milp(c=np.array(p["c"], dtype=float), integrality=np.array(p["integrality"], dtype=int), bounds=bounds, constraints=constraints)
    solution_x = list(res.x) if res.success and res.x is not None else []
    pd.DataFrame({"variable": [f"x{i+1}" for i in range(len(solution_x))], "value": solution_x}).to_csv(output / "solution.csv", index=False)
    (output / "summary.md").write_text(f"# Integer Programming Result\n\n- Success: {res.success}\n- Objective: {res.fun if res.success else 'NA'}\n- Message: {res.message}\n", encoding="utf-8")
    return 0 if res.success else 2


def main():
    parser = argparse.ArgumentParser(description="Solve a small integer programming JSON problem. If --input is omitted, a demo is used.")
    parser.add_argument("--input", help="Input JSON path.")
    parser.add_argument("--output", required=True, help="Output directory.")
    args = parser.parse_args()
    try:
        return run(args.input, args.output)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
