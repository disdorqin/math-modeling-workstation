from mathworkstation.c_problem_paper_profiles import CProblemPaperProfileRegistry
from mathworkstation.competition_paper_standard import CompetitionPaperStandardRegistry


def test_standard_registry_profiles():
    registry = CompetitionPaperStandardRegistry()
    cumcm = registry.resolve("CUMCM")
    mcm = registry.resolve("MCM")
    assert cumcm.profile_id == "CUMCM_C"
    assert mcm.profile_id == "MCM_C"
    assert cumcm.hard_constraint("body_max_pages") == 30
    assert mcm.hard_constraint("total_page_limit") == 25


def test_standard_registry_cumcm_format_constraints():
    cumcm = CompetitionPaperStandardRegistry().resolve("CUMCM")
    assert cumcm.hard_constraint("paper_size") == "A4"
    assert cumcm.hard_constraint("minimum_margin_cm") == 2.5
    assert cumcm.hard_constraint("table_of_contents") == "FORBIDDEN"
    assert cumcm.hard_constraint("electronic_first_page") == "abstract_special_page"
    assert cumcm.hard_constraint("electronic_excludes_commitment_and_number_pages") is True
    assert cumcm.official_font_is_fixed is False


def test_standard_registry_ai_requirements():
    ai = CompetitionPaperStandardRegistry().resolve("国赛").ai_use_hard_constraints
    assert ai["manual_review_of_ai_content_required"] is True
    assert ai["declaration_before_references_required"] is True
    assert ai["supporting_ai_usage_pdf_required_if_used"] is True


def test_standard_registry_research_refresh_and_modeling_anti_patterns():
    registry = CompetitionPaperStandardRegistry()
    assert registry.research_refresh_policy.required_before_each_v3_stage is True
    forbidden = set(registry.cross_competition_modeling_rules["forbidden_default_behavior"])
    assert "one_unrelated_model_per_question" in forbidden
    assert "algorithm_zoo_for_prestige" in forbidden
    assert "equation_count_as_modeling_depth" in forbidden
    assert "figure_count_as_visual_quality" in forbidden


def test_existing_profile_registry_exposes_standard():
    registry = CProblemPaperProfileRegistry()
    assert registry.resolve("CUMCM").profile_id == registry.resolve_standard("CUMCM").profile_id
