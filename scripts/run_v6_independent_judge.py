from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from mathworkstation.cli import _load_env_file
from mathworkstation.llm.config import RouterConfig
from mathworkstation.llm.router import ChatRequest, LLMRouter


DIMENSIONS = [
    "problem_insight",
    "scientific_modeling_core",
    "modeling_appropriateness",
    "mathematical_structure",
    "unified_framework_inheritance",
    "validation_rigor",
    "evidence_credibility",
    "innovation_non_obviousness",
    "story_discovery_progression",
    "figure_argumentative_value_from_text_evidence",
    "abstract_information_density",
    "decision_contest_usefulness",
    "writing_naturalness",
    "overall_award_preference",
]


def _json_from_response(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise TypeError("independent judge response must be a JSON object")
    return parsed


def _validate_result(payload: dict[str, Any]) -> dict[str, Any]:
    preference = str(payload.get("preference") or "").upper()
    if preference not in {"LEFT", "RIGHT", "TIE"}:
        raise ValueError(f"invalid preference: {preference!r}")
    confidence = float(payload.get("confidence", 0.0))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    dimensions = payload.get("dimensions") or {}
    if not isinstance(dimensions, dict):
        raise TypeError("dimensions must be an object")
    normalized_dimensions: dict[str, str] = {}
    for name in DIMENSIONS:
        decision = str(dimensions.get(name) or "TIE").upper()
        if decision not in {"LEFT", "RIGHT", "TIE"}:
            raise ValueError(f"invalid dimension preference {name}: {decision!r}")
        normalized_dimensions[name] = decision
    rationale = str(payload.get("rationale") or "").strip()
    return {
        "preference": preference,
        "confidence": confidence,
        "dimensions": normalized_dimensions,
        "rationale": rationale[:5000],
    }


def _judge_prompt(packet: dict[str, Any]) -> list[dict[str, str]]:
    dimension_text = "\n".join(f"- {name}" for name in DIMENSIONS)
    system = f"""You are an independent blind judge for mathematical-modeling competition papers.
You are not told the paper source, award, author, school, generator, or expected winner. Do not guess identity or provenance. Judge only the supplied anonymized paper contents.

Compare the two papers as competition submissions. A paper does NOT become better merely by having more formulas, figures, tables, sections, or buzzwords. Reward scientific/modeling substance, appropriate mathematical structure, justified progression, credible validation, non-obvious insight, and useful conclusions. Penalize decorative complexity, generic templates, unsupported claims, mechanical section filling, weak causal/validation logic, or a model zoo without a coherent framework.

The text was extracted from PDFs, so visual appearance itself is NOT directly available. For figure_argumentative_value_from_text_evidence, judge only whether the textual references/captions indicate figures are being used as arguments; do not invent visual-quality claims.

Evaluate these dimensions:
{dimension_text}

Return JSON only with exactly this shape:
{{
  "preference": "LEFT|RIGHT|TIE",
  "confidence": 0.0,
  "dimensions": {{"problem_insight": "LEFT|RIGHT|TIE", "...": "..."}},
  "rationale": "brief evidence-based comparison, no hidden chain-of-thought"
}}
"""
    left = packet["left"]
    right = packet["right"]
    user = (
        f"PAIR_ID: {packet['pair_id']}\n"
        f"LEFT_BLIND_ID: {left['blind_id']}\n"
        f"RIGHT_BLIND_ID: {right['blind_id']}\n\n"
        "===== LEFT PAPER =====\n"
        f"{left['text']}\n\n"
        "===== RIGHT PAPER =====\n"
        f"{right['text']}\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _single_model_router(config_path: Path, *, route_name: str, model: str) -> LLMRouter:
    _load_env_file(Path(".env.local"))
    full = RouterConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    routes = [route for route in full.routes if route.name == route_name and model in route.models]
    if len(routes) != 1:
        raise RuntimeError(
            f"expected exactly one route={route_name!r} carrying model={model!r}, found {len(routes)}"
        )
    config = RouterConfig(
        routes=routes,
        max_attempts=1,
        max_total_tokens=full.max_total_tokens,
        audit_enabled=full.audit_enabled,
    )
    # Touch the property before any expensive request so missing credentials fail
    # immediately rather than after packet preparation.
    _ = config.routes[0].api_key
    return LLMRouter(config)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run V6 blind independent model judge.")
    parser.add_argument("--root", default="artifacts/meta_benchmark/judge_v1")
    parser.add_argument("--routes", default="config/llm-routes.local.json")
    parser.add_argument("--route-name", default="deepseek-chat")
    parser.add_argument("--model", default="deepseek-reasoner")
    parser.add_argument("--judge-id", default="independent-deepseek-reasoner-v1")
    parser.add_argument("--only", nargs="*", default=None, help="optional pair IDs")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    report = json.loads((root / "materialization_report.json").read_text(encoding="utf-8"))
    if not report.get("ready_for_automatic_blind_judge"):
        raise RuntimeError("materialized packets have unresolved automatic identity leakage")

    router = _single_model_router(Path(args.routes), route_name=args.route_name, model=args.model)
    packet_paths = sorted((root / "packets").glob("*.json"))
    if args.only:
        wanted = set(args.only)
        packet_paths = [path for path in packet_paths if path.stem in wanted]
    if not packet_paths:
        raise RuntimeError("no judge packets selected")

    safe_judge = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.judge_id).strip("_")
    output = root / "judge_results" / f"{safe_judge}.jsonl"
    existing_pairs: set[str] = set()
    if output.is_file() and not args.force:
        for line in output.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("record_type") == "judge_vote":
                existing_pairs.add(str(row.get("pair_id") or ""))

    mode = "w" if args.force else "a"
    with output.open(mode, encoding="utf-8") as handle:
        for packet_path in packet_paths:
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            pair_id = str(packet["pair_id"])
            if pair_id in existing_pairs:
                print(f"SKIP {pair_id}: existing vote")
                continue
            result = router.chat(
                ChatRequest(
                    messages=_judge_prompt(packet),
                    model=args.model,
                    max_tokens=3500,
                    temperature=0.0,
                    metadata={"task": "v6_independent_blind_judge", "pair_id": pair_id},
                )
            )
            judged = _validate_result(_json_from_response(result.content))
            vote = {
                "record_type": "judge_vote",
                "judge_id": args.judge_id,
                "judge_kind": "INDEPENDENT_MODEL",
                "pair_id": pair_id,
                "decision": judged["preference"],
                "confidence": judged["confidence"],
                "rationale": judged["rationale"],
            }
            detail = {
                "record_type": "judge_detail",
                "judge_id": args.judge_id,
                "pair_id": pair_id,
                "route": result.route_name,
                "model": result.model,
                "usage": result.usage,
                "latency_ms": result.latency_ms,
                "dimensions": judged["dimensions"],
            }
            handle.write(json.dumps(vote, ensure_ascii=False) + "\n")
            handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
            handle.flush()
            print(
                json.dumps(
                    {
                        "pair_id": pair_id,
                        "preference": judged["preference"],
                        "confidence": judged["confidence"],
                        "route": result.route_name,
                        "model": result.model,
                    },
                    ensure_ascii=False,
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
