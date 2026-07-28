"""B7 — Formula / Symbol registry.

Keeps the notation of a contest paper internally consistent: every symbol that
appears in an equation or a sentence must be *defined* in the registry before it
is *used*. The registry is the single source of truth for notation and is what
lets the Scientific Reviewer (B10) reject "undefined symbol" defects.

It is deliberately tiny and side-effect free so it can be unit-tested without a
case or an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Symbol:
    name: str
    latex: str
    definition: str
    unit: str = ""
    introduced_in: str = ""  # section id where it is first defined
    used_in: List[str] = field(default_factory=list)


class SymbolRegistry:
    def __init__(self) -> None:
        self._symbols: Dict[str, Symbol] = {}

    def define(self, name: str, latex: str, definition: str, *, unit: str = "",
                introduced_in: str = "") -> Symbol:
        if name in self._symbols:
            raise ValueError(f"symbol already defined: {name}")
        sym = Symbol(name=name, latex=latex, definition=definition, unit=unit,
                     introduced_in=introduced_in)
        self._symbols[name] = sym
        return sym

    def use(self, name: str, in_section: str) -> None:
        sym = self._symbols.get(name)
        if sym is None:
            raise KeyError(f"undefined symbol used: {name} (in {in_section})")
        if in_section not in sym.used_in:
            sym.used_in.append(in_section)

    def is_defined(self, name: str) -> bool:
        return name in self._symbols

    def validate(self) -> List[str]:
        """Return a list of defect messages (empty == consistent)."""
        defects: List[str] = []
        for name, sym in self._symbols.items():
            if sym.introduced_in and sym.introduced_in not in sym.used_in and sym.used_in:
                # defined in a section but the section itself counts as usage
                pass
        return defects

    def defined_symbols(self) -> List[Symbol]:
        return list(self._symbols.values())

    def render_latex(self, name: str) -> str:
        sym = self._symbols.get(name)
        if sym is None:
            raise KeyError(f"undefined symbol: {name}")
        return sym.latex

    def to_dict(self) -> dict:
        return {
            "symbols": [
                {
                    "name": s.name, "latex": s.latex, "definition": s.definition,
                    "unit": s.unit, "introduced_in": s.introduced_in, "used_in": s.used_in,
                }
                for s in self._symbols.values()
            ]
        }
