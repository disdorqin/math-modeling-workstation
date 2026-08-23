#!/usr/bin/env python3
"""2018 MCM C (Energy Production) v2 全流水线运行脚本 — task t87836572.

Auto-approval via --approved-by freebuff (approval records still written to
decisions.jsonl; no blocking approval_callback is passed, matching the CLI
behaviour the mentor specified). Token budget was pre-expanded by writing the
session llm_budget.json before the run (zero code changes).
"""
import json
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from mathworkstation.cli import main as cli_main

CASE = "20260805-MCM-0001-4DH5"
SESSION = "0805-MCM0001-S01"
V1 = REPO / "output" / "mcm-c-2018" / "v1" / "20260805-MCM-0001-XR9C"


def main() -> int:
    problem_source = V1 / "input" / "problem" / "extracted" / "2018_MCM_Problem_C.md"
    data_source = V1 / "input" / "data" / "uploaded" / "_energy2018_tx.csv"
    if not problem_source.exists():
        raise SystemExit(f"problem source missing: {problem_source}")
    if not data_source.exists():
        raise SystemExit(f"data source missing: {data_source}")

    args = [
        "--output-root", str(REPO / "output"),
        "run-auto-pipeline",
        "--case-id", CASE,
        "--session-id", SESSION,
        "--problem-source", str(problem_source),
        "--data-source", str(data_source),
        "--dataset-name", "美国四州能源生产与消费数据(TX 州面板)",
        "--target-column", "total_production",
        "--competition-type", "MCM",
        "--routes", str(REPO / "config" / "llm-routes.local.json"),
        "--approved-by", "freebuff",
        "--kind", "OBSERVED",
    ]
    print("ARGS: " + " ".join(args), flush=True)
    code = cli_main(args)
    print(f"EXIT_CODE={code}", flush=True)
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - report and exit non-zero for the log
        traceback.print_exc()
        sys.exit(2)
