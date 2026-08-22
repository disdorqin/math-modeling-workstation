from mathworkstation.modeling_skills import ModelingSkillRetriever


def test_repository_modeling_skills_are_retrievable_by_task_family() -> None:
    retriever = ModelingSkillRetriever()
    assert retriever.available is True

    prediction = retriever.retrieve("forecasting", "future daily time series prediction")
    assert {item.name for item in prediction} >= {"mm-model-selector", "mm-prediction-models"}
    prediction_skill = next(item for item in prediction if item.name == "mm-prediction-models")
    assert "GM(1,1)" in prediction_skill.method_hints
    assert "time-series baseline" in prediction_skill.method_hints
    assert prediction_skill.quality_checks
    assert prediction_skill.when_not_to_use

    optimization = retriever.retrieve("optimization", "resource allocation with decision variables and constraints")
    optimization_skill = next(item for item in optimization if item.name == "mm-optimization-models")
    assert "linear programming" in optimization_skill.method_hints
    assert "integer programming" in optimization_skill.method_hints


def test_skill_retriever_returns_no_fake_skill_for_synthesis() -> None:
    retriever = ModelingSkillRetriever()
    assert retriever.retrieve("synthesis", "write a letter") == []
