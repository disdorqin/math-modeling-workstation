from __future__ import annotations

import hashlib
import json
import string
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(min_length=3)
    version: str = Field(min_length=1)
    allowed_nodes: list[str] = Field(min_length=1)
    system_template: str = Field(min_length=10)
    user_template: str = Field(min_length=3)
    output_mode: str = "text"

    def render(self, node_id: str, variables: dict[str, Any]) -> list[dict[str, str]]:
        if node_id not in self.allowed_nodes:
            raise PermissionError(f"prompt {self.prompt_id} is not allowed for node {node_id}")
        required = _fields(self.system_template) | _fields(self.user_template)
        missing = sorted(required - variables.keys())
        if missing:
            raise ValueError(f"missing prompt variables: {missing}")
        return [
            {"role": "system", "content": self.system_template.format_map(variables)},
            {"role": "user", "content": self.user_template.format_map(variables)},
        ]

    @property
    def digest(self) -> str:
        encoded = self.model_dump_json().encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class PromptRegistry:
    def __init__(self, root: str | Path = "prompts") -> None:
        self.root = Path(root)

    def load(self, prompt_id: str) -> PromptTemplate:
        matches = list(self.root.rglob(f"{prompt_id}.json"))
        if len(matches) != 1:
            raise KeyError(f"expected exactly one prompt {prompt_id}, found {len(matches)}")
        return PromptTemplate.model_validate_json(matches[0].read_text(encoding="utf-8-sig"))

    def list_prompts(self) -> list[dict[str, str]]:
        result = []
        for path in sorted(self.root.rglob("*.json")):
            template = PromptTemplate.model_validate_json(path.read_text(encoding="utf-8-sig"))
            result.append(
                {
                    "prompt_id": template.prompt_id,
                    "version": template.version,
                    "digest": template.digest,
                    "path": path.as_posix(),
                }
            )
        return result


def _fields(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name
    }

