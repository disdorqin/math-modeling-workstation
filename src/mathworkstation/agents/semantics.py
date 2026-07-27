"""The runtime semantics contract: what "the builtin runner and LangGraph agree" means.

Two runtimes executing the same agent sequence over the same case are not
required to produce byte-identical state -- wall-clock timestamps will differ,
and LangGraph's own internal bookkeeping fields are not something the builtin
runner produces at all. What they *are* required to agree on is everything
that actually describes what the pipeline decided: which proposals were made,
which verdicts were reached, which claims/figures were accepted, and why a run
halted if it halted.

Every field reachable from :class:`~mathworkstation.agents.contracts.WorkstationState`
is classified into exactly one bucket:

- ``EXACT``      -- must be byte-identical between runtimes, or the comparison fails.
- ``CANONICAL``  -- semantically must agree, but the two runtimes may format it
                    differently (e.g. dict key order); compared after
                    canonicalisation (sorted keys, normalised whitespace), not
                    ignored.
- ``RUNTIME_SPECIFIC`` -- expected to differ (wall-clock timestamps, ids that
                    embed process/thread identifiers). Reported as *skipped*,
                    not silently dropped, so a reviewer can see what was
                    deliberately not compared and why.

Nothing is normalised away without being named here. A field not listed is
treated as EXACT by default -- the conservative choice for a check whose whole
job is to catch runtime divergence.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def _sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

EXACT = "EXACT"
CANONICAL = "CANONICAL"
RUNTIME_SPECIFIC = "RUNTIME_SPECIFIC"

#: Dotted field paths within one WorkstationState, and within one verdict /
#: report record inside its lists. "*" matches any list index.
FIELD_CLASSIFICATION: dict[str, str] = {
    # top-level pipeline identity and inputs -- must match exactly, these are
    # inputs to the run, not runtime output.
    "case_id": EXACT,
    "session_id": EXACT,
    "dataset_id": EXACT,
    "target_column": EXACT,
    "goal": EXACT,
    "halted": EXACT,
    "halt_reason": EXACT,
    "blocked": EXACT,
    # proposals are content-addressed (Proposal.proposal_id is a hash of
    # kind/agent/summary/payload/evidence) -- identical inputs must produce
    # identical ids regardless of which runtime ran the agent.
    "verdicts.*.proposal_id": EXACT,
    "verdicts.*.status": EXACT,
    "verdicts.*.codes": EXACT,
    "verdicts.*.message": EXACT,
    "verdicts.*.produced": CANONICAL,  # a dict; key order is not meaningful
    "verdicts.*.replayed": EXACT,
    # decided_at is wall-clock -- the whole point of this bucket.
    "verdicts.*.decided_at": RUNTIME_SPECIFIC,
    "reports.*.agent": EXACT,
    "reports.*.status": EXACT,
    "reports.*.notes": EXACT,
    "reports.*.blocked_reason": EXACT,
    "reports.*.proposals": CANONICAL,  # list of proposal dicts; compared via canonical id set
    "accepted.*.agent": EXACT,
    "accepted.*.kind": EXACT,
    "accepted.*.summary": EXACT,
    "accepted.*.produced": CANONICAL,
}

#: Keys stripped wherever they appear, at any depth, before comparison --
#: these are wall-clock or process-local by construction (created_at on a
#: Proposal, decided_at on a Verdict, langgraph-internal bookkeeping keys).
_RUNTIME_SPECIFIC_KEYS = {"created_at", "decided_at"}


def _resolve_artifacts_in_state(
    state: dict[str, Any],
    artifact_sha: dict[str, str] | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Make a state comparable across isolated workspaces whose artifact ids
    are random per-run (``artifact-<uuid4>``).

    An artifact id embeds process-local randomness, so the *same* registered
    artifact produced by the builtin runner and by LangGraph gets two different
    ids. Those ids then cascade into proposal ids (a content hash of the
    proposal including its evidence artifact ids) and into every verdict /
    report that references them -- so a naive byte comparison reports spurious
    disagreement even when the two runtimes decided exactly the same things.

    This rewrites every artifact-id reference to the *content* sha256 stored in
    the artifact registry (identical content -> identical sha regardless of
    which runtime minted the id) and recomputes each proposal id from the
    resolved content, returning the rewritten state plus a
    ``old_proposal_id -> new_proposal_id`` map so verdict references can be
    rewritten too. With ``artifact_sha`` left as ``None`` (no registry
    available) the state is returned unchanged -- the contract stays exact for
    tests that compare synthetic states.
    """
    if not artifact_sha:
        return copy.deepcopy(state), {}
    state = copy.deepcopy(state)
    state = _walk_resolve(state, artifact_sha)
    proposal_id_map: dict[str, str] = {}
    for report in state.get("reports") or []:
        if not isinstance(report, dict):
            continue
        for proposal in report.get("proposals") or []:
            if not isinstance(proposal, dict):
                continue
            old_id = proposal.get("proposal_id")
            new_id = _canonical_proposal_id(proposal)
            proposal["proposal_id"] = new_id
            if old_id:
                proposal_id_map[old_id] = new_id
    for verdict in state.get("verdicts") or []:
        if not isinstance(verdict, dict):
            continue
        old_id = verdict.get("proposal_id")
        if old_id in proposal_id_map:
            verdict["proposal_id"] = proposal_id_map[old_id]
    return state, proposal_id_map


