"""
deadline.py -- a single shared, monotonic-clock deadline object threaded
through the whole ALNS call chain per WATCHDOG_SPEC.md:

    myalgorithm.algorithm -> alns.controller.run -> _run_loop -> _apply_repair
    -> repair.greedy_repair / repair.milp_repack -> alns.evaluate.objective

Goal: make timelimit overrun structurally impossible, replacing the
tail-fraction-only mitigation. The exposure the tail fraction alone cannot
close is UNCAPPED WORK INSIDE AN IN-FLIGHT ITERATION -- chiefly
`evaluate.objective()`'s and `milp_repack`'s full `utils.check_feasibility`
calls, which scale with instance size and were never individually bounded.
Deadline threads a single absolute cutoff (plus a measured est_check_cost)
through every one of those call sites so each can bail BEFORE starting an
operation it can't finish, rather than the controller only noticing after
the fact.

time.monotonic(), not time.time(): immune to system clock adjustments (NTP
sync, manual changes) during a run that can last up to 30 minutes on the
eval server -- a wall-clock jump could otherwise turn into a silently wrong
deadline. Every OTHER `t_start`/`timelimit` pair already in this codebase
(baseline_greedy.py's own Phase 1/2, `_place_blocks`, `_repair`) still uses
time.time() and is intentionally untouched by this module -- construction's
existing timing already works; Deadline exists specifically for the ALNS
loop's uncapped hot spots.
"""

import time


class DeadlineExceeded(Exception):
    """Raised by Deadline.check() once the deadline has passed. The ALNS
    loop (_run_loop) catches this specifically and BREAKS (not continues),
    falling through to the existing final verify/return path -- an
    in-flight iteration that hits this is abandoned, not retried."""


class Deadline:
    """A single absolute deadline on the time.monotonic() clock, shared by
    reference through the whole ALNS call chain.

    Parameters
    ----------
    wall_deadline : an absolute time.monotonic()-scale value (i.e.
        time.monotonic() + budget_seconds) -- NOT time.time().
    est_check_cost : seconds a single `utils.check_feasibility` call is
        expected to take on this instance, measured once (see
        `myalgorithm.algorithm`, which times the seed's own feasibility
        check and passes that measurement in here). Used by
        `can_afford_check()` so callers can skip an about-to-be-uncapped
        check_feasibility call rather than start one they can't finish.
    """

    def __init__(self, wall_deadline: float, est_check_cost: float = 0.05):
        self.t = wall_deadline
        self.est_check_cost = max(est_check_cost, 0.001)

    def remaining(self) -> float:
        """Seconds left before the deadline (negative once passed)."""
        return self.t - time.monotonic()

    def expired(self, margin: float = 0.0) -> bool:
        """True once fewer than `margin` seconds remain."""
        return self.remaining() <= margin

    def check(self) -> None:
        """Raise DeadlineExceeded if the deadline has already passed."""
        if self.expired():
            raise DeadlineExceeded(f"deadline exceeded by {-self.remaining():.3f}s")

    def can_afford_check(self, safety_mult: float = 1.5) -> bool:
        """True if there's plausibly enough time left to run one more
        `check_feasibility`-class call before the deadline, using the
        measured `est_check_cost` with a conservative safety multiplier."""
        return self.remaining() >= self.est_check_cost * safety_mult
