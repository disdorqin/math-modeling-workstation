from __future__ import annotations

import json
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RouteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2)
    base_url: str = Field(pattern=r"^https://")
    api_key_env: str = Field(min_length=3)
    models: list[str] = Field(min_length=1)
    priority: int = Field(default=100, ge=0)
    timeout_seconds: float = Field(default=45.0, gt=1, le=300)
    failure_threshold: int = Field(default=1, ge=1, le=10)
    cooldown_seconds: float = Field(default=60.0, ge=1, le=3600)
    kind: Literal["chat", "image"] = "chat"
    enabled: bool = True
    risk_flags: list[str] = Field(default_factory=list)

    @property
    def api_key(self) -> str:
        value = os.environ.get(self.api_key_env, "")
        if not value:
            raise ValueError(f"missing API key environment variable: {self.api_key_env}")
        return value


class RouterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routes: list[RouteConfig] = Field(min_length=1)
    max_attempts: int = Field(default=4, ge=1, le=20)
    max_total_tokens: int = Field(default=12000, ge=1)
    audit_enabled: bool = True

    @model_validator(mode="after")
    def unique_names(self) -> "RouterConfig":
        names = [route.name for route in self.routes]
        if len(names) != len(set(names)):
            raise ValueError("route names must be unique")
        return self

    @classmethod
    def from_environment(cls, variable: str = "MMW_LLM_ROUTES_JSON") -> "RouterConfig":
        raw = os.environ.get(variable)
        if not raw:
            raise ValueError(f"missing route configuration environment variable: {variable}")
        payload = json.loads(raw)
        if isinstance(payload, list):
            payload = {"routes": payload}
        return cls.model_validate(payload)

