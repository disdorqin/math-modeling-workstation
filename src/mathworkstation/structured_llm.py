from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .paper_contracts import SubproblemContract

from .llm.prompts import PromptRegistry
from .llm.service import CaseLLMService


def _camel_to_snake(name: str) -> str:
    """'subProblemId' -> 'sub_problem_id' (best-effort)."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


#: Semantic key aliases a real LLM commonly emits for a schema field. This is
#: a *best-effort* normalisation for structural drift, never a source of truth.
_SEMANTIC_ALIASES: dict[str, set[str]] = {
    "description": {"title", "objective", "summary", "detail"},
    "name": {"title", "label"},
    "title": {"name", "description"},
    "objective": {"description", "goal", "purpose"},
}


def _key_variants(key: str, model: type[BaseModel] | None = None) -> list[str]:
    """Candidate spellings a real LLM might emit for a schema field.

    Handles camelCase drift, the suffix collapse (``subproblem_id`` emitted as
    ``id``), and a small set of semantic aliases (``description`` -> ``title``).
    """
    base = key.strip()
    variants = {base, _camel_to_snake(base), _camel_to_snake(base).replace("_", "")}
    if model is not None:
        for field in model.model_fields:
            if base in ("id", "name", "description", "title", "objective") and (
                field == f"{base}_id"
                or field.endswith(f"_{base}")
                or field.startswith(f"{base}_")
            ):
                variants.add(field)
        for alias in _SEMANTIC_ALIASES.get(base, ()):
            if alias in model.model_fields:
                variants.add(alias)
    return [v for v in variants if v]
    return [v for v in variants if v]


def _field_child_model(model: type[BaseModel], field_name: str) -> type[BaseModel] | None:
    """Resolve the pydantic sub-model type for a field, unwrapping Optional/list."""
    import typing

    annotation = model.model_fields[field_name].annotation
    if annotation is None:
        return None
    # unwrap Optional[...] and list[...] to find a BaseModel
    args = getattr(annotation, "__args__", ())
    for candidate in [annotation, *args]:
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


def _coerce_keys(value: Any, model: type[BaseModel]) -> Any:
    """Recursively map payload keys onto a pydantic model's fields.

    Real LLMs (e.g. DeepSeek) occasionally return JSON whose keys drift from the
    schema ('id' instead of 'subproblem_id', camelCase instead of snake_case).
    When strict validation fails, this normalises keys to the model's declared
    fields so a formatting slip does not kill a whole evidence pipeline.
    """
    fields = set(model.model_fields)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        # Keys already present as literal payload keys — avoid mapping an alias
        # onto one of them (e.g. description->title when objective also present).
        present = {k for k in value if k in fields}
        for key, item in value.items():
            target = key
            if key not in fields:
                for variant in _key_variants(key, model):
                    if variant in fields and variant not in present:
                        target = variant
                        break
                else:
                    # no free alias target; fall back to first matching field
                    for variant in _key_variants(key, model):
                        if variant in fields:
                            target = variant
                            break
            child = _field_child_model(model, target) if target in model.model_fields else None
            if child is not None:
                item = _coerce_keys(item, child)
            result[target] = item
        return result
    if isinstance(value, list):
        # Coerce each element against the model (elements may be sub-models).
        return [_coerce_keys(item, model) for item in value]
    return value


class ProblemAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    objectives: list[str] = Field(default_factory=list)
    subproblems: list[SubproblemContract] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evaluation_targets: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    @field_validator("objectives", "variables", "constraints", "evaluation_targets", "uncertainties", "open_questions", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value]

    @field_validator("subproblems", mode="before")
    @classmethod
    def normalize_subproblems(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        values = [value] if isinstance(value, str) else list(value)
        normalized = []
        for index, item in enumerate(values, start=1):
            if isinstance(item, str):
                normalized.append(
                    {
                        "subproblem_id": f"subproblem-{index:02d}",
                        "title": item,
                        "objective": item,
                        "owner_section": "problem_restated",
                    }
                )
            else:
                normalized.append(item)
        return normalized


class ModelPlanCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    model: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = None
    notes: str | None = None
    supported: bool | None = None


class ModelPlanProposal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1
    purpose: str = "Validated modeling plan proposal"
    dataset_id: str
    task_type: str
    target_column: str
    feature_columns: list[str]
    candidate_models: list[ModelPlanCandidate] = Field(min_length=2)
    primary_metric: str
    cv_folds: int = 5
    test_size: float = 0.2
    random_seed: int = 42
    sensitivity_fractions: list[float] = Field(default_factory=lambda: [0.7, 0.85, 1.0])


class SectionPatchProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    source_sha256: str = Field(min_length=64, max_length=64)
    replacement_markdown: str = Field(min_length=20)
    rationale: str = Field(min_length=5)


class PaperRefinementProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    strategy: str = Field(min_length=5)
    issue_ids: list[str] = Field(min_length=1, max_length=3)
    expected_gains: dict[str, float] = Field(default_factory=dict)
    evidence_blockers: list[str] = Field(default_factory=list)
    patches: list[SectionPatchProposal] = Field(min_length=1, max_length=2)


class StructuredLLM:
    def __init__(self, service: CaseLLMService, prompts: PromptRegistry | None = None) -> None:
        self.service = service
        self.prompts = prompts or PromptRegistry("prompts")

    def json_call(
        self,
        case_id: str,
        session_id: str,
        node_id: str,
        prompt_id: str,
        variables: dict[str, Any],
        output_model: type[BaseModel],
        input_artifact_ids: list[str],
        max_tokens: int = 3000,
    ) -> tuple[BaseModel, dict[str, Any]]:
        prompt = self.prompts.load(prompt_id)
        messages = prompt.render(node_id, {key: _stringify(value) for key, value in variables.items()})
        result = self.service.invoke(
            case_id,
            session_id,
            node_id,
            messages,
            input_artifact_ids,
            max_tokens=max_tokens,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        payload = json.loads(_strip_json_fence(result["response"]["content"]))
        try:
            return output_model.model_validate(payload), result
        except ValidationError:
            # Fall back to key normalisation: a real LLM may have emitted
            # camelCase / alias keys. Map them onto the schema's fields before
            # re-validating; if that still fails, surface the original error.
            coerced = _coerce_keys(payload, output_model)
            return output_model.model_validate(coerced), result

    def markdown_call(
        self,
        case_id: str,
        session_id: str,
        node_id: str,
        prompt_id: str,
        variables: dict[str, Any],
        input_artifact_ids: list[str],
        max_tokens: int = 2500,
    ) -> tuple[str, dict[str, Any]]:
        prompt = self.prompts.load(prompt_id)
        messages = prompt.render(node_id, {key: _stringify(value) for key, value in variables.items()})
        result = self.service.invoke(
            case_id,
            session_id,
            node_id,
            messages,
            input_artifact_ids,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        content = result["response"]["content"].strip()
        if not content:
            raise ValueError(f"{prompt_id} returned empty Markdown")
        return content, result


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else stripped
