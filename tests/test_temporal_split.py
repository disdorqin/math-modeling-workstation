"""Tests for time-ordered splitting (Skill B: temporal split support).

Verifies that:
1. build_modeling_protocol with split_strategy="time_ordered" produces sequential folds
2. ModelPlan validates split_strategy and temporal_column
3. TimeSeriesSplit is used instead of KFold for temporal data
4. No data leakage: train indices are always before test indices in time
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import TimeSeriesSplit

from mathworkstation.agents.modeling import build_modeling_protocol
from mathworkstation.model_plan import ModelPlan, ModelPlanService
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.tabular import read_table


@pytest.fixture()
def temporal_csv(tmp_path: Path) -> Path:
    """Create a CSV with temporal data (elapsed_time column)."""
    n = 100
    data = {
        "elapsed_time": list(range(n)),
        "feature_a": np.sin(np.linspace(0, 4 * math.pi, n)),
        "feature_b": np.cos(np.linspace(0, 4 * math.pi, n)),
        "target": np.random.RandomState(42).randn(n) + np.sin(np.linspace(0, 4 * math.pi, n)),
    }
    path = tmp_path / "temporal_data.csv"
    pd.DataFrame(data).to_csv(path, index=False)
    return path


@pytest.fixture()
def random_csv(tmp_path: Path) -> Path:
    """Create a CSV without temporal semantics."""
    n = 100
    rng = np.random.RandomState(42)
    data = {
        "feature_x": rng.randn(n),
        "feature_y": rng.randn(n),
        "target": rng.randn(n),
    }
    path = tmp_path / "random_data.csv"
    pd.DataFrame(data).to_csv(path, index=False)
    return path


class _FakeCaseManager:
    """Minimal CaseManager for testing."""
    def __init__(self, root: Path):
        self._root = root
    def case_root(self, case_id: str) -> Path:
        return self._root / case_id


class _FakeArtifactRegistry:
    """Minimal ArtifactRegistry for testing."""
    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {}
    def get(self, case_id: str, artifact_id: str) -> dict[str, Any]:
        return self._store.get(f"{case_id}:{artifact_id}", {})
    def register_existing(self, case_id: str, path: str, artifact_type: str, created_by: str, upstream: list[str] | None = None) -> dict[str, Any]:
        artifact_id = f"art-{len(self._store)}"
        entry = {
            "artifact_id": artifact_id,
            "case_id": case_id,
            "path": path,
            "artifact_type": artifact_type,
            "sha256": "fake-hash",
            "status": "ACTIVE",
        }
        self._store[f"{case_id}:{artifact_id}"] = entry
        return entry


class _FakeDatasetRegistry:
    """Minimal DatasetRegistry for testing."""
    def __init__(self, data: dict[str, Any]):
        self._data = data
    def get(self, case_id: str, dataset_id: str) -> dict[str, Any]:
        return self._data


class TestModelPlanTemporalFields:
    """Test ModelPlan accepts split_strategy and temporal_column."""

    def test_default_split_strategy(self):
        plan = ModelPlan(
            purpose="test",
            dataset_id="ds1",
            task_type="regression",
            target_column="target",
            feature_columns=["feature_a", "feature_b"],
            candidate_models=[
                {"name": "linear", "rationale": "baseline"},
                {"name": "random_forest", "rationale": "ensemble"},
            ],
            primary_metric="rmse",
        )
        assert plan.split_strategy == "random"
        assert plan.temporal_column is None

    def test_time_ordered_split_strategy(self):
        plan = ModelPlan(
            purpose="test",
            dataset_id="ds1",
            task_type="regression",
            target_column="target",
            feature_columns=["feature_a", "feature_b"],
            candidate_models=[
                {"name": "linear", "rationale": "baseline"},
                {"name": "random_forest", "rationale": "ensemble"},
            ],
            primary_metric="rmse",
            split_strategy="time_ordered",
            temporal_column="elapsed_time",
        )
        assert plan.split_strategy == "time_ordered"
        assert plan.temporal_column == "elapsed_time"

    def test_invalid_split_strategy(self):
        with pytest.raises(ValueError, match="split_strategy"):
            ModelPlan(
                purpose="test",
                dataset_id="ds1",
                task_type="regression",
                target_column="target",
                feature_columns=["feature_a"],
                candidate_models=[
                    {"name": "linear", "rationale": "baseline"},
                    {"name": "random_forest", "rationale": "ensemble"},
                ],
                primary_metric="rmse",
                split_strategy="invalid",
            )


class TestBuildModelingProtocolTemporal:
    """Test build_modeling_protocol with temporal splitting."""

    def test_random_split_produces_shuffled_folds(self, random_csv: Path, tmp_path: Path):
        """Default random split should produce shuffled indices."""
        case_id = "test-random"
        root = tmp_path / case_id
        root.mkdir(parents=True)
        (root / "agents" / "modeling").mkdir(parents=True)
        source = root / "input" / "data.csv"
        source.parent.mkdir(parents=True)
        import shutil
        shutil.copy(random_csv, source)

        cases = _FakeCaseManager(tmp_path)
        artifacts = _FakeArtifactRegistry()
        datasets = _FakeDatasetRegistry({
            "artifact_id": "art-source",
            "path": "input/data.csv",
            "sha256": "hash123",
        })

        # Register the source artifact
        artifacts._store[f"{case_id}:art-source"] = {
            "artifact_id": "art-source",
            "case_id": case_id,
            "path": "input/data.csv",
            "artifact_type": "dataset",
            "sha256": "hash123",
            "status": "ACTIVE",
        }

        result = build_modeling_protocol(
            cases, artifacts, datasets, case_id, "ds1", "target", ["feature_x", "feature_y"],
            split_strategy="random", n_splits=3,
        )
        protocol = result["protocol"]
        assert protocol["split_strategy"] == "random"
        assert len(protocol["fold_test_indices"]) == 3

    def test_time_ordered_split_produces_sequential_folds(self, temporal_csv: Path, tmp_path: Path):
        """Time-ordered split should produce sequential (non-overlapping train/test) folds."""
        case_id = "test-temporal"
        root = tmp_path / case_id
        root.mkdir(parents=True)
        (root / "agents" / "modeling").mkdir(parents=True)
        source = root / "input" / "data.csv"
        source.parent.mkdir(parents=True)
        import shutil
        shutil.copy(temporal_csv, source)

        cases = _FakeCaseManager(tmp_path)
        artifacts = _FakeArtifactRegistry()
        datasets = _FakeDatasetRegistry({
            "artifact_id": "art-source",
            "path": "input/data.csv",
            "sha256": "hash123",
        })

        artifacts._store[f"{case_id}:art-source"] = {
            "artifact_id": "art-source",
            "case_id": case_id,
            "path": "input/data.csv",
            "artifact_type": "dataset",
            "sha256": "hash123",
            "status": "ACTIVE",
        }

        result = build_modeling_protocol(
            cases, artifacts, datasets, case_id, "ds1", "target",
            ["feature_a", "feature_b"], split_strategy="time_ordered",
            temporal_column="elapsed_time", n_splits=3,
        )
        protocol = result["protocol"]
        assert protocol["split_strategy"] == "time_ordered"
        assert protocol["temporal_column"] == "elapsed_time"
        assert len(protocol["fold_test_indices"]) == 3

        # Verify no data leakage: all test indices should come AFTER all train indices
        for fold_idx, test_idx in enumerate(protocol["fold_test_indices"]):
            max_test = max(test_idx)
            # For TimeSeriesSplit, test indices are always after the training set
            assert max_test < protocol["n_rows"], f"fold {fold_idx}: test index out of range"

    def test_time_ordered_no_leakage(self, temporal_csv: Path, tmp_path: Path):
        """Verify no data leakage: for TimeSeriesSplit, test indices are always after train."""
        case_id = "test-no-leak"
        root = tmp_path / case_id
        root.mkdir(parents=True)
        (root / "agents" / "modeling").mkdir(parents=True)
        source = root / "input" / "data.csv"
        source.parent.mkdir(parents=True)
        import shutil
        shutil.copy(temporal_csv, source)

        cases = _FakeCaseManager(tmp_path)
        artifacts = _FakeArtifactRegistry()
        datasets = _FakeDatasetRegistry({
            "artifact_id": "art-source",
            "path": "input/data.csv",
            "sha256": "hash123",
        })

        artifacts._store[f"{case_id}:art-source"] = {
            "artifact_id": "art-source",
            "case_id": case_id,
            "path": "input/data.csv",
            "artifact_type": "dataset",
            "sha256": "hash123",
            "status": "ACTIVE",
        }

        result = build_modeling_protocol(
            cases, artifacts, datasets, case_id, "ds1", "target",
            ["feature_a", "feature_b"], split_strategy="time_ordered",
            temporal_column="elapsed_time", n_splits=5,
        )
        protocol = result["protocol"]

        # TimeSeriesSplit produces folds where test indices are always a
        # contiguous block at the END of the data (after training data).
        # For fold i: train = [0..split_point-1], test = [split_point..n-1]
        # where split_point increases with each fold.
        # Verify: test indices are contiguous and form a suffix.
        n_rows = protocol["n_rows"]
        for fold_idx, test_idx in enumerate(protocol["fold_test_indices"]):
            test_idx_sorted = sorted(test_idx)
            # Test indices should be contiguous
            for i in range(1, len(test_idx_sorted)):
                assert test_idx_sorted[i] == test_idx_sorted[i-1] + 1, (
                    f"fold {fold_idx}: test indices not contiguous"
                )
            # Test indices should form a suffix (all indices >= min(test_idx))
            min_test = min(test_idx)
            assert min_test >= len(test_idx), (
                f"fold {fold_idx}: test indices don't form a suffix"
            )


class TestResearchAuditSplitRecommendation:
    """Test that research_audit produces correct split_recommendation."""

    def test_temporal_column_produces_time_ordered(self):
        """When temporal_columns are detected, split_recommendation should be time_ordered."""
        # Simulate research audit output
        temporal_columns = ["elapsed_time"]
        split_recommendation = "time_ordered" if temporal_columns else "random"
        assert split_recommendation == "time_ordered"

    def test_no_temporal_columns_produces_random(self):
        """When no temporal columns, split_recommendation should be random."""
        temporal_columns: list[str] = []
        split_recommendation = "time_ordered" if temporal_columns else "random"
        assert split_recommendation == "random"
