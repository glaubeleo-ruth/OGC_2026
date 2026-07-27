"""
budget.py -- monotonic deadline governor.

WATCHDOG rule served: safety factor.  The evaluation server may be slower per
core than the dev box and charges wall-clock; the effective budget is
max(1.0, timelimit * 0.93 - 1.0), identical to the legacy alns.deadline
contract.  Every stage of the pipeline receives this Deadline and must return
early when it expires -- overrun on the server scores -1.
"""

from __future__ import annotations

import time

SAFETY_FACTOR = 0.93
SAFETY_OFFSET = 1.0


class Deadline:
    """Monotonic-clock deadline shared by every pipeline stage."""

    def __init__(self, budget_seconds: float):
        self.t0 = time.monotonic()
        self.budget = float(budget_seconds)

    @classmethod
    def from_timelimit(cls, timelimit: float) -> "Deadline":
        return cls(max(1.0, timelimit * SAFETY_FACTOR - SAFETY_OFFSET))

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def remaining(self) -> float:
        return self.budget - self.elapsed()

    def expired(self, margin: float = 0.0) -> bool:
        return self.remaining() <= margin

    def sub_budget(self, fraction: float, cap: float | None = None) -> float:
        """A share of the remaining budget, optionally capped, never negative."""
        share = max(0.0, self.remaining() * fraction)
        return min(share, cap) if cap is not None else share
