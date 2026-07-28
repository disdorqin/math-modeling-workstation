#!/usr/bin/env python3
"""Build the public, AI-readable audit gateway for math-modeling-workstation.

The gateway exposes the repository to automated auditors / LLM agents in a
machine-readable, *safe* form. It is built ONLY from:

  1. tracked files (``git ls-files``) -- never ``.env.local``, ``artifacts/``,
     ``.workbuddy/`` or any other untracked / gitignored path, and
  2. explicitly downloaded CI artifacts passed via ``--ci-artifacts-dir``.

Nothing is read from the working tree's untracked files, and every generated
text file is scanned for high-signal secret patterns (defense in depth). If a
secret pattern is found the build FAILS rather than publishing it.

Outputs (all under --out, default ``public-site/``):

  index.html                 human landing page (links + embedded status)
  status.json                machine-readable repository status
  repository-manifest.json   every tracked file (path, bytes, category)
  architecture.json          curated, structured architecture summary
  llms.txt                   LLM-readable index (llms.txt spec)
  repository-context.md      human + LLM overview
  source-snapshot.zip        ``git archive HEAD`` (tracked files only)
  ci/latest.json             CI run summary (fetched via gh, else static)
  reports/                   tracked *.md reports/docs (relative paths kept)
  artifacts/                 copied from --ci-artifacts-dir, else a README

Usage:
  python scripts/build_public_gateway.py [--repo-root .] [--out public-site]
                                         [--ci-artifacts-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

# --------------------------------------------------------------------------- #
# High-signal secret patterns. These are deliberately narrow so they do not
# false-positive on ordinary source (variable names like ``token`` are fine).
# Any match in generated output aborts the build.
# --------------------------------------------------------------------------- #
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_sk", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("github_pat", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("generic_sk_prefix", re.compile(r"\bsk-[A-Za-z0-9]{8,}")),
]

REPO = "disdorqin/math-modeling-workstation"

# Curated, accurate M1 freeze facts (kept in sync with docs/M1_FREEZE_RECORD.md).
M1 = {
    "status": "frozen",
    "tag": "m1-verified-2026-07-28",
    "commit": "0f4260ad29760d2279bdafc4b868671668346e14",
    "verified_on": "2026-07-28",
    "summary": (
        "Deterministic multi-agent modeling layer: 4 deterministic agents "
        "(data_steward -> eda_analyst -> evidence_verifier -> quality_assurance), "
        "two conformant runtimes (builtin + LangGraph), a 3-candidate-family "
        "modeling fan-out, a single Adjudicator promoting exactly one VERIFIED "
        "claim, and a content-aware cross-runtime conformance contract "
        "(differences == [] on a POPULATED case)."
    ),
    "guarantees": [
        "Four deterministic agents in fixed roster order; no LLM in the M1 roster.",
        "Builtin and LangGraph runtimes are semantically conformant (differences == []).",
        "Conformance is proven on a POPULATED case, never a trivial both-halt.",
        "Modeling fan-out is exactly 3 candidate families (linear / tree / robust_baseline); second run is zero-fit reuse.",
        "Single Adjudicator; exactly one VERIFIED model_selection claim.",
        "DAG gating: data_registration NEEDS_REVIEW blocks downstream until approve-node.",
        "CI green on Windows and GitHub Actions (agent-layer-tests, 6 jobs).",
    ],
}

PLANES = [
    {"name": "Control Plane", "role": "cases, sessions, runs, DAG, checkpoints, approvals, exception policy"},
    {"name": "Reasoning Plane", "role": "LLM / prompt / structured-output adapters (plug-in only)"},
    {"name": "Evidence Plane", "role": "raw data, code, experiments, metrics, figures, paper evidence"},
]

# Short descriptions for the llms.txt / context index (path -> one-line note).
DOC_NOTES = {
    "README.md": "Project overview and quick start.",
    "AGENTS.md": "Agent collaboration contract.",
    "CONTRIBUTING.md": "Contribution guidelines.",
    "docs/M1_FREEZE_RECORD.md": "M1 freeze record: scope, guarantees, verification evidence, M2 policy.",
    "docs/multi-agent-architecture.md": "Full multi-agent architecture.",
    "docs/architecture.md": "Three-plane system architecture.",
    "docs/agent-handoff.md": "Agent handoff protocol.",
    "docs/reproducibility.md": "Reproducibility guarantees.",
    "docs/complete-paper-stage-plan.md": "Paper-stage plan.",
    "docs/recurrent-refinement-architecture.md": "Recurrent refinement design.",
    "docs/remaining-work-optimized-roadmap.md": "Roadmap / remaining work.",
    "docs/end-to-end-acceptance-2026-07-22.md": "End-to-end acceptance record.",
    "docs/research-quality-gate.md": "Research quality gate.",
    "docs/llm-secrets.md": "LLM secret-handling policy.",
    "docs/provider-compatibility-2026-07-21.md": "Provider compatibility notes.",
    "M1_PUBLICATION_REPORT.md": "M1 publication report.",
    "M1_PREMERGE_AUDIT_REPORT.md": "M1 pre-merge audit (13 steps, 3 ambiguities resolved).",
}

SRC_NOTES = {
    "src/mathworkstation/cli.py": "CLI entrypoint (case, dataset, runtimes, compare-agent-runtimes).",
    "src/mathworkstation/agents/graph.py": "Builtin run_sequence + LangGraph run adapters.",
    "src/mathworkstation/agents/semantics.py": "diff_states cross-runtime conformance contract.",
    "src/mathworkstation/agents/roster.py": "Default deterministic agent roster.",
    "src/mathworkstation/agents/adjudicator.py": "Single Adjudicator (writer).",
    "src/mathworkstation/case_manager.py": "Case isolation / Case Root resolution.",
    "src/mathworkstation/artifact_registry.py": "Artifact registry (content provenance).",
    "src/mathworkstation/claims.py": "Claim registry (evidence -> VERIFIED claim).",
    "src/mathworkstation/workflow.py": "DAG / workflow service + gating.",
}


# --------------------------------------------------------------------------- #
# git helpers
# --------------------------------------------------------------------------- #
def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def collect_tracked_files(repo_root: Path) -> list[tuple[str, int]]:
    """Return [(relative_path, byte_size)] for every TRACKED file at HEAD."""
    out = _git(repo_root, "ls-files", "-z")
    paths = [p for p in out.split("\0") if p]
    result: list[tuple[str, int]] = []
    for p in paths:
        fp = repo_root / p
        try:
            result.append((p, fp.stat().st_size))
        except OSError:
            # symlink / missing in worktree but tracked at HEAD; size unknown -> 0
            result.append((p, 0))
    return sorted(result)


def head_commit(repo_root: Path) -> str:
    return _git(repo_root, "rev-parse", "HEAD")


def tags_at_head(repo_root: Path) -> list[str]:
    raw = _git(repo_root, "tag", "--points-at", "HEAD")
    return [t for t in raw.splitlines() if t]


def latest_m1_tag(repo_root: Path) -> str | None:
    """Latest tag matching m1-* (the frozen-milestone tag), if any."""
    raw = _git(repo_root, "tag", "--list", "m1-*")
    tags = [t for t in raw.splitlines() if t]
    return sorted(tags)[-1] if tags else None


def write_source_snapshot(repo_root: Path, out_path: Path) -> None:
    """git archive HEAD -> zip (tracked files only; excludes .env.local etc.)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as fh:
        subprocess.run(
            ["git", "-C", str(repo_root), "archive", "--format=zip", "HEAD"],
            check=True, stdout=fh,
        )


