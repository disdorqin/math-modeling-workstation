from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import read_json


Competition = Literal["CUMCM", "MCM"]


class CProblemCorpusEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competition: Competition
    year: int
    problem_letter: str
    problem: str
    paper_count: int
    asset: str
    task_mix: list[str] = Field(default_factory=list)
    signature: list[str] = Field(default_factory=list)


class CProblemPrior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    meaning: str
    hard_gate: bool


class CProblemBenchmarkRegistry(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int
    scope: str
    primary_benchmark_policy: str
    source_policy: str = ""
    benchmark_status: dict[str, str] = Field(default_factory=dict)
    corpora: list[CProblemCorpusEntry]
    shared_c_problem_priors: list[CProblemPrior]
    total_reference_papers: int

    def validate_primary_gate(self, *, repo_root: Path | None = None) -> None:
        if self.scope != "C_PROBLEM_ONLY":
            raise ValueError("PRIMARY_BENCHMARK_SCOPE_MUST_BE_C_PROBLEM_ONLY")
        if not self.corpora:
            raise ValueError("C_PROBLEM_BENCHMARK_REQUIRES_CORPORA")
        if any(item.problem_letter.upper() != "C" for item in self.corpora):
            raise ValueError("NON_C_PROBLEM_IN_PRIMARY_BENCHMARK")

        cumcm = [item for item in self.corpora if item.competition == "CUMCM"]
        mcm = [item for item in self.corpora if item.competition == "MCM"]
        if len(cumcm) < 3:
            raise ValueError("PRIMARY_BENCHMARK_REQUIRES_AT_LEAST_3_CUMCM_C_PROBLEMS")
        if len(mcm) < 2:
            raise ValueError("PRIMARY_BENCHMARK_REQUIRES_AT_LEAST_2_MCM_C_PROBLEMS")

        counted = sum(item.paper_count for item in self.corpora)
        if counted != self.total_reference_papers:
            raise ValueError("REFERENCE_PAPER_COUNT_MISMATCH")
        if counted < 15:
            raise ValueError("C_PROBLEM_BENCHMARK_CORPUS_TOO_SMALL")

        prior_names = {item.name for item in self.shared_c_problem_priors}
        required = {
            "question_chain_not_independent_model_zoo",
            "data_and_constraint_driven_model_choice",
            "quantified_answers_in_high_visibility_sections",
            "validation_matches_claim_type",
            "algorithm_diversity_is_normal",
            "decision_or_deliverable_must_be_evidence_backed",
        }
        missing = required - prior_names
        if missing:
            raise ValueError("C_PROBLEM_BENCHMARK_REQUIRED_PRIORS_MISSING:" + ",".join(sorted(missing)))

        if repo_root is not None:
            missing_assets = [item.asset for item in self.corpora if not (repo_root / item.asset).is_file()]
            if missing_assets:
                raise ValueError("C_PROBLEM_BENCHMARK_ASSETS_MISSING:" + ",".join(missing_assets))


def load_c_problem_benchmark(path: str | Path, *, repo_root: Path | None = None) -> CProblemBenchmarkRegistry:
    source = Path(path)
    payload = read_json(source)
    registry = CProblemBenchmarkRegistry.model_validate(payload)
    registry.validate_primary_gate(repo_root=repo_root)
    return registry
