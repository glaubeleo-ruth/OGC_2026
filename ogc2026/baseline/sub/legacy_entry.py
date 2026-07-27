# legacy_entry.py (was myalgorithm.py -- the legacy ALNS pipeline, unchanged)
# Entry point for the OGC 2026 shipyard solver.
#
# Architecture (ADR-001):
#     algorithm() -> SEED (baseline_greedy Phases 1-2, feasible) -> ALNS loop -> return best feasible
#
# This file is a thin wrapper. All heavy lifting lives in baseline_greedy.py
# (seed construction) and alns/ (the ALNS controller). Hard rules from
# CLAUDE.md are enforced here: the function never raises, never returns None,
# always keeps a feasible fallback (the seed), and always verifies with
# utils.check_feasibility whatever it is about to return.
#
# Timing (WATCHDOG_SPEC.md): a single alns.deadline.Deadline, monotonic-clock
# based, is created once here and threaded through the whole ALNS call chain
# so uncapped work inside a single in-flight iteration can no longer blow the
# budget -- see alns/deadline.py's module docstring for why this exists
# alongside (not instead of) baseline_greedy's own existing time.time()-based
# timing, which is untouched.

import time
import concurrent.futures
import multiprocessing


def _fork_context():
    """Explicit fork context for all pools, or None if unavailable.

    macOS defaults to spawn: children RE-IMPORT the main module, which (a)
    breaks under test harnesses that call algorithm() at module top level
    with no __main__ guard (observed: recursive seed-portfolio launches +
    'bootstrapping phase' RuntimeError on Leo's Mac), and (b) requires
    pickle-by-name for every submitted callable.  fork inherits memory --
    no re-import, no main-module hazard.  The eval server (Linux) defaults
    to fork anyway.  Platforms without fork (Windows) return None and all
    pool users fall back to their sequential paths.
    """
    try:
        if "fork" in multiprocessing.get_all_start_methods():
            return multiprocessing.get_context("fork")
    except Exception:  # noqa: BLE001
        pass
    return None


