from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .checkpoint_manager import CheckpointManager
from .claims import ClaimRegistry
from .llm.config import RouterConfig
from .llm.router import LLMRouter
from .llm.service import CaseLLMService
from .memory_manager import MemoryManager
from .paper_consistency import PaperConsistencyChecker
from .paper_outline import PaperOutlineService
from .paper_sections import PaperSectionWorkspace
from .figure_registry import FigureRegistry
from .datasets import DatasetRegistry
from .run_manager import RunManager
from .session_manager import SessionManager
from .workflow import NodeStatus
from .workflow_service import WorkflowService
from .cli import _load_env_file


OUTPUT_ROOT = Path("output")
STATUS_ORDER = {
    "SUCCEEDED": 0,
    "DEGRADED": 1,
    "RUNNING": 2,
    "NEEDS_REVIEW": 3,
    "RETRYING": 4,
    "STALE": 5,
    "BLOCKED": 6,
    "FAILED": 7,
    "PENDING": 8,
}


def _services() -> dict[str, Any]:
    _load_env_file(Path(".env.local"))
    cases = CaseManager(OUTPUT_ROOT)
    artifacts = ArtifactRegistry(cases)
    checkpoints = CheckpointManager(cases)
    memory = MemoryManager(cases, artifacts)
    sessions = SessionManager(cases)
    workflow = WorkflowService(cases, RunManager(cases), checkpoints, memory)
    figures = FigureRegistry(cases, artifacts)
    datasets = DatasetRegistry(cases, artifacts)
    claims = ClaimRegistry(cases, artifacts, datasets)
    return {
        "cases": cases,
        "artifacts": artifacts,
        "checkpoints": checkpoints,
        "sessions": sessions,
        "workflow": workflow,
        "figures": figures,
        "claims": claims,
        "checker": PaperConsistencyChecker(cases, artifacts, claims, figures),
    }


def _case_options(cases: CaseManager) -> list[dict[str, Any]]:
    return cases.list_cases(include_archived=True)


def _load_case(services: dict[str, Any], case_id: str) -> dict[str, Any]:
    cases = services["cases"]
    root = cases.case_root(case_id)
    return {
        "manifest": cases.show_case(case_id),
        "workflow": services["checkpoints"].snapshot(case_id),
        "artifacts": services["artifacts"].list_artifacts(case_id),
        "figures": services["figures"].list_figures(case_id),
        "claims": services["claims"].list_claims(case_id),
        "root": root,
    }


def _sessions_for_case(cases: CaseManager, case_id: str) -> list[dict[str, Any]]:
    sessions_root = cases.case_root(case_id) / "sessions"
    sessions: list[dict[str, Any]] = []
    for path in sorted(sessions_root.glob("*/session.json")):
        sessions.append(json.loads(path.read_text(encoding="utf-8")))
    return sessions


