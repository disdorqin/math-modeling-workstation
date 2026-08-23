from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mathworkstation.competition_paper_auditor import CompetitionPaperAuditor
from mathworkstation.judge_validity import CalibrationPaper, PairSpec
from mathworkstation.paper_quality_benchmark import PaperQualityBenchmarkService


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _decision_from_lower_tuple(left: tuple[int, ...], right: tuple[int, ...]) -> str:
    if left < right:
        return "LEFT"
    if right < left:
        return "RIGHT"
    return "TIE"


def _decision_from_higher_score(left: float, right: float, *, atol: float = 1e-9) -> str:
    if left > right + atol:
        return "LEFT"
    if right > left + atol:
        return "RIGHT"
    return "TIE"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run current deterministic internal judges over V6 blind text papers.")
    parser.add_argument("--root", default="artifacts/meta_benchmark/judge_v1")
    args = parser.parse_args()

    root = Path(args.root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    papers = [CalibrationPaper(**row) for row in manifest.get("papers", [])]
    pairs = [PairSpec(**row) for row in _read_jsonl(root / "pairwise_pairs.jsonl")]

    auditor = CompetitionPaperAuditor()
    quality = PaperQualityBenchmarkService()
    scores: dict[str, dict[str, Any]] = {}

    for paper in papers:
        text_path = root / "anonymized" / f"{paper.blind_id}.txt"
        if not text_path.is_file():
            raise FileNotFoundError(text_path)
        text = text_path.read_text(encoding="utf-8")
        competition = paper.competition.upper()
        profile_id = "CUMCM_C" if competition == "CUMCM" else "MCM_C"

        audit = auditor.audit(text, narrative=None, competition=competition)
        benchmark = quality.assess(text, [], profile_id=profile_id, case_id=None)
        scores[paper.blind_id] = {
            "competition": competition,
            "profile_id": profile_id,
            "auditor": {
                "gate": audit.gate,
                "block_count": audit.block_count,
                "review_count": audit.review_count,
                "document_defects": audit.document_defects,
                "research_defects": audit.research_defects,
                "codes": [item.code for item in audit.findings],
            },
            "paper_quality_benchmark": {
                "gate": benchmark.gate,
                "score": benchmark.score,
                "dimensions": [
                    {
                        "dimension": item.dimension,
                        "status": item.status,
                        "observed": item.observed,
                        "benchmark": item.benchmark,
                    }
                    for item in benchmark.dimensions
                ],
            },
        }

    private_score_path = root / "internal_paper_scores.json"
    private_score_path.write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")

    output = root / "judge_results" / "internal_current.jsonl"
    with output.open("w", encoding="utf-8") as handle:
        for pair in pairs:
            left = scores[pair.left_id]
            right = scores[pair.right_id]

            left_audit = left["auditor"]
            right_audit = right["auditor"]
            left_tuple = (
                int(left_audit["block_count"]),
                int(left_audit["review_count"]),
                int(left_audit["document_defects"]),
                int(left_audit["research_defects"]),
            )
            right_tuple = (
                int(right_audit["block_count"]),
                int(right_audit["review_count"]),
                int(right_audit["document_defects"]),
                int(right_audit["research_defects"]),
            )
            audit_decision = _decision_from_lower_tuple(left_tuple, right_tuple)
            audit_vote = {
                "record_type": "judge_vote",
                "judge_id": "competition-paper-auditor-raw",
                "judge_kind": "INTERNAL",
                "pair_id": pair.pair_id,
                "decision": audit_decision,
                "confidence": 0.7 if audit_decision != "TIE" else 0.5,
                "rationale": (
                    f"Symmetric raw-text defect ordering: left={left_tuple}, right={right_tuple}; lower tuple preferred."
                ),
            }
            handle.write(json.dumps(audit_vote, ensure_ascii=False) + "\n")

            left_score = float(left["paper_quality_benchmark"]["score"])
            right_score = float(right["paper_quality_benchmark"]["score"])
            quality_decision = _decision_from_higher_score(left_score, right_score)
            quality_vote = {
                "record_type": "judge_vote",
                "judge_id": "paper-quality-benchmark-raw",
                "judge_kind": "INTERNAL",
                "pair_id": pair.pair_id,
                "decision": quality_decision,
                "confidence": 0.6 if quality_decision != "TIE" else 0.5,
                "rationale": (
                    f"Symmetric raw-text density benchmark: left={left_score:.2f}, right={right_score:.2f}; higher score preferred."
                ),
            }
            handle.write(json.dumps(quality_vote, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "papers_scored": len(papers),
                "pairs_scored": len(pairs),
                "votes_written": len(pairs) * 2,
                "score_path": str(private_score_path),
                "vote_path": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
