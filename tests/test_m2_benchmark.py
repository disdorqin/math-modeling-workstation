"""M2 — contest-grade benchmark (heavy, but offline and deterministic).

Runs the full B1-B11 pipeline with the FakeProvider against a small synthetic
dataset, then asserts the contest-grade structural and quality thresholds:

  figures   >= 8
  tables    >= 5
  equations >= 12
  candidates>= 3
  rubric    >= 75   (THRESHOLD)
  verifier  ok (no NO_CITATION / UNKNOWN_EVIDENCE / CONTRADICTION)

Deliverables (paper.html + benchmark_summary.json) are also written and checked.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from mathworkstation.m2.benchmark import run_benchmark


def _make_dataset(path: Path) -> None:
    rng = np.random.default_rng(42)
    n = 120
    X = rng.normal(size=(n, 5))
    beta = np.array([0.5, -0.3, 0.2, 0.1, -0.4])
    y = X @ beta + 0.1 * rng.normal(size=n)
    df = pd.DataFrame(X, columns=[f"x{i + 1}" for i in range(5)])
    df["progression"] = y
    df.to_csv(path, index=False)


def test_benchmark_meets_contest_grade(tmp_path: Path):
    ds = tmp_path / "data.csv"
    _make_dataset(ds)
    out = tmp_path / "out"

    res = run_benchmark(
        str(ds), target="progression", provider_name="fake",
        figures_dir=str(tmp_path / "figs"), out_dir=str(out),
    )

    assert res.passed is True
    c = res.summary["counts"]
    assert c["figures"] >= 8, c
    assert c["tables"] >= 5, c
    assert c["equations"] >= 12, c
    assert c["candidates"] >= 3, c
    assert res.summary["verifier"]["ok"] is True


def test_benchmark_writes_deliverables(tmp_path: Path):
    ds = tmp_path / "data.csv"
    _make_dataset(ds)
    out = tmp_path / "out"

    res = run_benchmark(
        str(ds), target="progression", provider_name="fake",
        figures_dir=str(tmp_path / "figs"), out_dir=str(out),
    )

    assert (out / "paper.html").exists()
    assert (out / "benchmark_summary.json").exists()

    data = json.loads((out / "benchmark_summary.json").read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert data["summary"]["reviewer"]["score"] >= data["threshold"]
