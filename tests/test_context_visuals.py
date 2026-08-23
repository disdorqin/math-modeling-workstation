from __future__ import annotations

from mathworkstation.context_visuals import ContextVisualCandidate, ContextVisualPolicy


def _candidate(**overrides: object) -> ContextVisualCandidate:
    payload: dict[str, object] = {
        "candidate_id": "produce-context",
        "title": "Produce section",
        "page_url": "https://commons.wikimedia.org/wiki/File:Fruit_section_of_a_grocery_store.jpg",
        "asset_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/Fruit_section_of_a_grocery_store.jpg?width=1600",
        "provider": "Wikimedia Commons",
        "author": "Alabama Extension",
        "license_id": "CC0 1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "description": "Reality context only.",
    }
    payload.update(overrides)
    return ContextVisualCandidate.model_validate(payload)


def test_policy_accepts_real_cc0_wikimedia_context() -> None:
    assessment = ContextVisualPolicy().assess(_candidate())
    assert assessment.gate == "PASS"
    assert "Alabama Extension" in assessment.attribution_text
    assert "CC0 1.0" in assessment.attribution_text


def test_policy_rejects_ai_generated_reality_context() -> None:
    assessment = ContextVisualPolicy().assess(_candidate(ai_generated=True))
    assert assessment.gate == "REJECT"
    assert "REALITY_CONTEXT_CANNOT_BE_AI_GENERATED" in assessment.reasons


def test_policy_rejects_unknown_host_and_license() -> None:
    assessment = ContextVisualPolicy().assess(
        _candidate(
            page_url="https://example.com/photo",
            asset_url="https://cdn.example.com/photo.jpg",
            license_id="All rights reserved",
        )
    )
    assert assessment.gate == "REJECT"
    assert "SOURCE_PAGE_HOST_NOT_TRUSTED" in assessment.reasons
    assert "ASSET_HOST_NOT_TRUSTED" in assessment.reasons
    assert "REUSE_LICENSE_NOT_ALLOWED" in assessment.reasons