def _status_counts(workflow: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in workflow["nodes"].values():
        status = node["status"]
        counts[status] = counts.get(status, 0) + 1
    return counts


def _workflow_rows(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for node_id, runtime in workflow["nodes"].items():
        definition = workflow["definitions"][node_id]
        rows.append(
            {
                "node": node_id,
                "status": runtime["status"],
                "attempts": runtime["attempts"],
                "approval_required": definition["approval_required"],
                "dependencies": ", ".join(definition["dependencies"]) or "-",
                "last_error": (runtime.get("last_error") or {}).get("message", ""),
            }
        )
    return rows


def _render_overview(services: dict[str, Any], case: dict[str, Any]) -> None:
    st.subheader("工作流总览")
    counts = _status_counts(case["workflow"])
    columns = st.columns(5)
    for column, label in zip(columns, ("已完成", "待审", "运行中", "阻塞", "降级")):
        key = {"已完成": "SUCCEEDED", "待审": "NEEDS_REVIEW", "运行中": "RUNNING", "阻塞": "BLOCKED", "降级": "DEGRADED"}[label]
        column.metric(label, counts.get(key, 0))
    st.dataframe(_workflow_rows(case["workflow"]), use_container_width=True, hide_index=True)

    st.subheader("人工控制")
    rows = _workflow_rows(case["workflow"])
    review_nodes = [row["node"] for row in rows if row["status"] == "NEEDS_REVIEW"]
    retry_nodes = [row["node"] for row in rows if row["status"] in {"FAILED", "BLOCKED", "STALE", "DEGRADED"}]
    left, right = st.columns(2)
    with left:
        if review_nodes:
            node = st.selectbox("待审批节点", review_nodes, key="approve_node")
            note = st.text_input("审批备注", value="Evidence reviewed", key="approve_note")
            if st.button("批准节点", type="primary"):
                services["workflow"].approve_node(case["manifest"]["manifest"]["case_id"], node, "ui-human", note)
                st.rerun()
        else:
            st.info("当前没有待审批节点")
    with right:
        if retry_nodes:
            node = st.selectbox("可重试节点", retry_nodes, key="retry_node")
            reason = st.text_input("重试原因", value="Manual retry from workstation", key="retry_reason")
            if st.button("请求重试"):
                services["workflow"].retry_node(case["manifest"]["manifest"]["case_id"], node, "ui-human", reason)
                st.rerun()
        else:
            st.info("当前没有可重试节点")


def _render_evidence(services: dict[str, Any], case: dict[str, Any]) -> None:
    st.subheader("数据、图表与证据")
    st.dataframe(case["artifacts"], use_container_width=True, hide_index=True)
    if case["claims"]:
        st.subheader("Claims")
        st.dataframe(case["claims"], use_container_width=True, hide_index=True)
    if case["figures"]:
        st.subheader("Figures")
        for figure in case["figures"]:
            path = case["root"] / figure["path"]
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                st.image(str(path), caption=f"{figure['title']} · {figure['status']}")


def _render_paper(case: dict[str, Any]) -> None:
    st.subheader("论文工作区")
    root = case["root"]
    paper = root / "paper" / "paper.md"
    consistency = root / "review" / "consistency" / "paper_consistency.json"
    if consistency.is_file():
        report = json.loads(consistency.read_text(encoding="utf-8"))
        gate = report.get("gate", "UNKNOWN")
        (st.success if gate == "PASS" else st.warning)(f"Consistency gate: {gate}")
    if paper.is_file():
        content = paper.read_text(encoding="utf-8")
        st.download_button("下载论文 Markdown", content, file_name=f"{case['manifest']['manifest']['case_id']}.md", mime="text/markdown")
        st.markdown(content)
    else:
        st.info("论文合并稿尚未生成")


def _render_chat(services: dict[str, Any], case: dict[str, Any]) -> None:
    st.subheader("受控 LLM 对话")
    st.caption("调用绑定当前 Case、Session 和 DAG 节点；响应会写入该 Case 的 sessions/responses 和 Artifact Registry。")
    case_id = case["manifest"]["manifest"]["case_id"]
    sessions = _sessions_for_case(services["cases"], case_id)
    if not sessions:
        st.warning("请先通过 CLI 创建 Session")
        return
    session = st.selectbox("Session", sessions, format_func=lambda item: item["session_id"])
    node = st.selectbox("绑定节点", list(case["workflow"]["definitions"]), index=1)
    message = st.text_area("消息", height=150, placeholder="输入本次受控分析请求")
    routes = "config/llm-routes.example.json"
    if st.button("发送 LLM 请求", type="primary", disabled=not message.strip()):
        service = CaseLLMService(
            services["cases"],
            services["artifacts"],
            services["sessions"],
            services["checkpoints"],
            LLMRouter(RouterConfig.model_validate_json(Path(routes).read_text(encoding="utf-8"))),
        )
        with st.spinner("路由请求中..."):
            result = service.invoke(case_id, session["session_id"], node, [{"role": "user", "content": message}], [])
        st.success(f"route={result['response']['route']} · model={result['response']['model']}")
        st.markdown(result["response"]["content"])


def main() -> None:
    st.set_page_config(page_title="Math Modeling Workstation", layout="wide", initial_sidebar_state="expanded")
    st.title("数学建模辅助工作站")
    st.caption("Evidence-first · Case-isolated · DAG-controlled")
    services = _services()
    cases = _case_options(services["cases"])
    if not cases:
        st.info("暂无 Case。先运行 `mathworkstation create-case`。")
        return
    labels = {item["case_id"]: f"{item['case_id']} · {item['title']}" for item in cases}
    default_case = st.session_state.get("case_id", cases[-1]["case_id"])
    case_id = st.sidebar.selectbox("当前 Case", list(labels), index=list(labels).index(default_case) if default_case in labels else 0, format_func=labels.get)
    st.session_state["case_id"] = case_id
    if st.sidebar.button("刷新 Case"):
        st.rerun()
    case = _load_case(services, case_id)
    st.sidebar.caption(f"Competition: {case['manifest']['manifest']['competition_type']}")
    st.sidebar.caption(f"Artifacts: {len(case['artifacts'])} · Claims: {len(case['claims'])}")
    overview, evidence, paper, chat = st.tabs(["总览", "证据", "论文", "受控对话"])
    with overview:
        _render_overview(services, case)
    with evidence:
        _render_evidence(services, case)
    with paper:
        _render_paper(case)
    with chat:
        _render_chat(services, case)


if __name__ == "__main__":
    main()
