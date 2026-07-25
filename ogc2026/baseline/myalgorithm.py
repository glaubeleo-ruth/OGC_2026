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

import multiprocessing
import os
import signal
import time


def _fork_context():
    try:
        if "fork" in multiprocessing.get_all_start_methods():
            return multiprocessing.get_context("fork")
    except Exception:
        pass
    return None


def _run_legacy_hard_walled(prob_info, child_tl, hard_wall):
    """Run legacy_entry.algorithm in a forked child that leads its own
    process group, and SIGKILL the whole group at `hard_wall` seconds.

    Why: the legacy pipeline's seed construction is not preemptible -- on
    dense instances a single pass can need ~40s no matter how small its
    grant is (eva panel: prob_38 walls 66.6/75.5s at timelimit 60 = server
    -1), and no static instance statistic separates that class (prob_38 and
    prob_40 share n=250; one fits, one blows).  A hedge line must never be
    able to sink the entry, so the parent holds a kill switch.  setsid()
    makes the child a group leader, so the kill also reaps the pool
    grandchildren the legacy line spawns.  Returns a solution dict or None
    (a killed child simply forfeits the hedge; the solver result stands).
    No fork context (non-Linux/mac) -> caller skips the legacy line.
    """
    ctx = _fork_context()
    if ctx is None:
        return None
    recv, send = ctx.Pipe(duplex=False)

    def _target(conn, pi, tl):
        os.setsid()
        try:
            import legacy_entry
            conn.send(legacy_entry.algorithm(pi, tl))
        except Exception:
            try:
                conn.send(None)
            except Exception:
                pass

    proc = ctx.Process(target=_target, args=(send, prob_info, child_tl))
    proc.start()
    send.close()
    result = None
    try:
        if recv.poll(hard_wall):
            result = recv.recv()
    except Exception:
        result = None
    finally:
        recv.close()
        proc.join(timeout=0.5)
        if proc.is_alive():
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
            proc.join(timeout=2.0)
    return result


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

    # -- Line 2: legacy ALNS portfolio on the remaining wall, hard-walled --
    # The child gets a discounted internal timelimit (so it normally
    # finishes on its own) inside a hard kill wall at what actually
    # remains minus the parent's audit reserve.
    try:
        import utils
        raw_left = timelimit - (time.monotonic() - t0)
        hard_wall = raw_left - 1.5
        legacy_tl = hard_wall * 0.85
        if legacy_tl > 5.0:
            leg = _run_legacy_hard_walled(prob_info, legacy_tl, hard_wall)
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
