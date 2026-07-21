from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .llm.prompts import PromptRegistry
from .llm.service import CaseLLMService


class ProblemAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    objectives: Any = Field(default_factory=list)
    subproblems: Any = Field(default_factory=list)
    variables: Any = Field(default_factory=list)
    constraints: Any = Field(default_factory=list)
    evaluation_targets: Any = Field(default_factory=list)
    uncertainties: Any = Field(default_factory=list)
    open_questions: Any = Field(default_factory=list)


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
        return output_model.model_validate(payload), result

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
