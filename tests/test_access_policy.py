import pytest

from mathworkstation.access_policy import DEFAULT_NODE_POLICIES
from mathworkstation.errors import PathViolationError


def test_node_policy_blocks_cross_scope_writes() -> None:
    policy = DEFAULT_NODE_POLICIES["paper_draft"]
    policy.assert_write("paper/draft/section.md")
    with pytest.raises(PathViolationError):
        policy.assert_write("results/metrics/fake.json")
    with pytest.raises(PathViolationError):
        policy.assert_read("../another-case/manifest.json")

