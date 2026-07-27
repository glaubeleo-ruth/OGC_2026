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
# incumbent, and the last resort is a feasible construction rather than an
# empty dict whenever one can be built and audited inside the reserve.
#
# -- Return-path ordering (parent-side audit ladder) ---------------------
# Every line of this file that can produce a return value goes through ONE
# ladder, in this order:
#
#   (1) best PARENT-AUDITED feasible incumbent (utils.check_feasibility run
#       here, in the parent, on the exact dict about to be returned) --
#       always preferred, regardless of which line produced it;
#   (2) the parent-side LAST-RESORT CONSTRUCTION (single-occupancy serial
#       placement), built and AUDITED inside the tail reserve whenever
#       clause (1) is empty; the reserve exists to pay for exactly that
#       build + audit.  A construction that passes is promoted into (1);
#   (3) an UNAUDITED candidate (never audited, or audited by a checker that
#       CRASHED -- both are epistemically "not known bad"), allowed only
#       when nothing audited-feasible exists;
#   (4) a candidate the checker actively REJECTED -- a certain -1, so it
#       ranks below anything merely unverified;
#   (5) the {"operations": {}} placeholder.  Never None, never raise.
#
# -- Audit-ladder repair pass, 2026-07-27 (BLINDSPOT F19-F24) ------------
# F19: the audit gate was the constant `_remaining() > 1.0` while a parent
#      audit measures 0.034-0.221 s, so the entry refused audits it could
#      afford 5-19x over -- and the measured kill-drain (M2: +0.51-0.54 s
#      past the hard wall) parks the entry at R ~ 0.97 s, 0.03 s inside
#      that refusal window, on precisely the hedge-killed path.  The gate
#      is now cost-based: `_remaining() > estimated_audit + margin`.
# F20: `_audit` collapsed "the checker said no" with "the checker could not
#      run"; both mapped to the rejected rank, which let a KNOWN-infeasible
#      dict outrank a dict whose audit merely crashed.  `_audit` is now
#      tri-state and a crashed audit ranks as unverified, never as bad.
# F21/F22: clause (2) had no parent-side construction at all -- solver dead
#      + hedge SIGKILLed returned {"operations": {}} with 100% of the
#      reserve unspent.  Those two failures are the SAME instance property
#      (dense pack), so they fire together.  The terminal rung is now a
#      single-occupancy serial construction: rex M6 measured 12/12 feasible
#      (every n=250/300 train instance included) at build+audit <= 0.169 s.
#      It reuses solver/emit.build_solution -- F23 showed the checker walks
#      `operations` in DICT INSERTION ORDER and needs EXIT before ENTRY
#      within a time key, so emission is never hand-rolled here.
# F24: the reserve and the gate were sized from line 1's measured audit,
#      which short-circuits in 0.001 s exactly when line 1 fails -- i.e. the
#      measurement is destroyed on the only path where the tail audit is the
#      only audit.  Both are now sized from an INSTANCE STATISTIC (audit
#      cost is linear in n^2/n_bays, M1), floored by any real measurement
#      taken during this run.
#
# WATCHDOG rules served by the timing changes here: *safety factor* +
# *deadline threading*.  The tail reserve is max(1.5 s, 3 x estimated audit
# + kill-drain margin): three audit-equivalents cover the worst tail
# sequence (tail audit of the hedge, then build + audit of the terminal
# rung) and the margin covers the measured kill-drain overshoot.  On every
# train instance the statistic tops out at n^2/n_bays = 20.8k -> estimate
# 0.21 s -> the expression stays at its 1.5 s floor, i.e. the hedge's hard
# wall is bit-identical to commit 1a02fb2 on everything we can measure; the
# adaptive term only engages above n^2/n_bays ~ 30k, where it must.

import math
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

# Tri-state audit outcome (F20).  "The checker ran and said no" and "the
# checker could not run" are different facts and must rank differently.
_AUDIT_FEASIBLE = "feasible"      # checker ran, all five stages passed
_AUDIT_INFEASIBLE = "infeasible"  # checker ran, returned a violation
_AUDIT_ERROR = "error"            # checker raised / was unavailable

