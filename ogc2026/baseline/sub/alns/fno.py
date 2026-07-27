"""
alns/fno.py -- Fix-and-Optimize engine (v17 M2, blueprint section 4).

Repairs a verified-feasible solution by repeatedly FREEING a small set of
blocks (a neighborhood) and re-solving their (x, y, entry) jointly and
EXACTLY with CP-SAT, all other blocks fixed.  This is the tool ALNS is not:
measured, destroy-repair with greedy reinsertion moves obj1 ~2% because Z1
improvements need coordinated multi-block relocation; an exact subproblem
finds those relocations.

Model correctness (the two bugs of the earlier CP-SAT draft, fixed):
  * Coordinates are REFERENCE-POINT based.  A block's world AABB is
    [x + lx0, x + lx1] x [y + ly0, y + ly1] where (lx0, ly0, lx1, ly1) is
    the orientation's local bbox (lx0 is typically NEGATIVE -- 220/250
    blocks on prob_39).  Domains: x in [ceil(-lx0), floor(W - lx1)].
  * Nothing is committed without utils.check_feasibility on the FULL
    candidate solution; rejected candidates change nothing.

Conservative feasibility: pairwise constraints demand space-OR-time
disjunction of world AABBs within a bay.  AABB-disjoint blocks cannot
violate the layer-collision or crane j>=k rules (utils' own AABB prefilter
skips such pairs), so every model solution passes the true checker's
spatial stages; the full check still runs before any accept (belt and
braces -- it also covers anything this docstring is wrong about).

Scope (M2): bay and orientation are FIXED to the incumbent; the solver
re-times and re-positions. Cross-bay moves are M2.5.

M2-gamma (parallel rounds): the sequential loop used 1 of the <=4 allowed
cores for the whole F&O budget.  With W = min(4, cores) fork workers, each
round selects W neighborhoods with DISJOINT freed sets, solves the W
CP-SAT subproblems concurrently (num_search_workers stays 1 per worker --
processes provide the parallelism), then the parent verifies and commits
the results sequentially against the evolving incumbent.  Disjoint freed
sets make most accepts compose; any stale-context conflict is caught by
the same check_feasibility gate as before.  Env: OGC_FNO_WORKERS (0 =
auto), 1 = exact sequential behavior; pool-creation failure or a
non-MainProcess caller also falls back to sequential.
"""

import math
import os
import time

try:
    from ortools.sat.python import cp_model
    _HAS_ORTOOLS = True
except Exception:  # noqa: BLE001
    _HAS_ORTOOLS = False

try:
    from alns import nfp as _nfp_mod
except Exception:  # noqa: BLE001
    _nfp_mod = None

try:
    import utils
except ImportError:  # pragma: no cover
    utils = None


# ---------------------------------------------------------------------------
# Solution parsing / building
# ---------------------------------------------------------------------------

def _parse(sol):
    """operations dict -> {bid: {bay, x, y, oi, entry, exit}}"""
    a = {}
    for t_s, lst in sol["operations"].items():
        t = int(t_s)
        for o in lst:
            b = o["block_id"]
            rec = a.setdefault(b, {})
            if o["type"] == "ENTRY":
                rec.update(bay=o["bay_id"], x=o["x"], y=o["y"],
                           oi=o["orient_idx"], entry=t)
            else:
                rec["exit"] = t
    return a


def _build(assign):
    """{bid: rec} -> operations dict (wire format).

    Mirrors baseline_greedy._build_operations exactly: keys inserted in
    ascending INT time order, EXITs before ENTRYs within a time point,
    block_id-sorted within type.  utils processes keys/ops in this order --
    a naive insertion-ordered dict made replay see EXIT@'11' before
    ENTRY@'2' (string keys) and reject with "no EXIT operation"."""
    buckets = {}
    for b, r in assign.items():
        buckets.setdefault(int(r["exit"]), []).append((0, b, r))
        buckets.setdefault(int(r["entry"]), []).append((1, b, r))
    ops = {}
    for t in sorted(buckets):
        out = []
        for kind, b, r in sorted(buckets[t], key=lambda x: (x[0], x[1])):
            if kind == 0:
                out.append({"type": "EXIT", "block_id": b, "bay_id": r["bay"]})
            else:
                out.append({"type": "ENTRY", "block_id": b, "bay_id": r["bay"],
                            "x": int(r["x"]), "y": int(r["y"]), "orient_idx": r["oi"]})
        ops[str(t)] = out
    return {"operations": ops}


