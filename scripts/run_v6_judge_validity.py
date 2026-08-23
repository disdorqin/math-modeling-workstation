from __future__ import annotations

import argparse
import json
from pathlib import Path

from mathworkstation.judge_validity import (
    CalibrationPaper,
    JudgeVote,
    PairSpec,
    aggregate_judge_validity,
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate V6 judge-validity calibration results.")
    parser.add_argument(
        "--root",
        default="artifacts/meta_benchmark/judge_v1",
        help="judge_v1 artifact directory",
    )
    parser.add_argument(
        "--judge-results",
        nargs="*",
        default=None,
        help="optional explicit judge result JSONL files; default is judge_results/*.jsonl",
    )
    args = parser.parse_args()

    root = Path(args.root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    papers = [CalibrationPaper(**row) for row in manifest.get("papers", [])]
    pairs = [PairSpec(**row) for row in _read_jsonl(root / "pairwise_pairs.jsonl")]

    if args.judge_results is None:
        result_paths = sorted((root / "judge_results").glob("*.jsonl"))
    else:
        result_paths = [Path(item) for item in args.judge_results]

    votes: list[JudgeVote] = []
    for path in result_paths:
        for row in _read_jsonl(path):
            if row.get("record_type") != "judge_vote":
                continue
            payload = {key: value for key, value in row.items() if key != "record_type"}
            votes.append(JudgeVote(**payload))

    aggregate = aggregate_judge_validity(papers, pairs, votes)
    serialized = json.dumps(aggregate, ensure_ascii=False, indent=2)
    (root / "aggregate.json").write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
