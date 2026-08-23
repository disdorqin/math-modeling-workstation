"""Simulate a simple M/M/1 queue and export waiting-time statistics."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load_params(path, arrival_rate, service_rate, customers):
    params = {"arrival_rate": arrival_rate, "service_rate": service_rate, "customers": customers}
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"input file not found: {p}")
        params.update(json.loads(p.read_text(encoding="utf-8")))
    return params


def run(input_path, output_dir, arrival_rate, service_rate, customers, seed):
    params = load_params(input_path, arrival_rate, service_rate, customers)
    lam = float(params["arrival_rate"])
    mu = float(params["service_rate"])
    n = int(params["customers"])
    if lam <= 0 or mu <= 0 or n <= 0:
        raise ValueError("arrival_rate, service_rate, and customers must be positive")
    rng = np.random.default_rng(seed)
    inter_arrivals = rng.exponential(1 / lam, n)
    service_times = rng.exponential(1 / mu, n)
    arrivals = np.cumsum(inter_arrivals)
    starts = np.zeros(n)
    departures = np.zeros(n)
    for i in range(n):
        starts[i] = max(arrivals[i], departures[i-1] if i else 0)
        departures[i] = starts[i] + service_times[i]
    waits = starts - arrivals
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"arrival": arrivals, "service_time": service_times, "service_start": starts, "departure": departures, "wait": waits}).to_csv(output / "queue_events.csv", index=False)
    utilization = service_times.sum() / departures[-1]
    pd.DataFrame([{"avg_wait": waits.mean(), "avg_system_time": (departures - arrivals).mean(), "utilization": utilization}]).to_csv(output / "queue_summary.csv", index=False)
    (output / "summary.md").write_text(f"# M/M/1 Queue Simulation\n\n- Customers: {n}\n- Utilization: {utilization:.4f}\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run an M/M/1 queue simulation template.")
    parser.add_argument("--input", help="Optional JSON parameter path.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--arrival-rate", type=float, default=0.8)
    parser.add_argument("--service-rate", type=float, default=1.0)
    parser.add_argument("--customers", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        return run(args.input, args.output, args.arrival_rate, args.service_rate, args.customers, args.seed)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
