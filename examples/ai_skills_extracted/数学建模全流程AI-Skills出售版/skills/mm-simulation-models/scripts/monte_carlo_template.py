"""Run a generic Monte Carlo profit simulation template."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load_params(path):
    params = {"demand_mean": 100, "demand_std": 15, "price": 20, "unit_cost": 12, "fixed_cost": 300}
    if path is None:
        return params
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"input file not found: {p}")
    params.update(json.loads(p.read_text(encoding="utf-8")))
    return params


def run(input_path, output_dir, iterations, seed):
    params = load_params(input_path)
    rng = np.random.default_rng(seed)
    demand = rng.normal(params["demand_mean"], params["demand_std"], iterations).clip(0)
    profit = demand * (params["price"] - params["unit_cost"]) - params["fixed_cost"]
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"demand": demand, "profit": profit}).to_csv(output / "monte_carlo_samples.csv", index=False)
    summary = pd.DataFrame([{"mean_profit": profit.mean(), "std_profit": profit.std(ddof=1), "p05_profit": np.percentile(profit, 5), "p95_profit": np.percentile(profit, 95)}])
    summary.to_csv(output / "summary_stats.csv", index=False)
    (output / "summary.md").write_text(f"# Monte Carlo Summary\n\n- Iterations: {iterations}\n- Seed: {seed}\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run a Monte Carlo simulation template. Optional --input is a JSON parameter file.")
    parser.add_argument("--input", help="Optional JSON parameters path.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        if args.iterations <= 0:
            raise ValueError("iterations must be positive")
        return run(args.input, args.output, args.iterations, args.seed)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
