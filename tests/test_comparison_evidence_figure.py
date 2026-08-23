from mathworkstation.comparison_evidence_figure import comparison_figure_specs


def test_comparison_specs_use_only_persisted_executed_runs() -> None:
    payload = {
        "subproblem_id": "SP1",
        "primary_metric": "rmse",
        "metric_direction": "MINIMIZE",
        "accepted": {
            "method": "Holt exponential smoothing",
            "value": 12.0,
        },
        "alternatives": [
            {"method": "ridge time trend", "value": 14.0},
        ],
        "best_method": "Holt exponential smoothing",
        "stress_test_sizes": [0.15, 0.2, 0.25],
        "stress_runs": [
            {
                "method": "Holt exponential smoothing",
                "is_accepted": True,
                "metric_by_test_size": {"0.15": 12.5, "0.2": 12.0, "0.25": 12.8},
            },
            {
                "method": "ridge time trend",
                "is_accepted": False,
                "metric_by_test_size": {"0.15": 14.5, "0.2": 14.0, "0.25": 15.1},
            },
        ],
        "robust_best_method": "Holt exponential smoothing",
    }

    specs = comparison_figure_specs(payload)
    assert [item["semantic_kind"] for item in specs] == [
        "alternative_model_metric_comparison",
        "alternative_model_stress_comparison",
    ]
    metric = specs[0]
    assert metric["labels"] == ["Holt exponential smoothing", "ridge time trend"]
    assert metric["values"] == [12.0, 14.0]
    stress = specs[1]
    assert len(stress["series"]) == 2
    assert stress["series"][0]["x"] == [0.15, 0.2, 0.25]


def test_comparison_specs_never_invent_missing_comparison_evidence() -> None:
    assert comparison_figure_specs({"primary_metric": "rmse", "accepted": {"method": "Holt", "value": 12.0}}) == []

    specs = comparison_figure_specs(
        {
            "primary_metric": "balanced_accuracy",
            "metric_direction": "MAXIMIZE",
            "accepted": {"method": "logistic", "value": 0.72},
            "alternatives": [{"method": "random forest", "value": 0.75}],
            "stress_runs": [],
        }
    )
    assert len(specs) == 1
    assert specs[0]["semantic_kind"] == "alternative_model_metric_comparison"
