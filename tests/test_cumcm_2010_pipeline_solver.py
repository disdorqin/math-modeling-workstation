from __future__ import annotations

from mathworkstation.solver_engine import PipelineLayoutOptimizationSolverPlugin, SolverRegistry
from mathworkstation.validation_protocol import ValidationRunner


def _plan(*, q3: bool = False, force_zero_shared: bool = False, surcharge: float = 21.5) -> dict:
    return {
        "solver_method": "pipeline_layout_continuous",
        "factory_a_height": 5.0,
        "factory_b_height": 8.0,
        "factory_b_x": 20.0,
        "urban_boundary_x": 15.0,
        "a_nonshared_cost": 5.6 if q3 else 7.2,
        "b_nonshared_cost": 6.0 if q3 else 7.2,
        "shared_cost": 7.2,
        "urban_surcharge": surcharge,
        "force_zero_shared": force_zero_shared,
    }


def test_cumcm_2010_q2_geometry_solver_reproduces_published_reference_without_hardcoded_solution() -> None:
    plugin = PipelineLayoutOptimizationSolverPlugin()
    plan = _plan()
    result = plugin.solve("optimization", plan, None)
    diagnostics = plugin.diagnose("optimization", plan, result)
    assessment = ValidationRunner().assess("optimization", plan, result, diagnostics)

    assert abs(result["objective_value"] - 282.6973) < 1e-3
    assert abs(result["solution"]["station_x"] - 5.4494) < 2e-3
    assert abs(result["solution"]["shared_junction_y"] - 1.853788) < 2e-3
    assert abs(result["solution"]["urban_boundary_crossing_y"] - 7.367829) < 2e-3
    assert assessment.gate == "PASS"
    assert assessment.protocol_id == "optimization.continuous-geometry.v1"
    assert len(result["sensitivity_runs"]) == 2


def test_cumcm_2010_q3_geometry_solver_matches_independent_excellent_solution() -> None:
    plugin = PipelineLayoutOptimizationSolverPlugin()
    plan = _plan(q3=True)
    plan["compare_no_shared"] = True
    result = plugin.solve("optimization", plan, None)

    assert abs(result["objective_value"] - 251.9685) < 1e-3
    assert abs(result["solution"]["station_x"] - 6.733784) < 2e-3
    assert abs(result["solution"]["shared_junction_y"] - 0.138899) < 2e-3
    assert abs(result["solution"]["urban_boundary_crossing_y"] - 7.279503) < 2e-3
    assert abs(result["no_shared_comparison"]["objective_value"] - 251.9755) < 2e-3
    assert 0.0 < result["metrics"]["shared_cost_advantage"] < 0.02


def test_cumcm_2010_long_term_no_shared_variant_is_solved_not_copied() -> None:
    plugin = PipelineLayoutOptimizationSolverPlugin()
    result = plugin.solve("optimization", _plan(q3=True, force_zero_shared=True), None)

    assert result["route_lengths"]["shared_EG"] == 0.0
    assert abs(result["objective_value"] - 251.9755) < 2e-3
    assert abs(result["solution"]["station_x"] - 6.752954) < 3e-3


def test_pipeline_solver_is_parameter_sensitive_and_registered_before_generic_grid() -> None:
    registry = SolverRegistry()
    normal = registry.resolve("optimization", _plan())
    low_surcharge = normal.solve("optimization", _plan(surcharge=15.0), None)
    high_surcharge = normal.solve("optimization", _plan(surcharge=30.0), None)

    assert normal.name == "gold.pipeline_layout_continuous"
    assert low_surcharge["objective_value"] < high_surcharge["objective_value"]
    assert abs(low_surcharge["solution"]["urban_boundary_crossing_y"] - high_surcharge["solution"]["urban_boundary_crossing_y"]) > 1e-3