def algorithm(prob_info, timelimit=60):
    """
    Custom solver entry point. Signature is fixed by the challenge -- do not
    change it. Returns a wire-format solution dict {"operations": {...}}.

    Flow:
      1. Build a guaranteed-feasible seed via baseline_greedy Phases 1-2
         (improve=False -- we deliberately skip baseline's weak Phase-3
         hill-climb; the ALNS controller does that job far better). If the
         seed comes back infeasible, retry once with double the budget
         (capped at half the effective timelimit) before giving up -- an
         infeasible seed is a guaranteed -1, so spending more time to avoid
         it is always correct (WATCHDOG_SPEC.md #3).
      2. Verify the seed. This is the fallback of last resort.
      3. Hand the remaining time budget, as a shared Deadline, to the ALNS
         controller.
      4. Only accept the ALNS result if it re-verifies feasible AND does not
         regress vs. the seed objective. Otherwise return the seed.
    """
    import baseline_greedy
    import utils
    from alns.deadline import Deadline

    start_mono = time.monotonic()

    # Server-speed safety factor (WATCHDOG_SPEC.md #4): this dev machine may
    # be faster than the eval server's <=4 cores, so shrink the effective
    # budget rather than trust the raw `timelimit` at face value -- an
    # overrun scores -1 regardless of cause; unused time only costs a little
    # solution quality.
    timelimit_eff = max(1.0, timelimit * 0.93 - 1.0)

    # --- Step 1+2: seed + verify (fallback of last resort) ----------------
    # Size-aware seed budget (WATCHDOG_SPEC.md #3): `0.08 * n_blocks` is a
    # FLOOR (never starve Phase 1-2 on large instances), and `timelimit_eff *
    # 0.25` is meant to let the seed use more of a genuinely generous budget
    # instead of flatlining at the floor. The previous formula wrapped both
    # in an outer min(), which made the floor act as a CAP whenever it was
    # smaller than the fraction term -- true for any timelimit_eff > ~80s
    # given this floor, i.e. most real hidden timelimits ("few min-30 min"
    # per the problem statement): the seed was silently capped at ~20s no
    # matter how much total budget was actually available, even on instances
    # (like a 250-block/3-bay dense one) where the greedy search genuinely
    # needs more than that to reliably land on a feasible placement. Fixed by
    # making the floor a genuine max() lower bound, then clipping the result
    # down to what's actually left in the budget (never handing
    # baseline_greedy a timelimit larger than the time myalgorithm itself
    # actually has -- that would overrun the caller's deadline, not just this
    # function's own budget).
    n_blocks = len(prob_info.get("blocks", []))
    size_floor = max(20.0, 0.08 * n_blocks)

    # Demand-ratio-aware seed share (prob_40 diagnosis, 2026-07-23): on
    # heavily overloaded instances (area-time demand >= the whole capacity
    # through max_due) ALNS moves the objective ~2% while the seed keeps
    # improving with budget -- seed-only at 45s beat the full 60s pipeline
    # by 12% on prob_40 (ratio 1.57).  So when the instance is overloaded
    # past ratio 1.0, hand the seed a much larger share and keep ALNS as a
    # short polish pass.  Below 1.0 nothing changes (prob_39 at 0.91 keeps
    # the validated 0.25 split).
    def _demand_ratio(pi):
        try:
            blocks = pi.get("blocks", [])
            bays = pi.get("bays", [])
            if not blocks or not bays:
                return 0.0
            def _sl(poly):
                s = 0.0
                for _i in range(len(poly)):
                    _x1, _y1 = poly[_i]
                    _x2, _y2 = poly[(_i + 1) % len(poly)]
                    s += _x1 * _y2 - _x2 * _y1
                return abs(s) / 2.0
            demand = sum(sum(_sl(l) for l in b["shape"][0]["layers"]) * b["processing_time"]
                         for b in blocks)
            cap = sum(b["width"] * b["height"] for b in bays)
            maxdue = max(b["due_date"] for b in blocks)
            return demand / (cap * maxdue) if cap * maxdue > 0 else 0.0
        except Exception:
            return 0.0

    _ratio = _demand_ratio(prob_info)
    _seed_frac = 0.65 if _ratio >= 1.0 else 0.25
    seed_timelimit = max(size_floor, timelimit_eff * _seed_frac)
    seed_timelimit = min(seed_timelimit, max(1.0, timelimit_eff - 1.0))

    # --- Multi-start seed: keep the best FEASIBLE of several greedy runs. ---
    # On these instances the dominant cost Z1 (tardiness) is set almost
    # entirely by the seed -- destroy/repair ALNS barely moves it -- and the
    # greedy construction carries real run-to-run variance (its per-block
    # search is bounded by wall-clock micro-timeouts, so which candidate
    # positions get evaluated is timing-dependent). Empirically prob_1's seed
    # Z1 ranges ~36-44 across independent runs. So we spend the seed budget on
    # a few independent starts and keep the lowest-objective feasible one,
    # rather than trusting whatever the first run happens to produce. Each
    # start still gets a full-quality budget; we simply stop launching new
    # ones once the seed budget is (nearly) spent or a start cap is hit. On
    # large instances where a single greedy already fills seed_timelimit this
    # naturally collapses to exactly one start, so ALNS is not starved.
    #
    # baseline_greedy internally runs Phase-2 repair + verify, so each start
    # should usually come back feasible. est_check_cost (needed by the shared
    # Deadline) is measured from these check_feasibility calls -- the max over
    # starts, the conservative choice for the tail reservation.
    seed_sol = None
    seed_check = None
    seed_obj = None
    # Potential track (class A): the best seed ASSUMING the ALNS chains can
    # clear a small residual obj1 (measured: chains routinely zero obj1 <= ~10
    # on easy instances).  potential = total - w1*obj1.  Never replaces the
    # raw-total seed -- it seeds HALF the chains; final selection is by true
    # verified total across everything, so a failed bet costs nothing.
    _w1 = prob_info.get("weights", {}).get("w1", 1.0)
    pot_sol = None
    pot_val = None
    est_check_cost = 0.0

    # --- Stage 0 profiler (v17 M1): Class A routing ----------------------
    # Easy instances (low demand ratio, and every bay can hold its #1-pref
    # demand) are ranked almost entirely on Z2/Z3 -- every competent solver
    # reaches obj1~0 there.  Measured opportunity: prob_1 pays ~90% of its
    # total in Z2/Z3 while Z3=0 is capacity-feasible (per-bay #1-pref demand
    # ratios 0.43/0.49).  For such instances the portfolio swaps in
    # preference-led strategies; the portfolio's existing best-verified-total
    # selection is the safety net (if pref-first misfires, Default wins).
    # Multiplier calibration: w1_mult=10 keeps one tardiness day dominant
    # over the max preference swing (e.g. prob_1: 10*29091 vs 20*200*50);
    # w3_mult=20 lifts preference above the w2 balance marginal and w4/w5
    # tie-breaks that currently trade preference away.
    def _class_a(pi):
        try:
            blocks = pi.get("blocks", [])
            bays = pi.get("bays", [])
            if not blocks or not bays:
                return False
            def _sl(poly):
                s = 0.0
                for _i in range(len(poly)):
                    _x1, _y1 = poly[_i]
                    _x2, _y2 = poly[(_i + 1) % len(poly)]
                    s += _x1 * _y2 - _x2 * _y1
                return abs(s) / 2.0
            m = len(bays)
            maxdue = max(b["due_date"] for b in blocks)
            pref_d = [0.0] * m
            for b in blocks:
                j = max(range(m), key=lambda k: b["bay_preferences"][k])
                pref_d[j] += sum(_sl(l) for l in b["shape"][0]["layers"]) * b["processing_time"]
            caps = [bays[j]["width"] * bays[j]["height"] * maxdue for j in range(m)]
            max_pref_ratio = max(pref_d[j] / caps[j] for j in range(m)) if maxdue > 0 else 9.9
            return _ratio < 0.55 and max_pref_ratio < 1.0
        except Exception:
            return False

    _band = 0.55 <= _ratio < 0.70
    if _band:
        print("[myalgorithm] profiler: gate blind-band (0.55<=ratio<0.70) -> T1 on/off portfolio")
        strategies = [
            {"name": "Band T1-on", "ord_delta_mult": 0.2, "force_tailw": True},
            {"name": "Band T1-off", "ord_delta_mult": 0.2, "force_tailw": False},
            {"name": "Band T1-on EDD", "ord_delta_mult": 0.0, "force_tailw": True},
            {"name": "Band T1-off Tight", "ord_delta_mult": 0.2, "w3_mult": 1.5, "force_tailw": False}
        ]
    elif _class_a(prob_info):
        print("[myalgorithm] profiler: Class A -> preference-led strategy portfolio")
        # Calibration (measured, seed-level): joint w1/w3 multipliers shift
        # RELATIVE ratios by ~2x and cross no decision boundary (identical
        # output); w3_mult=5 alone is the switch point -- prob_1 obj3 92->12
        # (potential 20,045->3,387), prob_12 potential -23%.  Its raw total
        # is WORSE (pays obj1 3-7), so it is selected via the POTENTIAL
        # track below, never by raw total.
        # A-Lexi: w1_mult=1e6 makes zero-tardiness lexicographically absolute,
        # w3_mult=8 lets preference dominate balance/tie-breaks AMONG the
        # zero-tard slots.  Measured: never trades obj1 (prob_12 193k vs 201k,
        # prob_14 373k vs 406k, prob_1 neutral).  A-PrefPush (w3x5, obj1
        # tradeable) generates the POTENTIAL seed (prob_1 potential 3,387) --
        # its payoff requires the M2 tardy-cluster repair; until then the
        # dual-seed chains give it a chance and the true-total selection
        # keeps it harmless.
        strategies = [
            {"name": "A-Lexi", "ord_delta_mult": 0.2, "w1_mult": 1e6, "w3_mult": 8.0},
            {"name": "Core 1 (Default)", "ord_delta_mult": 0.2, "w3_mult": 1.0},
            {"name": "A-PrefPush", "ord_delta_mult": 0.2, "w3_mult": 5.0},
            {"name": "Core 3 (Strict EDD)", "ord_delta_mult": 0.0, "w3_mult": 1.0}
        ]
    else:
        # NFP-slide as a PORTFOLIO axis (geometry-dependent: measured -4%x2
        # on prob_40 but +21-25%x2 on prob_39 -- narrow bays punish origin
        # compaction by walling off crane descent paths; best-verified-total
        # selection turns an instance-dependent lever into a no-loss one).
        # Slot order matters on narrow machines: strategies[:n_workers] run.
        # Slots 1-2 = the incumbent pair (a 2-core dev box reproduces the
        # pre-NFP stack exactly); NFP-slide rides slots 3-4, so it engages
        # only where >=3 cores exist (the 4-core eval server) and the
        # best-verified-total selection keeps it no-loss there.
        strategies = [
            {"name": "Core 1 (Default)", "ord_delta_mult": 0.2, "w3_mult": 1.0},
            {"name": "Core 2 (Area Priority)", "ord_delta_mult": 0.5, "w3_mult": 1.0},
            {"name": "Core 3 (NFP-slide)", "ord_delta_mult": 0.2, "w3_mult": 1.0, "nfp_slide": 30},
            # v21e: slot 4 was Strict EDD (ord 0.0).  Narrow bucket (0.1)
            # dominates it on the hard tail (measured x2: prob_40 5.07M/5.64M
            # vs 5.96M/6.04M -- best-ever seed obj1 7,389; prob_39 wash) --
            # same axis, better point.  Strict EDD remains in the Class A and
            # band lists where its dynamics were separately validated.
            {"name": "Core 4 (Narrow Bucket)", "ord_delta_mult": 0.1, "w3_mult": 1.0}
        ]

    # --- v21b: bay-assignment MIP as a portfolio slot (capacity-light only) --
    # Solves the assignment layer exactly (w2*Z2 + w3*Z3, fluid capacity) and
    # steers one greedy strategy via a preference REWRITE.  The worker's
    # self-check uses the rewritten prefs, so the parent RE-VERIFIES this
    # strategy's solution against the TRUE prob_info before comparing.
    # No-loss by construction: best-verified-true-total selection.
    _assign_prob = None
    if _ratio < 0.55 and len(prob_info.get("bays", [])) >= 2:
        try:
            from alns import bayassign as _ba
            _amap = _ba.solve_map(prob_info, time_cap=2.0)
            if _amap:
                _assign_prob = _ba.rewrite_prefs(prob_info, _amap)
                # Lexicographic zero-tardiness (A-Lexi's trick) + map steering:
                # plain steering (w3_mult=3) realized the map's Z2 promise but
                # paid obj1 2-13 x huge w1 -> lost (measured); with w1_mult=1e6
                # the map is followed only AMONG zero-tard slots: prob_10
                # total -26% x2 (obj2 6127->986), prob_2 loses -> portfolio
                # best-of keeps it no-loss (same pattern as NFP-slide).
                strategies[-1] = {"name": "A-Assign", "ord_delta_mult": 0.2,
                                  "w1_mult": 1e6, "w3_mult": 3.0}
                print(f"[myalgorithm] bay-assign MIP: map for {len(_amap)} "
                      f"blocks -> strategy slot {len(strategies)}")
        except Exception as _ba_exc:  # noqa: BLE001
            print(f"[myalgorithm] bay-assign skipped: {_ba_exc}")

    # Portfolio sizing MUST match the cores actually available (cgroup-aware):
    # measured on a 2-core box, 4 oversubscribed workers ran at 0.46x solo
    # throughput each and portfolio quality collapsed 3-5x on prob_20, while
    # a core-matched portfolio BEAT the single run (obj1 450 -> 268).  With
    # 1 core there is no parallelism to buy -- run one sequential seed.
    import os as _os
    try:
        _n_cores = len(_os.sched_getaffinity(0))
    except AttributeError:  # non-Linux dev machines
        _n_cores = _os.cpu_count() or 1
    _n_workers = max(1, min(4, _n_cores, len(strategies)))

    # No usable fork context, or we are ALREADY inside a worker process
    # (belt-and-braces against recursive pool bombs under spawn): run every
    # stage sequentially.
    _ctx = _fork_context()
    try:
        _is_main = multiprocessing.current_process().name == "MainProcess"
    except Exception:  # noqa: BLE001
        _is_main = True
    if _ctx is None or not _is_main:
        _n_workers = 1

    import baseline_greedy
    if _n_workers == 1:
        print("[myalgorithm] 1 core available -> single sequential seed")
        try:
            seed_sol, seed_check, est_check_cost = baseline_greedy.parallel_seed_worker(
                prob_info, seed_timelimit, strategies[0])
            if seed_check.get("feasible"):
                seed_obj = seed_check.get("objective", float("inf"))
        except Exception as exc:
            print(f"[myalgorithm] sequential seed failed: {exc}")
    else:
        print(f"[myalgorithm] Launching {_n_workers} parallel seed starts, "
              f"budget {seed_timelimit:.2f}s each...")
        # Hard wall for the whole seed phase: children respect their own
        # internal guards, but a hung child must not be able to blow the
        # global deadline -- bound the wait and salvage best-so-far.
        _seed_wall = min(seed_timelimit * 1.25 + 3.0,
                         max(1.0, timelimit_eff - (time.monotonic() - start_mono) - 2.0))
        executor = concurrent.futures.ProcessPoolExecutor(max_workers=_n_workers, mp_context=_ctx)
        futures = {executor.submit(baseline_greedy.parallel_seed_worker,
                                   (_assign_prob if (strat["name"] == "A-Assign"
                                                     and _assign_prob is not None)
                                    else prob_info),
                                   seed_timelimit, strat): strat["name"]
                   for strat in strategies[:_n_workers]}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=_seed_wall):
                strat_name = futures[future]
                try:
                    cand_sol, cand_check, cand_chk_cost = future.result()
                    est_check_cost = max(est_check_cost, cand_chk_cost)
                    if (strat_name == "A-Assign" and cand_sol is not None):
                        # worker self-checked against rewritten prefs --
                        # re-verify with the TRUE prob before comparing
                        cand_check = utils.check_feasibility(prob_info, cand_sol)
                    if cand_check.get("feasible"):
                        cand_obj = cand_check.get("objective", float("inf"))
                        print(f"[myalgorithm] {strat_name} finished. Feasible: True, Obj: {cand_obj}")
                        if seed_obj is None or cand_obj < seed_obj:
                            seed_sol, seed_check, seed_obj = cand_sol, cand_check, cand_obj
                        _o1 = cand_check.get("obj1")
                        if _o1 is not None and _o1 <= 10:
                            _pv = cand_obj - _w1 * _o1
                            if pot_val is None or _pv < pot_val:
                                pot_sol, pot_val = cand_sol, _pv
                    elif seed_sol is None:
                        print(f"[myalgorithm] {strat_name} finished. Feasible: False")
                        seed_sol, seed_check = cand_sol, cand_check
                except Exception as exc:
                    print(f"[myalgorithm] Parallel seed start ({strat_name}) failed: {exc}")
        except concurrent.futures.TimeoutError:
            print(f"[myalgorithm] seed wall ({_seed_wall:.1f}s) hit -- salvaging best-so-far")
        finally:
            # Do not block on stragglers; cancel what has not started.
            executor.shutdown(wait=False, cancel_futures=True)

    if seed_sol is None:
        # Every worker failed or timed out with nothing to salvage: build a
        # last-resort sequential seed with whatever time remains.  Without
        # this, the retry gate below dereferences seed_check=None and the
        # raised exception would score -1.
        _remaining = timelimit_eff - (time.monotonic() - start_mono)
        _lr_tl = max(1.0, min(seed_timelimit, _remaining - 1.0))
        print(f"[myalgorithm] no seed from portfolio -- last-resort sequential ({_lr_tl:.1f}s)")
        seed_sol = baseline_greedy.greedyalgorithm(prob_info, _lr_tl, improve=False)
        _t0 = time.monotonic()
        seed_check = utils.check_feasibility(prob_info, seed_sol)
        est_check_cost = max(est_check_cost, time.monotonic() - _t0)

    if seed_check is None or not seed_check.get("feasible"):
        # An infeasible seed is a guaranteed -1; spending more budget to
        # avoid it is always correct. Retry once with double the seed
        # budget, capped at half the effective timelimit -- and also clipped
        # to what's actually left (the previous version only gated WHETHER
        # to retry on remaining time, not the retry's own budget, so it
        # could hand baseline_greedy more time than truly remained and
        # overrun this function's own deadline).
        retry_timelimit = min(seed_timelimit * 2, 0.5 * timelimit_eff)
        remaining_for_retry = timelimit_eff - (time.monotonic() - start_mono)
        retry_timelimit = min(retry_timelimit, max(0.0, remaining_for_retry - 1.0))
        if retry_timelimit > seed_timelimit and remaining_for_retry > 1.0:
            seed_sol = baseline_greedy.greedyalgorithm(prob_info, retry_timelimit, improve=False)
            _t0 = time.monotonic()
            seed_check = utils.check_feasibility(prob_info, seed_sol)
            est_check_cost = time.monotonic() - _t0
        if not seed_check.get("feasible"):
            # Tried once, tried again, still infeasible: return now rather
            # than handing this state to ALNS. This was briefly changed to
            # fall through into ALNS instead (on the theory that ALNS can
            # recover a feasible result from a bad seed, per its own
            # "Defensive per the task contract" branch) -- reverted after
            # observing exactly that path take 185s against a 60s budget
            # and STILL come back infeasible on this same dense instance.
            # An infeasible seed likely means Phase 1/2 left the state
            # heavily congested (many blocks packed into overlapping-time
            # windows in one bay); ALNS's per-iteration check_feasibility
            # calls are not individually time-capped (utils.py is
            # read-only, per CLAUDE.md), so a more congested starting state
            # can make a single already-in-flight iteration arbitrarily
            # slow in a way no governor here catches until after the fact.
            # A fast, bounded, guaranteed-(-1) return beats a slow,
            # unbounded one that's still just as guaranteed-(-1) --
            # overrunning the timelimit scores identically to infeasible.
            return seed_sol

    seed_obj = seed_check.get("objective")

    # Single shared deadline for the whole ALNS phase (WATCHDOG_SPEC.md).
    # est_check_cost lets every downstream check_feasibility-class call
    # (evaluate.objective, milp_repack) decide up front whether it can
    # plausibly finish before this deadline, instead of finding out too late.
    deadline = Deadline(start_mono + timelimit_eff, est_check_cost=est_check_cost)

    # --- Step 4: remaining budget gate ------------------------------------
    # If too little time is left for the ALNS controller to do anything
    # useful (it needs room for at least a destroy/repair/verify cycle plus
    # its tail reservation), skip it and return the verified seed.
    if deadline.remaining() < 2.0:
        return seed_sol

    # --- Step 4b (v17-M2beta): fix-and-optimize the seed -------------------
    # Positional F&O: free small neighborhoods and re-solve their (position,
    # entry) jointly and exactly with CP-SAT over pre-verified true-geometry
    # candidates; every accept is check_feasibility-gated inside fno.improve.
    # Measured (seed-level, 30s): prob_38 obj1 -4.2%, prob_39 -5.4%.  This is
    # the anytime engine -- its share of the remaining budget scales with
    # whatever the evaluation timelimit turns out to be.  Any exception or a
    # missing ortools -> seed passes through untouched.
    # v21d hyperparameter gate (measured, 2 reps each): on T1-heavy instances
    # (ratio >= 0.70) smaller neighborhoods solve faster and accept more
    # (K 15->8) and F&O deserves a bigger budget share than ALNS (0.4->0.6):
    # prob_39 wins x2, prob_40 wins x2.  On lighter instances the bigger F&O
    # share steals ALNS's Z2/Z3 polish (prob_29 +7.5~9.5% x2) -> keep 15/0.4.
    # K25 and C5 were swept and rejected (wash); cap3 weak-positive, unshipped.
    # User env overrides always win (setdefault / explicit get-default).
    if _ratio >= 0.70:
        _os.environ.setdefault("OGC_FNO_K", "8")
    _fno_frac = float(_os.environ.get("OGC_FNO",
                                      "0.6" if _ratio >= 0.70 else "0.4"))
    if _fno_frac > 0 and deadline.remaining() > 10.0:
        try:
            from alns import fno as _fno_mod
            _fno_budget = deadline.remaining() * _fno_frac
            _fno_res = _fno_mod.improve(prob_info, seed_sol,
                                        time_budget=_fno_budget,
                                        est_check_cost=est_check_cost)
            if _fno_res is not None:
                _fno_chk = utils.check_feasibility(prob_info, _fno_res)
                if (_fno_chk.get("feasible")
                        and _fno_chk["objective"] < seed_obj):
                    print(f"[myalgorithm] F&O improved seed: "
                          f"{seed_obj:.0f} -> {_fno_chk['objective']:.0f}")
                    seed_sol, seed_check = _fno_res, _fno_chk
                    seed_obj = _fno_chk["objective"]
        except Exception as exc:  # noqa: BLE001 -- engine must never break the pipeline
            print(f"[myalgorithm] F&O skipped: {type(exc).__name__}: {exc}")

    # --- Step 5: ALNS, fully guarded --------------------------------------
    # Parallel chains (2026-07-23): after the seed phase the other cores sat
    # idle for the whole ALNS window.  With >=2 detected cores, run
    # min(4, cores) INDEPENDENT chains from the best seed (distinct RNG
    # seeds; chain 0 keeps the historical seed so single-chain behavior is
    # reproducible), each child verifies its own result, and the parent
    # keeps the best verified one.  Falls back to the classic in-process
    # single chain on 1 core or on any pool failure.  A hung child cannot
    # blow the budget: the wait is bounded and stragglers are abandoned.
    try:
        if _n_workers >= 2 and deadline.remaining() > 4.0:
            _margin = max(1.0, est_check_cost * 2 + 0.5)
            _chain_wall = deadline.remaining() - _margin
            _chain_ts = time.monotonic() + _chain_wall
            print(f"[myalgorithm] Launching {_n_workers} parallel ALNS chains, "
                  f"{_chain_wall:.1f}s each...")
            result = None
            _result_obj = None
            from alns import controller as _alns_controller
            _chain_seeds = [seed_sol]
            if (pot_sol is not None and pot_sol is not seed_sol
                    and seed_obj is not None and pot_val is not None
                    and pot_val < seed_obj):
                _chain_seeds.append(pot_sol)
                print(f"[myalgorithm] dual-seed chains: total-best {seed_obj:.0f} "
                      f"+ potential-best {pot_val:.0f}")
            _ex2 = concurrent.futures.ProcessPoolExecutor(max_workers=_n_workers, mp_context=_ctx)
            _futs = [_ex2.submit(_alns_controller.chain_worker, prob_info,
                                 _chain_seeds[_ci % len(_chain_seeds)],
                                 _chain_ts, est_check_cost, 0xA1A5 + 7919 * _ci)
                     for _ci in range(_n_workers)]
            try:
                for _f in concurrent.futures.as_completed(_futs, timeout=_chain_wall + 3.0):
                    try:
                        _r, _obj = _f.result()
                        if _obj is not None and (_result_obj is None or _obj < _result_obj):
                            result, _result_obj = _r, _obj
                    except Exception as exc:  # noqa: BLE001
                        print(f"[myalgorithm] ALNS chain failed: {exc}")
            except concurrent.futures.TimeoutError:
                print("[myalgorithm] ALNS chain wall hit -- salvaging best-so-far")
            finally:
                _ex2.shutdown(wait=False, cancel_futures=True)
            if result is None:
                result = seed_sol
            print(f"[myalgorithm] parallel ALNS best verified obj: {_result_obj}")
        else:
            from alns.controller import run as alns_run
            result = alns_run(prob_info, seed_sol, deadline)
    except Exception as exc:  # noqa: BLE001 -- deliberate broad guard, safety net
        print(f"[myalgorithm] ALNS path failed ({type(exc).__name__}: {exc}); returning seed")
        return seed_sol

    # --- Step 6: re-verify ALNS result; never regress vs. seed ------------
    if result is not None:
        try:
            res_check = utils.check_feasibility(prob_info, result)
        except Exception as exc:  # noqa: BLE001 -- verification itself must not crash us
            print(f"[myalgorithm] ALNS result verify crashed ({type(exc).__name__}: {exc}); returning seed")
            return seed_sol
        if (res_check.get("feasible") is True
                and res_check.get("objective") is not None
                and seed_obj is not None
                and res_check["objective"] <= seed_obj + 1e-6):
            return result

    # ALNS produced nothing acceptable -> verified seed.
    return seed_sol
