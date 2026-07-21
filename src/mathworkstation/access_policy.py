from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

from .errors import PathViolationError


@dataclass(frozen=True)
class NodeAccessPolicy:
    node_id: str
    readable: tuple[str, ...]
    writable: tuple[str, ...]
    tools: tuple[str, ...]

    def can_read(self, relative_path: str) -> bool:
        return _matches(relative_path, self.readable)

    def can_write(self, relative_path: str) -> bool:
        return _matches(relative_path, self.writable)

    def assert_read(self, relative_path: str) -> None:
        if not self.can_read(relative_path):
            raise PathViolationError(f"node {self.node_id} cannot read {relative_path}")

    def assert_write(self, relative_path: str) -> None:
        if not self.can_write(relative_path):
            raise PathViolationError(f"node {self.node_id} cannot write {relative_path}")

    def assert_tool(self, tool_name: str) -> None:
        if tool_name not in self.tools:
            raise PermissionError(f"node {self.node_id} cannot call tool {tool_name}")


def _matches(relative_path: str, patterns: tuple[str, ...]) -> bool:
    normalized = PurePosixPath(relative_path.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        return False
    normalized_text = normalized.as_posix()
    return any(fnmatchcase(normalized_text, pattern) for pattern in patterns)


DEFAULT_NODE_POLICIES = {
    "problem_analysis": NodeAccessPolicy(
        "problem_analysis",
        readable=("input/problem/**", "input/requirements/**"),
        writable=("analysis/**", ".internal/problem_spec.json"),
        tools=("read_artifact", "write_analysis", "validate_schema"),
    ),
    "data_quality": NodeAccessPolicy(
        "data_quality",
        readable=("input/data/**", "data/raw/**", "data/dictionaries/**"),
        writable=("analysis/**", ".internal/data_profile.json"),
        tools=("read_artifact", "inspect_dataframe", "run_python", "validate_schema"),
    ),
    "paper_draft": NodeAccessPolicy(
        "paper_draft",
        readable=(
            "analysis/**",
            "results/**",
            "figures/final/**",
            "tables/final/**",
            "paper/sections/*/context.json",
            ".internal/**",
        ),
        writable=("paper/draft/**", "paper/sections/**"),
        tools=("read_artifact", "write_paper_draft", "validate_claims"),
    ),
}