# Fallback ranks for clauses (3)-(5).  A candidate we KNOW fails utils is a
# certain -1; one we never got to audit -- or one whose audit crashed -- is
# only a risk, so the unverified ones outrank it.  Rank never decreases.
_RANK_EMPTY = 0            # the {"operations": {}} placeholder
_RANK_REJECTED = 1         # parent audit ran and said infeasible
_RANK_UNAUDITED = 2        # never audited (budget too tight to start one)
_RANK_AUDIT_ERROR = 2      # audit attempted but the checker raised: as F20
#                            requires, epistemically identical to "never
#                            audited" and strictly above _RANK_REJECTED.

# Parent-audit cost model (F24).  rex M1 fitted utils.check_feasibility on
# the returned dict across prob_1/31/20/38: cost is linear in n^2/n_bays
# (NOT in n -- prob_38, n=250 in 3 bays, costs more than prob_20, n=300 in
# 5 bays), with coefficient ~1.0e-5 s under 5 GB of swap and 0.6-0.8e-5 s on
# the cleaner run.  The swap-inflated coefficient is the conservative one,
# so it is the one shipped.
_AUDIT_COST_COEFF_S = 1.0e-5

# Headroom kept free on both sides of any tail audit.  Provenance: rex M2
# measured the real _run_legacy_hard_walled kill-drain overshooting its own
# hard wall by +0.510 / +0.508 / +0.525 / +0.537 s (SIGKILL reaps promptly;
# the theoretical 2.5 s join chain is never realised).  0.6 s covers the
# worst measurement with slack.
_KILL_DRAIN_MARGIN_S = 0.6

# Tail-reserve floor, unchanged from commit 1a02fb2.
_RESERVE_FLOOR_S = 1.5


def _fork_context():
    try:
        if "fork" in multiprocessing.get_all_start_methods():
            return multiprocessing.get_context("fork")
    except Exception:
        pass
    return None


def _audit_cost_estimate(prob_info):
    """Estimated parent-audit wall for this instance, from instance stats.

    F24: sizing the reserve from line 1's *measured* audit collapses to
    0.001 s whenever line 1's dict fails at stage 1 -- which is exactly the
    path where the tail audit is the only audit that will ever run.  An
    instance statistic cannot be destroyed that way.  Never raises.
    """
    try:
        n = len(prob_info.get("blocks") or ())
        n_bays = max(1, len(prob_info.get("bays") or ()))
        return _AUDIT_COST_COEFF_S * float(n) * float(n) / float(n_bays)
    except Exception:
        return 0.0


def _audit(prob_info, solution):
    """Parent-side utils audit of exactly the dict we might return.

    Returns (status, objective, wall_seconds) with status one of
    _AUDIT_FEASIBLE / _AUDIT_INFEASIBLE / _AUDIT_ERROR (F20).  objective is
    None unless the status is _AUDIT_FEASIBLE.  Never raises -- note that
    utils.check_feasibility is NOT total (rex F23: a block_id outside
    range(n_blocks) raises IndexError), so every call site stays wrapped.
    """
    t0 = time.monotonic()
    if not isinstance(solution, dict):
        return _AUDIT_INFEASIBLE, None, time.monotonic() - t0
    try:
        import utils
        res = utils.check_feasibility(prob_info, solution)
        dt = time.monotonic() - t0
        if res.get("feasible") and res.get("objective") is not None:
            return _AUDIT_FEASIBLE, float(res["objective"]), dt
        return _AUDIT_INFEASIBLE, None, dt
    except Exception:
        # The checker could not deliver a verdict.  This is NOT evidence the
        # solution is bad; treating it as such once let a known-infeasible
        # dict outrank a good one (F20).
        return _AUDIT_ERROR, None, time.monotonic() - t0


