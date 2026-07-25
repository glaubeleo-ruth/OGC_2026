# myalgorithm.py -- CHIMERA entry (FINALE_PLAN Phase 2, milestone-3 switch).
#
# Two independent lines, best verified result wins per instance:
#
#   1. the clean-slate solver (solver/, LBBD master + oracle + repair) runs
#      first on OGC_SOLVER_FRAC of the raw timelimit (default 0.55); it
#      audits internally via utils and returns its best store incumbent;
#   2. the legacy ALNS portfolio (legacy_entry.py, byte-for-byte the
#      pre-switch myalgorithm.py) runs on whatever wall-clock actually
#      remains -- so when the solver stops early at a certificate
#      (prob_1-class, < 3 s) the legacy line inherits nearly everything.
#
# Rationale (R - nb): the v0.4 sweep has the solver >= legacy on all 40
# train instances, but the hidden set is not train; the legacy line is the
# hedge for instance classes the new pipeline has never seen.  Each line
# already enforces its own 0.93*t - 1 watchdog against the timelimit IT is
# given, so the split keeps the total wall under the raw limit with margin.
#
# Hard rules (CLAUDE.md) enforced here: fixed signature, never raises,
# never returns None, nothing unverified is preferred over a verified
# incumbent, and the last resort is the solver's best-effort construction
# rather than an empty dict whenever one exists.

import os
import time


def algorithm(prob_info, timelimit=60):
    t0 = time.monotonic()
    best_sol = None
    best_obj = float("inf")
    last_resort = {"operations": {}}

    # -- Line 1: clean-slate solver ---------------------------------------
    try:
        frac = float(os.environ.get("OGC_SOLVER_FRAC", "0.55"))
        from solver.api import solve as _solver_solve
        sol, info = _solver_solve(prob_info, max(1.0, timelimit * frac))
        if sol and sol.get("operations"):
            last_resort = sol
        obj = info.get("best_objective")
        # best_objective < inf iff the store holds a utils-audited feasible
        # incumbent; the returned sol is that incumbent.
        if sol is not None and obj is not None and obj < float("inf"):
            best_sol, best_obj = sol, float(obj)
    except Exception:
        pass

    # -- Line 2: legacy ALNS portfolio on the remaining wall ---------------
    try:
        import utils
        remaining = timelimit - (time.monotonic() - t0) - 2.0  # audit reserve
        if remaining > 5.0:
            import legacy_entry
            leg = legacy_entry.algorithm(prob_info, remaining)
            if leg is not None and leg.get("operations") is not None:
                chk = utils.check_feasibility(prob_info, leg)
                if chk.get("feasible") and chk.get("objective") is not None \
                        and chk["objective"] < best_obj:
                    best_sol, best_obj = leg, chk["objective"]
                elif best_sol is None and last_resort is not None \
                        and not last_resort.get("operations"):
                    last_resort = leg
    except Exception:
        pass

    return best_sol if best_sol is not None else last_resort
