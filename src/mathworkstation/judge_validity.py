from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Iterable, Literal

from .io_utils import now_iso

PaperOrigin = Literal["REAL_EXCELLENT", "WORKSTATION_CURRENT", "WORKSTATION_OLDER"]
PairKind = Literal["REAL_VS_CURRENT", "REAL_VS_REAL", "CURRENT_VS_OLDER"]
JudgeKind = Literal["INTERNAL", "INDEPENDENT_MODEL", "HUMAN"]
Decision = Literal["LEFT", "RIGHT", "TIE", "ABSTAIN"]
HypothesisStatus = Literal["SUPPORTED", "REJECTED", "INCONCLUSIVE"]


@dataclass(frozen=True)
class CalibrationPaper:
    """Private calibration manifest entry.

    ``source_path`` and ``origin`` belong in the private manifest only.  They must
    never be included in the payload handed to a blind judge.
    """

    blind_id: str
    origin: PaperOrigin
    competition: str
    year: int
    problem_letter: str
    problem_key: str
    source_path: str
    award: str = ""
    case_id: str = ""
    version: str = ""
    visual_verified: bool = False


@dataclass(frozen=True)
class PairSpec:
    pair_id: str
    swap_group: str
    left_id: str
    right_id: str
    kind: PairKind

    def __post_init__(self) -> None:
        if self.left_id == self.right_id:
            raise ValueError("judge pair cannot compare a paper with itself")


@dataclass(frozen=True)
class JudgeVote:
    judge_id: str
    judge_kind: JudgeKind
    pair_id: str
    decision: Decision
    confidence: float = 0.0
    rationale: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be in [0, 1]")


def anonymize_paper_text(text: str) -> str:
    """Remove obvious source/award identity leakage while preserving paper content.

    This is intentionally conservative.  It masks common competition metadata but
    does not claim author-name NER.  If names/schools survive, the anonymization
    manifest must mark the sample for manual review before a true blind run.
    """

    value = text
    award_patterns = (
        r"\bOutstanding\s+(?:Winner|Award)?\b",
        r"\bFinalist\b",
        r"\bMeritorious\b",
        r"\bHonorable\s+Mention\b",
        r"\bO\s*[- ]?Award\b",
        r"\bAMS\s+Award\b",
        r"\bVilfredo\s+Pareto\s+Award\b",
        r"\b国(?:家)?(?:一|二|三)等奖\b",
        r"\b国一\b",
    )
    for pattern in award_patterns:
        value = re.sub(pattern, "[AWARD REDACTED]", value, flags=re.IGNORECASE)

    identity_patterns = (
        r"(?im)^\s*(?:Team\s*#?|Control\s*Number|Team\s*Control\s*Number)\s*[:#-]?\s*[A-Za-z0-9_-]{4,}\s*$",
        r"(?im)^\s*(?:Author|Authors|School|University|Institution)\s*[:：].*$",
    )
    for pattern in identity_patterns:
        value = re.sub(pattern, "[IDENTITY REDACTED]", value)

    # COMAP team numbers commonly appear as a standalone 6- or 7-digit token in
    # headers.  Only mask whole header-like lines, not arbitrary numerical results.
    value = re.sub(r"(?m)^\s*\d{6,7}\s*$", "[TEAM ID REDACTED]", value)
    return value


def make_swapped_pair(
    *,
    swap_group: str,
    left_id: str,
    right_id: str,
    kind: PairKind,
) -> tuple[PairSpec, PairSpec]:
    """Create the canonical A/B pair plus a position-swapped duplicate."""

    return (
        PairSpec(
            pair_id=f"{swap_group}-ab",
            swap_group=swap_group,
            left_id=left_id,
            right_id=right_id,
            kind=kind,
        ),
        PairSpec(
            pair_id=f"{swap_group}-ba",
            swap_group=swap_group,
            left_id=right_id,
            right_id=left_id,
            kind=kind,
        ),
    )


def preferred_blind_id(vote: JudgeVote, pair: PairSpec) -> str | None:
    if vote.decision == "LEFT":
        return pair.left_id
    if vote.decision == "RIGHT":
        return pair.right_id
    return None


