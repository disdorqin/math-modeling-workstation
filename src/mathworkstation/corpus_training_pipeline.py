from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .corpus_distillation import (
    distill_registered_corpus_cached,
    scan_registered_excellent_papers,
    teacher_packet,
)
from .corpus_prior_bank import build_prior_bank, persist_prior_bank
from .io_utils import atomic_write_json, now_iso


DEFAULT_REGISTRY = Path("config/ref_models/local_knowledge_base_registry.json")
DEFAULT_CACHE = Path("artifacts/corpus_distillation/fingerprint_cache.json")
DEFAULT_PRIOR_BANK = Path("config/ref_models/distilled_prior_bank_v1.json")
DEFAULT_REPORT = Path("artifacts/corpus_distillation/latest_training_report.json")


def run_training_pipeline(
    *,
    registry_path: str | Path = DEFAULT_REGISTRY,
    cache_path: str | Path = DEFAULT_CACHE,
    prior_bank_path: str | Path = DEFAULT_PRIOR_BANK,
    report_path: str | Path = DEFAULT_REPORT,
    workers: int | None = None,
) -> dict[str, Any]:
    registry = Path(registry_path)
    cache = Path(cache_path)
    prior_path = Path(prior_bank_path)
    report = Path(report_path)

    sources = scan_registered_excellent_papers(registry)
    fingerprints, summary, cache_stats = distill_registered_corpus_cached(
        registry,
        cache,
        workers=workers,
        sources=sources,
        write_cache=True,
    )
    bank = build_prior_bank(fingerprints)
    persist_prior_bank(prior_path, bank)

    status_counts: dict[str, int] = {}
    for item in fingerprints:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
    by_competition: dict[str, int] = {}
    for item in fingerprints:
        by_competition[item.source.competition] = by_competition.get(item.source.competition, 0) + 1

    payload = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "source_inventory": len(sources),
        "cache": cache_stats,
        "status_counts": dict(sorted(status_counts.items())),
        "competition_counts": dict(sorted(by_competition.items())),
        "c_problem_count": sum(item.source.c_problem for item in fingerprints),
        "modern_2023_plus_count": sum(item.source.year >= 2023 for item in fingerprints),
        "teacher_packet": teacher_packet(summary),
        "prior_bank": {
            "path": prior_path.as_posix(),
            "slices": len(bank.slices),
            "students": sorted(bank.students),
            "universal_rules": bank.universal_rules,
        },
    }
    atomic_write_json(report, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the local excellent-paper corpus and build a routed prior bank")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--prior-bank", default=str(DEFAULT_PRIOR_BANK))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args(argv)
    payload = run_training_pipeline(
        registry_path=args.registry,
        cache_path=args.cache,
        prior_bank_path=args.prior_bank,
        report_path=args.report,
        workers=args.workers or None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
