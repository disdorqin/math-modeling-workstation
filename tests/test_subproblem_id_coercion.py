"""Tests for _fill_required_fields type coercion."""
from mathworkstation.structured_llm import _fill_required_fields
from mathworkstation.paper_contracts import SubproblemContract


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