def aggregate_judge_validity(
    papers: Iterable[CalibrationPaper],
    pairs: Iterable[PairSpec],
    votes: Iterable[JudgeVote],
) -> dict[str, object]:
    """Aggregate judge-calibration evidence without inventing a reward score.

    A H1 verdict is intentionally conservative: without at least one *blind human*
    vote, the result stays ``INCONCLUSIVE``.  Provenance labels and internal
    detector disagreement are useful diagnostics, but are not substitutes for the
    human anchor required by V6.
    """

    paper_list = list(papers)
    pair_list = list(pairs)
    vote_list = list(votes)
    paper_by_id = {item.blind_id: item for item in paper_list}
    pair_by_id = {item.pair_id: item for item in pair_list}
    if len(paper_by_id) != len(paper_list):
        raise ValueError("duplicate blind_id in calibration manifest")
    if len(pair_by_id) != len(pair_list):
        raise ValueError("duplicate pair_id in pair manifest")
    for pair in pair_list:
        if pair.left_id not in paper_by_id or pair.right_id not in paper_by_id:
            raise ValueError(f"pair references unknown blind paper: {pair.pair_id}")
    for vote in vote_list:
        if vote.pair_id not in pair_by_id:
            raise ValueError(f"vote references unknown pair: {vote.pair_id}")

    preferred: dict[tuple[str, str], str | None] = {}
    judge_kind: dict[str, JudgeKind] = {}
    for vote in vote_list:
        pair = pair_by_id[vote.pair_id]
        preferred[(vote.judge_id, vote.pair_id)] = preferred_blind_id(vote, pair)
        judge_kind[vote.judge_id] = vote.judge_kind

    position_checked = 0
    position_consistent = 0
    by_swap: dict[str, list[PairSpec]] = defaultdict(list)
    for pair in pair_list:
        by_swap[pair.swap_group].append(pair)
    for judge_id in judge_kind:
        for group_pairs in by_swap.values():
            choices = [
                preferred.get((judge_id, pair.pair_id))
                for pair in group_pairs
                if (judge_id, pair.pair_id) in preferred
            ]
            choices = [item for item in choices if item is not None]
            if len(choices) >= 2:
                position_checked += 1
                position_consistent += int(len(set(choices)) == 1)

    logical_choices: dict[tuple[str, str], str] = {}
    for judge_id in judge_kind:
        for swap_group, group_pairs in by_swap.items():
            choices = [
                preferred.get((judge_id, pair.pair_id))
                for pair in group_pairs
                if preferred.get((judge_id, pair.pair_id)) is not None
            ]
            if choices and len(set(choices)) == 1:
                logical_choices[(judge_id, swap_group)] = choices[0]

    agreement_hits = 0
    agreement_total = 0
    for swap_group in by_swap:
        judge_choices = [
            logical_choices[(judge_id, swap_group)]
            for judge_id in judge_kind
            if (judge_id, swap_group) in logical_choices
        ]
        for left, right in combinations(judge_choices, 2):
            agreement_total += 1
            agreement_hits += int(left == right)

    discrimination: dict[str, dict[str, float | int | None]] = {}
    for jid, kind in judge_kind.items():
        total = 0
        correct = 0
        for swap_group, group_pairs in by_swap.items():
            pair = group_pairs[0]
            if pair.kind not in {"REAL_VS_CURRENT", "CURRENT_VS_OLDER"}:
                continue
            choice = logical_choices.get((jid, swap_group))
            if choice is None:
                continue
            ids = {pair.left_id, pair.right_id}
            if pair.kind == "REAL_VS_CURRENT":
                expected = next(
                    (pid for pid in ids if paper_by_id[pid].origin == "REAL_EXCELLENT"),
                    None,
                )
            else:
                expected = next(
                    (pid for pid in ids if paper_by_id[pid].origin == "WORKSTATION_CURRENT"),
                    None,
                )
            if expected is None:
                continue
            total += 1
            correct += int(choice == expected)
        discrimination[jid] = {
            "judge_kind": kind,
            "checked": total,
            "correct": correct,
            "accuracy_vs_provenance_prior": (round(correct / total, 6) if total else None),
        }

    human_vote_count = sum(item.judge_kind == "HUMAN" for item in vote_list)
    independent_vote_count = sum(item.judge_kind == "INDEPENDENT_MODEL" for item in vote_list)
    internal_vote_count = sum(item.judge_kind == "INTERNAL" for item in vote_list)

    # V6 requires a human anchor.  Non-blind user preferences and known award labels
    # are retained as priors, not silently promoted into JudgeEval ground truth.
    hypothesis: HypothesisStatus = "INCONCLUSIVE"
    verdict_reason = "blind human anchor is still missing"
    if human_vote_count > 0:
        internal_rows = [
            row
            for jid, row in discrimination.items()
            if judge_kind.get(jid) == "INTERNAL" and row["accuracy_vs_provenance_prior"] is not None
        ]
        internal_accuracy = (
            sum(float(row["accuracy_vs_provenance_prior"]) for row in internal_rows) / len(internal_rows)
            if internal_rows
            else None
        )
        pos = position_consistent / position_checked if position_checked else None
        if internal_accuracy is not None and internal_accuracy < 0.75:
            hypothesis = "SUPPORTED"
            verdict_reason = "internal judge disagrees materially with the blind human/provenance ordering"
        elif (
            internal_accuracy is not None
            and internal_accuracy >= 0.85
            and pos is not None
            and pos >= 0.95
            and independent_vote_count > 0
        ):
            hypothesis = "REJECTED"
            verdict_reason = "internal judge is aligned with blind human anchor and position-stable"
        else:
            verdict_reason = "available human evidence is insufficient for a decisive H1 verdict"

    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "paper_count": len(paper_list),
        "pair_count": len(pair_list),
        "vote_count": len(vote_list),
        "human_vote_count": human_vote_count,
        "independent_model_vote_count": independent_vote_count,
        "internal_vote_count": internal_vote_count,
        "position_swap_consistency": (
            round(position_consistent / position_checked, 6) if position_checked else None
        ),
        "position_swap_groups_checked": position_checked,
        "cross_judge_agreement": (
            round(agreement_hits / agreement_total, 6) if agreement_total else None
        ),
        "cross_judge_pairs_checked": agreement_total,
        "discrimination": discrimination,
        "h1_judge_validity_bottleneck": hypothesis,
        "h1_reason": verdict_reason,
        "visual_dimension": "UNVERIFIED",
    }


def paper_manifest_rows(papers: Iterable[CalibrationPaper]) -> list[dict[str, object]]:
    return [asdict(item) for item in papers]


def blind_pair_rows(pairs: Iterable[PairSpec]) -> list[dict[str, object]]:
    """Return only fields safe to expose to a blind judge."""

    return [
        {
            "pair_id": item.pair_id,
            "swap_group": item.swap_group,
            "left_id": item.left_id,
            "right_id": item.right_id,
            "kind": item.kind,
        }
        for item in pairs
    ]
