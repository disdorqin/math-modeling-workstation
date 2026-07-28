"""Paper data model for the M2 contest-grade paper layer.

A :class:`Paper` is a structured, machine-checkable document: sections contain
paragraphs (each evidence-anchored via ``[cite:artifact_id]``), equations (each
tied to registry symbols), figures and tables (each tied to a registered
evidence artifact). The model is plain dataclasses so it serialises to dict /
HTML and is trivially countable for the benchmark (>=8 figs, >=5 tables,
>=12 equations, >=3 candidates).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Equation:
    id: str
    latex: str
    introduced_symbols: List[str] = field(default_factory=list)
    used_symbols: List[str] = field(default_factory=list)
    evidence_ref: Optional[str] = None
    section_id: str = ""


@dataclass
class Figure:
    id: str
    kind: str  # "line" | "scatter" | "bar" | "heatmap" | "residual" ...
    caption: str
    evidence_ref: str
    section_id: str = ""
    path: Optional[str] = None


@dataclass
class Table:
    id: str
    caption: str
    columns: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    evidence_ref: str = ""
    section_id: str = ""


@dataclass
class Paragraph:
    section_id: str
    text: str
    evidence_refs: List[str] = field(default_factory=list)


@dataclass
class Section:
    id: str
    title: str
    paragraphs: List[Paragraph] = field(default_factory=list)
    equations: List[Equation] = field(default_factory=list)
    figures: List[Figure] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)


@dataclass
class Paper:
    title: str = ""
    abstract: str = ""
    sections: List[Section] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    candidate_families: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # -- construction helpers -------------------------------------------- #
    def add_section(self, section_id: str, title: str) -> Section:
        sec = Section(id=section_id, title=title)
        self.sections.append(sec)
        return sec

    def get_section(self, section_id: str) -> Section:
        for s in self.sections:
            if s.id == section_id:
                return s
        raise KeyError(f"no such section: {section_id}")

    def add_paragraph(self, section_id: str, text: str, evidence_refs: Optional[List[str]] = None) -> Paragraph:
        p = Paragraph(section_id=section_id, text=text, evidence_refs=evidence_refs or [])
        self.get_section(section_id).paragraphs.append(p)
        return p

    def add_equation(self, section_id: str, eq_id: str, latex: str, *, introduced: Optional[List[str]] = None,
                     used: Optional[List[str]] = None, evidence_ref: Optional[str] = None) -> Equation:
        eq = Equation(id=eq_id, latex=latex, introduced_symbols=introduced or [], used_symbols=used or [],
                      evidence_ref=evidence_ref, section_id=section_id)
        self.get_section(section_id).equations.append(eq)
        return eq

    def add_figure(self, section_id: str, fig_id: str, kind: str, caption: str, evidence_ref: str,
                   path: Optional[str] = None) -> Figure:
        f = Figure(id=fig_id, kind=kind, caption=caption, evidence_ref=evidence_ref,
                   section_id=section_id, path=path)
        self.get_section(section_id).figures.append(f)
        return f

    def add_table(self, section_id: str, table_id: str, caption: str, columns: List[str],
                  rows: List[List[str]], evidence_ref: str) -> Table:
        t = Table(id=table_id, caption=caption, columns=columns, rows=rows,
                  evidence_ref=evidence_ref, section_id=section_id)
        self.get_section(section_id).tables.append(t)
        return t

    # -- counts ---------------------------------------------------------- #
    def count_figures(self) -> int:
        return sum(len(s.figures) for s in self.sections)

    def count_tables(self) -> int:
        return sum(len(s.tables) for s in self.sections)

    def count_equations(self) -> int:
        return sum(len(s.equations) for s in self.sections)

    def count_candidates(self) -> int:
        return len(self.candidate_families)

    def all_evidence_refs(self) -> List[str]:
        refs: List[str] = []
        for s in self.sections:
            for p in s.paragraphs:
                refs.extend(p.evidence_refs)
            for f in s.figures:
                refs.append(f.evidence_ref)
            for t in s.tables:
                if t.evidence_ref:
                    refs.append(t.evidence_ref)
            for e in s.equations:
                if e.evidence_ref:
                    refs.append(e.evidence_ref)
        return refs

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "abstract": self.abstract,
            "candidate_families": self.candidate_families,
            "sections": [
                {
                    "id": s.id, "title": s.title,
                    "paragraphs": [{"text": p.text, "evidence_refs": p.evidence_refs} for p in s.paragraphs],
                    "equations": [e.__dict__ for e in s.equations],
                    "figures": [f.__dict__ for f in s.figures],
                    "tables": [t.__dict__ for t in s.tables],
                }
                for s in self.sections
            ],
            "references": self.references,
            "metadata": self.metadata,
            "counts": {
                "figures": self.count_figures(), "tables": self.count_tables(),
                "equations": self.count_equations(), "candidates": self.count_candidates(),
            },
        }

    def to_html(self) -> str:
        """Best-effort human-readable HTML rendering (used for the deliverable)."""
        parts: List[str] = [f"<h1>{self.title}</h1>", f"<p><em>Abstract.</em> {self.abstract}</p>"]
        for s in self.sections:
            parts.append(f"<h2>{s.title}</h2>")
            for p in s.paragraphs:
                parts.append(f"<p>{_esc(p.text)}</p>")
            for e in s.equations:
                parts.append(f"<div class='eq'>{_esc(e.latex)}</div>")
            for t in s.tables:
                parts.append(_render_table(t))
            for f in s.figures:
                if f.path:
                    parts.append(f"<figure><img src='{_esc(f.path)}' alt='{_esc(f.id)}'/><figcaption>{_esc(f.caption)}</figcaption></figure>")
                else:
                    parts.append(f"<figure><em>[{_esc(f.kind)} figure: {_esc(f.id)}]</em><figcaption>{_esc(f.caption)}</figcaption></figure>")
        return "\n".join(parts)


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _render_table(t: Table) -> str:
    head = "".join(f"<th>{_esc(c)}</th>" for c in t.columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(str(c))}</td>" for c in row) + "</tr>" for row in t.rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
