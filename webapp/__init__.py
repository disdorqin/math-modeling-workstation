"""Web shell (FastAPI + lightweight frontend) for the math modeling workstation.

This package is additive: it imports the existing `mathworkstation` services
and never modifies them.
"""

__all__ = ["main", "services", "driver", "jobs", "ledger"]
