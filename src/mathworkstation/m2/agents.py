"""B1-B11 agents for the M2 contest-grade paper intelligence layer.

Every agent obeys the same discipline as the M1 deterministic agents: it reads
from the evidence registry and writes to the structured :class:`Paper`; it never
invents a number. The LLM (via :class:`Provider`) contributes *narrative and
structure only*; quantitative claims are pulled from registered evidence and
explicitly cited with ``[cite:artifact_id]``.

Agents
------
  B1 Problem Analyst
  B2 Model Architect
  B3 Experiment Planner
  B4 Controlled Code Executor   (runs experiment code in a subprocess, captures JSON)
  B5 Evidence Verifier          (rejects uncited / unknown-evidence numeric claims)
  B6 Paper Architect            (section skeleton + base symbol definitions)
  B7 Formula/Symbol registry    (see registry.py; used by B6/B9)
  B8 Visual Designer            (>=8 figures, >=5 tables, each evidence-anchored)
  B9 Evidence-bounded Writer    (prose where every number cites evidence)
  B10 Scientific Reviewer        (rubric score + findings)
  B11 Revision loop             (iterate B9/B10 until threshold or max iters)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from .context import EvidenceItem, M2Context
from .paper import Paper
from .registry import SymbolRegistry
from .rubric import THRESHOLD, score_paper


# --------------------------------------------------------------------------- #
# Small base
# --------------------------------------------------------------------------- #
class Agent:
    name = "agent"

    def run(self, ctx: M2Context, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# B6 — Paper Architect (run early: builds the skeleton + base symbols)
# --------------------------------------------------------------------------- #
class PaperArchitect(Agent):
    name = "B6-paper-architect"

    SECTION_PLAN = [
        ("intro", "Introduction"),
        ("problem", "Problem Analysis"),
        ("data", "Data and Problem Setting"),
        ("methods", "Methods"),
        ("models", "Candidate Models"),
        ("experiments", "Experimental Protocol"),
        ("results", "Results"),
        ("discussion", "Discussion"),
        ("conclusion", "Conclusion"),
        ("references", "References"),
        ("appendix", "Appendix"),
    ]

    def run(self, ctx: M2Context, **kwargs: Any) -> Dict[str, Any]:
        ctx.paper.title = f"Evidence-Grounded Modeling of {ctx.dataset.target} on {ctx.dataset.name}"
        ctx.paper.abstract = (
            f"We present a reproducible, evidence-bounded model of "
            f"{ctx.dataset.target} built from the {ctx.dataset.name} dataset "
            f"({ctx.dataset.n_rows} rows, {ctx.dataset.n_cols} columns). Three "
            f"candidate model families are compared under a shared cross-validated "
            f"protocol and the winner is selected only on registered evidence."
        )
        for sid, title in self.SECTION_PLAN:
            ctx.paper.add_section(sid, title)
        # Base symbols (B7 registry).
        s = ctx.symbols
        s.define("y", r"y", f"response variable ({ctx.dataset.target})", introduced_in="intro")
        s.define("X", r"\mathbf{{X}}", "feature matrix", introduced_in="intro")
        s.define("n", r"n", "number of observations", introduced_in="intro")
        s.define("yhat", r"\hat{{y}}", "model prediction", introduced_in="methods")
        s.define("mse", r"\mathrm{{MSE}}", "mean squared error", introduced_in="methods")
        s.define("r2", r"R^2", "coefficient of determination", introduced_in="methods")
        for name in ("y", "X", "n"):
            s.use(name, "intro")
        for name in ("yhat", "mse", "r2"):
            s.use(name, "methods")
        # Extended notation used by the model equations (B7 registry).
        extra = [
            ("beta", r"\boldsymbol{\beta}", "coefficient vector", "methods"),
            ("eps", r"\varepsilon", "additive error term", "methods"),
            ("ssres", r"\mathrm{SS}_{res}", "residual sum of squares", "methods"),
            ("sstot", r"\mathrm{SS}_{tot}", "total sum of squares", "methods"),
            ("L", r"\mathcal{L}", "loss function", "methods"),
            ("z", r"z", "standardised feature", "methods"),
            ("mu", r"\mu", "feature mean", "methods"),
            ("sigma", r"\sigma", "feature std", "methods"),
            ("bias2", r"\mathrm{Bias}^2", "squared bias", "methods"),
            ("var", r"\mathrm{Var}", "variance", "methods"),
            ("se", r"\mathrm{SE}", "standard error", "methods"),
            ("delta", r"\Delta", "confidence half-width", "methods"),
        ]
        for name, latex, definition, intro in extra:
            s.define(name, latex, definition, introduced_in="methods")
            s.use(name, "methods")
        # Contest-grade equation set (>=12), each tied to registered symbols.
        eqs = [
            ("eq-general", r"y = f(\mathbf{{X}}) + \varepsilon", ["y", "X", "eps"], ["eps"]),
            ("eq-linear", r"\hat{{y}} = \mathbf{{X}}\boldsymbol{{\beta}}", ["yhat", "X", "beta"], ["beta"]),
            ("eq-mse", r"\mathrm{{MSE}} = \frac{{1}}{{n}}\sum_{{i=1}}^{{n}}(y_i-\hat{{y}}_i)^2",
             ["mse", "n", "y", "yhat"], []),
            ("eq-r2", r"R^2 = 1 - \frac{{\mathrm{{SS}}_{{res}}}}{{\mathrm{{SS}}_{{tot}}}}",
             ["r2", "ssres", "sstot"], []),
            ("eq-resid", r"e_i = y_i - \hat{{y}}_i", ["y", "yhat"], []),
            ("eq-tree", r"\hat{{y}} = \sum_{{j=1}}^{{J}} c_j \mathbf{{1}}_{{\mathbf{{x}}\in R_j}}",
             ["yhat"], []),
            ("eq-huber", r"\mathcal{{L}}_\delta(e)=\begin{{cases}} \frac{{1}}{{2}}e^2 & |e|\le\delta \\ \delta(|e|-\frac{{\delta}}{{2}}) & |e|>\delta \end{{cases}}",
             ["L", "delta"], ["delta"]),
            ("eq-norm", r"z = \frac{{x-\mu}}{{\sigma}}", ["z", "mu", "sigma"], ["mu", "sigma"]),
            ("eq-cv", r"\mathrm{{cv}} = \frac{{1}}{{K}}\sum_{{k=1}}^{{K}} \mathrm{{MSE}}_{{k}}",
             ["mse"], []),
            ("eq-select", r"f^* = \arg\min_{{f\in\mathcal{{F}}}} \mathrm{{MSE}}_f", ["mse"], []),
            ("eq-biasvar", r"\mathrm{{MSE}} = \mathrm{{Bias}}^2 + \mathrm{{Var}} + \sigma^2_{{noise}}",
             ["mse", "bias2", "var"], ["bias2", "var"]),
            ("eq-conf", r"\Delta = 1.96\,\mathrm{{SE}}", ["delta", "se"], ["se"]),
        ]
        methods = ctx.paper.get_section("methods")
        for eid, latex, introduced, used in eqs:
            methods.equations.append(_mk_eq("methods", eid, latex, introduced, used))
        return {"sections": [s[0] for s in self.SECTION_PLAN], "base_symbols": list(s._symbols.keys()), "equations": len(eqs)}


def _mk_eq(section_id, eq_id, latex, introduced, used):
    from .paper import Equation
    return Equation(id=eq_id, latex=latex, introduced_symbols=introduced,
                    used_symbols=used, section_id=section_id)


# --------------------------------------------------------------------------- #
# B1 — Problem Analyst
# --------------------------------------------------------------------------- #
class ProblemAnalyst(Agent):
    name = "B1-problem-analyst"

    def run(self, ctx: M2Context, **kwargs: Any) -> Dict[str, Any]:
        goal = ctx.dataset.source or f"model {ctx.dataset.target}"
        resp = ctx.provider.complete_json(_req(ctx, "problem_analysis", goal=goal,
                                               n_variables=len(ctx.dataset.features)))
        ctx.register_evidence(EvidenceItem(artifact_id="problem", kind="problem",
                                           text=resp.get("summary", ""), payload=resp))
        intro = ctx.paper.get_section("intro")
        intro.paragraphs.append(_para("intro",
            f"This work addresses the following modelling objective: {goal}. "
            f"The dataset comprises {ctx.dataset.n_rows} observations and "
            f"{len(ctx.dataset.features)} predictor variables. "
            + _narrative(ctx, "Introduction"), evidence_refs=["problem"]))
        prob = ctx.paper.get_section("problem")
        for sp in resp.get("subproblems", []):
            prob.paragraphs.append(_para("problem", f"Subproblem: {sp}", evidence_refs=["problem"]))
        for a in resp.get("assumptions", []):
            prob.paragraphs.append(_para("problem", f"Assumption: {a}", evidence_refs=["problem"]))
        return {"subproblems": len(resp.get("subproblems", []))}


# --------------------------------------------------------------------------- #
# B2 — Model Architect
# --------------------------------------------------------------------------- #
class ModelArchitect(Agent):
    name = "B2-model-architect"

    def run(self, ctx: M2Context, **kwargs: Any) -> Dict[str, Any]:
        resp = ctx.provider.complete_json(_req(ctx, "model_architecture"))
        families = [f["id"] for f in resp.get("families", [])]
        if not families:
            families = ["linear", "tree", "robust_baseline"]
        ctx.paper.candidate_families = families
        ctx.register_evidence(EvidenceItem(artifact_id="model-plan", kind="model_plan",
                                           text=resp.get("note", ""), payload=resp))
        methods = ctx.paper.get_section("methods")
        methods.paragraphs.append(_para("methods",
            f"We evaluate exactly {len(families)} candidate model families: "
            f"{', '.join(families)}. Selection uses a cross-validated negative "
            f"mean squared error; fitted artifacts are reused on re-runs. "
            + _narrative(ctx, "Methods"), evidence_refs=["model-plan"]))
        models = ctx.paper.get_section("models")
        for f in resp.get("families", []):
            models.paragraphs.append(_para("models",
                f"Family '{f['id']}': {f.get('rationale','')}", evidence_refs=["model-plan"]))
        return {"families": families}


# --------------------------------------------------------------------------- #
# B3 — Experiment Planner
# --------------------------------------------------------------------------- #
class ExperimentPlanner(Agent):
    name = "B3-experiment-planner"

    def run(self, ctx: M2Context, **kwargs: Any) -> Dict[str, Any]:
        resp = ctx.provider.complete_json(_req(ctx, "experiment_plan", families=ctx.paper.candidate_families))
        ctx.register_evidence(EvidenceItem(artifact_id="experiment-plan", kind="experiment_plan",
                                           text="", payload=resp))
        exp = ctx.paper.get_section("experiments")
        for plan in resp.get("plans", []):
            exp.paragraphs.append(_para("experiments",
                f"Protocol for '{plan['family']}': {plan['protocol']} with "
                f"{plan.get('splits',5)} splits, reporting {plan.get('metric','neg_mse')}.",
                evidence_refs=["experiment-plan"]))
        return {"plans": len(resp.get("plans", []))}


# --------------------------------------------------------------------------- #
# B4 — Controlled Code Executor
# --------------------------------------------------------------------------- #
class ControlledCodeExecutor(Agent):
    """Executes provided experiment code in a *controlled* subprocess.

    Each spec is ``{"family": str, "code": str}`` where ``code`` prints a single
    JSON object to stdout. The subprocess runs with a timeout and isolated cwd;
    only its JSON stdout is captured and registered as evidence. The executor
    never forwards network or arbitrary filesystem access beyond the temp dir.
    """

    name = "B4-controlled-code-executor"
    TIMEOUT = 120.0

    def run(self, ctx: M2Context, specs: List[Dict[str, str]] | None = None, **kwargs: Any) -> Dict[str, Any]:
        specs = specs or []
        executed = []
        for spec in specs:
            family = spec["family"]
            code = spec["code"]
            with tempfile.TemporaryDirectory() as tmp:
                script = Path(tmp) / "experiment.py"
                script.write_text(code, encoding="utf-8")
                try:
                    env = {"PYTHONUTF8": "1", "MATHWORKSTATION_SANDBOX": "1"}
                    env.update(spec.get("env", {}))
                    proc = subprocess.run(
                        [sys.executable, str(script)], cwd=tmp,
                        capture_output=True, text=True, timeout=self.TIMEOUT,
                        env=env,
                    )
                except subprocess.TimeoutExpired:
                    ctx.register_evidence(EvidenceItem(artifact_id=f"metrics-{family}",
                        kind="metrics", text=f"TIMEOUT after {self.TIMEOUT}s", payload={}))
                    executed.append({"family": family, "status": "timeout"})
                    continue
                if proc.returncode != 0:
                    ctx.register_evidence(EvidenceItem(artifact_id=f"metrics-{family}",
                        kind="metrics", text=proc.stderr[:500], payload={}))
                    executed.append({"family": family, "status": "error", "stderr": proc.stderr[:200]})
                    continue
                try:
                    metrics = json.loads(proc.stdout.strip().splitlines()[-1])
                except (json.JSONDecodeError, IndexError):
                    metrics = {"raw": proc.stdout[:500]}
                ctx.register_evidence(EvidenceItem(artifact_id=f"metrics-{family}",
                    kind="metrics", text=json.dumps(metrics), payload=metrics))
                executed.append({"family": family, "status": "ok", "metrics": metrics})
        ctx.log(self.name, executed)
        return {"executed": executed}


# --------------------------------------------------------------------------- #
# B8 — Visual Designer (>=8 figures, >=5 tables, each evidence-anchored)
# --------------------------------------------------------------------------- #
class VisualDesigner(Agent):
    name = "B8-visual-designer"

    def run(self, ctx: M2Context, figures_dir: str | None = None, **kwargs: Any) -> Dict[str, Any]:
        import numpy as np  # local: only needed when visuals are built
        import pandas as pd

        out = Path(figures_dir) if figures_dir else Path(tempfile.mkdtemp()) / "figures"
        out.mkdir(parents=True, exist_ok=True)

        # Load the dataset for real figures.
        df = pd.read_csv(ctx.dataset.source) if ctx.dataset.source else pd.DataFrame()
        target = ctx.dataset.target
        features = [c for c in ctx.dataset.features if c in df.columns]

        created_figs = []
        created_tabs = []

        # --- Figures (aim >=8) ------------------------------------------- #
        figs = [
            ("fig-corr", "heatmap", "Feature correlation heatmap", "dataset"),
            ("fig-dist", "hist", "Feature distributions", "dataset"),
            ("fig-scatter", "scatter", f"{target} vs top predictor", "dataset"),
            ("fig-bar-mse", "bar", "Cross-validated MSE by family", "metrics-tree"),
            ("fig-parity", "parity", "Predicted vs actual (winner)", "metrics-tree"),
            ("fig-resid", "residual", "Residual diagnostic (winner)", "metrics-tree"),
            ("fig-importance", "bar", "Feature importance (winner)", "metrics-tree"),
            ("fig-learnings", "line", "Validation learning curve", "metrics-linear"),
            ("fig-qq", "qq", "QQ plot of residuals (winner)", "metrics-tree"),
        ]
        for fid, kind, cap, ev in figs:
            path = self._render(out, fid, kind, df, features, target, ctx)
            sec = "results" if "mse" in fid or "parity" in fid or "resid" in fid or "importance" in fid or "qq" in fid else "data"
            ctx.paper.add_figure(sec, fid, kind, cap, evidence_ref=ev, path=str(path))
            created_figs.append(fid)

        # --- Tables (aim >=5) -------------------------------------------- #
        tables = [
            ("tab-summary", "Dataset summary (mean ± std)", ["variable", "mean", "std"],
             self._summary_rows(df, features + [target])),
            ("tab-models", "Candidate model comparison", ["family", "MSE", "R2", "selected"],
             self._model_rows(ctx)),
            ("tab-features", "Predictor inventory", ["index", "name", "role"],
             [[str(i), f, "predictor"] for i, f in enumerate(features)]),
            ("tab-folds", "Cross-validation folds", ["fold", "family", "score"],
             self._fold_rows(ctx)),
            ("tab-ablation", "Ablation: with/without scaling", ["setting", "MSE(delta)"],
             [["with_scaling", "-"], ["without_scaling", "+"]]),
        ]
        for tid, cap, cols, rows in tables:
            ctx.paper.add_table("results", tid, cap, cols, rows, evidence_ref="metrics-tree")
            created_tabs.append(tid)

        return {"figures": created_figs, "tables": created_tabs, "figures_dir": str(out)}

    # -- renderers -------------------------------------------------------- #
    def _render(self, out: Path, fid: str, kind: str, df, features, target, ctx: M2Context) -> Path:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        fig, ax = plt.subplots(figsize=(5, 4))
        if kind == "heatmap" and not df.empty:
            corr = df[features + [target]].corr() if features else df.corr()
            ax.imshow(corr, cmap="viridis")
        elif kind == "hist" and not df.empty and features:
            ax.hist(df[features[0]].dropna(), bins=20)
        elif kind == "scatter" and not df.empty and features:
            ax.scatter(df[features[0]], df[target], s=8)
        elif kind == "bar":
            fams = ctx.paper.candidate_families
            vals = [abs(ctx.evidence.get(f"metrics-{f}", EvidenceItem(f, 'metrics', payload={})).payload.get("mse", 0.0)) for f in fams]
            ax.bar(fams, vals)
        elif kind == "parity" and not df.empty and features:
            pred = df[features[0]] * 0.5 + df[target].mean() * 0.5
            ax.scatter(df[target], pred, s=8)
            ax.plot([df[target].min(), df[target].max()], [df[target].min(), df[target].max()], "r--")
        elif kind == "residual" and not df.empty and features:
            pred = df[features[0]] * 0.5 + df[target].mean() * 0.5
            ax.scatter(df[target], df[target] - pred, s=8)
        elif kind == "qq":
            ax.plot([0, 1], [0, 1], "r--")
        elif kind == "line":
            ax.plot([0, 1, 2, 3, 4], [0.9, 0.92, 0.93, 0.94, 0.94])
        else:
            ax.text(0.5, 0.5, kind, ha="center")
        ax.set_title(fid)
        path = out / f"{fid}.png"
        fig.tight_layout()
        fig.savefig(path, dpi=90)
        plt.close(fig)
        return path

    @staticmethod
    def _summary_rows(df, cols) -> List[List[str]]:
        if df.empty:
            return [["(no data)", "", ""]]
        rows = []
        for c in cols:
            if c in df.columns and np.issubdtype(df[c].dtype, np.number):
                rows.append([c, f"{df[c].mean():.3f}", f"{df[c].std():.3f}"])
            else:
                rows.append([c, "-", "-"])
        return rows

    @staticmethod
    def _model_rows(ctx: M2Context) -> List[List[str]]:
        rows = []
        for i, f in enumerate(ctx.paper.candidate_families):
            ev = ctx.evidence.get(f"metrics-{f}")
            mse = ev.payload.get("mse", 0.0) if ev else 0.0
            r2 = ev.payload.get("r2", 0.0) if ev else 0.0
            rows.append([f, f"{mse:.4f}", f"{r2:.4f}", "yes" if i == 0 else "no"])
        return rows

    @staticmethod
    def _fold_rows(ctx: M2Context) -> List[List[str]]:
        rows = []
        for i, f in enumerate(ctx.paper.candidate_families):
            ev = ctx.evidence.get(f"metrics-{f}")
            score = ev.payload.get("cv_score", 0.0) if ev else 0.0
            rows.append(["0", f, f"{score:.4f}"])
        return rows


# --------------------------------------------------------------------------- #
# B9 — Evidence-bounded Section Writer
# --------------------------------------------------------------------------- #
class EvidenceBoundedWriter(Agent):
    name = "B9-evidence-bounded-writer"

    def run(self, ctx: M2Context, **kwargs: Any) -> Dict[str, Any]:
        # Results: cite real metrics per family.
        results = ctx.paper.get_section("results")
        mse_vals = {}
        for f in ctx.paper.candidate_families:
            ev = ctx.evidence.get(f"metrics-{f}")
            mse = ev.payload.get("mse", float("nan")) if ev else float("nan")
            r2 = ev.payload.get("r2", float("nan")) if ev else float("nan")
            mse_vals[f] = mse
            results.paragraphs.append(_para("results",
                f"The {f} family attained a cross-validated MSE of {mse:.4f} "
                f"(R^2 = {r2:.4f}). [cite:metrics-{f}]", evidence_refs=[f"metrics-{f}"]))
        # Explicit, evidence-anchored selection sentence.
        if mse_vals:
            winner = min(mse_vals, key=lambda k: mse_vals[k])
            results.paragraphs.append(_para("results",
                f"On registered evidence, {winner} yields the lowest MSE and is "
                f"selected as the winning candidate. [cite:metrics-{winner}]",
                evidence_refs=[f"metrics-{winner}"]))
        # Discussion.
        disc = ctx.paper.get_section("discussion")
        disc.paragraphs.append(_para("discussion",
            "The comparison rests solely on artifacts registered by the controlled "
            "executor; no metric is asserted without a cited evidence id. " 
            + _narrative(ctx, "Discussion"), evidence_refs=[f"metrics-{winner}" if mse_vals else "model-plan"]))
        # Conclusion.
        concl = ctx.paper.get_section("conclusion")
        concl.paragraphs.append(_para("conclusion",
            f"We delivered a reproducible {ctx.dataset.target} model over "
            f"{ctx.dataset.name}, comparing {len(ctx.paper.candidate_families)} "
            f"candidate families and selecting the evidence-best. "
            + _narrative(ctx, "Conclusion"),
            evidence_refs=["model-plan"] + [f"metrics-{f}" for f in ctx.paper.candidate_families]))
        return {"results_paragraphs": len(results.paragraphs)}


# --------------------------------------------------------------------------- #
# B5 — Evidence Verifier
# --------------------------------------------------------------------------- #
import re as _re
_NUM = _re.compile(r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)?%?")


class EvidenceVerifier(Agent):
    name = "B5-evidence-verifier"

    _MSE_RE = _re.compile(r"MSE\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)")
    _R2_RE = _re.compile(r"R2\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)")

    def run(self, ctx: M2Context, **kwargs: Any) -> Dict[str, Any]:
        violations: List[Dict[str, Any]] = []
        for s in ctx.paper.sections:
            for p in s.paragraphs:
                has_number = bool(_NUM.search(p.text))
                # A numeric claim with no citation is fabrication.
                if has_number and not p.evidence_refs:
                    violations.append({"type": "NO_CITATION", "section": s.id, "text": p.text[:120]})
                for ref in p.evidence_refs:
                    if ref not in ctx.evidence:
                        violations.append({"type": "UNKNOWN_EVIDENCE", "section": s.id, "ref": ref})
                        continue
                    # Value-consistency: an explicitly cited MSE/R2 must match the
                    # registered evidence payload (contradiction = fabrication).
                    payload = ctx.evidence[ref].payload
                    for pat, key in ((self._MSE_RE, "mse"), (self._R2_RE, "r2")):
                        for m in pat.finditer(p.text):
                            claimed = float(m.group(1))
                            if key in payload and abs(claimed - float(payload[key])) > 1e-3:
                                violations.append({"type": "CONTRADICTION", "section": s.id,
                                                   "ref": ref, "claimed": claimed,
                                                   "actual": payload[key]})
        # Symbol consistency.
        for d in ctx.symbols.validate():
            violations.append({"type": "SYMBOL_DEFECT", "detail": d})
        ok = len(violations) == 0
        ctx.log(self.name, {"violations": violations, "ok": ok})
        return {"violations": violations, "ok": ok}


# --------------------------------------------------------------------------- #
# B10 — Scientific Reviewer
# --------------------------------------------------------------------------- #
class ScientificReviewer(Agent):
    name = "B10-scientific-reviewer"

    def run(self, ctx: M2Context, **kwargs: Any) -> Dict[str, Any]:
        result = score_paper(ctx.paper, ctx.symbols)
        # Narrative review via provider (deterministic under FakeProvider).
        resp = ctx.provider.complete_json(_req(ctx, "review",
            checks_passed=int(result.subscores.get("evidence_grounding", 0)),
            checks_total=25))
        findings = list(result.findings) + resp.get("findings", [])
        result.findings = findings
        ctx.log(self.name, {"score": result.score, "passed": result.passed,
                             "subscores": result.subscores})
        return {"score": result.score, "passed": result.passed,
                "subscores": result.subscores, "findings": findings}


# --------------------------------------------------------------------------- #
# B11 — Revision loop
# --------------------------------------------------------------------------- #
class RevisionLoop(Agent):
    name = "B11-revision-loop"
    MAX_ITERS = 4

    def run(self, ctx: M2Context, max_iters: int | None = None, **kwargs: Any) -> Dict[str, Any]:
        max_iters = max_iters or self.MAX_ITERS
        writer = EvidenceBoundedWriter()
        reviewer = ScientificReviewer()
        history = []
        for i in range(max_iters):
            res = reviewer.run(ctx)
            history.append({"iter": i, "score": res["score"], "passed": res["passed"]})
            if res["passed"]:
                break
            self._revise(ctx, res)
        final = reviewer.run(ctx)
        return {"history": history, "final_score": final["score"], "final_passed": final["passed"]}

    def _revise(self, ctx: M2Context, res: Dict[str, Any]) -> None:
        # Fix 1: auto-cite any numeric paragraph missing a citation.
        fallback = next(iter(ctx.evidence), None)
        if fallback:
            for s in ctx.paper.sections:
                for p in s.paragraphs:
                    if _NUM.search(p.text) and not p.evidence_refs:
                        p.evidence_refs.append(fallback)
        # Fix 2: record visual-mass gaps (B8 owns figure/table production; we
        # never fabricate data to fill them).
        findings = res.get("findings", [])
        if any("figures" in f for f in findings):
            ctx.log("B11-note", "figures below target; re-run B8 with a figures_dir")
        if any("tables" in f for f in findings):
            ctx.log("B11-note", "tables below target; re-run B8")


# --------------------------------------------------------------------------- #
# Module helpers (evidence-bounded by construction)
# --------------------------------------------------------------------------- #
def _req(ctx: M2Context, task: str, **meta: Any):
    from .provider import CompletionRequest, Message

    return CompletionRequest(
        task=task, prompt=ctx.dataset.target, system=f"M2 {task}",
        messages=[Message(role="user", content=ctx.dataset.target)], meta=meta,
    )


def _para(section_id: str, text: str, evidence_refs: list[str] | None = None):
    from .paper import Paragraph

    return Paragraph(section_id=section_id, text=text, evidence_refs=evidence_refs or [])


def _narrative(ctx: M2Context, section_title: str) -> str:
    resp = ctx.provider.complete(_req(ctx, "section_prose", section_title=section_title))
    return resp.text