def _emitter():
    """The solver's own emission entry point, or None.

    F23 documents two traps that make hand-rolling emission unsafe: the
    checker's first pass walks `operations` in dict INSERTION order, and
    within a time key every EXIT must precede every ENTRY.  solver/emit.py
    already gets both right, so the terminal rung reuses it rather than
    re-deriving it.

    Load order matters for the budget: `from solver.emit import ...` runs
    the solver PACKAGE __init__, which pulls in the whole engine and cost a
    measured 3.5 s cold -- more than the entire tail reserve, on exactly the
    path (line 1 dead, so the package may never have been imported) where
    this rung is the last thing between us and a -1.  So: an already-loaded
    module first, then the same file loaded directly by path (emit.py
    imports nothing but collections), and only then the package import.
    """
    mod = sys.modules.get("solver.emit")
    if mod is not None:
        try:
            return mod.build_solution
        except Exception:
            pass
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_ogc_emit", os.path.join(_BASE, "solver", "emit.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.build_solution
    except Exception:
        pass
    try:
        from solver.emit import build_solution
        return build_solution
    except Exception:
        return None


class _Place(object):
    """Duck-typed stand-in for solver.oracle.Placement, which is all that
    solver/emit.build_solution reads (block_id, bay_id, x, y, orient_idx,
    entry, exit).  Importing oracle would drag in the whole engine."""

    __slots__ = ("block_id", "bay_id", "x", "y", "orient_idx", "entry", "exit")

    def __init__(self, block_id, bay_id, x, y, orient_idx, entry, exit):
        self.block_id = block_id
        self.bay_id = bay_id
        self.x = x
        self.y = y
        self.orient_idx = orient_idx
        self.entry = entry
        self.exit = exit


