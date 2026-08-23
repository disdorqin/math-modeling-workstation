"""Backward-compatible import shim.

The canonical implementation lives in ``evidence_expression_fulfillment``.
Keeping this module tiny prevents two competing fulfillment policies from
silently diverging while older experiments/imports are migrated.
"""

from .evidence_expression_fulfillment import (  # noqa: F401
    EvidenceExpressionFulfillmentService,
    ExpressionFulfillmentAssessment,
    ExpressionFulfillmentItem,
    FulfillmentGate,
    FulfillmentStatus,
)

__all__ = [
    "EvidenceExpressionFulfillmentService",
    "ExpressionFulfillmentAssessment",
    "ExpressionFulfillmentItem",
    "FulfillmentGate",
    "FulfillmentStatus",
]