def _walk_resolve(node: Any, artifact_sha: dict[str, str]) -> Any:
    if isinstance(node, dict):
        resolved = {}
        for key, value in node.items():
            if key == "artifact_id" and isinstance(value, str) and value in artifact_sha:
                resolved[key] = artifact_sha[value]
            elif isinstance(value, str) and value in artifact_sha:
                resolved[key] = artifact_sha[value]
            else:
                resolved[key] = _walk_resolve(value, artifact_sha)
        return resolved
    if isinstance(node, list):
        return [_walk_resolve(item, artifact_sha) for item in node]
    return node


def _canonical_proposal_id(proposal: dict[str, Any]) -> str:
    """Recompute a proposal_id from its resolved content, mirroring
    ``Proposal._content_hash`` in ``contracts.py`` (kind/agent/summary/payload/
    evidence, ``created_at`` excluded)."""
    evidence = sorted(
        f"{item.get('artifact_id')}:{item.get('role')}"
        for item in (proposal.get("evidence") or [])
    )
    canonical = {
        "kind": proposal.get("kind"),
        "agent": proposal.get("agent"),
        "summary": proposal.get("summary"),
        "payload": proposal.get("payload", {}) or {},
        "evidence": evidence,
    }
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return "proposal-" + hashlib.sha256(blob).hexdigest()[:16]


def canonicalize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy ``state`` with RUNTIME_SPECIFIC content stripped and
    CANONICAL collections normalised (sorted), so two semantically-equal
    states compare equal even if key order or wall-clock timestamps differ.

    This does not paper over EXACT-field differences -- those are left
    exactly as they are so :func:`diff_states` still catches them.
    """
    return _strip(copy.deepcopy(state))


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _strip(value)
            for key, value in sorted(node.items())
            if key not in _RUNTIME_SPECIFIC_KEYS
        }
    if isinstance(node, list):
        return [_strip(item) for item in node]
    return node


def diff_states(
    builtin_state: dict[str, Any],
    langgraph_state: dict[str, Any],
    builtin_artifact_sha: dict[str, str] | None = None,
    langgraph_artifact_sha: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Compare two final :class:`WorkstationState` dicts under the contract above.

    Returns a list of difference records, each ``{"path", "classification",
    "builtin", "langgraph"}``. An empty list means the two runtimes are
    conformant under this contract -- not byte-identical, conformant, which is
    the distinction the contract exists to make precise.

    When ``builtin_artifact_sha`` / ``langgraph_artifact_sha`` are supplied
    (a mapping of each workspace's random ``artifact-<uuid>`` ids to their
    content sha256), artifact-id references and proposal ids are resolved to
    their content identity first, so two runtimes that decided the same things
    but minted different ids compare conformant instead of spuriously diverging.
    """
    builtin_state, _ = _resolve_artifacts_in_state(builtin_state, builtin_artifact_sha)
    langgraph_state, _ = _resolve_artifacts_in_state(langgraph_state, langgraph_artifact_sha)
    canonical_builtin = canonicalize_state(builtin_state)
    canonical_langgraph = canonicalize_state(langgraph_state)
    differences: list[dict[str, Any]] = []
    keys = set(canonical_builtin) | set(canonical_langgraph)
    for key in sorted(keys):
        _diff_field(
            key,
            canonical_builtin.get(key),
            canonical_langgraph.get(key),
            differences,
        )
    return differences


def _classification_for(path: str) -> str:
    if path in FIELD_CLASSIFICATION:
        return FIELD_CLASSIFICATION[path]
    # try the wildcard form for list-indexed paths, e.g. "verdicts.3.status"
    parts = path.split(".")
    wildcard = ".".join(part if not part.isdigit() else "*" for part in parts)
    return FIELD_CLASSIFICATION.get(wildcard, EXACT)


def _diff_field(path: str, left: Any, right: Any, out: list[dict[str, Any]]) -> None:
    classification = _classification_for(path)
    if classification == RUNTIME_SPECIFIC:
        return  # deliberately skipped, not compared -- see module docstring
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            out.append(
                {
                    "path": path,
                    "classification": classification,
                    "builtin": f"<list len={len(left)}>",
                    "langgraph": f"<list len={len(right)}>",
                }
            )
            return
        for index, (litem, ritem) in enumerate(zip(left, right)):
            if isinstance(litem, dict) and isinstance(ritem, dict):
                subkeys = set(litem) | set(ritem)
                for subkey in sorted(subkeys):
                    _diff_field(
                        f"{path}.{index}.{subkey}",
                        litem.get(subkey),
                        ritem.get(subkey),
                        out,
                    )
            elif litem != ritem:
                out.append(
                    {
                        "path": f"{path}.{index}",
                        "classification": classification,
                        "builtin": litem,
                        "langgraph": ritem,
                    }
                )
        return
    if isinstance(left, dict) and isinstance(right, dict):
        subkeys = set(left) | set(right)
        for subkey in sorted(subkeys):
            _diff_field(f"{path}.{subkey}", left.get(subkey), right.get(subkey), out)
        return
    if left != right:
        out.append({"path": path, "classification": classification, "builtin": left, "langgraph": right})


def render_report(differences: list[dict[str, Any]]) -> str:
    """Human-readable report. Machine-readable is just ``differences`` as JSON."""
    if not differences:
        return "CONFORMANT: builtin and langgraph runtimes agree under the semantics contract.\n"
    lines = [f"NON-CONFORMANT: {len(differences)} difference(s) found.\n"]
    for item in differences:
        lines.append(
            f"- [{item['classification']}] {item['path']}: "
            f"builtin={item['builtin']!r} langgraph={item['langgraph']!r}"
        )
    return "\n".join(lines) + "\n"