def _bbox(blk_data, oi):
    xs, ys = [], []
    for layer in blk_data["shape"][oi]["layers"]:
        for (px, py) in layer:
            xs.append(px)
            ys.append(py)
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# Neighborhood selection
# ---------------------------------------------------------------------------

def _tardy_ids(assign, blocks):
    out = []
    for b, r in assign.items():
        t = r["exit"] - blocks[b]["due_date"]
        if t > 0:
            out.append((t, b))
    out.sort(reverse=True)
    return out


def _select(kind, assign, blocks, rng, K, maxdue):
    """Return a list of freed block ids (<= K)."""
    tardy = _tardy_ids(assign, blocks)
    if not tardy and kind in ("tardy", "tail", "ontime"):
        return []
    if kind == "tardy":
        # top tardy seeds + same-bay time-overlapping neighbors
        seeds = [b for _, b in tardy[:max(3, K // 3)]]
        freed = list(seeds)
        seen = set(seeds)
        for s in seeds:
            rs = assign[s]
            for b, r in assign.items():
                if b in seen or r["bay"] != rs["bay"]:
                    continue
                if r["entry"] < rs["exit"] and r["exit"] > rs["entry"]:
                    freed.append(b)
                    seen.add(b)
                    if len(freed) >= K:
                        return freed
        return freed
    if kind == "tail":
        cand = sorted((b for b, r in assign.items() if r["entry"] >= maxdue),
                      key=lambda b: assign[b]["entry"])
        return cand[:K]
    if kind == "ontime":
        # Target-window neighborhood: the thin-slack residuals (e.g. a block
        # with rel+proc == due must enter EXACTLY at release) are blocked by
        # residents of their ON-TIME window, not their current window.  Free
        # the tardy block + the blocks (any bay -- cross-bay candidates make
        # that useful) overlapping [release, min(current exit, due)).
        t_b = tardy[rng.randrange(min(3, len(tardy)))][1]
        blk = blocks[t_b]
        lo = blk["release_time"]
        hi = min(assign[t_b]["exit"], blk["due_date"])
        if hi <= lo:
            hi = lo + blk["processing_time"]
        freed = [t_b]
        near = sorted((abs(r["entry"] - lo), b) for b, r in assign.items()
                      if b != t_b and r["entry"] < hi and r["exit"] > lo)
        freed += [b for _, b in near[:K - 1]]
        return freed
    # time-band: window around a random tardy block's entry
    anchor = tardy[rng.randrange(len(tardy))][1] if tardy else \
        rng.choice(list(assign))
    t0 = assign[anchor]["entry"]
    procs = sorted(blocks[b]["processing_time"] for b in assign)
    delta = 2 * procs[len(procs) // 2]
    cand = [b for b, r in assign.items()
            if t0 - delta // 2 <= r["entry"] <= t0 + delta]
    cand.sort(key=lambda b: -(assign[b]["exit"] - blocks[b]["due_date"]))
    return cand[:K]


# ---------------------------------------------------------------------------
# CP-SAT subproblem
# ---------------------------------------------------------------------------

def _pair_flags(bay_obj, blk_i, blk_j):
    """Exact pairwise coexistence semantics per utils (all pairwise):
    E_ij: i may ENTER while j present; X_ij: i may EXIT while j present."""
    E_ij = not utils.check_entry(bay_obj, [blk_j], blk_i, fast=True)
    X_ij = not utils.check_exit(bay_obj, [blk_j], blk_i, fast=True)
    E_ji = not utils.check_entry(bay_obj, [blk_i], blk_j, fast=True)
    X_ji = not utils.check_exit(bay_obj, [blk_i], blk_j, fast=True)
    return E_ij, X_ij, E_ji, X_ji


def _cand_positions(blk_data, oi, bay_obj, residents, C):
    """Candidate reference positions for a freed block: contact-driven
    bottom-left points derived from resident rects (same generator family as
    the greedy), capped at C-1 (the incumbent is appended by the caller --
    the model must always CONTAIN the incumbent, per the M2-alpha lesson)."""
    import math as _m
    xs_l, ys_l = [], []
    for layer in blk_data["shape"][oi]["layers"]:
        for (px, py) in layer:
            xs_l.append(px)
            ys_l.append(py)
    lx0, ly0, lx1, ly1 = min(xs_l), min(ys_l), max(xs_l), max(ys_l)
    xs = {max(0, _m.ceil(-lx0))}
    ys = {max(0, _m.ceil(-ly0))}
    for b in residents:
        rb = b.bounding_rect()
        xs.add(_m.ceil(rb[2] - lx0))
        ys.add(_m.ceil(rb[3] - ly0))
    out = []
    for x in xs:
        for y in ys:
            if x + lx1 <= bay_obj.width + 1e-6 and y + ly1 <= bay_obj.height + 1e-6:
                out.append((int(x), int(y)))
    out.sort(key=lambda p: (p[0] + p[1], p[1], p[0]))
    return out[:max(0, C - 1)]


def _solve_sub(prob_info, assign, freed, time_cap, horizon, C=3):
    C = int(os.environ.get("OGC_FNO_C", "0")) or C
    """M2-beta: jointly re-optimize POSITION (one-hot over pre-verified
    candidates) and ENTRY time of the freed blocks; bay/orientation fixed.

    Soundness: the incumbent (position, entry) of every freed block is always
    among its candidates, and pairwise semantics are utils' own checks with
    the order-conditional encoding -- the model CONTAINS the incumbent and
    every model solution obeys the true checker's pairwise stages.  The full
    check_feasibility still gates every commit upstream.

    Returns {bid: (x, y, entry, exit)} or None."""
    blocks = prob_info["blocks"]
    bays_data = prob_info["bays"]
    m = cp_model.CpModel()

    Bay = utils.Bay
    Block = utils.Block
    bay_objs = {}
    blk_cache = {}

    def _bay(bid_bay):
        if bid_bay not in bay_objs:
            bay_objs[bid_bay] = Bay.from_dict(bays_data[bid_bay], bid_bay)
        return bay_objs[bid_bay]

    def _blk_at(bid, x, y):
        key = (bid, x, y)
        if key not in blk_cache:
            blk_cache[key] = Block(block_id=bid, block_data=blocks[bid],
                                   x=x, y=y, orient_idx=assign[bid]["oi"])
        return blk_cache[key]

    freed_set = set(freed)
    fl = list(freed)

    # Candidate (bay, x, y) triples per freed block: incumbent first (model
    # must contain the incumbent), then contact positions in the OWN bay,
    # then 1-2 contact positions in every OTHER bay whose bounds fit the
    # orientation -- the cross-bay dimension M2-alpha identified as the
    # missing slack (and the only route for e.g. prob_1's blocked pref
    # blocks).  Preference cost of a bay change is priced exactly in the
    # objective below, so cross-bay moves that trade Z3 for Z1 are chosen
    # only when the true weights favor them.
    # v21: raster-NFP candidate enumeration (deep pockets) when available;
    # contact corners as fallback.  Raster feasibility is judged against the
    # residents of the freed block's RELEVANT window [release, current exit]
    # (timing is decided exactly by the model's pairwise flags); with the
    # richer generator C grows (OGC_FNO_C, default 6 vs contact's 3) --
    # flag cost is O(K^2*C^2) same-bay, parallelized across M2-gamma workers.
    # DEFAULT OFF -- falsified as F&O default (2026-07-24 A/B: prob_38 loses
    # x2 reps 146.1M/134.6M vs 131.4M/131.7M, prob_39 wash; 2-6x more accepts
    # but worse finals: myopic small accepts lock the trajectory and C=6 flag
    # cost O(K^2*C^2) shallows each solve).  Kept as opt-in capability; the
    # raster machinery itself validated (12/12 exact-check precision).
    use_nfp = _nfp_mod is not None and os.environ.get("OGC_NFP_CAND", "0") == "1"
    if use_nfp:
        C = max(C, 6)
    n_bays = len(bays_data)
    cands = {}
    for b in fl:
        r = assign[b]
        lst = [(r["bay"], r["x"], r["y"])]
        seen = {(r["bay"], r["x"], r["y"])}
        w_lo = int(blocks[b]["release_time"])
        w_hi = max(int(r["exit"]), w_lo + int(blocks[b]["processing_time"]))
        for bay_id in range(n_bays):
            per = (C - 1) if bay_id == r["bay"] else max(1, (C - 1) // 2)
            extra = None
            if use_nfp:
                res_win = [(o, blocks[o], ro["oi"], ro["x"], ro["y"])
                           for o, ro in assign.items()
                           if o != b and ro["bay"] == bay_id
                           and ro["entry"] < w_hi and ro["exit"] > w_lo]
                extra = _nfp_mod.positions(
                    bays_data[bay_id]["width"], bays_data[bay_id]["height"],
                    res_win, b, blocks[b], r["oi"], per + 1)
            if extra is None:
                residents = [_blk_at(o, ro["x"], ro["y"])
                             for o, ro in assign.items()
                             if o != b and ro["bay"] == bay_id]
                extra = _cand_positions(blocks[b], r["oi"], _bay(bay_id),
                                        residents, per + 1)
            for p in extra:
                key = (bay_id, p[0], p[1])
                if key not in seen:
                    lst.append(key)
                    seen.add(key)
        cands[b] = lst

    w1 = int(round(prob_info.get("weights", {}).get("w1", 1.0)))
    w3 = int(round(prob_info.get("weights", {}).get("w3", 0.0)))

    fv = {}
    pref_terms = []
    for b in fl:
        r = assign[b]
        blk = blocks[b]
        e = m.NewIntVar(int(blk["release_time"]), horizon, f"e{b}")
        proc = int(blk["processing_time"])
        tard = m.NewIntVar(0, horizon + proc, f"t{b}")
        m.Add(tard >= e + proc - int(blk["due_date"]))
        pos_lits = [m.NewBoolVar(f"p{b}_{a}") for a in range(len(cands[b]))]
        m.AddExactlyOne(pos_lits)
        prefs = blk.get("bay_preferences", [0] * len(bays_data))
        s_max = max(prefs)
        for a, (bay_id, _x, _y) in enumerate(cands[b]):
            pen = w3 * (s_max - prefs[bay_id])
            if pen:
                pref_terms.append(pen * pos_lits[a])
        fv[b] = {"e": e, "proc": proc, "tard": tard, "pos": pos_lits}
        m.AddHint(e, r["entry"])
        m.AddHint(pos_lits[0], 1)  # incumbent

    def _excl(v, lo_v, hi_v, strict_lo, gate):
        """Under `gate` (list of lits), forbid lo (<|<=) v < hi."""
        left = m.NewBoolVar("")
        right = m.NewBoolVar("")
        if strict_lo:
            m.Add(v <= lo_v).OnlyEnforceIf(left)
        else:
            m.Add(v <= lo_v - 1).OnlyEnforceIf(left)
        m.Add(v >= hi_v).OnlyEnforceIf(right)
        m.AddBoolOr([left, right] + [g.Not() for g in gate])

    def _pair_constraints(flags, i_e, i_x, j_e, j_x, gate):
        E_ij, X_ij, E_ji, X_ji = flags
        if not E_ij:
            _excl(i_e, j_e, j_x, False, gate)
        if not X_ij:
            _excl(i_x, j_e, j_x, True, gate)
        if not E_ji:
            _excl(j_e, i_e, i_x, False, gate)
        if not X_ji:
            _excl(j_x, i_e, i_x, True, gate)

    # freed-freed: constrain only SAME-BAY candidate combos (different bays
    # never interact), gated on both selection lits
    for ii in range(len(fl)):
        for jj in range(ii + 1, len(fl)):
            bi, bj = fl[ii], fl[jj]
            i_x = fv[bi]["e"] + fv[bi]["proc"]
            j_x = fv[bj]["e"] + fv[bj]["proc"]
            for a, (ba, xa, ya) in enumerate(cands[bi]):
                for c, (bc, xc, yc) in enumerate(cands[bj]):
                    if ba != bc:
                        continue
                    flags = _pair_flags(_bay(ba), _blk_at(bi, xa, ya),
                                        _blk_at(bj, xc, yc))
                    _pair_constraints(flags, fv[bi]["e"], i_x, fv[bj]["e"], j_x,
                                      [fv[bi]["pos"][a], fv[bj]["pos"][c]])

    # freed-fixed: per freed candidate, vs fixed blocks in THAT candidate's bay
    for bi in fl:
        i_x = fv[bi]["e"] + fv[bi]["proc"]
        for a, (ba, xa, ya) in enumerate(cands[bi]):
            bay_o = _bay(ba)
            cand_blk = _blk_at(bi, xa, ya)
            for o, ro in assign.items():
                if o in freed_set or ro["bay"] != ba:
                    continue
                flags = _pair_flags(bay_o, cand_blk, _blk_at(o, ro["x"], ro["y"]))
                _pair_constraints(flags, fv[bi]["e"], i_x,
                                  int(ro["entry"]), int(ro["exit"]),
                                  [fv[bi]["pos"][a]])

    m.Minimize(sum(v["tard"] for v in fv.values()) * max(1, w1)
               + sum(pref_terms)
               + sum(v["e"] for v in fv.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.5, time_cap)
    solver.parameters.num_search_workers = 1
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    out = {}
    for b in fl:
        a_sel = next(a for a, lit in enumerate(fv[b]["pos"])
                     if solver.Value(lit))
        bay_id, x, y = cands[b][a_sel]
        e_val = solver.Value(fv[b]["e"])
        out[b] = (bay_id, x, y, e_val, e_val + fv[b]["proc"])
    return out


# ---------------------------------------------------------------------------
# M2-gamma: parallel round machinery
# ---------------------------------------------------------------------------

_PAR_PROB = None  # set in the parent right before Pool creation; fork-inherited


def _par_solve(args):
    """Worker entry: solve one neighborhood against a snapshot assign.
    Runs in a fork child; prob_info comes from the inherited module global
    (never pickled -- shapes are large)."""
    assign, freed, cap, horizon = args
    try:
        return _solve_sub(_PAR_PROB, assign, freed, cap, horizon)
    except Exception:  # noqa: BLE001 -- a worker must never poison the pool
        return None


def _n_workers():
    import os
    try:
        w = int(os.environ.get("OGC_FNO_WORKERS", "0"))
    except ValueError:
        w = 0
    if w <= 0:
        try:
            cores = len(os.sched_getaffinity(0))
        except Exception:  # noqa: BLE001
            import multiprocessing as _mp
            cores = _mp.cpu_count() or 1
        w = min(4, max(1, cores))
    return w


def _improve_parallel(prob_info, pool, W, assign, blocks, best_obj,
                      t_end, est_check_cost, rng, maxdue, horizon):
    """Parallel anytime loop.  Returns (assign, best_obj, improved_any)."""
    kinds = ["tardy", "band", "tail", "ontime"]
    weights = {k: 1.0 for k in kinds}
    K = int(os.environ.get("OGC_FNO_K", "0")) or 15
    improved_any = False
    rounds = 0
    import os as _os
    dbg = _os.environ.get("OGC_FNO_DBG") == "1"

    while time.monotonic() < t_end - max(1.0, 2 * est_check_cost):
        rounds += 1
        if rounds > 400:
            break
        # -- pick up to W neighborhoods with disjoint freed sets ------------
        used = set()
        tasks = []
        attempts = 0
        while len(tasks) < W and attempts < 3 * W:
            attempts += 1
            total_w = sum(weights.values())
            pick = rng.random() * total_w
            kind = kinds[-1]
            acc = 0.0
            for k in kinds:
                acc += weights[k]
                if pick <= acc:
                    kind = k
                    break
            freed_raw = _select(kind, assign, blocks, rng, K, maxdue)
            if len(freed_raw) < 2:
                # genuine selection failure -- same penalty as sequential
                weights[kind] = max(0.1, weights[kind] * 0.8)
                continue
            freed = [b for b in freed_raw if b not in used]
            if len(freed) < 2:
                # lost to the disjointness filter, NOT a bad kind: no penalty.
                # (Measured on prob_39: penalizing filter losses decayed the
                # dominant 'tardy' kind at 2x rate and drove selection to
                # junk kinds -- par lost to seq by 14% x2 reps.)
                continue
            used.update(freed)
            tasks.append((kind, freed))
        if not tasks:
            continue
        # reserve verification time for up to W results this round (weakness
        # found in review: W checks after collection could overshoot t_end)
        cap = min(float(os.environ.get("OGC_FNO_CAP", "6")),
                  max(1.0, (t_end - time.monotonic())
                      - (2 + len(tasks)) * est_check_cost))
        asyncs = [pool.apply_async(_par_solve, ((assign, freed, cap, horizon),))
                  for _, freed in tasks]
        # -- collect with bounded wait, verify+commit sequentially ----------
        # Weight learning uses task 0 ONLY: task 0 is unfiltered (identical to
        # the sequential pick), so the roulette sees the same signal as the
        # sequential loop; filtered bonus tasks must not distort it.
        for ti, ((kind, freed), ar) in enumerate(zip(tasks, asyncs)):
            wait = min(cap + 5.0, max(0.5, t_end - time.monotonic() + 1.0))
            try:
                res = ar.get(timeout=wait)
            except Exception:  # noqa: BLE001 -- timeout or worker death
                res = None
            if res is None:
                if dbg:
                    print(f"[fno-dbg] r{rounds} {kind} K={len(freed)} -> none")
                if ti == 0:
                    weights[kind] = max(0.1, weights[kind] * 0.9)
                continue
            cand_assign = {b: dict(r) for b, r in assign.items()}
            for b, (bay_id, x, y, e, ex) in res.items():
                cand_assign[b].update(bay=bay_id, x=x, y=y, entry=e, exit=ex)
            cand_sol = _build(cand_assign)
            chk = utils.check_feasibility(prob_info, cand_sol)
            if chk.get("feasible") and chk["objective"] < best_obj - 1e-9:
                gain = best_obj - chk["objective"]
                best_obj = chk["objective"]
                assign = cand_assign
                improved_any = True
                if ti == 0:
                    weights[kind] = min(10.0, weights[kind] * 1.5)
                print(f"[fno-par] round {rounds} {kind}(K={len(freed)}): "
                      f"-{gain:.0f} -> {best_obj:.0f}")
            else:
                if dbg and not chk.get("feasible"):
                    print(f"[fno-rej] stage={chk.get('stage')} "
                          f"viol={str(chk.get('violations', ['?'])[:1])[:140]}")
                if ti == 0:
                    weights[kind] = max(0.1, weights[kind] * 0.9)
    return assign, best_obj, improved_any


# ---------------------------------------------------------------------------
# Anytime improve loop
# ---------------------------------------------------------------------------

def improve(prob_info, sol, time_budget, est_check_cost=0.3, rng_seed=0xF60):
    """Fix-and-optimize `sol` within `time_budget` seconds.

    Returns an improved solution dict, or None if no accepted improvement.
    Every accepted candidate has passed utils.check_feasibility; on any
    internal error the incumbent (or None) is returned -- never raises.
    """
    if not _HAS_ORTOOLS or utils is None:
        return None
    import random
    rng = random.Random(rng_seed)
    t_end = time.monotonic() + time_budget

    try:
        base = utils.check_feasibility(prob_info, sol)
        if not base.get("feasible"):
            return None
        best_obj = base["objective"]
        assign = _parse(sol)
        blocks = prob_info["blocks"]
        maxdue = max(b["due_date"] for b in blocks)
        horizon = max(r["exit"] for r in assign.values()) + 3 * maxdue

        # -- M2-gamma: parallel rounds when >1 core is available ------------
        W = _n_workers()
        import multiprocessing as _mp
        pool = None
        if W > 1 and _mp.current_process().name == "MainProcess":
            try:
                global _PAR_PROB
                _PAR_PROB = prob_info
                pool = _mp.get_context("fork").Pool(W)
            except Exception:  # noqa: BLE001 -- no fork / pool failure -> sequential
                pool = None
        if pool is not None:
            try:
                print(f"[fno] parallel rounds: W={W}")
                assign, best_obj, improved_any = _improve_parallel(
                    prob_info, pool, W, assign, blocks, best_obj,
                    t_end, est_check_cost, rng, maxdue, horizon)
            finally:
                pool.terminate()
                pool.join()
            if improved_any:
                return _build(assign)
            return None

        kinds = ["tardy", "band", "tail", "ontime"]
        weights = {k: 1.0 for k in kinds}
        K = int(os.environ.get("OGC_FNO_K", "0")) or 15
        improved_any = False
        rounds = 0

        while time.monotonic() < t_end - max(1.0, 2 * est_check_cost):
            rounds += 1
            if rounds > 400:
                break
            total_w = sum(weights.values())
            pick = rng.random() * total_w
            kind = kinds[-1]
            acc = 0.0
            for k in kinds:
                acc += weights[k]
                if pick <= acc:
                    kind = k
                    break
            freed = _select(kind, assign, blocks, rng, K, maxdue)
            if len(freed) < 2:
                weights[kind] = max(0.1, weights[kind] * 0.8)
                continue
            cap = min(float(os.environ.get("OGC_FNO_CAP", "6")),
                      max(1.0, t_end - time.monotonic() - 2 * est_check_cost))
            _inc_tard = sum(max(0, assign[b]["exit"] - blocks[b]["due_date"]) for b in freed)
            res = _solve_sub(prob_info, assign, freed, cap, horizon)
            if res is None:
                import os as _os
                if _os.environ.get("OGC_FNO_DBG") == "1":
                    print(f"[fno-dbg] r{rounds} {kind} K={len(freed)} inc_tard={_inc_tard} -> INFEAS/TIMEOUT")
                weights[kind] = max(0.1, weights[kind] * 0.9)
                continue
            import os as _os
            if _os.environ.get("OGC_FNO_DBG") == "1":
                _new_tard = sum(max(0, res[b][4] - blocks[b]["due_date"]) for b in res)
                print(f"[fno-dbg] r{rounds} {kind} K={len(freed)} tard {_inc_tard} -> {_new_tard}")
            cand_assign = {b: dict(r) for b, r in assign.items()}
            for b, (bay_id, x, y, e, ex) in res.items():
                cand_assign[b].update(bay=bay_id, x=x, y=y, entry=e, exit=ex)
            cand_sol = _build(cand_assign)
            chk = utils.check_feasibility(prob_info, cand_sol)
            import os as _os2
            if _os2.environ.get("OGC_FNO_DBG") == "1" and not chk.get("feasible"):
                print(f"[fno-rej] stage={chk.get('stage')} viol={str(chk.get('violations', ['?'])[:1])[:140]}")
            if chk.get("feasible") and chk["objective"] < best_obj - 1e-9:
                gain = best_obj - chk["objective"]
                best_obj = chk["objective"]
                assign = cand_assign
                improved_any = True
                weights[kind] = min(10.0, weights[kind] * 1.5)
                print(f"[fno] round {rounds} {kind}(K={len(freed)}): "
                      f"-{gain:.0f} -> {best_obj:.0f}")
            else:
                weights[kind] = max(0.1, weights[kind] * 0.9)
        if improved_any:
            return _build(assign)
        return None
    except Exception as exc:  # noqa: BLE001 -- engine must never break the pipeline
        print(f"[fno] aborted: {type(exc).__name__}: {exc}")
        return None
