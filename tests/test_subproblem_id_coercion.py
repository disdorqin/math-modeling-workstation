"""Tests for _fill_required_fields type coercion."""
from mathworkstation.structured_llm import _fill_required_fields
from mathworkstation.paper_contracts import SubproblemContract
from mathworkstation.model_plan import ModelPlan


def test_literal_schema_version_drift_falls_back_to_default():
    """schema_version 2 (echoed from the catalog) -> Literal[1] default."""
    data = {
        "schema_version": 2,
        "purpose": "Plan",
        "dataset_id": "d1",
        "task_type": "regression",
        "target_column": "y",
        "feature_columns": ["a", "b"],
        "candidate_models": [
            {"name": "linear", "rationale": "baseline"},
            {"name": "ridge", "rationale": "regularised"},
        ],
        "primary_metric": "rmse",
    }
    result = _fill_required_fields(data, ModelPlan)
    assert result["schema_version"] == 1


def test_literal_task_type_drift_picks_first_allowed():
    """Invalid task_type (no default) -> first allowed literal, pipeline lives."""
    data = {
        "schema_version": 1,
        "purpose": "Plan",
        "dataset_id": "d1",
        "task_type": "clustering",
        "target_column": "y",
        "feature_columns": ["a", "b"],
        "candidate_models": [
            {"name": "linear", "rationale": "baseline"},
            {"name": "ridge", "rationale": "regularised"},
        ],
        "primary_metric": "rmse",
    }
    result = _fill_required_fields(data, ModelPlan)
    assert result["task_type"] == "regression"  # first allowed literal



def test_integer_subproblem_id_coerced_and_padded():
    """int 1 → str 'SP1' (min_length=3 satisfied)."""
    data = {"subproblem_id": 1, "title": "Test", "objective": "Test obj"}
    result = _fill_required_fields(data, SubproblemContract)
    assert isinstance(result["subproblem_id"], str)
    assert result["subproblem_id"] == "SI1"
    assert len(result["subproblem_id"]) >= 3


def test_integer_subproblem_id_already_long_enough():
    """int 100 → str '100' (already 3 chars, no padding needed)."""
    data = {"subproblem_id": 100, "title": "Test", "objective": "Test obj"}
    result = _fill_required_fields(data, SubproblemContract)
    assert result["subproblem_id"] == "100"


def test_float_subproblem_id_coerced():
    """float 2.5 → str '2.5' (5 chars, min_length satisfied)."""
    data = {"subproblem_id": 2.5, "title": "Test", "objective": "Test obj"}
    result = _fill_required_fields(data, SubproblemContract)
    assert result["subproblem_id"] == "2.5"


def test_string_subproblem_id_unchanged():
    data = {"subproblem_id": "ABC", "title": "Test", "objective": "Test obj"}
    result = _fill_required_fields(data, SubproblemContract)
    assert result["subproblem_id"] == "ABC"


def test_none_subproblem_id_unchanged():
    data = {"subproblem_id": None, "title": "Test", "objective": "Test obj"}
    result = _fill_required_fields(data, SubproblemContract)
    assert result["subproblem_id"] is None
