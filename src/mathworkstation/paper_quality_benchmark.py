from __future__ import annotations

import re
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .abstract_quality import extract_abstract
from .io_utils import atomic_write_json, now_iso, read_json


BenchmarkStatus = Literal["PASS", "REVIEW"]


class PaperQualityDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    status: BenchmarkStatus
    observed: float
    benchmark: float
    evidence: str
    gap: str = ""


class PaperQualityBenchmarkAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str | None = None
    profile_id: str
    gate: BenchmarkStatus
    score: float = Field(ge=0.0, le=100.0)
    source_corpora: list[str]
    dimensions: list[PaperQualityDimension]
    checked_at: str


class PaperQualityBenchmarkService:
    """Calibrate a generated paper against the existing excellent C-paper corpus.

    This is intentionally a REVIEW calibration, not a quota system.  Excellent
    papers provide realistic density ranges (abstract information, figures,
    tables, references), but a paper is never told to invent models or add
    decorative charts merely to match a count.
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self.registry = read_json(self.repo_root / "config" / "ref_models" / "c_problem_excellent_benchmark_v1.json")
        distilled_path = self.repo_root / "config" / "ref_models" / "distilled_prior_bank_v1.json"
        self.distilled_prior_bank = read_json(distilled_path) if distilled_path.is_file() else {}
        modern_path = self.repo_root / "config" / "ref_models" / "modern_competition_paper_prior_v1.json"
        self.modern_prior = read_json(modern_path) if modern_path.is_file() else {}

    def assess(
        self,
        paper_text: str,
        figures: list[dict[str, Any]],
        *,
        profile_id: str,
        case_id: str | None = None,
    ) -> PaperQualityBenchmarkAssessment:
        peer = self._peer_profile(profile_id)
        abstract = extract_abstract(paper_text)
        abstract_units = _text_units(abstract)
        abstract_numbers = len(re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?", abstract))
        figure_count = len([item for item in figures if item.get("status") == "FINAL"])
        table_count = _table_count(paper_text)
        reference_count = _reference_count(paper_text, profile_id)

        dimensions = [
            _range_dimension(
                "excellent_abstract_density",
                abstract_units,
                peer["abstract_units"],
                low_ratio=0.55,
                high_ratio=1.45,
                evidence=f"generated abstract information units={abstract_units}; excellent-C peer median≈{peer['abstract_units']:.1f}",
                gap="Keep the abstract high-information, but compress or expand only with already-supported task methods/results.",
            ),
            _minimum_dimension(
                "excellent_abstract_numeric_density",
                abstract_numbers,
                max(2.0, peer["abstract_numeric_tokens"] * 0.45),
                evidence=f"generated abstract numeric tokens={abstract_numbers}; excellent-C peer median≈{peer['abstract_numeric_tokens']:.1f}",
                gap="More of the already-computed headline answers should appear in the abstract; do not manufacture extra numbers.",
            ),
            _minimum_dimension(
                "excellent_figure_density",
                figure_count,
                max(2.0, peer["figure_mentions"] * 0.45),
                evidence=f"FINAL evidence figures={figure_count}; excellent-C peer textual figure mentions median≈{peer['figure_mentions']:.1f}",
                gap="Current visual argument is thinner than the excellent-paper corpus. Add only evidence-matched figures such as sensitivity, relation, state, or uncertainty plots.",
            ),
            _minimum_dimension(
                "excellent_table_density",
                table_count,
                max(2.0, peer["table_mentions"] * 0.35),
                evidence=f"paper table count≈{table_count}; excellent-C peer textual table mentions median≈{peer['table_mentions']:.1f}",
                gap="Use compact result/parameter/comparison tables where they carry information better than prose; do not split tables for quota padding.",
            ),
        ]
        if peer["reference_entries"] > 0:
            dimensions.append(
                _minimum_dimension(
                    "excellent_reference_density",
                    reference_count,
                    max(3.0, peer["reference_entries"] * 0.5),
                    evidence=f"verified references rendered={reference_count}; MCM C excellent-paper median≈{peer['reference_entries']:.1f}",
                    gap="Bibliography is sparse relative to the peer corpus; add only verified method/domain/data references that genuinely support the paper.",
                )
            )

        score = sum(item_status_score(item.status) for item in dimensions) / len(dimensions)
        gate: BenchmarkStatus = "PASS" if all(item.status == "PASS" for item in dimensions) else "REVIEW"
        return PaperQualityBenchmarkAssessment(
            case_id=case_id,
            profile_id=profile_id,
            gate=gate,
            score=round(score, 2),
            source_corpora=peer["source_corpora"],
            dimensions=dimensions,
            checked_at=now_iso(),
        )

    def persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        assessment: PaperQualityBenchmarkAssessment,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "review" / "paper_quality_benchmark" / "assessment.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "excellent_c_paper_quality_benchmark",
            "paper_quality_benchmark",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}

    def _peer_profile(self, profile_id: str) -> dict[str, Any]:
        competition = "CUMCM" if profile_id == "CUMCM_C" else "MCM"
        slice_id = f"competition:{competition}:C:modern"
        distilled = (self.distilled_prior_bank.get("slices") or {}).get(slice_id) or {}
        distilled_metrics = distilled.get("style_metrics") or {}
        if distilled_metrics and int(distilled.get("parsed_count") or 0) >= 4:
            return {
                "abstract_units": float(distilled_metrics.get("weighted_median_abstract_units", 0.0)),
                "abstract_numeric_tokens": float(distilled_metrics.get("weighted_median_abstract_numeric_tokens", 0.0)),
                "figure_mentions": float(distilled_metrics.get("weighted_median_figure_mentions", 0.0)),
                "table_mentions": float(distilled_metrics.get("weighted_median_table_mentions", 0.0)),
                # Deliberately excluded: the fast parser can over-count numbered
                # list items as bibliography entries. VerifiedReference remains
                # the source of bibliography truth.
                "reference_entries": 0.0,
                "source_corpora": [
                    f"distilled_prior_bank_v1:{slice_id}:papers={int(distilled.get('paper_count') or 0)}:parsed={int(distilled.get('parsed_count') or 0)}"
                ],
            }

        modern_profile = (self.modern_prior.get("profiles") or {}).get(profile_id) or {}
        modern_metrics = modern_profile.get("metrics") or {}
        if modern_metrics:
            return {
                "abstract_units": float(modern_metrics.get("abstract_units", 0.0)),
                "abstract_numeric_tokens": float(modern_metrics.get("abstract_numeric_tokens", 0.0)),
                "figure_mentions": float(modern_metrics.get("figure_mentions", 0.0)),
                "table_mentions": float(modern_metrics.get("table_mentions", 0.0)),
                # The current batch parser intentionally does not hard-gate on
                # reference counts because numeric-list lines can inflate that
                # signal in some PDFs. Bibliography truth remains covered by the
                # verified-reference subsystem instead.
                "reference_entries": 0.0,
                "source_corpora": [
                    str(modern_profile.get("source") or f"modern_{profile_id}_distillation")
                ],
            }

        rows: list[dict[str, float | str]] = []
        sources: list[str] = []
        for corpus in self.registry.get("corpora", []):
            if corpus.get("competition") != competition:
                continue
            asset = self.repo_root / str(corpus["asset"])
            payload = read_json(asset)
            sources.append(str(corpus.get("problem") or asset.name))
            if competition == "CUMCM":
                metrics = payload.get("medians") or {}
                if metrics:
                    rows.append(
                        {
                            "abstract_units": float(metrics.get("abstract_tokens", 0.0)),
                            "abstract_numeric_tokens": float(metrics.get("abstract_numeric_tokens", 0.0)),
                            "figure_mentions": float(metrics.get("figure_mentions", 0.0)),
                            "table_mentions": float(metrics.get("table_mentions", 0.0)),
                            "reference_entries": 0.0,
                        }
                    )
            else:
                metrics = payload.get("corpus") or {}
                if metrics:
                    rows.append(
                        {
                            "abstract_units": float(metrics.get("median_abstract_word_count", 0.0)),
                            "abstract_numeric_tokens": float(metrics.get("median_abstract_numeric_tokens", 0.0)),
                            "figure_mentions": float(metrics.get("median_figure_mentions", 0.0)),
                            "table_mentions": float(metrics.get("median_table_mentions", 0.0)),
                            "reference_entries": float(metrics.get("median_reference_entries", 0.0)),
                        }
                    )
        if not rows:
            raise ValueError(f"EXCELLENT_C_PAPER_STYLE_BENCHMARK_UNAVAILABLE:{profile_id}")
        keys = ["abstract_units", "abstract_numeric_tokens", "figure_mentions", "table_mentions", "reference_entries"]
        result: dict[str, Any] = {
            key: float(median([float(row[key]) for row in rows if float(row[key]) > 0]))
            if any(float(row[key]) > 0 for row in rows)
            else 0.0
            for key in keys
        }
        result["source_corpora"] = sources
        return result


def _range_dimension(
    name: str,
    observed: float,
    benchmark: float,
    *,
    low_ratio: float,
    high_ratio: float,
    evidence: str,
    gap: str,
) -> PaperQualityDimension:
    low, high = benchmark * low_ratio, benchmark * high_ratio
    passed = low <= observed <= high
    return PaperQualityDimension(
        dimension=name,
        status="PASS" if passed else "REVIEW",
        observed=float(observed),
        benchmark=float(benchmark),
        evidence=evidence + f"; calibration band≈[{low:.1f}, {high:.1f}]",
        gap="" if passed else gap,
    )


def _minimum_dimension(
    name: str,
    observed: float,
    threshold: float,
    *,
    evidence: str,
    gap: str,
) -> PaperQualityDimension:
    passed = observed >= threshold
    return PaperQualityDimension(
        dimension=name,
        status="PASS" if passed else "REVIEW",
        observed=float(observed),
        benchmark=float(threshold),
        evidence=evidence + f"; conservative review threshold≈{threshold:.1f}",
        gap="" if passed else gap,
    )


def _text_units(text: str) -> int:
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    english = re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text)
    return len(chinese) + len(english)


def _table_count(text: str) -> int:
    captions = re.findall(r"(?im)^\s*(?:\*\*)?(?:表\s*\d+|table\s+\d+)[^\n]*", text)
    markdown_headers = re.findall(r"(?m)^\|[^\n]+\|\s*$\n^\|\s*:?-+", text)
    return max(len(captions), len(markdown_headers))


def _reference_count(text: str, profile_id: str) -> int:
    heading = r"参考文献" if profile_id == "CUMCM_C" else r"References"
    match = re.search(rf"(?im)^#\s*\d*\.?\s*{heading}\s*$", text)
    if not match:
        return 0
    rest = text[match.end():]
    stop = re.search(r"(?im)^#\s+", rest)
    section = rest[: stop.start()] if stop else rest
    return len(re.findall(r"(?m)^\s*\[?\d+\]?\s*[.、)]", section))


def item_status_score(status: BenchmarkStatus) -> float:
    return 100.0 if status == "PASS" else 55.0
