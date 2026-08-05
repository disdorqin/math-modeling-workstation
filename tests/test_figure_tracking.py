"""图表注册/追踪机制测试 (task t38a82dee, 图表注册/追踪机制)."""
from __future__ import annotations
from pathlib import Path
from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.figure_tracking import (
    attach_figure_source, check_figure_tracking, figure_analysis, figure_description,
    find_figures_by_source, list_figure_sources, source_path, write_tracking_report,
)

def _make_env(tmp_path):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "tu")
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    return cases, artifacts, figures, case["case_id"]

def _register_source(artifacts, case_id, tmp_path, name, text):
    source = tmp_path / name
    source.write_text(text, encoding="utf-8")
    return artifacts.ingest_file(case_id, source, "input", "source")

def _register_figure(figures, case_id, tmp_path, source_id, title="tu"):
    root = figures.cases.case_root(case_id)
    png = root / "figures" / (title + ".png")
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    return figures.register(case_id, png.relative_to(root).as_posix(), title, [source_id], "mathworkstation.eda", {}, None)

def test_source_path_roundtrip():
    assert source_path("c1", []) == "(none)"
    assert source_path("c1", ["a", "b"]) == "a / b"

def test_attach_and_list_figure_sources(tmp_path):
    cases, artifacts, figures, cid = _make_env(tmp_path)
    sid = _register_source(artifacts, cid, tmp_path, "src.txt", "ev")["artifact_id"]
    fig = _register_figure(figures, cid, tmp_path, sid)
    up = attach_figure_source(figures, cid, fig["figure_id"], sid, "ctx1", "sec")
    assert up["figure_id"] == fig["figure_id"]
    assert len(up["sources"]) == 1
    assert up["sources"][0]["source_artifact_id"] == sid
    listed = list_figure_sources(figures, cid, fig["figure_id"])
    assert len(listed) == 1
    assert listed[0]["source_artifact_id"] == sid

def test_attach_source_requires_registered_artifact(tmp_path):
    cases, artifacts, figures, cid = _make_env(tmp_path)
    sid = _register_source(artifacts, cid, tmp_path, "src.txt", "ev")["artifact_id"]
    fig = _register_figure(figures, cid, tmp_path, sid)
    try:
        attach_figure_source(figures, cid, fig["figure_id"], "nope", "c", "s")
    except KeyError:
        return
    raise AssertionError("expected KeyError")

def test_find_figures_by_source(tmp_path):
    cases, artifacts, figures, cid = _make_env(tmp_path)
    s1 = _register_source(artifacts, cid, tmp_path, "s1.txt", "a")["artifact_id"]
    s2 = _register_source(artifacts, cid, tmp_path, "s2.txt", "b")["artifact_id"]
    f1 = _register_figure(figures, cid, tmp_path, s1, "f1")
    _register_figure(figures, cid, tmp_path, s2, "f2")
    attach_figure_source(figures, cid, f1["figure_id"], s2, "can", "res")
    hits = find_figures_by_source(figures, cid, s2)
    assert {h["figure_id"] for h in hits} == {f1["figure_id"]}

def test_figure_description_and_analysis(tmp_path):
    cases, artifacts, figures, cid = _make_env(tmp_path)
    sid = _register_source(artifacts, cid, tmp_path, "src.txt", "ev")["artifact_id"]
    fig = _register_figure(figures, cid, tmp_path, sid)
    attach_figure_source(figures, cid, fig["figure_id"], sid, "EDA", "da")
    rec = figures.get(cid, fig["figure_id"])
    num = {fig["figure_id"]: {"label": "tu1", "number": 1, "title": "t"}}
    desc = figure_description(rec, num)
    assert "tu1" in desc and fig["figure_id"] in desc and sid in desc
    ana = figure_analysis(rec, num, "x")
    assert "tu1" in ana and "x" in ana

def test_check_figure_tracking_flags_issues(tmp_path):
    cases, artifacts, figures, cid = _make_env(tmp_path)
    sid = _register_source(artifacts, cid, tmp_path, "src.txt", "ev")["artifact_id"]
    fig = _register_figure(figures, cid, tmp_path, sid)
    rep = check_figure_tracking(cid, "no-ref", figures)
    assert "FIGURE_WITHOUT_SOURCE" in {f["code"] for f in rep["findings"]}
    from mathworkstation.io_utils import append_jsonl
    broken = {**figures.get(cid, fig["figure_id"]), "sources": [{"source_artifact_id": "nope"}]}
    append_jsonl(figures.registry_path(cid), broken)
    rep2 = check_figure_tracking(cid, "no", figures)
    assert rep2["gate"] == "BLOCK"
    assert "SOURCE_ARTIFACT_MISSING" in {f["code"] for f in rep2["findings"]}
    rep3 = check_figure_tracking(cid, "see Figure 9", figures)
    assert "UNRESOLVED_FIGURE_TRACKING" in {f["code"] for f in rep3["findings"]}

def test_write_tracking_report(tmp_path):
    cases, artifacts, figures, cid = _make_env(tmp_path)
    sid = _register_source(artifacts, cid, tmp_path, "src.txt", "ev")["artifact_id"]
    _register_figure(figures, cid, tmp_path, sid)
    rep = check_figure_tracking(cid, "", figures)
    result = write_tracking_report(cid, rep, figures)
    root = cases.case_root(cid)
    assert (root / "review" / "figure_tracking" / "figure_tracking_report.json").is_file()
    assert (root / "review" / "figure_tracking" / "figure_tracking_report.md").is_file()
    assert result["report_artifact_id"]
    assert artifacts.get(cid, result["report_artifact_id"])["artifact_type"] == "figure_tracking_report"