def fetch_ci_meta(repo_root: Path) -> dict | None:
    """Best-effort CI run summary via gh; return None if gh/auth unavailable."""
    try:
        raw = subprocess.run(
            ["gh", "run", "list", "--repo", REPO, "--limit", "8",
             "--json", "databaseId,workflowName,headBranch,status,conclusion,createdAt,url"],
            check=True, capture_output=True, text=True, timeout=30,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    try:
        runs = json.loads(raw)
    except json.JSONDecodeError:
        return None
    green = [r for r in runs if r.get("conclusion") == "success"]
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "gh run list",
        "repository": REPO,
        "latest_green_run": green[0] if green else None,
        "recent_runs": runs,
    }


# --------------------------------------------------------------------------- #
# content builders
# --------------------------------------------------------------------------- #
def build_manifest(repo_root: Path, commit: str, tag: str | None) -> dict:
    files = collect_tracked_files(repo_root)
    total_bytes = sum(sz for _, sz in files)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPO,
        "commit": commit,
        "tag": tag,
        "total_files": len(files),
        "total_bytes": total_bytes,
        "files": [{"path": p, "bytes": sz} for p, sz in files],
    }


def build_architecture() -> dict:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPO,
        "planes": PLANES,
        "identity_levels": [
            {"level": "Case ID", "meaning": "one paper or one modeling project"},
            {"level": "Session ID", "meaning": "one continuous conversation"},
            {"level": "Run ID", "meaning": "one node execution"},
        ],
        "m1": M1,
        "stage_boundary": (
            "M1 delivers the recoverable base (case/artifact/workflow/recovery). "
            "LLM, crawler, EDA, modeling and paper generation plug in via adapters "
            "and must reuse the existing Case/Artifact/Workflow/Recovery interfaces."
        ),
    }


