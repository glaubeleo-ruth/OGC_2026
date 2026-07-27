"""
incumbent.py -- incumbent store behind the utils audit gate.

Hard rule: whatever algorithm() returns must have passed
utils.check_feasibility (T6: the checker is the final gate and spot-audit,
never an inner loop).  The store keeps the best *audited* solution; anything
unaudited can guide search but can never be returned.
"""

from __future__ import annotations


class IncumbentStore:
    def __init__(self, prob_info: dict, utils_module):
        self.prob_info = prob_info
        self.utils = utils_module
        self.best_solution: dict | None = None
        self.best_objective: float = float("inf")
        self.audits = 0

    def audit_and_update(self, solution: dict) -> dict:
        """Run the official checker; keep the solution iff feasible and
        better. Returns the checker result dict."""
        self.audits += 1
        try:
            res = self.utils.check_feasibility(self.prob_info, solution)
        except Exception as exc:               # a crashing checker never
            return {"feasible": False,        # propagates out of the store
                    "violations": [f"checker raised: {exc!r}"],
                    "objective": None}
        if res.get("feasible") and res["objective"] < self.best_objective:
            self.best_solution = solution
            self.best_objective = res["objective"]
        return res
