from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from mathworkstation.judge_validity import (
    CalibrationPaper,
    PairSpec,
    anonymize_paper_text,
    identity_leakage_findings,
)


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source_path(repo_root: Path, source: str) -> Path:
    path = Path(source)
    return path if path.is_absolute() else repo_root / path


def _extract_pdf_text(path: Path) -> str:
    completed = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(path), "-"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.decode("utf-8", errors="replace")


def _private_literals(paper: CalibrationPaper) -> list[str]:
    values: list[str] = []
    # Only redact literals that are safe to replace globally.  Short award codes
    # such as "O" must never be treated as literals because they occur inside
    # ordinary words throughout an English paper.
    if paper.case_id:
        values.append(paper.case_id)
    filename = Path(paper.source_path).name
    values.extend(re.findall(r"(?<!\d)\d{6,7}(?!\d)", filename))
    return list(dict.fromkeys(item for item in values if item))


def _redact_private_literals(text: str, literals: list[str]) -> str:
    value = text
    for literal in sorted(literals, key=len, reverse=True):
        if literal:
            value = re.sub(re.escape(literal), "[IDENTITY REDACTED]", value, flags=re.IGNORECASE)
    return value


def _packet(pair: PairSpec, texts: dict[str, str]) -> dict[str, object]:
    # Private pair kind/origin are intentionally absent.  The independent/human
    # judge sees only random blind IDs and the two anonymized paper bodies.
    return {
        "schema_version": 1,
        "pair_id": pair.pair_id,
        "swap_group": pair.swap_group,
        "left": {"blind_id": pair.left_id, "text": texts[pair.left_id]},
        "right": {"blind_id": pair.right_id, "text": texts[pair.right_id]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize anonymized V6 blind-judge packets.")
    parser.add_argument("--root", default="artifacts/meta_benchmark/judge_v1")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    root = (repo_root / args.root).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    papers = [CalibrationPaper(**row) for row in manifest.get("papers", [])]
    pairs = [PairSpec(**row) for row in _read_jsonl(root / "pairwise_pairs.jsonl")]

    anonymized_dir = root / "anonymized"
    packets_dir = root / "packets"
    anonymized_dir.mkdir(parents=True, exist_ok=True)
    packets_dir.mkdir(parents=True, exist_ok=True)

    texts: dict[str, str] = {}
    reports: list[dict[str, object]] = []
    for paper in papers:
        source = _source_path(repo_root, paper.source_path)
        if not source.is_file():
            raise FileNotFoundError(source)
        raw = _extract_pdf_text(source)
        literals = _private_literals(paper)
        anonymized = _redact_private_literals(anonymize_paper_text(raw), literals)
        findings = identity_leakage_findings(anonymized, forbidden_literals=literals)
        text_path = anonymized_dir / f"{paper.blind_id}.txt"
        text_path.write_text(anonymized, encoding="utf-8")
        texts[paper.blind_id] = anonymized
        reports.append(
            {
                "blind_id": paper.blind_id,
                "source_exists": True,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "anonymized_sha256": _sha256_text(anonymized),
                "raw_characters": len(raw),
                "anonymized_characters": len(anonymized),
                "identity_leakage_findings": findings,
                "manual_review_required": bool(findings),
            }
        )

    for pair in pairs:
        payload = _packet(pair, texts)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        private_keys = {"source_path", "case_id", "award", "origin", "kind"}
        packet_keys = set(payload) | set(payload["left"]) | set(payload["right"])
        leaked_keys = sorted(private_keys & packet_keys)
        provenance_values = (
            "REAL_VS_CURRENT",
            "REAL_VS_REAL",
            "CURRENT_VS_OLDER",
            "REAL_EXCELLENT",
            "WORKSTATION_CURRENT",
            "WORKSTATION_OLDER",
        )
        leaked_values = [token for token in provenance_values if token.lower() in serialized.lower()]
        if leaked_keys or leaked_values:
            raise RuntimeError(
                f"blind packet leaks private provenance {pair.pair_id}: "
                f"keys={leaked_keys}, values={leaked_values}"
            )
        (packets_dir / f"{pair.pair_id}.json").write_text(serialized, encoding="utf-8")

    report = {
        "schema_version": 1,
        "paper_count": len(papers),
        "pair_count": len(pairs),
        "papers": reports,
        "ready_for_automatic_blind_judge": all(not row["identity_leakage_findings"] for row in reports),
        "manual_review_note": (
            "Automatic leakage scan is necessary but not sufficient for a human-blind claim. "
            "A human must still inspect the materialized packet before their vote is labeled blind."
        ),
    }
    (root / "materialization_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