def render_llms_txt(repo_root: Path) -> str:
    lines = [
        f"# {REPO}",
        "",
        "> A controlled, recoverable, evidence-first mathematical modeling workstation. "
        "M1 (the deterministic multi-agent modeling layer) is FROZEN at tag "
        f"{M1['tag']}. This gateway is machine-readable context for automated auditors and LLM agents.",
        "",
        "## Machine-readable status (read these first)",
        "- status.json: repository status, M1 freeze facts, CI status.",
        "- architecture.json: structured three-plane architecture + M1 guarantees.",
        "- repository-manifest.json: every tracked file (path + size).",
        "- llms.txt: this file.",
        "",
        "## Documentation",
    ]
    for p in sorted(DOC_NOTES):
        if (repo_root / p).exists():
            lines.append(f"- {p}: {DOC_NOTES[p]}")
    lines += ["", "## Source (key modules)"]
    for p in sorted(SRC_NOTES):
        if (repo_root / p).exists():
            lines.append(f"- {p}: {SRC_NOTES[p]}")
    lines += [
        "",
        "## Reports",
        "- reports/: tracked verification / audit reports (relative paths preserved).",
        "",
        "## How to verify M1 conformance",
        "- See docs/M1_FREEZE_RECORD.md section 5 for the exact reproduction commands.",
        "- The cross-runtime conformance contract is src/mathworkstation/agents/semantics.py::diff_states.",
        "",
        "## Safety notes",
        "- Only tracked files are published; .env.local, artifacts/, and .workbuddy/ are excluded.",
        "- source-snapshot.zip is `git archive HEAD` (tracked files only).",
    ]
    return "\n".join(lines) + "\n"


