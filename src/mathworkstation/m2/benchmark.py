"""M2 contest-grade benchmark.

Builds the experiment specs (real, deterministic sklearn code), runs the full
B1-B11 pipeline with the FakeProvider, asserts the contest-grade structural and
quality thresholds, and writes deliverables (HTML paper + JSON summary, and a
PDF when reportlab is available).

Thresholds (all must hold):
  figures   >= 8
  tables    >= 5
  equations >= 12
  candidates>= 3
  rubric    >= 75   (THRESHOLD in rubric.py)
  verifier  ok (no NO_CITATION / UNKNOWN_EVIDENCE / symbol defects)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .context import DatasetDescriptor, EvidenceItem, M2Context
from .paper import Paper
from .pipeline import pipeline_summary, run_pipeline
from .provider import get_provider
from .registry import SymbolRegistry
from .rubric import THRESHOLD

EXPERIMENT_CODE = '''import os, json
import numpy as np, pandas as pd
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.linear_model import LinearRegression, HuberRegressor
from sklearn.tree import DecisionTreeRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score

path = os.environ["DATASET_PATH"]
family = os.environ["FAMILY"]
target = os.environ.get("TARGET", "progression")
df = pd.read_csv(path)
X = df.drop(columns=[target]).select_dtypes(include=[np.number])
y = df[target].values.astype(float)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
if family == "linear":
    model = make_pipeline(StandardScaler(), LinearRegression())
elif family == "tree":
    model = DecisionTreeRegressor(random_state=42, max_depth=4)
elif family == "robust_baseline":
    model = make_pipeline(StandardScaler(), HuberRegressor(max_iter=200))
else:
    raise SystemExit("unknown family: " + family)
cv = cross_val_score(model, X, y, cv=5, scoring="neg_mean_squared_error", n_jobs=1)
model.fit(Xtr, ytr)
pred = model.predict(Xte)
mse = float(mean_squared_error(yte, pred))
r2 = float(r2_score(yte, pred))
print(json.dumps({"family": family, "mse": mse, "r2": r2,
                  "cv_score": float(-cv.mean())}))
'''


def build_experiment_specs(dataset_path: str, target: str, families: List[str]) -> List[Dict[str, str]]:
    specs = []
    for f in families:
        specs.append({
            "family": f,
            "code": EXPERIMENT_CODE,
            "env": {"DATASET_PATH": dataset_path, "FAMILY": f, "TARGET": target},
        })
    return specs


def _describe_dataset(dataset_path: str, target: str) -> DatasetDescriptor:
    import pandas as pd

    df = pd.read_csv(dataset_path)
    features = [c for c in df.columns if c != target]
    return DatasetDescriptor(
        name=Path(dataset_path).stem, target=target, features=features,
        n_rows=int(df.shape[0]), n_cols=int(df.shape[1]), source=dataset_path,
    )


@dataclass
class BenchmarkResult:
    passed: bool
    summary: Dict[str, object]
    failures: List[str]

    def to_dict(self) -> dict:
        return {"passed": self.passed, "failures": self.failures, "summary": self.summary,
                "threshold": THRESHOLD}


def run_benchmark(dataset_path: str, target: str = "progression",
                  families: List[str] | None = None,
                  provider_name: str = "fake", figures_dir: str | None = None,
                  out_dir: str | None = None, max_revision_iters: int = 4) -> BenchmarkResult:
    families = families or ["linear", "tree", "robust_baseline"]
    descriptor = _describe_dataset(dataset_path, target)
    ctx = M2Context(dataset=descriptor, provider=get_provider(provider_name),
                    paper=Paper(), symbols=SymbolRegistry())
    specs = build_experiment_specs(dataset_path, target, families)
    run_pipeline(ctx, specs, figures_dir=figures_dir, max_revision_iters=max_revision_iters)
    summary = pipeline_summary(ctx)

    failures: List[str] = []
    c = summary["counts"]
    if c["figures"] < 8:
        failures.append(f"figures {c['figures']} < 8")
    if c["tables"] < 5:
        failures.append(f"tables {c['tables']} < 5")
    if c["equations"] < 12:
        failures.append(f"equations {c['equations']} < 12")
    if c["candidates"] < 3:
        failures.append(f"candidates {c['candidates']} < 3")
    reviewer = summary["reviewer"]
    score = reviewer.get("score", 0)
    if score < THRESHOLD:
        failures.append(f"rubric {score} < {THRESHOLD}")
    verifier = summary["verifier"]
    if not verifier.get("ok", False):
        failures.append(f"evidence verifier found violations: {verifier.get('violations')}")

    passed = not failures

    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "paper.html").write_text(ctx.paper.to_html(), encoding="utf-8")
        (out / "benchmark_summary.json").write_text(
            json.dumps(BenchmarkResult(passed, summary, failures).to_dict(),
                       ensure_ascii=False, indent=2), encoding="utf-8")
        _maybe_pdf(ctx, out)

    return BenchmarkResult(passed=passed, summary=summary, failures=failures)


def _maybe_pdf(ctx, out: Path) -> None:
    try:
        from reportlab.lib.pagesizes import A4  # noqa: F401
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer  # noqa: F401
    except Exception:
        return  # reportlab optional; HTML deliverable is sufficient
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

        doc = SimpleDocTemplate(str(out / "paper.pdf"), pagesize=A4)
        styles = getSampleStyleSheet()
        story = [Paragraph(ctx.paper.title, styles["Title"]),
                 Paragraph(ctx.paper.abstract, styles["BodyText"])]
        for s in ctx.paper.sections:
            story.append(Paragraph(s.title, styles["Heading2"]))
            for p in s.paragraphs:
                story.append(Paragraph(p.text.replace("[cite:", "(cite ").replace("]", ")"), styles["BodyText"]))
            for e in s.equations:
                story.append(Paragraph(e.latex, styles["BodyText"]))
        doc.build(story)
    except Exception:
        return
