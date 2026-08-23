from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from mathworkstation.judge_validity import JudgeVote


AI_IDENTITIES = {
    "ai",
    "agent",
    "llm",
    "gpt",
    "bot",
    "assistant",
    "model",
    "chatgpt",
    "deepseek",
    "grok",
    "claude",
    "codex",
}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a genuine human vote for V6 JudgeEval.")
    parser.add_argument("vote_json")
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--root", default="artifacts/meta_benchmark/judge_v1")
    args = parser.parse_args()

    reviewer = args.reviewer_id.strip()
    normalized = re.sub(r"[^a-z0-9]+", "_", reviewer.lower()).strip("_")
    if not normalized or normalized in AI_IDENTITIES or normalized.startswith("ai_"):
        raise ValueError("reviewer-id must identify a real human reviewer, not an AI/model placeholder")

    root = Path(args.root)
    vote_payload = json.loads(Path(args.vote_json).read_text(encoding="utf-8"))
    pair_id = str(vote_payload.get("pair_id") or "")
    valid_pairs = {str(row.get("pair_id")) for row in _read_jsonl(root / "pairwise_pairs.jsonl")}
    if pair_id not in valid_pairs:
        raise ValueError(f"unknown pair_id: {pair_id}")

    decision = str(vote_payload.get("decision") or "").upper()
    confidence = float(vote_payload.get("confidence", 0.0))
    rationale = str(vote_payload.get("rationale") or "").strip()
    blind_verified = bool(vote_payload.get("blind_verified"))
    attestation = str(vote_payload.get("blindness_attestation") or "").strip()
    if not blind_verified or attestation != "content_only_before_provenance_reveal":
        raise ValueError("human vote is not a verified blind-review vote")
    judge_id = f"human-{normalized}"
    vote = JudgeVote(
        judge_id=judge_id,
        judge_kind="HUMAN",
        pair_id=pair_id,
        decision=decision,  # type: ignore[arg-type]
        confidence=confidence,
        rationale=rationale,
        blind_verified=True,
    )

    output = root / "judge_results" / f"{judge_id}.jsonl"
    existing = _read_jsonl(output)
    if any(row.get("record_type") == "judge_vote" and row.get("pair_id") == pair_id for row in existing):
        raise ValueError(f"human reviewer {reviewer!r} already voted on pair {pair_id}")

    detail = {
        "record_type": "judge_detail",
        "judge_id": judge_id,
        "pair_id": pair_id,
        "dimensions": vote_payload.get("dimensions") or {},
        "visual_dimension": vote_payload.get("visual_dimension") or "UNVERIFIED_TEXT_ONLY",
        "blindness_attestation": attestation,
        "blind_verified": True,
    }
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"record_type": "judge_vote", **vote.__dict__}, ensure_ascii=False) + "\n")
        handle.write(json.dumps(detail, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "recorded": True,
                "judge_id": judge_id,
                "pair_id": pair_id,
                "decision": vote.decision,
                "confidence": vote.confidence,
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
