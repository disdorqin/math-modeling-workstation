"""Tool whitelist for the web chat driver.

A user (or an Agent) may only invoke tools declared here. Each tool maps 1:1 to
an existing workstation service method; the driver forbids any other write path
into a Case, so the evidence gates and approval state machine can never be
bypassed by conversational input. ``needs_approval`` marks tools that require an
explicit human confirmation over and above the workflow's own approval gates.

The whitelist is frozen in ``docs/web-chat-driver-contract.md`` section 1.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..research_preferences import ResearchPreferenceProfile, ResearchPreferenceService, default_interview

#: handler signature: (args, ctx) -> result-dict
Handler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Handler
    needs_approval: bool = False
    audited: bool = True


def _case_root(ctx: dict[str, Any]) -> Path:
    return ctx["cases"].case_root(ctx["case_id"])


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
def _list_cases(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    manifests = ctx["cases"].list_cases(include_archived=True)
    return {
        "count": len(manifests),
        "cases": [
            {"case_id": m["case_id"], "title": m["title"], "competition_type": m["competition_type"]}
            for m in manifests
        ],
    }


def _get_case(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    case_id = args.get("case_id") or ctx["case_id"]
    cases = ctx["cases"]
    manifest = cases.show_case(case_id)
    return {
        "manifest": manifest,
        "workflow": ctx["checkpoints"].snapshot(case_id),
        "artifacts": ctx["artifacts"].list_artifacts(case_id),
        "figures": ctx["figures"].list_figures(case_id),
        "claims": ctx["claims"].list_claims(case_id),
    }


def _create_case(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    manifest = ctx["cases"].create_case(
        competition=args.get("competition", "SM"),
        title=args.get("title", "对话创建案例"),
        problem_type=args.get("problem_type"),
        year=args.get("year"),
        version=args.get("version", 1),
    )
    return {"manifest": manifest, "case_id": manifest["case_id"]}


def _get_research_interview(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    interview = default_interview()
    return interview.model_dump(mode="json")


def _get_research_preferences(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    case_id = args.get("case_id") or ctx["case_id"]
    profile = ResearchPreferenceService(ctx["cases"], ctx.get("artifacts")).load(case_id)
    return {"case_id": case_id, "profile": profile.model_dump(mode="json")}


def _set_research_preferences(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    case_id = args.get("case_id") or ctx["case_id"]
    payload = dict(args.get("profile") or {})
    profile = ResearchPreferenceProfile.model_validate(payload)
    result = ResearchPreferenceService(ctx["cases"], ctx.get("artifacts")).save(case_id, profile)
    return {
        "case_id": case_id,
        "profile": profile.model_dump(mode="json"),
        "artifact_id": (result.get("artifact") or {}).get("artifact_id"),
    }


def _read_paper(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    root = _case_root(ctx)
    paper = root / "paper" / "current.md"
    if not paper.is_file():
        paper = root / "paper" / "paper.md"
    if not paper.is_file():
        return {"exists": False, "content": None}
    return {"exists": True, "content": paper.read_text(encoding="utf-8")}


def _approve_node(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    # Approval itself is the human action; the caller identity must be real.
    approved_by = args.get("approved_by") or ctx.get("approved_by") or "chat-human"
    node = ctx["workflow"].approve_node(
        ctx["case_id"],
        args["node_id"],
        approved_by,
        args.get("note", "Approved via chat shell"),
    )
    return {"node": node}


def _retry_node(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    requested_by = args.get("requested_by") or ctx.get("approved_by") or "chat-human"
    node = ctx["workflow"].retry_node(
        ctx["case_id"],
        args["node_id"],
        requested_by,
        args.get("reason", "Retry requested via chat shell"),
    )
    return {"node": node}


def _degrade_node(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    approved_by = args.get("approved_by") or ctx.get("approved_by") or "chat-human"
    node = ctx["workflow"].degrade_node(
        ctx["case_id"],
        args["node_id"],
        approved_by,
        args.get("reason", "Degraded via chat shell"),
    )
    return {"node": node}


def _list_ledger(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    entries = ctx["ledger"].list()
    return {"count": len(entries), "entries": entries}


# --------------------------------------------------------------------------- #
# Whitelist assembly
# --------------------------------------------------------------------------- #
def build_tools(services: dict[str, Any]) -> dict[str, ToolSpec]:
    """Return the whitelisted tools bound to the provided services."""
    specs: list[ToolSpec] = [
        ToolSpec(
            "list_cases",
            "列出所有案例",
            _list_cases,
            needs_approval=False,
        ),
        ToolSpec(
            "get_case",
            "查看某个案例的清单、DAG 状态、产物、图表与 Claims",
            _get_case,
            needs_approval=False,
        ),
        ToolSpec(
            "create_case",
            "创建新案例(竞赛类型 SM/MCM/ICM/CUMCM 等)",
            _create_case,
            needs_approval=False,
        ),
        ToolSpec(
            "get_research_interview",
            "获取正式比赛前的研究偏好访谈问题与默认配置",
            _get_research_interview,
            needs_approval=False,
        ),
        ToolSpec(
            "get_research_preferences",
            "读取当前案例的建模/论文风格偏好",
            _get_research_preferences,
            needs_approval=False,
        ),
        ToolSpec(
            "set_research_preferences",
            "保存当前案例的建模优先级、偏好模型风格、视觉密度与人工检查点配置",
            _set_research_preferences,
            needs_approval=False,
        ),
        ToolSpec(
            "read_paper",
            "读取当前论文草稿(current.md 或 paper.md)",
            _read_paper,
            needs_approval=False,
        ),
        ToolSpec(
            "approve_node",
            "批准一个待审节点(批准人必须是真人标识)",
            _approve_node,
            needs_approval=False,  # 该动作本身就是审批
        ),
        ToolSpec(
            "retry_node",
            "请求重试失败/阻塞节点(需二次确认)",
            _retry_node,
            needs_approval=True,
        ),
        ToolSpec(
            "degrade_node",
            "降级可选分支并记录理由(需人工确认)",
            _degrade_node,
            needs_approval=True,
        ),
        ToolSpec(
            "list_ledger",
            "查看本案例的 AI 使用台账",
            _list_ledger,
            needs_approval=False,
        ),
    ]
    return {spec.name: spec for spec in specs}


# --------------------------------------------------------------------------- #
# Intent resolution (rule-based, deterministic; LLM provider as a later opt-in)
# --------------------------------------------------------------------------- #
#: (tool_name, trigger keywords, default args)
_INTENT_RULES: list[tuple[str, list[str], dict[str, Any]]] = [
    # Order matters: "查看案例列表" must match list_cases before get_case's
    # broader "查看案例" keyword does. More specific phrases come first.
    ("list_cases", ["列出案例", "有哪些案例", "查看案例列表", "list cases"], {}),
    ("get_case", ["查看案例", "案例详情", "get case"], {}),
    ("create_case", ["创建案例", "新建案例", "建案例", "create case"], {}),
    ("read_paper", ["查看论文", "论文内容", "读论文", "read paper"], {}),
    ("list_ledger", ["查看台账", "ai台账", "ai ledger", "使用台账"], {}),
    ("approve_node", ["批准", "审批", "通过节点", "approve"], {}),
    ("retry_node", ["重试", "retry"], {"needs_confirm": True}),
    ("degrade_node", ["降级", "degrade"], {"needs_confirm": True}),
]

#: reserved words that hint at a pipeline run (mapped in ChatDriver, not a plain tool)
_PIPELINE_HINTS = [
    "自动", "流水线", "跑一遍", "完整求解", "做这道题", "生成论文",
    "auto", "pipeline", "run", "solve",
]


def resolve_intent(message: str) -> list[dict[str, Any]]:
    """Deterministically map a chat message to candidate tool calls.

    Returns an empty list when no tool is a confident match; the driver then
    replies with guidance instead of guessing at a destructive action.
    """
    lowered = message.lower()
    for tool_name, keywords, default_args in _INTENT_RULES:
        if any(keyword.lower() in lowered for keyword in keywords):
            return [{"tool": tool_name, "args": dict(default_args)}]
    return []


def hints_pipeline(message: str) -> bool:
    lowered = message.lower()
    return any(hint.lower() in lowered for hint in _PIPELINE_HINTS)


def extract_case_id(message: str, known: list[str]) -> str | None:
    """Find a known case id inside free text (e.g. '20260804-SM-0001-ABCD')."""
    for candidate in known:
        if candidate.lower() in message.lower():
            return candidate
    return None


def extract_node_id(message: str, nodes: list[str]) -> str | None:
    """Find a workflow node id inside free text (e.g. 'model_selection')."""
    for node in nodes:
        if node.lower() in message.lower():
            return node
    return None


def _json_arg(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    if start == -1:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return None