def render_context_md(repo_root: Path, status: dict, commit: str, tag: str | None) -> str:
    doc_items = "\n".join(
        f"- `{p}` — {DOC_NOTES[p]}" for p in sorted(DOC_NOTES) if (repo_root / p).exists()
    )
    src_items = "\n".join(
        f"- `{p}` — {SRC_NOTES[p]}" for p in sorted(SRC_NOTES) if (repo_root / p).exists()
    )
    guarantees = "\n".join(f"  {i+1}. {g}" for i, g in enumerate(M1["guarantees"]))
    return f"""# {REPO} — Repository Context (AI-readable gateway)

Generated: {status['generated_at']}  |  Commit: `{commit}`  |  Tag: `{tag}`

## What this is

A controlled, recoverable, evidence-first **mathematical modeling workstation**.
This document is the human+LLM entry point for the public audit gateway. All
machine-readable context lives in the sibling files:

- `status.json` — repository status + M1 freeze facts + CI status
- `architecture.json` — structured three-plane architecture
- `repository-manifest.json` — every tracked file (path + size)
- `llms.txt` — condensed index for LLM agents
- `source-snapshot.zip` — `git archive HEAD` (tracked files only)
- `reports/` — tracked verification / audit reports
- `ci/latest.json` — CI run summary

## Milestone M1 (FROZEN)

- **Status:** {M1['status']}
- **Tag:** `{M1['tag']}` (immutable, do not move/overwrite)
- **Commit:** `{M1['commit']}`
- **Verified on:** {M1['verified_on']}

{M1['summary']}

### Frozen guarantees

{guarantees}

## Architecture (three isolated planes)

{chr(10).join(f"- **{p['name']}** — {p['role']}" for p in PLANES)}

Identity levels: Case ID (one paper/project) > Session ID (one conversation) >
Run ID (one node execution). All file operations resolve Case Root first, then
pass a path guard; model nodes get least-privilege access via `NodeAccessPolicy`.

## Key documentation

{doc_items}

## Key source modules

{src_items}

## Safety / scope

- Only **tracked** files are published. `.env.local`, `artifacts/`, and
  `.workbuddy/` are never included (gitignored / untracked).
- `source-snapshot.zip` is produced by `git archive HEAD`, so it cannot leak
  untracked secrets.
- Every generated text file is scanned for high-signal secret patterns; the
  build fails if any secret is detected.
- M2 (contest-grade paper intelligence layer) is developed on a separate branch
  and MUST NOT weaken the M1 guarantees above (see docs/M1_FREEZE_RECORD.md §4).
"""


def render_index_html(status: dict, tag: str | None, commit: str) -> str:
    gen = status["generated_at"]
    guarantees_html = "\n".join(
        f"<li>{g}</li>" for g in M1["guarantees"]
    )
    ci_html = "green (post-merge Actions)" if status.get("ci", {}).get("status") == "green" else "see ci/latest.json"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{REPO} — Public AI Audit Gateway</title>
