"""Hidden-state refinement: RNN/GRU/LSTM-inspired inter-stage communication.

Design record: ``docs/hidden-state-refinement-design.md``.

The LSTM analogy: a neural net updates its cell state ``c_t`` as new inputs
arrive, carrying a compact memory forward instead of recomputing from scratch.
This module gives the paper refinement loop the same property:

* every Stage runs the **same** full-paper audit (already true in
  :class:`RefinementService`);
* but between Stages a dedicated, in-place-updated file
  (``refinement/hidden_state.json``) carries the *focus curriculum* and a
  compact *memory* summary, so Stage N+1 knows exactly what was improved, what
  is frozen, and what to focus on next — without re-reading the whole paper.

Invariants:
  * ``frozen`` fields are append-only; a Stage that tries to change them is
    rejected by the existing hard gate, never by this module.
  * ``memory`` is a one-or-two-sentence *summary* (LSTM cell state), never raw
    paper text — context windows are not persistent memory (project iron rule).
  * The module is a pure add-on: when not wired in, ``RefinementService``
    behaves exactly as before (existing tests untouched).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .io_utils import atomic_write_json, now_iso

#: Default focus curriculum — the user's five-stage "one paper, five polishes".
FOCUS_CURRICULUM: list[str] = [
    "coherence",          # stage 1: completeness, subproblem closure
    "humanize",           # stage 2: natural prose, no template filler
    "figures_and_tables", # stage 3: embed figures/tables + explanations
    "notation_and_latex", # stage 4: symbols, formulas, LaTeX
    "final_polish",       # stage 5: rigor, reduce AI trace, final flowchart
]


@dataclass(frozen=True)
class StageFocusPolicy:
    """Curriculum of stage focuses; rotates as stages advance."""

    curriculum: tuple[str, ...] = tuple(FOCUS_CURRICULUM)

    def focus_for(self, stage: int) -> str:
        """Return the focus for a 1-based stage number (cycles past the end)."""
        if not self.curriculum:
            return "coherence"
        return self.curriculum[(stage - 1) % len(self.curriculum)]


class HiddenState:
    """Dedicated, in-place-updated inter-stage memory (the LSTM cell state).

    Stored at ``<case_root>/refinement/hidden_state.json``. Each Stage reads it
    at start and *overwrites* it in place at end — never a second file, so
    there is exactly one channel of inter-stage communication.
    """

    def __init__(self, case_root: Path, focus_policy: StageFocusPolicy | None = None) -> None:
        self.path = case_root / "refinement" / "hidden_state.json"
        self.focus_policy = focus_policy or StageFocusPolicy()

    # ------------------------------------------------------------- persistence

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._blank()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict[str, Any]) -> dict[str, Any]:
        state["updated_at"] = now_iso()
        atomic_write_json(self.path, state)
        return state

    def _blank(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "epoch": 1,
            "stage": 0,
            "focus": None,
            "quality": {},
            "memory": "",
            "frozen": {"number_tokens": {}, "claim_ids": [], "figure_ids": [], "synthetic_disclosure": False},
            "deltas": [],
        }

    # ------------------------------------------------------------- read/write

    def begin(self, stage: int, *, epoch: int = 1, frozen: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read hidden state for a Stage and report the focus to work on."""
        state = self.load()
        state["stage"] = stage
        state["epoch"] = epoch
        state["focus"] = self.focus_policy.focus_for(stage)
        if frozen is not None:
            # Frozen block is append-only: seed only if empty, never overwrite.
            current = state["frozen"]
            for key, value in frozen.items():
                if key in current and current[key]:
                    continue
                current[key] = value
        return state

    def record(
        self,
        *,
        stage: int,
        accepted: bool,
        focus: str,
        quality_before: dict[str, Any] | None,
        quality_after: dict[str, Any] | None,
        note: str,
        frozen: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update the hidden state in place after a Stage finishes."""
        state = self.load()
        state["stage"] = stage
        state["focus"] = focus
        state["epoch"] = state.get("epoch", 1)
        if quality_after:
            state["quality"] = quality_after.get("quality_vector", quality_after)
        if frozen is not None:
            current = state["frozen"]
            for key, value in frozen.items():
                if key in current and current[key]:
                    continue
                current[key] = value
        total_before = (quality_before or {}).get("quality_vector", {}).get("total", 0.0)
        total_after = (quality_after or {}).get("quality_vector", {}).get("total", 0.0)
        delta = round(total_after - total_before, 6)
        deltas = list(state.get("deltas", []))
        deltas.append(
            {
                "stage": stage,
                "focus": focus,
                "accepted": bool(accepted),
                "total_delta": delta,
                "at": now_iso(),
            }
        )
        state["deltas"] = deltas[-50:]  # bound history, like a cell state window
        state["memory"] = note
        return self.save(state)

    # ------------------------------------------------------------- helpers

    def summary(self) -> dict[str, Any]:
        """Compact view for the Web shell / proposer context (never raw paper)."""
        state = self.load()
        return {
            "epoch": state.get("epoch", 1),
            "stage": state.get("stage", 0),
            "focus": state.get("focus"),
            "quality_total": state.get("quality", {}).get("total"),
            "memory": state.get("memory", ""),
            "deltas": state.get("deltas", [])[-5:],
        }
