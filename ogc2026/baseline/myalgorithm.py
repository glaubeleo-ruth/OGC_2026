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
#
# -- Return-path ordering (parent-side audit, 2026-07-27) ----------------
# Every line of this file that can produce a return value now goes through
# ONE ladder, in this order:
#
#   (1) best PARENT-AUDITED feasible incumbent (utils.check_feasibility run
#       here, in the parent, on the exact dict about to be returned) --
#       always preferred, regardless of which line produced it;
#   (2) the last-resort construction, AUDITED inside the tail reserve --
#       the reserve exists to pay for that audit, so the audit is never
#       skipped while the reserve is intact; a construction that passes is
#       promoted into (1);
#   (3) an UNAUDITED candidate, allowed only when nothing audited-feasible
#       exists AND the reserve is spent -- an unaudited dict is a *risk*
#       of -1, returning None is a *certain* -1, so the unaudited candidate
#       wins.  Never None, never raise.
#
# Motivation (eva P0(b), results/2026-07-27_submission5_arm_gate_baseline.md):
# on the prob_38 timeout/kill class the hedge child is SIGKILLed at the hard
# wall, and it is precisely the parent's return-path ordering that decides
# whether the entry ships an audited incumbent or a kill artifact.
#
# WATCHDOG rules served by the timing change here: *safety factor* +
# *deadline threading*.  The tail reserve is no longer the flat 1.5 s of
# commit 1a02fb2 but max(1.5 s, 1.6 x measured parent audit + 0.4 s), where
# the measurement is line 1's own parent-side audit on this instance -- the
# same measured-reserve discipline solver/api.py uses (1.5 x t_audit1).  A
# reserve derived from a measurement on THIS instance cannot be undersized
# by an instance whose audit is slow, and it only ever moves the hedge's
# hard wall EARLIER, never later.

import multiprocessing
import os
import signal
import sys
import time

# utils.py lives next to this file; the audit ladder must be able to import
# it no matter what the harness' cwd is (solver/api.py does the same).
_BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

# Fallback ranks for the clause-(3) candidate.  A candidate we KNOW fails
# utils is a certain -1; one we never got to audit is only a risk, so the
# unaudited one outranks it.  Rank never decreases.
_RANK_EMPTY = 0        # the {"operations": {}} placeholder
_RANK_REJECTED = 1     # parent audit ran and said infeasible
_RANK_UNAUDITED = 2    # never audited (no budget / audit unavailable)


def _fork_context():
    try:
        if "fork" in multiprocessing.get_all_start_methods():
            return multiprocessing.get_context("fork")
    except Exception:
        pass
    return None


def _audit(prob_info, solution):
    """Parent-side utils audit of exactly the dict we might return.

    Returns (feasible, objective, wall_seconds).  feasible is False and
    objective None on any failure -- an audit that cannot run is treated as
    "not audited feasible", never as a pass.  Never raises.
    """
    t0 = time.monotonic()
    if not isinstance(solution, dict):
        return False, None, time.monotonic() - t0
    try:
        import utils
        res = utils.check_feasibility(prob_info, solution)
        dt = time.monotonic() - t0
        if res.get("feasible") and res.get("objective") is not None:
            return True, float(res["objective"]), dt
        return False, None, dt
    except Exception:
        return False, None, time.monotonic() - t0


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

    # Clause (1) slot: only ever holds a dict that passed a parent-side
    # utils.check_feasibility in THIS process, with its checker objective.
    best_sol = None
    best_obj = float("inf")

    # Clause (3) slot: never None, never preferred over best_sol.
    fallback = {"operations": {}}
    fallback_rank = _RANK_EMPTY

    # Measured parent-side audit wall on this instance; sizes the reserve.
    audit_cost = 0.0

    def _remaining():
        return timelimit - (time.monotonic() - t0)

    def _offer(sol, allow_audit=True):
        """Push one candidate through the ladder.  Audits it when the
        budget allows (clause 2: the audit is what the reserve is for);
        promotes it to best_sol on a pass, otherwise files it as the
        clause-(3) fallback at the appropriate rank."""
        nonlocal best_sol, best_obj, fallback, fallback_rank, audit_cost
        if not isinstance(sol, dict) or not sol.get("operations"):
            return
        # Audit unless the entry has less slack left than CLAUDE.md's own
        # 1 s watchdog term -- past that point an audit could itself push
        # the entry over the limit, and an unaudited dict still beats None.
        if allow_audit and _remaining() > 1.0:
            feasible, obj, dt = _audit(prob_info, sol)
            audit_cost = max(audit_cost, dt)
            if feasible:
                if obj < best_obj:          # clause 1: best audited wins
                    best_sol, best_obj = sol, obj
                return
            rank = _RANK_REJECTED           # certain -1 if ever returned
        else:
            rank = _RANK_UNAUDITED          # clause 3: risk, not certainty
        if rank > fallback_rank:
            fallback, fallback_rank = sol, rank

    # -- Line 1: clean-slate solver ---------------------------------------
    # solve() hands back its store incumbent when it has one, else its best
    # -effort construction.  We do not trust either label: the parent runs
    # its own utils audit on whatever came back, so best_sol and the legacy
    # candidate below are ranked by the SAME checker on the SAME objective.
    try:
        frac = float(os.environ.get("OGC_SOLVER_FRAC", "0.55"))
        from solver.api import solve as _solver_solve
        sol, _info = _solver_solve(prob_info, max(1.0, timelimit * frac))
        _offer(sol)
    except Exception:
        pass

    # -- Line 2: legacy ALNS portfolio on the remaining wall, hard-walled --
    # The child gets a discounted internal timelimit (so it normally
    # finishes on its own) inside a hard kill wall at what actually
    # remains minus the parent's tail reserve.  The reserve is measured
    # (see the WATCHDOG note in the header), floored at the 1.5 s of
    # commit 1a02fb2, and is what pays for the tail audit below.
    try:
        tail_reserve = max(1.5, 1.6 * audit_cost + 0.4)
        hard_wall = _remaining() - tail_reserve
        legacy_tl = hard_wall * 0.85
        if legacy_tl > 5.0:
            leg = _run_legacy_hard_walled(prob_info, legacy_tl, hard_wall)
            # A killed / crashed child yields None and simply forfeits the
            # hedge -- the audited solver incumbent stands (eva P0(b)).
            if leg is not None:
                # Clause 2: spend the reserve on this audit rather than
                # skip it.  Only when we already hold an audited incumbent
                # AND the reserve is provably gone do we forfeit instead --
                # an unaudited hedge could never outrank best_sol anyway.
                affordable = _remaining() > 1.0 + audit_cost
                _offer(leg, allow_audit=affordable or best_sol is None)
    except Exception:
        pass

    # -- Return ladder ----------------------------------------------------
    # (1) best parent-audited feasible; (2) an audited last resort has
    # already been promoted into (1) by _offer; (3) otherwise the highest
    # -ranked unaudited/rejected candidate.  Never None, never raise.
    if best_sol is not None:
        return best_sol
    if isinstance(fallback, dict) and "operations" in fallback:
        return fallback
    return {"operations": {}}