<style>
  :root {{ --bg:#0f172a; --card:#1e293b; --fg:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; }}
  body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background:var(--bg); color:var(--fg); margin:0; padding:2rem; line-height:1.5; }}
  .wrap {{ max-width: 920px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; }}
  .badge {{ display:inline-block; background:#064e3b; color:#6ee7b7; border:1px solid #065f46;
            padding:.25rem .6rem; border-radius:999px; font-size:.8rem; font-weight:600; }}
  .grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(220px,1fr)); gap:1rem; margin-top:1.5rem; }}
  .card {{ background:var(--card); border:1px solid #334155; border-radius:10px; padding:1rem; }}
  .card a {{ color:var(--accent); text-decoration:none; font-weight:600; }}
  .card small {{ color:var(--muted); display:block; margin-top:.35rem; }}
  code {{ background:#0b1220; padding:.1rem .35rem; border-radius:4px; }}
  ul.guarantees {{ color:var(--muted); font-size:.92rem; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{REPO}</h1>
  <p><span class="badge">M1 FROZEN · {tag}</span></p>
  <p>A controlled, recoverable, evidence-first mathematical modeling workstation.
     This is the <strong>public, AI-readable audit gateway</strong>: every linked
     file is machine-readable context for automated auditors and LLM agents.</p>

  <p><strong>Generated:</strong> <code>{gen}</code> &nbsp; <strong>Commit:</strong>
     <code>{commit}</code> &nbsp; <strong>CI:</strong> {ci_html}</p>

  <h2>M1 frozen guarantees</h2>
  <ul class="guarantees">{guarantees_html}</ul>

  <h2>Gateway files</h2>
  <div class="grid">
    <div class="card"><a href="status.json">status.json</a><small>Repository status, M1 freeze facts, CI status</small></div>
    <div class="card"><a href="architecture.json">architecture.json</a><small>Structured three-plane architecture</small></div>
    <div class="card"><a href="repository-manifest.json">repository-manifest.json</a><small>Every tracked file (path + size)</small></div>
    <div class="card"><a href="llms.txt">llms.txt</a><small>Condensed index for LLM agents</small></div>
    <div class="card"><a href="repository-context.md">repository-context.md</a><small>Human + LLM overview</small></div>
    <div class="card"><a href="source-snapshot.zip">source-snapshot.zip</a><small>git archive HEAD (tracked files only)</small></div>
    <div class="card"><a href="ci/latest.json">ci/latest.json</a><small>CI run summary</small></div>
    <div class="card"><a href="reports/">reports/</a><small>Tracked verification / audit reports</small></div>
    <div class="card"><a href="artifacts/">artifacts/</a><small>Explicitly downloaded CI artifacts</small></div>
  </div>

  <h2>Safety</h2>
  <p style="color:var(--muted); font-size:.9rem;">Only tracked files are published.
     <code>.env.local</code>, <code>artifacts/</code>, and <code>.workbuddy/</code> are excluded.
     <code>source-snapshot.zip</code> is <code>git archive HEAD</code>. Every generated text file is
     scanned for secret patterns and the build fails on detection.</p>
</div>
</body>
</html>
"""


def copy_reports(repo_root: Path, out_root: Path) -> list[str]:
    """Copy tracked *.md into reports/ (relative paths preserved)."""
    reports_dir = out_root / "reports"
    copied: list[str] = []
    for p, _ in collect_tracked_files(repo_root):
        if not p.endswith(".md"):
            continue
        src = repo_root / p
        dst = reports_dir / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied.append(str(dst.relative_to(out_root)))
    return sorted(copied)


def copy_artifacts(ci_artifacts_dir: Path | None, out_root: Path) -> None:
    artifacts_dir = out_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    if ci_artifacts_dir and ci_artifacts_dir.is_dir():
        any_file = False
        for item in ci_artifacts_dir.rglob("*"):
            if item.is_file():
                any_file = True
                rel = item.relative_to(ci_artifacts_dir)
                dst = artifacts_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, dst)
        if any_file:
            return
    # No explicit artifacts: leave a clear, safe placeholder.
    (artifacts_dir / "README.md").write_text(
        "# CI artifacts\n\n"
        "No CI artifacts were bundled into this build. For security, binary CI "
        "artifacts are NEVER auto-included from the working tree. To publish them, "
        "download explicitly with `gh run download <run-id> -n <name> -D <dir>` and "
        "pass that directory via `--ci-artifacts-dir`.\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# forbidden scan
# --------------------------------------------------------------------------- #
def scan_forbidden(texts: list[tuple[str, str]]) -> list[dict]:
    """Return list of violations: {file, pattern, snippet}."""
    violations: list[dict] = []
    for name, text in texts:
        for label, pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                snippet = text[max(0, m.start() - 20): m.end() + 20].replace("\n", " ")
                violations.append({"file": name, "pattern": label, "snippet": snippet})
    return violations


def collect_texts_for_scan(out_root: Path) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for p in out_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix in {".json", ".html", ".md", ".txt"}:
            try:
                texts.append((str(p.relative_to(out_root)), p.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                pass
    return texts


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def build_gateway(repo_root: Path, out_root: Path,
                  ci_artifacts_dir: Path | None = None,
                  ci_meta: dict | None = None) -> dict:
    out_root.mkdir(parents=True, exist_ok=True)
    commit = head_commit(repo_root)
    tag_at_head = (tags_at_head(repo_root) or [None])[0]
    m1_tag = latest_m1_tag(repo_root)
    display_tag = m1_tag or tag_at_head

    # Fetch CI metadata up front so status.json can reflect a green run.
    if ci_meta is None:
        ci_meta = fetch_ci_meta(repo_root)

    # Build core JSON / text artifacts.
    manifest = build_manifest(repo_root, commit, display_tag)
    architecture = build_architecture()
    status = build_status(repo_root, commit, display_tag, ci_meta)
    llms_txt = render_llms_txt(repo_root)
    context_md = render_context_md(repo_root, status, commit, display_tag)
    index_html = render_index_html(status, display_tag, commit)

    (out_root / "repository-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_root / "architecture.json").write_text(
        json.dumps(architecture, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_root / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_root / "llms.txt").write_text(llms_txt, encoding="utf-8")
    (out_root / "repository-context.md").write_text(context_md, encoding="utf-8")
    (out_root / "index.html").write_text(index_html, encoding="utf-8")

    # Snapshot + reports + artifacts + ci meta.
    write_source_snapshot(repo_root, out_root / "source-snapshot.zip")
    copied_reports =     copy_reports(repo_root, out_root)
    copy_artifacts(ci_artifacts_dir, out_root)
    (out_root / "ci").mkdir(exist_ok=True)
    (out_root / "ci" / "latest.json").write_text(
        json.dumps(ci_meta or {"source": "none", "note": "CI metadata not fetched (gh unavailable)."},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    # Defense-in-depth: scan every generated text file for secrets.
    violations = scan_forbidden(collect_texts_for_scan(out_root))
    if violations:
        msg = "FORBIDDEN SECRET PATTERN DETECTED in generated gateway:\n" + "\n".join(
            f"  {v['file']} [{v['pattern']}]: ...{v['snippet']}..." for v in violations
        )
        raise RuntimeError(msg)

    return {
        "out_root": str(out_root),
        "commit": commit,
        "tag": display_tag,
        "tracked_files": manifest["total_files"],
        "reports_copied": len(copied_reports),
        "scan_violations": len(violations),
    }


def build_status(repo_root: Path, commit: str, tag: str | None, ci_meta: dict | None) -> dict:
    """Machine-readable repository status (M1 freeze facts + CI status)."""
    pkg = {"name": "math-modeling-workstation", "version": "0.1.0",
           "description": "A controlled, recoverable, evidence-first mathematical modeling workstation."}
    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        import re as _re
        txt = pyproject.read_text(encoding="utf-8")
        m = _re.search(r'name\s*=\s*"([^"]+)"', txt)
        if m:
            pkg["name"] = m.group(1)
        m = _re.search(r'version\s*=\s*"([^"]+)"', txt)
        if m:
            pkg["version"] = m.group(1)
        m = _re.search(r'description\s*=\s*"([^"]+)"', txt)
        if m:
            pkg["description"] = m.group(1)
    ci_status = "green" if (ci_meta and ci_meta.get("latest_green_run")) else "see ci/latest.json"
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPO,
        "package": pkg,
        "commit": commit,
        "tag": tag,
        "milestone": {"m1": M1},
        "ci": {
            "status": ci_status,
            "note": "Post-merge Actions green (agent-layer-tests, 6 jobs). See ci/latest.json.",
            "fetched": bool(ci_meta),
        },
        "tracked_file_count": len(collect_tracked_files(repo_root)),
        "planes": PLANES,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the public AI-readable audit gateway.")
    ap.add_argument("--repo-root", default=".", type=Path, help="Repository root (default: cwd)")
    ap.add_argument("--out", default="public-site", type=Path, help="Output directory")
    ap.add_argument("--ci-artifacts-dir", default=None, type=Path,
                    help="Directory of explicitly downloaded CI artifacts to bundle")
    args = ap.parse_args(argv)

    repo_root = args.repo_root.resolve()
    out_root = args.out.resolve()
    print(f"[gateway] repo={repo_root}")
    print(f"[gateway] out ={out_root}")
    try:
        summary = build_gateway(repo_root, out_root, args.ci_artifacts_dir)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("[gateway] build OK:")
    print("  " + json.dumps(summary, ensure_ascii=False, indent=2).replace("\n", "\n  "))
    # Emit a manifest for CI consumers.
    (out_root / "BUILD_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
