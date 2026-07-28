"""Provider-neutral LLM interface for the M2 contest-grade paper layer.

M2 must run in CI without any API key. To make that possible the layer talks to
LLMs only through :class:`Provider`, and ships a deterministic
:class:`FakeProvider` that returns structured, reproducible output derived from
the request's ``task`` tag. A real :class:`OpenAICompatibleProvider` adapts the
existing ``mathworkstation.llm`` router for non-CI use; it is never imported by
tests or the benchmark.

Design rules (evidence-bounded by construction):
  * A Provider only ever produces *language* — narrative, structure, framing.
  * It never produces numbers that are not already present in the evidence pack
    an agent passes in. Numbers in the final paper come from the evidence
    registry, never from the model.
  * ``FakeProvider`` is a pure function of (task, prompt, seed): same inputs ->
    same outputs, so CI is stable and adversarial tests are reproducible.
"""
from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class CompletionRequest:
    system: str = ""
    prompt: str = ""
    messages: list[Message] = field(default_factory=list)
    temperature: float = 0.0
    max_tokens: int = 2048
    #: Deterministic dispatch key for FakeProvider (and a hint for real ones).
    task: str = "chat"
    #: Optional structured schema the caller expects back (for complete_json).
    response_schema: dict | None = None
    #: Arbitrary metadata (never sent to a network provider).
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResult:
    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    name = "base"

    @abstractmethod
    def complete(self, req: CompletionRequest) -> CompletionResult:
        ...

    # Subclasses may override; default best-effort JSON extraction.
    def complete_json(self, req: CompletionRequest) -> dict:
        text = self.complete(req).text
        return _extract_json(text)