def _serial_construction(prob_info, keep_going=None):
    """Clause-(2) terminal rung: single-occupancy serial placement.

    One block in a bay at a time.  Each block takes the earliest bay/
    orientation that can hold it alone, entering at
    max(ceil(release_time), bay_free_time) and leaving processing_time
    later; the next block may enter at exactly that instant because the
    checker frees the bay first (EXIT precedes ENTRY within a time key).
    Single occupancy makes stages 2-4 vacuous: nothing else is ever in the
    bay to collide with or to obstruct a crane path.

    The offset is the analytic bounding-box shift, ACCEPTED ONLY when
    utils.Bay.contains_block itself agrees -- the boundary verdict is never
    re-derived here.  Objective quality is bad by construction (rex M6:
    5.9e7-2.9e9); this is -1 insurance, not an objective play, and it only
    ever occupies the terminal rung.

    Returns a solution dict, or None if any block cannot be placed alone in
    any bay, if the emitter is unavailable, or if keep_going() went False.
    Never raises.
    """
    try:
        import utils
    except Exception:
        return None
    build_solution = _emitter()
    if build_solution is None:
        return None
    try:
        bays = [utils.Bay.from_dict(d, j)
                for j, d in enumerate(prob_info["bays"])]
        blocks = prob_info["blocks"]
    except Exception:
        return None
    if not bays or not blocks:
        return None

    free = [0] * len(bays)
    places = []
    for bi, blk in enumerate(blocks):
        if keep_going is not None and (bi & 31) == 0 and not keep_going():
            return None
        try:
            release = int(math.ceil(float(blk.get("release_time", 0) or 0)))
            proc = max(1, int(math.ceil(float(blk.get("processing_time", 1)
                                              or 1))))
            n_orient = len(blk["shape"])
        except Exception:
            return None
        best = None
        for oi in range(n_orient):
            if best is not None and best[0] <= release:
                break               # already at the earliest legal entry
            try:
                probe = utils.Block(block_id=bi, block_data=blk,
                                    x=0, y=0, orient_idx=oi)
                bb = probe.bounding_rect()
                x0 = int(math.ceil(-bb[0]))
                y0 = int(math.ceil(-bb[1]))
                cands = [utils.Block(block_id=bi, block_data=blk,
                                     x=x, y=y, orient_idx=oi)
                         for x in (x0, x0 + 1) for y in (y0, y0 + 1)]
            except Exception:
                continue
            for j, bay in enumerate(bays):
                start = max(release, free[j])
                if best is not None and start >= best[0]:
                    continue        # cannot beat the incumbent placement
                for cand in cands:
                    try:
                        fits = bay.contains_block(cand)
                    except Exception:
                        fits = False
                    if fits:
                        best = (start, j, oi, cand.x, cand.y)
                        break
        if best is None:
            return None             # no bay holds this block even alone
        entry, j, oi, x, y = best
        exit_t = entry + proc
        free[j] = exit_t
        places.append(_Place(bi, j, int(x), int(y), oi, entry, exit_t))

    try:
        return build_solution(places)
    except Exception:
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

    # Clause (1) slot: only ever holds a dict that passed a parent-side
    # utils.check_feasibility in THIS process, with its checker objective.
    best_sol = None
    best_obj = float("inf")

    # Clauses (3)-(5) slot: never None, never preferred over best_sol.
    fallback = {"operations": {}}
    fallback_rank = _RANK_EMPTY

    # Audit-cost estimate.  Starts from the instance statistic (F24: the
    # only estimate that survives a line-1 collapse) and is raised, never
    # lowered, by any real parent audit measured during this run.
    est_audit = _audit_cost_estimate(prob_info)

    def _remaining():
        return timelimit - (time.monotonic() - t0)

    def _affordable(n_audits):
        """True when n_audits parent audits still fit with margin left."""
        return _remaining() > n_audits * est_audit + _KILL_DRAIN_MARGIN_S

    def _offer(sol):
        """Push one candidate through the ladder.  Audits it whenever the
        measured cost of an audit fits in what is left (clause 2: the audit
        is what the reserve is for); promotes it to best_sol on a pass,
        otherwise files it as the clause-(3)/(4) fallback at the rank its
        audit STATUS earns."""
        nonlocal best_sol, best_obj, fallback, fallback_rank, est_audit
        if not isinstance(sol, dict) or not sol.get("operations"):
            return
        # F19: gate on the estimated cost of the audit, not on a constant.
        # The old `_remaining() > 1.0` refused audits costing 0.03-0.22 s
        # and the kill-drain lands the entry inside that window by design.
        if _affordable(1):
            status, obj, dt = _audit(prob_info, sol)
            est_audit = max(est_audit, dt)   # measurement floors the model
            if status == _AUDIT_FEASIBLE:
                if obj < best_obj:          # clause 1: best audited wins
                    best_sol, best_obj = sol, obj
                return
            # F20: a crashed checker is not a verdict.  Rank it as
            # unverified so it can never lose to a known-infeasible dict.
            rank = (_RANK_AUDIT_ERROR if status == _AUDIT_ERROR
                    else _RANK_REJECTED)
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
    # remains minus the parent's tail reserve.  The reserve must pay for
    # the worst tail sequence the ladder can still owe: the hedge's own
    # audit, then the terminal rung's build AND audit, plus the measured
    # kill-drain margin -- three audit-equivalents (see the WATCHDOG note
    # in the header), floored at the 1.5 s of commit 1a02fb2.
    try:
        tail_reserve = max(_RESERVE_FLOOR_S,
                           3.0 * est_audit + _KILL_DRAIN_MARGIN_S)
        hard_wall = _remaining() - tail_reserve
        legacy_tl = hard_wall * 0.85
        if legacy_tl > 5.0:
            leg = _run_legacy_hard_walled(prob_info, legacy_tl, hard_wall)
            # A killed / crashed child yields None and simply forfeits the
            # hedge -- the audited solver incumbent stands (eva P0(b)).
            if leg is not None:
                _offer(leg)
    except Exception:
        pass

    # -- Clause (2): parent-side last resort (F21/F22) --------------------
    # Runs ONLY when nothing audited-feasible exists -- it never competes
    # with best_sol, it only replaces the empty-dict terminal rung on the
    # solver-dead + hedge-killed path, which is a certain -1.  Budgeted at
    # two audit-equivalents (build, then audit) plus margin; its result
    # goes through the SAME tri-state audit and ranking as every other
    # candidate, so a construction that somehow fails cannot be promoted.
    try:
        if best_sol is None and _affordable(2):
            _offer(_serial_construction(prob_info,
                                        keep_going=lambda: _affordable(1)))
    except Exception:
        pass

    # -- Return ladder ----------------------------------------------------
    # (1) best parent-audited feasible -- including a promoted last-resort
    # construction; (3)/(4) otherwise the highest-ranked unverified or
    # rejected candidate; (5) the placeholder.  Never None, never raise.
    if best_sol is not None:
        return best_sol
    if isinstance(fallback, dict) and "operations" in fallback:
        return fallback
    return {"operations": {}}
