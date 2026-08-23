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
    blind_verified: bool = False

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
        r"国(?:家)?(?:一|二|三)等奖",
        r"(?:全国大学生数学建模竞赛)?(?:一|二|三)等奖",
        r"优秀论文",
        r"国[一二三]",
    )
    for pattern in award_patterns:
        value = re.sub(pattern, "[AWARD REDACTED]", value, flags=re.IGNORECASE)

    identity_patterns = (
        r"(?im)^\s*(?:Team\s*#|Team\s*Number|Control\s*Number|Team\s*Control\s*Number)\s*[:#-]?\s*[A-Za-z0-9_-]{4,}\s*$",
        r"(?i)\bTeam\s*#\s*(?:\[IDENTITY REDACTED\]|[A-Za-z0-9_-]{4,})\b",
        r"(?i)\b(?:Team\s*Control\s*Number|Control\s*Number)\s*[:#-]?\s*(?:\[IDENTITY REDACTED\]|[A-Za-z0-9_-]{4,})\b",
        r"(?im)^\s*(?:Author|Authors|School|University|Institution)\s*[:：].*$",
        r"(?m)^\s*(?:参赛队号|队号|学校|作者|单位|指导教师)\s*[:：].*$",
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
    blind_human_votes = [
        item for item in vote_list if item.judge_kind == "HUMAN" and bool(item.blind_verified)
    ]
    blind_human_vote_count = len(blind_human_votes)
    independent_vote_count = sum(item.judge_kind == "INDEPENDENT_MODEL" for item in vote_list)
    internal_vote_count = sum(item.judge_kind == "INTERNAL" for item in vote_list)

    # Build a consensus blind-human anchor per logical swap group.  A group is
    # usable only when every blind human preference available for that group
    # resolves to the same paper identity.  Provenance labels are never used here.
    blind_human_preferred: dict[tuple[str, str], str | None] = {}
    for vote in blind_human_votes:
        pair = pair_by_id[vote.pair_id]
        blind_human_preferred[(vote.judge_id, vote.pair_id)] = preferred_blind_id(vote, pair)

    blind_human_logical: dict[tuple[str, str], str] = {}
    blind_human_ids = sorted({item.judge_id for item in blind_human_votes})
    for judge_id in blind_human_ids:
        for swap_group, group_pairs in by_swap.items():
            choices = [
                blind_human_preferred.get((judge_id, pair.pair_id))
                for pair in group_pairs
                if blind_human_preferred.get((judge_id, pair.pair_id)) is not None
            ]
            if choices and len(set(choices)) == 1:
                blind_human_logical[(judge_id, swap_group)] = choices[0]

    blind_anchor_by_group: dict[str, str] = {}
    blind_anchor_disagreement_groups: list[str] = []
    for swap_group in by_swap:
        choices = [
            blind_human_logical[(judge_id, swap_group)]
            for judge_id in blind_human_ids
            if (judge_id, swap_group) in blind_human_logical
        ]
        if not choices:
            continue
        if len(set(choices)) == 1:
            blind_anchor_by_group[swap_group] = choices[0]
        else:
            blind_anchor_disagreement_groups.append(swap_group)

    for jid, row in discrimination.items():
        anchor_total = 0
        anchor_correct = 0
        for swap_group, expected in blind_anchor_by_group.items():
            choice = logical_choices.get((jid, swap_group))
            if choice is None:
                continue
            anchor_total += 1
            anchor_correct += int(choice == expected)
        row["checked_vs_blind_human"] = anchor_total
        row["correct_vs_blind_human"] = anchor_correct
        row["accuracy_vs_blind_human"] = (
            round(anchor_correct / anchor_total, 6) if anchor_total else None
        )

    # H1 is decided only from actual blind-human preference agreement.  Provenance
    # accuracy remains a diagnostic prior but cannot unlock the hypothesis verdict.
    hypothesis: HypothesisStatus = "INCONCLUSIVE"
    blind_anchor_group_count = len(blind_anchor_by_group)
    internal_anchor_accuracy: float | None = None
    internal_anchor_total = 0
    independent_anchor_accuracy: float | None = None
    independent_anchor_total = 0
    verdict_reason = "blind human anchor is still missing"
    if blind_anchor_group_count == 1:
        verdict_reason = "only one blind-human logical pair is anchored; at least two are required"
    elif blind_anchor_group_count >= 2:
        internal_anchor_hits = 0
        internal_anchor_total = 0
        for jid, row in discrimination.items():
            if judge_kind.get(jid) != "INTERNAL":
                continue
            internal_anchor_hits += int(row["correct_vs_blind_human"] or 0)
            internal_anchor_total += int(row["checked_vs_blind_human"] or 0)
        internal_anchor_accuracy = (
            internal_anchor_hits / internal_anchor_total if internal_anchor_total else None
        )
        independent_anchor_hits = 0
        independent_anchor_total = 0
        for jid, row in discrimination.items():
            if judge_kind.get(jid) != "INDEPENDENT_MODEL":
                continue
            independent_anchor_hits += int(row["correct_vs_blind_human"] or 0)
            independent_anchor_total += int(row["checked_vs_blind_human"] or 0)
        independent_anchor_accuracy = (
            independent_anchor_hits / independent_anchor_total if independent_anchor_total else None
        )
        pos = position_consistent / position_checked if position_checked else None
        if internal_anchor_accuracy is not None and internal_anchor_total >= 2 and internal_anchor_accuracy < 0.75:
            hypothesis = "SUPPORTED"
            verdict_reason = "internal judge disagrees materially with blind-human preferences across multiple logical pairs"
        elif (
            internal_anchor_accuracy is not None
            and internal_anchor_total >= 3
            and internal_anchor_accuracy >= 0.85
            and independent_anchor_accuracy is not None
            and independent_anchor_total >= 2
            and independent_anchor_accuracy >= 0.80
            and pos is not None
            and pos >= 0.95
        ):
            hypothesis = "REJECTED"
            verdict_reason = "internal judge aligns with multi-pair blind-human and independent-model anchors"
        else:
            verdict_reason = "available blind-human evidence is not yet decisive for H1"

    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "paper_count": len(paper_list),
        "pair_count": len(pair_list),
        "vote_count": len(vote_list),
        "human_vote_count": human_vote_count,
        "blind_human_vote_count": blind_human_vote_count,
        "blind_human_anchor_group_count": blind_anchor_group_count,
        "blind_human_anchor_disagreement_groups": sorted(blind_anchor_disagreement_groups),
        "internal_checked_vs_blind_human": internal_anchor_total,
        "internal_accuracy_vs_blind_human": (
            round(internal_anchor_accuracy, 6) if internal_anchor_accuracy is not None else None
        ),
        "independent_checked_vs_blind_human": independent_anchor_total,
        "independent_accuracy_vs_blind_human": (
            round(independent_anchor_accuracy, 6) if independent_anchor_accuracy is not None else None
        ),
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
    """Return only fields safe to expose to a blind judge.

    ``kind`` is deliberately private provenance.  Labels such as
    ``REAL_VS_CURRENT`` would reveal the comparison class and must never enter a
    blind judge payload.
    """

    return [
        {
            "pair_id": item.pair_id,
            "swap_group": item.swap_group,
            "left_id": item.left_id,
            "right_id": item.right_id,
        }
        for item in pairs
    ]


def identity_leakage_findings(text: str, *, forbidden_literals: Iterable[str] = ()) -> list[str]:
    """Return obvious identity/provenance leakage signals in anonymized text."""

    findings: list[str] = []
    patterns = {
        "award_label": r"\b(?:outstanding|finalist|meritorious|honorable\s+mention|o\s*[- ]?award|ams\s+award|vilfredo\s+pareto\s+award)\b",
        "award_label_zh": r"(?:全国大学生数学建模竞赛)?(?:一|二|三)等奖|国[一二三]|优秀论文",
        "team_control_label": r"\b(?:team\s*#|team\s+number|control\s+number|team\s+control\s+number)\b",
        "team_control_label_zh": r"参赛队号|队号",
        "institution_label": r"(?im)^\s*(?:author|authors|school|university|institution)\s*[:：]",
        "institution_label_zh": r"(?m)^\s*(?:学校|作者|单位|指导教师)\s*[:：]",
        "workstation_identity": r"\b(?:mathworkstation|workstation[_ -]?current|workstation[_ -]?older|generated[_ -]?sample|showcase)\b",
        "case_id": r"\b20\d{6}-(?:MCM|CUMCM)-\d{4}-[A-Z0-9]{4}\b",
    }
    for name, pattern in patterns.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            findings.append(name)
    lowered = text.lower()
    for literal in forbidden_literals:
        value = str(literal).strip()
        if value and value.lower() in lowered:
            findings.append(f"forbidden_literal:{value}")
    return sorted(set(findings))