def _extract_json(text: str) -> dict:
    """Pull the first balanced JSON object out of a model response."""
    start = text.find("{")
    if start == -1:
        raise ValueError(f"no JSON object in provider response: {text[:200]!r}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError(f"unbalanced JSON in provider response: {text[:200]!r}")


class FakeProvider(Provider):
    """Deterministic, offline provider.

    Maps ``req.task`` to a templated, content-derived response. It is a pure
    function of the request, so identical calls yield identical output — which
    is exactly what lets the benchmark and adversarial tests be reproducible in
    CI without a network or an API key.
    """

    name = "fake"

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed

    def complete(self, req: CompletionRequest) -> CompletionResult:
        text = self._render(req)
        digest = hashlib.sha256((req.task + req.prompt).encode("utf-8")).hexdigest()
        return CompletionResult(
            text=text,
            model=f"fake-{self.seed}",
            provider="fake",
            usage={"prompt_tokens": len(req.prompt) // 4, "completion_tokens": len(text) // 4},
            raw={"digest": digest},
        )

    # -- task dispatch ----------------------------------------------------- #
    def _render(self, req: CompletionRequest) -> str:
        handler = {
            "problem_analysis": self._t_problem_analysis,
            "model_architecture": self._t_model_architecture,
            "experiment_plan": self._t_experiment_plan,
            "section_prose": self._t_section_prose,
            "review": self._t_review,
            "revision": self._t_revision,
            "chat": lambda r: "Acknowledged.",
        }.get(req.task, lambda r: "Acknowledged.")
        return handler(req)

    @staticmethod
    def _t_problem_analysis(req: CompletionRequest) -> str:
        goal = req.meta.get("goal", req.prompt)
        n_vars = req.meta.get("n_variables", 10)
        return json.dumps(
            {
                "summary": f"Problem analysis for: {goal}",
                "subproblems": [
                    "formulate the response variable and modelling objective",
                    "characterise the predictors and their scales",
                    "select candidate model families appropriate to the objective",
                    "define the validation protocol and decision metric",
                ],
                "assumptions": [
                    "observational features are measured without systematic bias",
                    "the target is approximately homoscedastic after transformation",
                ],
                "deliverables": [
                    "a quantitative model of the target",
                    "an evidence-grounded selection among candidates",
                    "a reproducible, auditable paper",
                ],
                "n_variables": n_vars,
            },
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def _t_model_architecture(req: CompletionRequest) -> str:
        return json.dumps(
            {
                "families": [
                    {"id": "linear", "rationale": "interpretable baseline, closed-form inference"},
                    {"id": "tree", "rationale": "captures nonlinearities and interactions"},
                    {"id": "robust_baseline", "rationale": "resistant to outliers / leverage points"},
                ],
                "selection_metric": "negative_mean_squared_error (cross-validated)",
                "note": "exactly three candidate families are evaluated; reuse of fitted artifacts is mandatory on re-runs.",
            },
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def _t_experiment_plan(req: CompletionRequest) -> str:
        families = req.meta.get("families", ["linear", "tree", "robust_baseline"])
        plans = [
            {
                "family": f,
                "protocol": f"kfold_cv_5",
                "metric": "neg_mse",
                "splits": 5,
                "reports_metric": True,
            }
            for f in families
        ]
        return json.dumps({"plans": plans}, ensure_ascii=False, indent=2)

    @staticmethod
    def _t_section_prose(req: CompletionRequest) -> str:
        # The model returns connective narrative only. Every numeric claim is
        # injected by the section writer from the evidence pack, never here.
        section = req.meta.get("section_title", "section")
        return (
            f"In this {section}, we synthesise the registered evidence. "
            f"[EVIDENCE_NARRATIVE] The methodological choices follow directly "
            f"from the problem analysis and the validation protocol, and every "
            f"quantitative statement below is anchored to a registered artifact."
        )

    @staticmethod
    def _t_review(req: CompletionRequest) -> str:
        # Returns a structured review with a score and findings. The score is a
        # function of how many evidence/consistency checks the caller embedded
        # in the prompt, so it is reproducible and improvable by revision.
        checks_passed = req.meta.get("checks_passed", 6)
        checks_total = req.meta.get("checks_total", 8)
        score = int(round(60 + 40 * (checks_passed / max(1, checks_total))))
        findings = []
        if checks_passed < checks_total:
            findings.append("some quantitative claims lack a visible evidence citation")
        findings.append("notation is internally consistent")
        findings.append("figures and tables are referenced in the text")
        return json.dumps(
            {"score": score, "findings": findings, "checks_passed": checks_passed, "checks_total": checks_total},
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def _t_revision(req: CompletionRequest) -> str:
        return json.dumps(
            {
                "actions": [
                    "add explicit [cite:] anchors to every numeric claim",
                    "expand the results section with the registered metrics",
                    "cross-check symbol definitions against the registry",
                ]
            },
            ensure_ascii=False,
            indent=2,
        )


class OpenAICompatibleProvider(Provider):
    """Talks to a real OpenAI-compatible endpoint via the existing router.

    Imported lazily so the M2 package (and CI) never requires the network stack.
    """

    name = "openai-compatible"

    def __init__(self, model: str = "gpt-4o-mini", route: str = "default", timeout: float = 60.0) -> None:
        self.model = model
        self.route = route
        self.timeout = timeout

    def complete(self, req: CompletionRequest) -> CompletionResult:
        from mathworkstation.llm import LLMRouter, ChatRequest  # noqa: WPS433

        router = LLMRouter.from_env()
        chat = ChatRequest(
            model=self.model,
            messages=[{"role": m.role, "content": m.content} for m in req.messages]
            or [{"role": "system", "content": req.system}, {"role": "user", "content": req.prompt}],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        result = router.complete(chat)
        return CompletionResult(text=result.text, model=result.model, provider="openai-compatible",
                                usage=getattr(result, "usage", {}) or {})


def get_provider(name: str = "fake", **kwargs: Any) -> Provider:
    """Factory. CI always uses ``fake``; real runs pass ``openai-compatible``."""
    if name == "fake":
        return FakeProvider(seed=kwargs.get("seed", 0))
    if name in ("openai", "openai-compatible"):
        return OpenAICompatibleProvider(**kwargs)
    raise ValueError(f"unknown provider: {name!r}")
