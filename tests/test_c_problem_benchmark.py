from __future__ import annotations

from pathlib import Path

import pytest

from mathworkstation.c_problem_benchmark import CProblemBenchmarkRegistry, load_c_problem_benchmark


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "config" / "ref_models" / "c_problem_excellent_benchmark_v1.json"


def test_primary_c_problem_benchmark_is_c_only_and_meets_3_plus_2_gate() -> None:
    registry = load_c_problem_benchmark(REGISTRY_PATH, repo_root=REPO_ROOT)

    assert registry.scope == "C_PROBLEM_ONLY"
    assert all(item.problem_letter == "C" for item in registry.corpora)
    assert sum(item.competition == "CUMCM" for item in registry.corpora) >= 3
    assert sum(item.competition == "MCM" for item in registry.corpora) >= 2
    assert registry.total_reference_papers == 21


def test_primary_c_problem_benchmark_rejects_non_c_problem() -> None:
    registry = load_c_problem_benchmark(REGISTRY_PATH, repo_root=REPO_ROOT)
    payload = registry.model_dump(mode="python")
    payload["corpora"][0]["problem_letter"] = "A"
    bad = CProblemBenchmarkRegistry.model_validate(payload)

    with pytest.raises(ValueError, match="NON_C_PROBLEM_IN_PRIMARY_BENCHMARK"):
        bad.validate_primary_gate(repo_root=REPO_ROOT)


def test_primary_c_problem_benchmark_keeps_algorithm_frequency_as_prior_not_mandate() -> None:
    registry = load_c_problem_benchmark(REGISTRY_PATH, repo_root=REPO_ROOT)
    priors = {item.name: item for item in registry.shared_c_problem_priors}

    assert priors["algorithm_diversity_is_normal"].hard_gate is True
    assert "must never force one method" in priors["algorithm_diversity_is_normal"].meaning
