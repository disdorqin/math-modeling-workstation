#!/usr/bin/env python3
"""C题重跑验证:验证字段兜底修复后能跑通2023/2018 C题。"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from mathworkstation.cli import main as cli_main


class CRerun:
    def __init__(self, output_root: str) -> None:
        self.root = Path(output_root)

    def cli(self, *args: str) -> dict:
        """Run one real CLI command; raise on non-zero exit; parse JSON stdout."""
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli_main(["--output-root", str(self.root), *args])
        if code != 0:
            raise SystemExit(f"command failed (exit {code}): {' '.join(args)}\n{out.getvalue()}")
        text = out.getvalue().strip()
        try:
            return json.loads(text) if text else {}
        except json.JSONDecodeError:
            return {"raw": text}

    def run_2023(self) -> dict:
        """Run 2023 C题 with field兜底 fix verification."""
        step = lambda msg: print(f"==> {msg}", flush=True)

        # Source files from v1
        v1_case = self.root / "mcm-c-2023" / "v1" / "20260805-MCM-0001-J5GW"
        problem_source = v1_case / "input" / "problem" / "extracted" / "2023_MCM_Problem_C.md"
        data_source = v1_case / "input" / "data" / "uploaded" / "_wordle_data_clean.csv"

        if not problem_source.exists():
            raise SystemExit(f"Problem file not found: {problem_source}")
        if not data_source.exists():
            raise SystemExit(f"Data file not found: {data_source}")

        step("create case (2023 C题 v2)")
        case = self.cli(
            "create-case",
            "--competition", "MCM",
            "--title", "2023 MCM C: Wordle 预测",
            "--problem-type", "c",
            "--year", "2023",
            "--version", "2",
        )["case_id"]
        session = self.cli("create-session", "--case-id", case)["session_id"]
        print(f"    case={case} session={session}")

        step("run auto-pipeline (full LLM pipeline)")
        routes = str(REPO / "config" / "llm-routes.local.json")
        result = self.cli(
            "run-auto-pipeline",
            "--case-id", case,
            "--session-id", session,
            "--problem-source", str(problem_source),
            "--data-source", str(data_source),
            "--dataset-name", "Wordle 猜测数据",
            "--target-column", "Number in hard mode",
            "--competition-type", "MCM",
            "--routes", routes,
            "--approved-by", "rerun-test",
            "--kind", "OBSERVED",
        )

        return {
            "case_id": case,
            "session_id": session,
            "result": result,
        }

    def run_2018(self) -> dict:
        """Run 2018 C题 with field兜底 fix verification."""
        step = lambda msg: print(f"==> {msg}", flush=True)

        # Check if 2018 data exists
        v1_case = self.root / "mcm-c-2018" / "v1"
        if not v1_case.exists():
            raise SystemExit("2018 C题 data not found")

        # Find the case directory
        cases = list(v1_case.iterdir())
        if not cases:
            raise SystemExit("No 2018 C题 cases found")
        case_dir = cases[0]

        # Find problem and data files
        problem_files = list((case_dir / "input" / "problem" / "extracted").glob("*.md"))
        data_files = list((case_dir / "input" / "data" / "uploaded").glob("*.csv"))
        if not problem_files:
            raise SystemExit("No problem files found")
        if not data_files:
            raise SystemExit("No data files found")

        problem_source = problem_files[0]
        data_source = data_files[0]

        step("create case (2018 C题 v2)")
        case = self.cli(
            "create-case",
            "--competition", "MCM",
            "--title", "2018 MCM C: 热狗比赛",
            "--problem-type", "c",
            "--year", "2018",
            "--version", "2",
        )["case_id"]
        session = self.cli("create-session", "--case-id", case)["session_id"]
        print(f"    case={case} session={session}")

        step("run auto-pipeline (full LLM pipeline)")
        routes = str(REPO / "config" / "llm-routes.local.json")
        result = self.cli(
            "run-auto-pipeline",
            "--case-id", case,
            "--session-id", session,
            "--problem-source", str(problem_source),
            "--data-source", str(data_source),
            "--dataset-name", "热狗比赛数据",
            "--target-column", "total_games",
            "--competition-type", "MCM",
            "--routes", routes,
            "--approved-by", "rerun-test",
            "--kind", "OBSERVED",
        )

        return {
            "case_id": case,
            "session_id": session,
            "result": result,
        }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python scripts/rerun_c_test.py <output_root> [2023|2018|both]")
    
    output_root = sys.argv[1]
    year = sys.argv[2] if len(sys.argv) > 2 else "2023"
    
    rerun = CRerun(output_root)
    
    if year == "2023" or year == "both":
        print("\n" + "="*60)
        print("Running 2023 C题 verification...")
        print("="*60)
        result_2023 = rerun.run_2023()
        print(f"\n2023 Result: {json.dumps(result_2023, ensure_ascii=False, indent=2)}")
    
    if year == "2018" or year == "both":
        print("\n" + "="*60)
        print("Running 2018 C题 verification...")
        print("="*60)
        result_2018 = rerun.run_2018()
        print(f"\n2018 Result: {json.dumps(result_2018, ensure_ascii=False, indent=2)}")
    
    print("\n" + "="*60)
    print("Verification complete!")
    print("="*60)
