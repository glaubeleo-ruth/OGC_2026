"""
baseline_greedy.py -- EDD + Best-Fit Greedy Algorithm with Post-Hoc Repair

===============================================================================
ALGORITHM OVERVIEW
===============================================================================

Phase 1 -- Aggressive greedy placement (EDD order):
  Blocks are sorted by due-date BUCKETS (R1: width = eff_ord_delta, default
  ord_delta_mult x median proc), area-DESCENDING within each bucket; strict
  EDD when ord_delta_mult=0.  For each block, every (bay, orientation,
  position, time-slot)
  combination is scored; the cheapest is committed.  Crane-path feasibility
  (check_entry / check_exit) is verified against the current bay state, so
  most Phase-1 placements are already crane-feasible.

  Tardiness-focused refinements (2026-07-21):
    * Earliness incentive: _placement_score includes a small w5 * entry term
      so that, among placements with equal tardiness (typically all non-tardy
      options), the earliest entry slot always wins.  Previously the choice
      fell to the w4 * top_y packing tie-break, which could pick a needlessly
      late slot and steal time-window capacity from every subsequent block.
    * Exit-aligned entry candidates: _find_earliest_slot additionally tries
      entry times e_k - proc and a_k - proc (aligning this block's exit with
      another block's departure or arrival).  These cover Stage-3 exit
      obstructions that the exit-boundary candidates alone cannot fix without
      paying up to `proc` extra delay per conflict.

Phase 2 -- Iterative repair:
  check_feasibility is called on the Phase-1 solution.  Violating blocks are
  re-placed in EDD order.  Two modes are supported (repair_mode parameter):

  * "greedy" (default)
      Violating blocks are removed from the current solution and re-placed
      using the same full Phase-1 search (best bay + position + time-slot).
      State (bay_placed / bay_schedule / bay_loads) is reconstructed from
      the non-violating assignments before each pass.
      Cycle detection: if a block reappears in a second repair pass it is
      added to forced_ids, which bypasses search and uses _force_place
      (empty-bay window at (0,0)) to guarantee termination.
      Time guard: blocks whose turn comes after 90% of timelimit are also
      sent to _force_place to ensure all blocks are assigned before timeout.

  * "simple"
      Each violating block keeps its current (bay, x, y, orient) and is only
      pushed to the next empty-bay window (bay completely empty for the full
      processing duration).  Stage-4 (spatial collision) violations are also
      reset to position (0,0).

Phase 3 -- Local-search improvement (only runs if Phase 2 reached a feasible
  solution and time remains):
  Repeatedly removes one block at a time from the current solution and
  reinserts it via the same search used in Phase 1 (_place_blocks with a
  prev_assignments fast-path), keeping whichever placement -- old or new --
  scores lower under _placement_score.  Because the block's own previous
  (bay, x, y, orient) is always re-tested through _find_earliest_slot as part
  of the same search, a move is only taken when it is provably feasible and
  strictly improves the composite score, so the loop is a monotone hill-climb
  on the weighted objective (w1*obj1 + w2*obj2 + w3*obj3).  A full
  check_feasibility pass validates the result before it replaces the Phase-2
  solution; if anything looks wrong the Phase-2 solution is kept.

===============================================================================
SOLUTION DICT FORMAT
===============================================================================

{
    "operations": {
        "<time_int>": [           # integer time-point as string key
            {
                "type":       "EXIT",   # crane removes block from bay
                "block_id":   int,
                "bay_id":     int,
            },
            {
                "type":       "ENTRY",  # crane places block into bay
                "block_id":   int,
                "bay_id":     int,
                "x":          int,      # bottom-left x the reference point within the bay
                "y":          int,      # bottom-left y the reference point within the bay
                "orient_idx": int,      # index into block["shape"] list
            },
            ...
        ],
        ...
    }
}

At each time-point, EXIT operations always precede ENTRY operations.
Within the same type, operations are ordered so that each is feasible given
the bay state after all preceding operations at that time have completed.
entry_time = int(t_str) for ENTRY ops; exit_time = int(t_str) for EXIT ops.

Feasibility checking and objective computation: utils.check_feasibility(prob_info, solution).
"""

import math
import time
from utils import Bay, Block, check_entry, check_exit, check_collisions, _resolve_layers, _bounding_box, _bb_overlap

# -----------------------------------------------------------------------------
# Search-breadth knobs.  Since the per-block wall-clock budget (see
# _place_blocks) became the binding constraint, these caps no longer exist to
# prevent time-guard forced placements (the pre-v4 rationale); they allocate
# the fixed budget between BREADTH (how many positions get probed) and DEPTH
# (how many entry times each position gets).  Both extremes fail, measured on
# a 2-rep sweep over prob_20/25/39 at 24s:
#   * too tight ((15,60) or the old (40,150)): the search starves -- the old
#     values left 13-26% obj1 on the table vs (100,500);
#   * uncapped: on saturated instances each position burns the whole budget
#     walking infeasible early entry candidates, breadth collapses, and
#     prob_39 obj1 nearly doubles.
# (100, 500) was the best tested interior point (see baseline/EXPERIMENT_LOG.md).
# -----------------------------------------------------------------------------
_MAX_ENTRY_CANDIDATES = 100  # earliest entry-time candidates tried per (bay, position)
_MAX_POSITIONS        = 500  # bottom-left candidate positions tried per (bay, orientation)

# -- Rule knobs (R-spec 2026-07-22).  Env-overridable for A/B; every default
#    reproduces the previous (v7.2) behavior bit-for-bit. -------------------
import os as _os
# Defaults reflect the A/B-tested rule set (2026-07-22, 2 reps each, within-
# batch baselines; see baseline/EXPERIMENT_LOG.md "Rule batch" section):
#   R5a GUARD 0.92     : accepted -- neutral-to-positive, and separates the
#                        guard from the 0.82 per-block budget fraction.
#   R1  ORD_DELTA 2    : accepted -- due-buckets of width 2, area-descending
#                        inside a bucket; prob_20 obj1 ~283 -> ~149.
#   R6  DEFER_MULT 2   : accepted -- defer blocks whose best slot is tardier
#                        than 2x median proc to a due-ordered post-pass;
#                        prob_39 obj1 ~11.7k -> ~8.6k (the v8-family goal,
#                        achieved cascade-safely).
#   R3  R0K 3          : accepted -- score 3 r_time hits per (bay, orient);
#                        prob_39 -> ~8.0k, neutral elsewhere.
#   R4  (perfect-exit gate) rejected: prob_25 "win" was noise, prob_39 loss
#                        was real.  Kept as an off-by-default switch.
#   R2  W6F (bay pressure) rejected: gains on prob_25/39 but unstable on
#                        prob_20 (per-candidate cost eats the budget).
_R4_GATE    = _os.environ.get("OGC_R4", "0") == "1"
_GUARD      = float(_os.environ.get("OGC_GUARD", "0.92"))
_ORD_DELTA  = int(_os.environ.get("OGC_ORD_DELTA", "2"))
_DEFER_MULT = float(_os.environ.get("OGC_DEFER_MULT", "2"))
_R0K        = int(_os.environ.get("OGC_R0K", "3"))
_W6F        = float(_os.environ.get("OGC_W6F", "0"))
_FP_REGION  = _os.environ.get("OGC_FP_REGION", "1") == "1"   # region-clear force-place (attempt 1.5)
_TAILW      = _os.environ.get("OGC_TAILW", "1") == "1"       # T1: wave repack of deferred blocks
_TAILW_POS  = int(_os.environ.get("OGC_TAILW_POS", "16"))    # positions probed per (block,bay,orient)
_TAILW_CAP  = int(_os.environ.get("OGC_TAILW_CAP", "80"))   # slot-checks per (block,event)
_TAILW_ORD  = _os.environ.get("OGC_TAILW_ORD", "desc")       # within-event order: proc desc|asc
_TAILW_RATIO = float(_os.environ.get("OGC_TAILW_RATIO", "0.70"))  # activate T1 only when overloaded
_TAILW_MIN   = int(_os.environ.get("OGC_TAILW_MIN", "8"))    # min deferred set size for waves (smaller -> serial)
_TAILW_MAIN  = float(_os.environ.get("OGC_TAILW_MAIN", "0.55"))  # hard main-pass window when ratio>=1.0
_TAILW_EVB   = int(_os.environ.get("OGC_TAILW_EVBUDGET", "8000"))  # slot-check budget per wave event
_R9W         = float(_os.environ.get("OGC_R9", "2"))         # pressure-aware bay choice weight (time units)
_BT_CAP      = float(_os.environ.get("OGC_BT_CAP", "0.8"))   # per-block budget ceiling (V16 dynamic budget)
_NFP_SLIDE   = int(_os.environ.get("OGC_NFP", "0"))          # polygon-slide compaction max steps (0 = off)
_NFP_EFF     = 0   # per-instance effective value (strategy-overridable)
_DEF_RESTORE = _os.environ.get("OGC_DEF_RESTORE", "0") == "1"  # v21f: defer held-slot restore
# ^ DEFAULT OFF -- falsified 2026-07-24.  Round 1 (hint bypasses force-place):
#   prob_39 2-3x WORSE x2 (stale hints are feasible-but-late; v21c's widened
#   force-place finds earlier region-clears; blind adoption chains deferred
#   blocks into mutually-blocking old spots).  Round 2 (hint competes via
#   min-entry): wash-to-slightly-negative x2 -> not shipped.  System-level
#   lesson: held slots of deferred blocks are MUTUALLY INCOMPATIBLE (all found
#   on the same pre-defer state; restoring one invalidates the others), and
#   R6's aggregate win already prices in individual sacrifices like block 6.
_NFP_FULL    = int(_os.environ.get("OGC_NFPF", "0"))         # raster-NFP candidate augmentation count (0 = off)
_NFP_FULL_EFF = 0  # per-instance effective value (strategy-overridable)
_NFPF_BUDGET = 0.0  # per-run wall budget for raster calls (s)
_NFPF_SPENT  = 0.0
_TAILW_RATIO_SEEN = 0.0  # set per-instance by greedyalgorithm (drives budget scaling)
# Set per-instance by greedyalgorithm: T1 active only when the instance's
# area-time demand ratio (sum(area_i*proc_i) / (total_bay_area * max_due))
# says the yard is overloaded enough that heavy deferral is inevitable.
# Below the threshold the pipeline is bit-identical to the pre-T1 code
# (full 0.82 main-pass budget, serial post-pass): measured on the train
# set the ratio splits cleanly (winners 0.79-0.91, losers 0.36-0.52).
_TAILW_ACTIVE = False


# -----------------------------------------------------------------------------
# Helpers: block bounding box (anchored, per orientation)
# -----------------------------------------------------------------------------

def _block_bbox(block_data: dict, orient_idx: int) -> tuple[float, float, float, float]:
    """Bounding box of a block in local coordinates relative to the reference
    point (first vertex of first layer = (0, 0)).  Returns (min_x, min_y, max_x, max_y)."""
    raw_layers = block_data["shape"][orient_idx]["layers"]
    layers = _resolve_layers(raw_layers)
    if not layers:
        return (0.0, 0.0, 1.0, 1.0)
    all_verts = [v for l in layers for v in l]
    return _bounding_box(all_verts)


def _orient_key(block_data: dict, orient_idx: int) -> tuple:
    """
    Canonical geometry key for an orientation: all layers anchored by the union
    bounding-box min corner, each layer reduced to a frozenset of rounded
    vertices.  Two orientations with identical keys have identical footprints
    at every layer (e.g. the 180-degree rotation of a rectangle, or all four
    rotations of a square), so searching one representative is enough.  With
    ~8 orientations per block on the OGC train instances this typically
    halves or quarters the orientation loop.
    """
    raw_layers = _resolve_layers(block_data["shape"][orient_idx]["layers"])
    all_verts = [v for l in raw_layers for v in l]
    if not all_verts:
        return (orient_idx,)
    mx = min(v[0] for v in all_verts)
    my = min(v[1] for v in all_verts)
    return tuple(frozenset((round(x - mx, 6), round(y - my, 6)) for x, y in l)
                 for l in raw_layers)


# -----------------------------------------------------------------------------
# Helper: time interval overlap check
# -----------------------------------------------------------------------------

def _time_overlaps(a_entry: int, a_exit: int,
                   b_entry: int, b_exit: int) -> bool:
    """True if intervals [a_entry, a_exit) and [b_entry, b_exit) overlap."""
    return a_entry < b_exit and b_entry < a_exit


# -----------------------------------------------------------------------------
# Helper: candidate position generation (bottom-left corner based)
# -----------------------------------------------------------------------------

def _candidate_positions(bay_w: float, bay_h: float,
                         placed_blocks: list[Block],
                         blk_bb: tuple[float, float, float, float]) -> list[tuple[int, int]]:
    """
    Return integer (x, y) reference-point candidate positions for a new block
    using the "bottom-left fill" heuristic.

    blk_bb = (local_min_x, local_min_y, local_max_x, local_max_y) in local
    coordinates (reference point = first vertex of first layer = (0, 0)).
    A placement (x, y) is valid iff the block's world bbox stays within the bay:
      x + blk_bb[0] >= 0,  y + blk_bb[1] >= 0
      x + blk_bb[2] <= bay_w,  y + blk_bb[3] <= bay_h
    Candidates are sorted by (x, y) so the search visits left-most / bottom-most
    positions first.
    """
    lx0, ly0, lx1, ly1 = blk_bb
    # Smallest valid integer reference-point position (block's left/bottom edge at bay wall)
    xs = {max(0, math.ceil(-lx0))}
    ys = {max(0, math.ceil(-ly0))}
    for b in placed_blocks:
        bb = b.bounding_rect()
        # Reference-point x/y such that new block's left/bottom edge touches the
        # right/top edge of this placed block
        xs.add(math.ceil(bb[2] - lx0))
        ys.add(math.ceil(bb[3] - ly0))

    candidates = []
    for x in xs:
        for y in ys:
            if x + lx1 <= bay_w + 1e-6 and y + ly1 <= bay_h + 1e-6:
                candidates.append((int(x), int(y)))

    # Gravity sort: Manhattan distance to the bay's bottom-left corner, so the
    # search (and the _MAX_POSITIONS cap) favours tightly-packed positions in
    # both axes instead of pure column-major order.
    candidates.sort(key=lambda pos: (pos[0] + pos[1], pos[1], pos[0]))
    return candidates


def _nfpf_augment(candidates, bay, active_in_bay, blk_data, oi, bi):
    """v21 (strategy 'nfp_full'): augment corner candidates with raster-NFP
    deep-pocket positions the bottom-left cross-product cannot propose.
    Wall-time bounded per run (_NFPF_BUDGET); needs >=2 residents (no pockets
    otherwise); any failure returns `candidates` unchanged."""
    global _NFPF_SPENT
    if (_NFP_FULL_EFF <= 0 or len(active_in_bay) < 2
            or _NFPF_SPENT >= _NFPF_BUDGET):
        return candidates
    t0 = time.time()
    try:
        from alns import nfp as _nfp
        res = [(b.block_id, b.block_data, b.orient_idx, int(b.x), int(b.y))
               for b in active_in_bay]
        pts = _nfp.positions(int(bay.width), int(bay.height), res,
                             bi, blk_data, oi, _NFP_FULL_EFF)
        if pts:
            seen = set(candidates)
            merged = list(candidates)
            for p in pts:
                if p not in seen:
                    merged.append(p)
                    seen.add(p)
            merged.sort(key=lambda pos: (pos[0] + pos[1], pos[1], pos[0]))
            candidates = merged
    except Exception:  # noqa: BLE001 -- augmentation must never break placement
        pass
    finally:
        _NFPF_SPENT += time.time() - t0
    return candidates


# -----------------------------------------------------------------------------
# Placement score (lower is better)
# -----------------------------------------------------------------------------

def _placement_score(tardiness: float, workload: float,
                     bay_loads: list[float], bay_id: int,
                     pref_penalty: float,
                     bay_weights: list[float],
                     w1: float, w2: float, w3: float,
                     top_y: float = 0.0, w4: float = 1e-4,
                     entry: float = 0.0, w5: float = 1e-3) -> float:
    """
    Composite score for placing a block in bay_id (lower is better).

      w1 * tardiness    -- total tardiness: max(0, exit_time - due_date).

      w2 * new_obj2     -- approximation of normalized load-balance penalty.
                          new_obj2 = max_j |u[bay_id]*new_load - u[j]*load_j|
                          where u_j = avg_bay_area / (W_j * H_j).

      w3 * pref_penalty -- preference penalty: S_i_max - S_i_bay_id.
                          0 when placed in most-preferred bay.

      w4 * top_y        -- tie-breaking: lower top edge -> tighter packing.

      w5 * entry        -- earliness incentive.  Tardiness is flat at zero for
                          every slot that meets the due date, so without this
                          term the choice among non-tardy slots falls to the
                          w4 packing tie-break and can pick a needlessly LATE
                          slot, occupying the bay later and stealing
                          time-window capacity from every subsequent block in
                          the EDD order.  w5 must stay small relative to w1
                          (never trade real tardiness for earliness) but large
                          enough to dominate the w4 * top_y term.  Set w5=0.0
                          to recover the original behaviour.
    """
    new_load = bay_loads[bay_id] + workload
    new_obj2 = max(
        (abs(bay_weights[bay_id] * new_load - bay_weights[j] * bay_loads[j])
         for j in range(len(bay_loads)) if j != bay_id),
        default=0.0
    )
    return (w1 * tardiness + w2 * new_obj2 + w3 * pref_penalty
            + w4 * top_y + w5 * entry)


# -----------------------------------------------------------------------------
# R2: bay-pressure -- fraction of the bay's space-time occupied by already-
# scheduled blocks during a candidate's own window.  The score's only
# forward-looking term: placements pay for entering contested space-time.
# -----------------------------------------------------------------------------

def _bay_pressure(placed_in_bay, schedule_in_bay, entry, exit_t, bay_area):
    if exit_t <= entry or bay_area <= 0:
        return 0.0
    occ = 0.0
    for b, (a, e) in zip(placed_in_bay, schedule_in_bay):
        lo = a if a > entry else entry
        hi = e if e < exit_t else exit_t
        if hi > lo:
            bb = b.bounding_rect()
            occ += (hi - lo) * (bb[2] - bb[0]) * (bb[3] - bb[1])
    return occ / (bay_area * (exit_t - entry))


# -----------------------------------------------------------------------------
# Earliest feasible entry slot (aggressive -- allows time overlap)
# -----------------------------------------------------------------------------

def _find_earliest_slot(new_blk: Block,
                        bay: Bay,
                        placed_in_bay: list[Block],
                        schedule_in_bay: list[tuple[int, int]],
                        r_time: int,
                        proc: int,
                        candidate_entries: list[int] | None = None) -> tuple[int | None, int | None]:
    """
    Return the earliest (entry, exit_t) time slot >= r_time at which new_blk
    can be crane-placed into bay without violating Stage-2 (entry) or Stage-3
    (exit) feasibility.  Returns (None, None) if no candidate entry passes
    both checks.  NOTE: this means infeasible within the EARLIEST
    _MAX_ENTRY_CANDIDATES (=100) candidate entries >= r_time, NOT provably
    infeasible for all time -- the ascending sort means only very-late slots
    are ever truncated, and callers (defer / _force_place / wave) handle
    those better anyway.

    -- Candidate enumeration ----------------------------------------------------
    Candidates = {r_time}
               | {exit_time e_k of every already-placed block in bay}
               | {e_k - proc for every already-placed block in bay}
               | {a_k - proc for every already-placed block in bay}.

    The e_k candidates cover Stage-2: the present-at-entry set only shrinks at
    exits, so the earliest entry that clears an ENTRY obstruction is at some
    block's departure.  The e_k - proc and a_k - proc candidates cover Stage-3:
    when the *exit* at entry+proc is what is obstructed, the earliest fix is to
    align this block's exit with the obstructing block's departure (e_k) or to
    finish just as it arrives (a_k) -- entry values that are generally NOT exit
    boundaries.  Without them the search skips to entry = e_k and pays up to
    `proc` extra time units of delay per conflict.

    This set depends only on (schedule_in_bay, r_time, proc) -- not on
    new_blk's position/orientation -- so callers that try many candidate
    positions for the same block in the same bay (the full search in
    _place_blocks) should compute it once and pass it in via candidate_entries,
    instead of paying the O(len(schedule_in_bay)) set-build cost again for
    every position.  If omitted it is computed internally.

    -- Feasibility checks (mirror of check_feasibility Stages 2 & 3) -----------
    Stage-2 (crane entry): the crane path must not be blocked at entry_time.
      present_at_entry = blocks b_k with  a_k <= entry < e_k
      check_entry(bay, present_at_entry, new_blk, fast=True) returns True if
      ANY block in present_at_entry obstructs the crane path; fast=True exits
      on the first obstruction to avoid unnecessary Shapely work.

    Stage-3 (crane exit): the crane path must not be blocked at exit_time.
      present_at_exit  = [new_blk] + blocks b_k with  a_k < exit_t < e_k
      (new_blk itself is included because it will be present during its own exit)
      check_exit(bay, present_at_exit, new_blk, fast=True) returns True if
      ANY block in present_at_exit obstructs the crane exit path.

    Stage-4 (interior-interval): blocks whose interval is strictly inside
      [entry, exit_t) -- i.e. entry < a_k AND e_k < exit_t -- are invisible
      to the Stage-2 and Stage-3 boundary checks above.  They are present
      during new_blk's stay but not at its entry or exit moment.  A per-pair
      spatial collision check is run for these blocks to avoid producing
      Stage-4 violations that the repair loop cannot detect at placement time.
    """
    if candidate_entries is None:
        exits   = {e for _, e in schedule_in_bay}
        entries = {a for a, _ in schedule_in_bay}
        candidate_entries = sorted(
            {r_time}
            | {e for e in exits if e > r_time}
            | {e - proc for e in exits if e - proc > r_time}
            | {a - proc for a in entries if a - proc > r_time}
        )[:_MAX_ENTRY_CANDIDATES]

    for entry_candidate in candidate_entries:
        entry  = max(r_time, entry_candidate)
        exit_t = entry + proc

        # Stage-2: blocks already present when new_blk arrives (a_k < entry < e_k),
        # PLUS blocks entering at the exact same moment (a_k == entry).  Stage 5
        # replays same-time ENTRYs in block_id order, so depending on the order
        # either block may already be in the bay when the other descends.  The
        # original strict-bound check (a_k < entry) left this case entirely
        # unchecked -- the root cause of Stage-5 "obstructed (sweep)" repair
        # cascades.  We check BOTH directions (our descent past them, their
        # descent past us) so the placement is safe under any Stage-5 ordering.
        present_at_entry = [
            b for b, (a, e) in zip(placed_in_bay, schedule_in_bay)
            if a < entry < e
        ]
        same_time_entry = [
            b for b, (a, e) in zip(placed_in_bay, schedule_in_bay)
            if a == entry and e > entry
        ]
        if check_entry(bay, present_at_entry + same_time_entry, new_blk, fast=True):
            continue  # crane path blocked at entry -> try next candidate
        _rev_blocked = False
        for b_other in same_time_entry:
            if check_entry(bay, [new_blk], b_other, fast=True):
                _rev_blocked = True
                break
        if _rev_blocked:
            continue  # our block would obstruct a same-time entry -> next candidate

        # Stage-3: blocks still present when new_blk departs (a_k < exit_t < e_k),
        # PLUS blocks exiting at the exact same moment (e_k == exit_t) -- same
        # Stage-5 ordering argument as above, in both directions.
        present_at_exit = [new_blk] + [
            b for b, (a, e) in zip(placed_in_bay, schedule_in_bay)
            if a < exit_t < e
        ]
        same_time_exit = [
            b for b, (a, e) in zip(placed_in_bay, schedule_in_bay)
            if e == exit_t and a < exit_t
        ]
        if check_exit(bay, present_at_exit + same_time_exit, new_blk, fast=True):
            continue  # crane path blocked at exit -> try next candidate
        _rev_blocked = False
        for b_other in same_time_exit:
            if check_exit(bay, [new_blk, b_other], b_other, fast=True):
                _rev_blocked = True
                break
        if _rev_blocked:
            continue  # our block would obstruct a same-time exit -> next candidate

        # Interaction check over every block whose stay overlaps [entry, exit_t):
        #   (a) b_other ENTERS during our stay (entry < a_other < exit_t):
        #       our block must not obstruct b_other's crane DESCENT.  b_other's
        #       own entry check was run at ITS placement time, before we
        #       existed -- without this check our placement can invalidate it
        #       (Stage-2 violations found only by the repair loop).
        #   (b) b_other EXITS during our stay (entry < e_other < exit_t):
        #       same argument for b_other's crane ASCENT (Stage-3 violations).
        #   (c) blocks strictly interior to our window (absent at both of our
        #       boundary moments): same-height spatial collision check
        #       (Stage-4).  Boundary-overlapping blocks are already covered by
        #       the j==k case of check_entry / check_exit above.
        blocked = False
        for b_other, (a_other, e_other) in zip(placed_in_bay, schedule_in_bay):
            if not _time_overlaps(entry, exit_t, a_other, e_other):
                continue  # disjoint in time
            if entry < a_other < exit_t and check_entry(bay, [new_blk], b_other, fast=True):
                blocked = True  # we would obstruct b_other's later entry
                break
            if entry < e_other < exit_t and check_exit(bay, [new_blk, b_other], b_other, fast=True):
                blocked = True  # we would obstruct b_other's later exit
                break
            if a_other >= entry and e_other <= exit_t and check_collisions(bay, [new_blk, b_other]):
                blocked = True  # interior-interval same-height collision
                break
        if blocked:
            continue

        return entry, exit_t

    return None, None  # no valid time slot for this (position, bay) combination


# -----------------------------------------------------------------------------
# Guaranteed-feasible entry: empty-bay window
# -----------------------------------------------------------------------------

def _empty_bay_entry(schedule_in_bay: list[tuple[int, int]],
                     r_time: int, proc: int) -> int:
    """
    Return the earliest entry time >= r_time such that the bay is completely
    empty for the entire window [entry, entry + proc).

    This guarantees crane-path feasibility: when the bay is empty at both
    entry_time and exit_time, check_entry and check_exit trivially pass
    (no blocks present means no polygon obstructions).

    Algorithm -- iterative push:
      Start with entry = r_time.  Scan all existing slots (a_k, e_k).  If
      [entry, entry+proc) overlaps any slot, advance entry to e_k (the end of
      that slot) so the window no longer overlaps it.  Repeat until no
      overlaps remain.

    Convergence guarantee:
      Each iteration advances entry by at least the distance to the next
      slot endpoint.  Because the number of slots is finite, the loop
      terminates after at most len(schedule_in_bay) passes.
    """
    entry = int(r_time)
    changed = True
    while changed:
        changed = False
        exit_t = entry + proc
        for a, e in schedule_in_bay:
            if _time_overlaps(entry, exit_t, a, e):
                entry = max(entry, e)  # push past the overlapping slot
                changed = True
    return entry


# -----------------------------------------------------------------------------
# Main algorithm
# -----------------------------------------------------------------------------

def greedyalgorithm(prob_info: dict, timelimit: float,
                    repair_mode: str = "greedy",
                    improve: bool = True,
                    strategy: dict = None,
                    _allow_restart: bool = True) -> dict:
    """
    EDD + Best-Fit Greedy algorithm with post-hoc feasibility repair and
    optional local-search improvement.

    Parameters
    ----------
    prob_info   : instance JSON dict with keys "name", "bays", "blocks", "weights"
    timelimit   : wall-clock time limit in seconds
    repair_mode : "greedy" (default) or "simple" -- see module docstring for details
    improve     : if True (default), run Phase 3 local-search improvement
                  using any timelimit remaining after Phase 2 reaches a
                  feasible solution.

    Returns
    -------
    solution dict in the format described in the module docstring

    Phase 1 -- EDD greedy placement:
        Blocks sorted by due-date buckets (R1, width eff_ord_delta),
        area-descending within a bucket (strict (due, proc) EDD only when
        ord_delta_mult=0, e.g. the "Strict EDD" strategy).  For each block, every
        (bay, orientation, candidate position) is tried; _find_earliest_slot
        computes the earliest crane-feasible time slot.  The combination
        minimising _placement_score is committed.  bay_placed, bay_schedule,
        and bay_loads are updated incrementally.

    Phase 2 -- Repair (see _repair and module docstring for details):
        Calls _repair which runs up to max_passes rounds of
        check_feasibility -> re-place violating blocks.

    Phase 3 -- Local-search improvement (see _improve and module docstring):
        Only runs if Phase 2 reached a feasible solution and time remains.
        The result is validated with check_feasibility before it replaces
        the Phase-2 solution; the Phase-2 solution is kept if anything looks
        wrong or does not improve the objective.
    """
    t_start = time.time()

    bays_data   = prob_info["bays"]
    blocks_data = prob_info["blocks"]
    n_bays      = len(bays_data)
    n_blocks    = len(blocks_data)

    w1 = prob_info.get("weights", {}).get("w1", 1.0)
    w2 = prob_info.get("weights", {}).get("w2", 1.0)
    w3 = prob_info.get("weights", {}).get("w3", 1.0)
    
    global _NFP_EFF
    _NFP_EFF = int(strategy["nfp_slide"]) if (strategy and "nfp_slide" in strategy) else _NFP_SLIDE

    global _NFP_FULL_EFF, _NFPF_BUDGET, _NFPF_SPENT
    _NFP_FULL_EFF = int(strategy["nfp_full"]) if (strategy and "nfp_full" in strategy) else _NFP_FULL
    _NFPF_BUDGET = 0.15 * timelimit if _NFP_FULL_EFF > 0 else 0.0
    _NFPF_SPENT = 0.0

    if strategy and "w3_mult" in strategy:
        w3 *= strategy["w3_mult"]
    if strategy and "w1_mult" in strategy:
        w1 *= strategy["w1_mult"]
    if strategy and "w2_mult" in strategy:
        w2 *= strategy["w2_mult"]

    print(f"[Greedy] Instance : {prob_info.get('name', '?')}")
    print(f"[Greedy] Bays     : {n_bays}  |  Blocks : {n_blocks}  |  Timelimit : {timelimit:.1f}s")
    print(f"[Greedy] Weights  : w1={w1}  w2={w2}  w3={w3}")
    print(f"[Greedy] {'-' * 56}")

    bays = [Bay.from_dict(d, i) for i, d in enumerate(bays_data)]
    for i, b in enumerate(bays):
        print(f"[Greedy]   bay[{i}]  {b.width}x{b.height}")

    # T1 activation: overload predictor (see _TAILW_ACTIVE comment above).
    global _TAILW_ACTIVE
    _TAILW_ACTIVE = False
    if _TAILW:
        def _sl(poly):
            s = 0.0
            for _i in range(len(poly)):
                _x1, _y1 = poly[_i]
                _x2, _y2 = poly[(_i + 1) % len(poly)]
                s += _x1 * _y2 - _x2 * _y1
            return abs(s) / 2.0
        _demand = sum(sum(_sl(l) for l in blk["shape"][0]["layers"]) * blk["processing_time"]
                      for blk in blocks_data)
        _cap = sum(b.width * b.height for b in bays)
        _maxdue = max((blk["due_date"] for blk in blocks_data), default=0)
        _ratio = _demand / (_cap * _maxdue) if _cap * _maxdue > 0 else 0.0
        _TAILW_ACTIVE = _ratio >= _TAILW_RATIO
        if strategy and "force_tailw" in strategy:
            # M3 blind-band fix: for demand ratios in [0.55, 0.70) the right
            # T1 setting is instance-dependent (measured: prob_29 obj1
            # 854-1687 -> 11-13 with T1 ON; prob_34/21 slightly worse), so
            # the portfolio runs BOTH and the best verified total wins.
            _TAILW_ACTIVE = bool(strategy["force_tailw"])
        global _TAILW_RATIO_SEEN
        _TAILW_RATIO_SEEN = _ratio
        print(f"[Greedy] T1 demand_ratio={_ratio:.2f} -> wave repack "
              f"{'ON' if _TAILW_ACTIVE else 'off'}")

    # -- Instance validity check: every block must have at least one valid -----
    # integer (x, y) position in at least one bay and orientation.
    # If not, the problem instance itself is malformed -- abort immediately.
    invalid_blocks = []
    for bi, blk_data in enumerate(blocks_data):
        placeable = False
        for bay in bays:
            for oi in range(len(blk_data["shape"])):
                bb = _block_bbox(blk_data, oi)
                lx0, ly0, lx1, ly1 = bb
                if (math.ceil(-lx0) <= math.floor(bay.width  - lx1) and
                        math.ceil(-ly0) <= math.floor(bay.height - ly1)):
                    placeable = True
                    break
            if placeable:
                break
        if not placeable:
            invalid_blocks.append(bi)
    if invalid_blocks:
        print(f"[Greedy] ERROR: {len(invalid_blocks)} block(s) cannot be placed at any integer "
              f"position in any bay -- malformed instance.")
        for bi in invalid_blocks:
            blk_data = blocks_data[bi]
            for bay in bays:
                for oi in range(len(blk_data["shape"])):
                    bb = _block_bbox(blk_data, oi)
                    lx0, ly0, lx1, ly1 = bb
                    bw, bh = lx1 - lx0, ly1 - ly0
                    print(f"[Greedy]   block {bi} oi={oi} bay{bay.id}({bay.width}x{bay.height}): "
                          f"bw={bw:.4f} bh={bh:.4f} "
                          f"px=[{math.ceil(-lx0)},{math.floor(bay.width-lx1)}] "
                          f"py=[{math.ceil(-ly0)},{math.floor(bay.height-ly1)}]")
        raise ValueError(
            f"Malformed instance '{prob_info.get('name', '?')}': "
            f"block(s) {invalid_blocks} have no valid integer placement in any bay."
        )

    # -- Phase 1: aggressive greedy --------------------------------------------
    eff_ord_delta = _ORD_DELTA
    if strategy and "ord_delta_mult" in strategy:
        _odm = strategy["ord_delta_mult"]
        if _odm <= 0:
            # mult 0 = strict EDD (no bucketing) -- max(1, ...) would have
            # silently turned "Strict EDD" into bucket-width-1 instead.
            eff_ord_delta = 0
        else:
            median_proc = sorted([b["processing_time"] for b in blocks_data])[n_blocks // 2] if n_blocks > 0 else 1.0
            eff_ord_delta = max(1, int(median_proc * _odm))

    if eff_ord_delta > 0:
        # R1: group near-equal due dates into buckets of width eff_ord_delta and
        # let LARGER blocks pick first inside a bucket -- big blocks need
        # contiguous space that only exists early; small ones fill gaps later.
        def _area0(i: int) -> float:
            bb = _block_bbox(blocks_data[i], 0)
            return (bb[2] - bb[0]) * (bb[3] - bb[1])
        sorted_indices = sorted(
            range(n_blocks),
            key=lambda i: (blocks_data[i]["due_date"] // eff_ord_delta,
                           -_area0(i),
                           blocks_data[i]["processing_time"])
        )
    else:
        sorted_indices = sorted(
            range(n_blocks),
            key=lambda i: (blocks_data[i]["due_date"], blocks_data[i]["processing_time"])
        )
    print(f"[Greedy] {'-' * 56}")
    print("[Greedy] Phase 1 : EDD greedy placement ...")

    bay_placed:   list[list[Block]]             = [[] for _ in range(n_bays)]
    bay_schedule: list[list[tuple[int, int]]]   = [[] for _ in range(n_bays)]
    bay_loads:    list[float]                   = [0.0] * n_bays

    assignments = _place_blocks(
        sorted_indices, blocks_data, bays,
        bay_placed, bay_schedule, bay_loads,
        w1, w2, w3, forced_ids=set(),
        t_start=t_start, log_interval=max(1, n_blocks // 10),
        timelimit=timelimit,
    )

    elapsed_p1 = time.time() - t_start
    loads_str = "  ".join(f"bay{i}={round(bay_loads[i])}" for i in range(n_bays))
    print(f"[Greedy] Phase 1 done  |  placed={len(assignments)}  {loads_str}  "
          f"elapsed={elapsed_p1:.2f}s")

    # -- Phase 2: repair infeasible assignments --------------------------------
    print(f"[Greedy] {'-' * 56}")
    print(f"[Greedy] Phase 2 : repair  mode={repair_mode}")
    sol = {"operations": _build_operations(list(assignments.values()))}
    assignments = _repair(prob_info, sol, assignments, bays, blocks_data,
                          w1, w2, w3, t_start, timelimit,
                          repair_mode=repair_mode)

    from utils import check_feasibility
    sol = {"operations": _build_operations(list(assignments.values()))}
    result = check_feasibility(prob_info, sol)

    # -- Phase 3: local-search improvement (best-effort, time permitting) -----
    elapsed_p2 = time.time() - t_start
    if improve and result["feasible"] and timelimit - elapsed_p2 > 0.5:
        print(f"[Greedy] {'-' * 56}")
        print(f"[Greedy] Phase 3 : local-search improvement  "
              f"(budget remaining={timelimit - elapsed_p2:.1f}s)")
        candidate = _improve(dict(assignments), bays, blocks_data,
                             w1, w2, w3, t_start, timelimit)
        candidate_sol = {"operations": _build_operations(list(candidate.values()))}
        candidate_result = check_feasibility(prob_info, candidate_sol)
        if candidate_result["feasible"] and candidate_result["objective"] <= result["objective"] + 1e-6:
            print(f"[Greedy] Phase 3 accepted  |  objective {result['objective']:.0f} "
                  f"-> {candidate_result['objective']:.0f}")
            assignments, sol, result = candidate, candidate_sol, candidate_result
        else:
            print(f"[Greedy] Phase 3 rejected  |  kept Phase 2 solution "
                  f"(candidate feasible={candidate_result['feasible']})")

    # V16 surplus restart: if this attempt left most of the budget unused
    # (cheap searches under the per-block caps -- measured: prob_20@24s
    # finished in 7s, obj1=220, while the same code given bigger per-block
    # caps used 17.7s and reached obj1=6), spend the remainder on ONE fresh,
    # deeper attempt and keep the better verified solution.
    _elapsed_now = time.time() - t_start
    _surplus = timelimit - _elapsed_now
    if (_allow_restart and result["feasible"] and not improve
            and _elapsed_now < 0.45 * timelimit and _surplus > max(3.0, _elapsed_now)):
        print(f"[Greedy] {'-' * 56}")
        print(f"[Greedy] V16 surplus restart: {_surplus:.1f}s unused -> second attempt")
        retry_sol = greedyalgorithm(prob_info, _surplus - 0.5, repair_mode=repair_mode,
                                    improve=False, strategy=strategy, _allow_restart=False)
        from utils import check_feasibility as _cf16
        retry_res = _cf16(prob_info, retry_sol)
        if retry_res["feasible"] and retry_res["objective"] < result["objective"]:
            print(f"[Greedy] V16 restart accepted: {result['objective']:.0f} -> {retry_res['objective']:.0f}")
            sol, result = retry_sol, retry_res
        else:
            print(f"[Greedy] V16 restart rejected (kept first attempt)")

    elapsed_total = time.time() - t_start
    final_sol = sol
    final_result = result
    print(f"[Greedy] {'-' * 56}")
    print(f"[Greedy] Done  |  assigned={len(assignments)}/{n_blocks}  "
          f"elapsed={elapsed_total:.2f}s")
    if final_result["feasible"]:
        print(f"[Greedy] Objective : {final_result['objective']:.0f}  "
              f"(obj1={final_result['obj1']:.1f}  "
              f"obj2={final_result['obj2']:.1f}  "
              f"obj3={final_result['obj3']:.1f})")
    else:
        print(f"[Greedy] INFEASIBLE stage={final_result['stage']}")
        for v in final_result["violations"][:5]:
            print(f"[Greedy]   {v}")

    return final_sol


# -----------------------------------------------------------------------------
# Force-place helper (no feasibility check -- used as phase-1 last resort)
# -----------------------------------------------------------------------------

def _force_place(bi: int,
                 blocks_data: list[dict],
                 bays: list[Bay],
                 bay_placed: list[list[Block]],
                 bay_schedule: list[list[tuple[int, int]]],
                 prefs: list[float],
                 t_start: float | None = None,
                 timelimit: float | None = None) -> tuple:
    """
    Fallback placement: place block bi at the minimum valid position in the
    highest-preference bay whose dimensions accommodate the block, using
    an empty-bay entry window.

    When called:
      * _place_blocks found no feasible (position, bay, time-slot) combination
        during Phase-1 search (should be rare for well-formed instances).
      * bi is in forced_ids during repair -- the block has appeared in two or
        more consecutive repair passes, indicating a crane-path cycle.  Forcing
        it to an empty-bay window breaks the cycle by guaranteeing that both
        check_entry and check_exit trivially pass (bay is empty).

    Why minimum-valid position with empty-bay window is always feasible:
      _empty_bay_entry returns a time interval [entry, exit_t) during which no
      other block occupies the bay.  With the bay empty at both entry_time and
      exit_time, check_entry/check_exit have no polygon obstructions to report,
      so Stage-2 and Stage-3 always pass regardless of block shape or position.
      The minimum-valid position (max(0, ceil(-lx0)), max(0, ceil(-ly0)))
      ensures the block's bounding box starts at the bay's lower-left corner,
      so the bay boundary check also passes.

    Orientation selection: the first orientation whose footprint fits within
    the bay is used.  If no orientation fits (degenerate instance), the
    preferred bay with orientation 0 is used as an absolute last resort.

    Position selection: the minimum valid reference-point position is used,
    i.e. (max(0, ceil(-lx0)), max(0, ceil(-ly0))) derived from the block's
    local bounding box.  This ensures the block's world bounding box starts at
    the bay's lower-left corner regardless of which vertex is the reference
    point.  Placing at (0, 0) would be wrong when lx0 < 0 or ly0 < 0.
    """
    blk_data = blocks_data[bi]
    r_time   = blk_data["release_time"]
    proc     = blk_data["processing_time"]
    n_bays   = len(bays)

    # -- Attempt 1: bounded real-slot search (coexist with other blocks) ------
    # Instead of demanding an exclusive empty-bay window, try to find an
    # actual (position, time) slot alongside other blocks, exactly like the
    # main search but tightly bounded: capped candidates, a ~30ms wall-clock
    # budget, and skipped entirely inside the last 7% of the time limit so a
    # long tail of forced blocks can never overrun the total budget (the
    # empty-window fallback below is O(len(schedule)) and always safe).
    # Selection: earliest entry across ALL bays (preference as tie-break) --
    # with w1 >> w3 an earlier slot in a less-preferred bay is almost always
    # the right trade.
    _do_search = True
    if t_start is not None and timelimit is not None:
        if time.time() - t_start > timelimit * 0.93:
            _do_search = False

    if _do_search:
        fp_deadline = time.time() + 0.03
        fp_best: tuple | None = None  # (entry, -pref, bay_id, cx, cy, oi, exit_t)
        fp_stop = False
        _uoi: list[int] = []
        _seen: set = set()
        for _oi in range(len(blk_data["shape"])):
            _k = _orient_key(blk_data, _oi)
            if _k not in _seen:
                _seen.add(_k)
                _uoi.append(_oi)
        for bay_id in sorted(range(n_bays), key=lambda j: prefs[j], reverse=True):
            if fp_stop:
                break
            bay             = bays[bay_id]
            placed_in_bay   = bay_placed[bay_id]
            schedule_in_bay = bay_schedule[bay_id]
            _ex = {e for _, e in schedule_in_bay}
            _en = {a for a, _ in schedule_in_bay}
            cand_entries = sorted(
                {r_time}
                | {e for e in _ex if e > r_time}
                | {e - proc for e in _ex if e - proc > r_time}
                | {a - proc for a in _en if a - proc > r_time}
            )[:_MAX_ENTRY_CANDIDATES]
            for oi in _uoi:
                if fp_stop:
                    break
                bb = _block_bbox(blk_data, oi)
                lx0_o, ly0_o, lx1_o, ly1_o = bb
                if (math.ceil(-lx0_o) > math.floor(bay.width  - lx1_o) or
                        math.ceil(-ly0_o) > math.floor(bay.height - ly1_o)):
                    continue
                active_in_bay = [
                    b for b, (a_k, e_k) in zip(placed_in_bay, schedule_in_bay)
                    if e_k > r_time
                ]
                candidates = _candidate_positions(bay.width, bay.height,
                                                  active_in_bay, bb)
                if len(candidates) > _MAX_POSITIONS:
                    candidates = candidates[:_MAX_POSITIONS]
                for (cx, cy) in candidates:
                    if time.time() > fp_deadline:
                        fp_stop = True
                        break
                    new_blk = Block(block_id=bi, block_data=blk_data,
                                    x=cx, y=cy, orient_idx=oi)
                    if not bay.contains_block(new_blk):
                        continue
                    entry, exit_t = _find_earliest_slot(
                        new_blk, bay, placed_in_bay, schedule_in_bay,
                        r_time, proc, candidate_entries=cand_entries
                    )
                    if entry is None:
                        continue
                    key = (entry, -prefs[bay_id])
                    if fp_best is None or key < (fp_best[0], fp_best[1]):
                        fp_best = (entry, -prefs[bay_id], bay_id, cx, cy, oi, exit_t)
                        if entry <= r_time:
                            fp_stop = True  # cannot start earlier than release
                            break
        if fp_best is not None:
            return (fp_best[2], fp_best[3], fp_best[4], fp_best[5],
                    fp_best[0], fp_best[6])

    # -- Attempt 1.5 (region-clear): the empty-bay window demands 100%
    # exclusivity of a bay for a block occupying 5-10% of it; measured on
    # prob_39, stratified positions in OTHER regions clear at median t=49
    # while the bay only empties at t=139 (90 time-units/block cheaper).
    # For each bay, probe corner/center positions; region-clear time = max
    # exit among AABB-overlapping residents (pure AABB scans, no Shapely).
    # By maximality no overlapping block exists at or after that time, so
    # the slot is near-guaranteed feasible; each candidate is still verified
    # through _find_earliest_slot before use, and the empty-window safety
    # net below remains the terminal fallback.

    # -- Attempt 2 (always-feasible safety net) baseline calculation ----
    # Evaluate EVERY bay and pick the one whose empty window opens earliest
    # (preference as tie-break).  This serves as the absolute upper bound
    # (worst-case) for entry time; Attempt 1.5 must strictly beat this.
    best_fallback: tuple | None = None  # (entry, -pref, bay_id, px, py, oi)
    for bay_id in sorted(range(n_bays), key=lambda j: prefs[j], reverse=True):
        bay = bays[bay_id]
        for oi in range(len(blk_data["shape"])):
            bb = _block_bbox(blk_data, oi)
            lx0, ly0, lx1, ly1 = bb
            # Block translates all layers by (px - ref_x, py - ref_y).
            # With ref point guaranteed (0,0) by the instance generator:
            #   world_xmin = lx0 + px >= 0   =>  px >= ceil(-lx0)
            #   world_xmax = lx1 + px <= W   =>  px <= floor(W - lx1)
            #   world_ymin = ly0 + py >= 0   =>  py >= ceil(-ly0)
            #   world_ymax = ly1 + py <= H   =>  py <= floor(H - ly1)
            # A valid integer px exists iff ceil(-lx0) <= floor(W - lx1).
            px_lo = math.ceil(-lx0)
            px_hi = math.floor(bay.width  - lx1)
            py_lo = math.ceil(-ly0)
            py_hi = math.floor(bay.height - ly1)
            if px_lo > px_hi or py_lo > py_hi:
                continue  # no valid integer position for this orientation
            px = max(0, px_lo)
            py = max(0, py_lo)
            entry = _empty_bay_entry(bay_schedule[bay_id], r_time, proc)
            cand = (entry, -prefs[bay_id], bay_id, px, py, oi)
            if best_fallback is None or cand < best_fallback:
                best_fallback = cand
            break  # first fitting orientation suffices for this bay

    # -- Attempt 1.5 (region-clear) -------------------------------------------
    if _FP_REGION:
        _cands = []
        for _j in range(n_bays):
            _bayj = bays[_j]
            for _oi in range(len(blk_data["shape"])):
                _bb = _block_bbox(blk_data, _oi)
                _plo_x = math.ceil(-_bb[0]); _phi_x = math.floor(_bayj.width  - _bb[2])
                _plo_y = math.ceil(-_bb[1]); _phi_y = math.floor(_bayj.height - _bb[3])
                if _plo_x > _phi_x or _plo_y > _phi_y:
                    continue
                # v21c (Leo): bottom-left-fill candidates instead of 6 fixed
                # corner/center probes -- derive candidates from every block
                # CURRENTLY in this bay via the same generator _place_blocks
                # uses, so the region-clear search can land in any open gap.
                # Clear-time semantics below are unchanged.  Measured (24s
                # seed, 2 reps): prob_39 obj1 -22~34%, prob_40 -16~27%,
                # prob_10 identical (FP2-inactive there).
                _bl_cands = _candidate_positions(
                    _bayj.width, _bayj.height, bay_placed[_j], _bb
                )
                if len(_bl_cands) > _MAX_POSITIONS:
                    _bl_cands = _bl_cands[:_MAX_POSITIONS]
                for (_px, _py) in _bl_cands:
                    _blk = Block(block_id=bi, block_data=blk_data,
                                 x=_px, y=_py, orient_idx=_oi)
                    _nb = _blk.bounding_rect()
                    _tc = int(r_time)
                    for _b, (_a, _e) in zip(bay_placed[_j], bay_schedule[_j]):
                        if _e > _tc and _bb_overlap(_nb, _b.bounding_rect()):
                            _tc = int(_e)
                    # Only consider regions that clear earlier than the fallback
                    if best_fallback is None or _tc < best_fallback[0]:
                        _cands.append((_tc, -prefs[_j], _j, _px, _py, _oi))
                break  # first fitting orientation per bay
        _cands.sort()
        for (_tc, _np, _j, _px, _py, _oi) in _cands[:8]:
            _blk = Block(block_id=bi, block_data=blk_data,
                         x=_px, y=_py, orient_idx=_oi)
            _en, _ex = _find_earliest_slot(
                _blk, bays[_j], bay_placed[_j], bay_schedule[_j],
                r_time, proc, candidate_entries=[_tc])
            if _en is not None:
                # Double check the verified slot actually beats the fallback
                if best_fallback is None or _en < best_fallback[0]:
                    return (_j, _px, _py, _oi, _en, _ex)

    if best_fallback is not None:
        entry, _, bay_id, px, py, oi = best_fallback
        return (bay_id, px, py, oi, entry, entry + proc)

    # This path should never be reached: greedyalgorithm() checks at startup that
    # every block has at least one valid integer position and raises ValueError for
    # malformed instances before any placement begins.
    raise RuntimeError(
        f"_force_place: block {bi} has no valid integer position in any bay "
        f"-- instance validation should have caught this."
    )


# -----------------------------------------------------------------------------
# Rebuild per-bay state from a flat assignment collection
# -----------------------------------------------------------------------------

def _rebuild_bay_state(
    assignments: dict[int, dict] | list[dict],
    bays: list[Bay],
    blocks_data: list[dict],
) -> tuple[list[list[Block]], list[list[tuple[int, int]]], list[float]]:
    """
    Rebuild bay_placed / bay_schedule / bay_loads from a flat assignment
    collection (dict[block_id -> assignment] or a plain list of assignment
    dicts).  Used by _repair (greedy mode) and _improve, which both need an
    accurate view of current bay occupancy derived from committed
    assignments before running _place_blocks again.
    """
    n_bays = len(bays)
    bay_placed:   list[list[Block]]           = [[] for _ in range(n_bays)]
    bay_schedule: list[list[tuple[int, int]]] = [[] for _ in range(n_bays)]
    bay_loads:    list[float]                 = [0.0] * n_bays

    values = assignments.values() if isinstance(assignments, dict) else assignments
    for a in values:
        bid    = a["block_id"]
        bay_id = a["bay_id"]
        blk = Block(block_id=bid, block_data=blocks_data[bid],
                    x=int(a["x"]), y=int(a["y"]), orient_idx=a["orient_idx"])
        bay_placed[bay_id].append(blk)
        bay_schedule[bay_id].append((a["entry_time"], a["exit_time"]))
        bay_loads[bay_id] += blocks_data[bid]["workload"]

    return bay_placed, bay_schedule, bay_loads


# -----------------------------------------------------------------------------
# Shared greedy placement kernel (used by Phase 1 and _repair)
# -----------------------------------------------------------------------------

def _slide_tight(bi: int,
                 blk_data: dict,
                 placement: tuple,
                 bay,
                 placed_in_bay: list,
                 schedule_in_bay: list,
                 max_steps: int) -> tuple:
    """NFP-lite compaction: slide a CHOSEN placement left/down one integer
    cell at a time, revalidating the SAME time slot with the exact
    machinery, until true polygon contact stops it.

    Why: AABB-corner candidates cannot PROPOSE interlocking positions
    (L/U-shape nesting) -- but they can often be REACHED by sliding from an
    AABB position through the exact checker, which uses full polygon
    geometry.  The slot (entry, exit) is fixed, so the placement score is
    unchanged-or-better (top_y can only drop); the whole gain is the space
    freed for FUTURE blocks -- the density lever, at ~1 slot-check per step.
    """
    bay_id, cx, cy, oi, entry, exit_t = placement
    proc = exit_t - entry
    bb = _block_bbox(blk_data, oi)
    steps = 0
    moved = True
    while moved and steps < max_steps:
        moved = False
        for dx, dy in ((-1, 0), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if nx + bb[0] < -1e-9 or ny + bb[1] < -1e-9:
                continue  # bay wall
            cand = Block(block_id=bi, block_data=blk_data,
                         x=nx, y=ny, orient_idx=oi)
            en, _ex = _find_earliest_slot(cand, bay, placed_in_bay,
                                          schedule_in_bay, entry, proc,
                                          candidate_entries=[entry])
            if en == entry:
                cx, cy = nx, ny
                steps += 1
                moved = True
                break
    return (bay_id, cx, cy, oi, entry, exit_t)


def _place_blocks(
    block_ids: list[int],
    blocks_data: list[dict],
    bays: list[Bay],
    bay_placed: list[list[Block]],
    bay_schedule: list[list[tuple[int, int]]],
    bay_loads: list[float],
    w1: float, w2: float, w3: float,
    forced_ids: set[int],
    prev_assignments: dict[int, dict] | None = None,
    t_start: float | None = None,
    log_interval: int = 0,
    timelimit: float | None = None,
    time_guard_frac: float = _GUARD,
    allow_defer: bool = True,
) -> dict[int, dict]:
    """
    Shared placement kernel used by both Phase 1 and _repair (greedy mode).

    For each block in block_ids, finds the best (bay, x, y, orient, entry_time)
    by minimising _placement_score, then commits it to bay_placed /
    bay_schedule / bay_loads.  Returns a dict mapping block_id -> assignment.

    Search order:
      1. Repair fast-path (only when prev_assignments is provided):
         Try the block's previous (bay, x, y, orient) with _find_earliest_slot.
         If that position is still crane-feasible, record it as the initial
         best candidate.  This avoids re-solving the position search for blocks
         that only need a time adjustment.
      2. Full search (Phase-1 style):
         Iterate bays in decreasing preference order, then orientations, then
         candidate positions from _candidate_positions.  For each (bay, orient,
         pos), call _find_earliest_slot to get the earliest crane-feasible slot.
         Keep the (bay, orient, pos, slot) with the lowest _placement_score.
      3. Forced path (forced_ids, time_guard_frac exceeded, or no feasible
         combination found): skip steps 1-2 entirely and go straight to
         _force_place.  If the full search in step 2 found nothing,
         _force_place is used as a fallback and n_fallback is incremented.

    Parameters
    ----------
    block_ids        : ordered list of block indices to place (EDD order)
    blocks_data      : raw block data list from prob_info
    bays             : Bay objects (width, height, polygon)
    bay_placed       : mutable per-bay lists of placed Block objects (updated in-place)
    bay_schedule     : mutable per-bay lists of (entry_time, exit_time) (updated in-place)
    bay_loads        : mutable per-bay cumulative workload floats (updated in-place)
    w1, w2, w3       : objective weights
    forced_ids       : block ids to bypass search and use _force_place directly
    prev_assignments : previous assignment dict (repair mode fast-path)
    t_start          : wall-clock start time (for log timestamps and time_guard_frac)
    log_interval     : print a progress line every N blocks (0 = silent)
    timelimit        : total wall-clock budget; if set (together with t_start),
                        any block whose turn starts after time_guard_frac *
                        timelimit has elapsed is force-placed instead of run
                        through the full search, bounding worst-case runtime.
    time_guard_frac  : fraction of timelimit after which the time guard kicks in

    Returns
    -------
    dict[block_id -> assignment dict] for all blocks in block_ids
    """
    n_bays  = len(bays)
    n_total = len(block_ids)
    result: dict[int, dict] = {}
    n_forced = n_fallback = 0

    # Bay weights for normalized obj2: u_j = avg_area / (W_j * H_j)
    _bay_areas   = [bay.width * bay.height for bay in bays]
    _avg_area    = sum(_bay_areas) / n_bays
    bay_weights  = [_avg_area / a for a in _bay_areas]

    # R9 (pressure-aware bay choice, prob_40 finding #4): per-bay SPACE-TIME
    # fill fraction inside the due horizon H, maintained incrementally at
    # commit -- so the per-candidate cost is ZERO (a per-block, per-bay
    # lookup), unlike the falsified R2 which paid O(residents) per candidate.
    # Score adds w1 * _R9W * fill_j: equal-tardiness candidates drift to the
    # under-filled bay; a fill gap of f only outweighs real tardiness beyond
    # _R9W * f time units.  Gated with T1 (overloaded instances only) --
    # measured on prob_40, bays sustained 92/79/61/40% during [0,H] while
    # tardiness scales ~1/utilization.
    _r9_H = max((b["due_date"] for b in blocks_data), default=0)
    _r9_on = _R9W > 0 and _TAILW_ACTIVE and _r9_H > 0
    _bay_st = [0.0] * n_bays
    if _r9_on:
        _bay_cap_st = [max(1.0, _bay_areas[j] * _r9_H) for j in range(n_bays)]
        for _j9 in range(n_bays):
            for _b9, (_a9, _e9) in zip(bay_placed[_j9], bay_schedule[_j9]):
                _ov = min(_e9, _r9_H) - max(_a9, 0)
                if _ov > 0:
                    _rb = _b9.bounding_rect()
                    _bay_st[_j9] += (_rb[2] - _rb[0]) * (_rb[3] - _rb[1]) * _ov

    # R4: the perfect-placement early exit assumes obj2/obj3 residuals are
    # noise, which is only true when one time-unit of tardiness outweighs the
    # worst possible preference mistake (preferences sum to 100).  Gate it.
    _pe_ok = (not _R4_GATE) or (w1 > float(_os.environ.get("OGC_R4_T", "100")) * w3)

    # R6: defer-don't-jam.  A block whose best slot is already hopeless
    # (tardiness > theta) is NOT committed mid-order -- committing it would
    # consume capacity every later block needs (the v8 cascade).  Deferred
    # blocks are placed after the main pass, in due order, competing only
    # against the committed schedule and each other.
    _theta = None
    if _DEFER_MULT > 0 and allow_defer and n_total > 1:
        _procs_sorted = sorted(b["processing_time"] for b in blocks_data)
        _theta = _DEFER_MULT * _procs_sorted[len(_procs_sorted) // 2]
    _deferred: list[int] = []
    # v21f (block-6 finding): remember the slot a block HELD when R6 deferred
    # it, so the post-pass can restore it if re-entry does worse.  Measured
    # failure without this: prob_38 block 6 held (entry 99, tard 51), was
    # deferred (51 > theta), re-entered after the space was consumed and got
    # force-placed at entry 151 (tard 103) -- defer doubled its tardiness.
    _defer_slots: dict[int, tuple | None] = {}

    # Per-block search budget: a per-block timeout guarantees every block in
    # the EDD order gets *some* real search instead of a few early blocks
    # consuming the whole budget and the global time guard force-placing the
    # entire tail.  Since V16 the budget is DYNAMIC (remaining pool over
    # remaining blocks, surplus banking, cap OGC_BT_CAP) -- except in T1
    # hard-defer mode (ratio >= 1.0), which keeps a uniform window/n share
    # (dynamic was measured to regress there).  Details at the computation
    # site inside the loop.

    # T1 hard defer-deadline (ratio >= 1.0 only): once the main pass has
    # used its window, every remaining block is deferred WHOLESALE to the
    # wave pass instead of being searched/force-placed serially.  On very
    # overloaded instances the wave pass places the tail far better than
    # end-of-budget serial placement, so the budget belongs there.
    _bulk_defer = (_TAILW_ACTIVE and allow_defer and _theta is not None
                   and _TAILW_RATIO_SEEN >= 1.0
                   and timelimit is not None and t_start is not None)

    for rank, bi in enumerate(block_ids):
        if _bulk_defer and time.time() - t_start > _TAILW_MAIN * timelimit:
            _deferred.extend(block_ids[rank:])
            print(f"[Greedy]   T1 hard-defer: {len(block_ids) - rank} remaining "
                  f"blocks -> wave pass at {_TAILW_MAIN:.2f}*T")
            break
        blk_data = blocks_data[bi]
        r_time   = blk_data["release_time"]
        due      = blk_data["due_date"]
        proc     = blk_data["processing_time"]
        workload = blk_data["workload"]
        prefs    = blk_data["bay_preferences"]
        s_max    = max(prefs)
        n_orient = len(blk_data["shape"])

        best_score     = float("inf")
        best_placement = None
        _r9_pen = ([_R9W * w1 * (_bay_st[j] / _bay_cap_st[j]) for j in range(n_bays)]
                   if _r9_on else None)
        used_forced    = bi in forced_ids
        if (not used_forced and timelimit is not None and t_start is not None
                and time.time() - t_start > timelimit * time_guard_frac):
            used_forced = True

        if not used_forced:
            # -- Repair fast-path: try previous (bay, x, y, orient) first -----
            if prev_assignments and bi in prev_assignments:
                pa = prev_assignments[bi]
                pb_id = pa["bay_id"]
                px, py, poi = int(pa["x"]), int(pa["y"]), pa["orient_idx"]
                prev_blk = Block(block_id=bi, block_data=blk_data,
                                 x=px, y=py, orient_idx=poi)
                if bays[pb_id].contains_block(prev_blk):
                    entry, exit_t = _find_earliest_slot(
                        prev_blk, bays[pb_id],
                        bay_placed[pb_id], bay_schedule[pb_id],
                        r_time, proc
                    )
                    if entry is not None:
                        tardiness = max(0.0, exit_t - due)
                        p_bb = _block_bbox(blk_data, poi)
                        best_score     = (_r9_pen[pb_id] if _r9_pen else 0.0) + _placement_score(
                            tardiness, workload, bay_loads, pb_id,
                            s_max - prefs[pb_id], bay_weights, w1, w2, w3,
                            top_y=py + p_bb[3], entry=entry
                        )
                        if _W6F > 0:
                            best_score += w1 * _W6F * _bay_pressure(
                                bay_placed[pb_id], bay_schedule[pb_id],
                                entry, exit_t,
                                bays[pb_id].width * bays[pb_id].height)
                        best_placement = (pb_id, px, py, poi, entry, exit_t)

            # -- Full search (Phase-1 style) -----------------------------------
            # Mid-search circuit breaker: a single block's full search can, in
            # a heavily-occupied bay, take many seconds by itself (observed:
            # 10-16s for one block) because cost scales with
            # candidates x orientations x entry-slots, each candidate needing
            # real Shapely geometry work in check_entry/check_exit.  The
            # time_guard_frac check above only guards *whether* a block's
            # search starts; hard_deadline bounds it once it has, by checking
            # periodically inside the innermost loop and keeping whatever
            # best_placement has been found so far (falling through to
            # _force_place below if nothing has been found yet).
            hard_deadline = (
                t_start + timelimit * time_guard_frac
                if (timelimit is not None and t_start is not None) else None
            )
            time_exceeded = False
            found_perfect = False
            # Budget pool share: ~82% of the total limit goes to Phase-1
            # search (V16 splits it DYNAMICALLY below; the pre-V16 uniform
            # split is kept only in hard-defer mode).  The 0.82 share was
            # swept (2 reps x prob_20/25/39 at 24s): 0.45 and 0.6 starve the
            # search (prob_20 obj1 ~450/480); 0.75 -> ~174; 0.82 -> ~76.
            # More Phase-1 search beats leftover Phase-2/3 time; 0.82 sits
            # just under the 0.85 time guard so the guard stays a backstop.
            if timelimit is not None and n_total > 0:
                # T1 reservation: when the wave repack is on, the main pass
                # keeps a slightly smaller share so the post-pass gets a real
                # slice (~10% of budget) instead of the scraps after 0.82 +
                # overheads -- measured: without this the wave pass starts at
                # ~0.94*T and places nothing.
                if _TAILW_ACTIVE and allow_defer:
                    # ratio >= 1.0: the hard defer-deadline below ends the
                    # main pass at _TAILW_MAIN * timelimit, so per-block
                    # micro-budgets are aligned to that window.  (A deeper
                    # flat reservation was tried first and failed: per-block
                    # overhead beyond the micro-timeouts ate it -- prob_40
                    # main pass ran 31s against a 21.4s nominal budget.)
                    _bt_frac = _TAILW_MAIN if _TAILW_RATIO_SEEN >= 1.0 else 0.72
                else:
                    _bt_frac = 0.82
                # V16 dynamic budget: divide the REMAINING pool over the
                # REMAINING blocks instead of a fixed timelimit/n share.
                # Measured indictment: on prob_20@24s the uniform formula
                # starved every block at 0.066s while the whole run finished
                # in 7s of 24 -- 17s of wall unused, obj1=220; the same code
                # with a 3.9x per-block cap (via tl=96) used 17.7s total and
                # reached obj1=6.  Cheap early placements now bank their
                # surplus for the crowded middle/late blocks.  Cap raised via
                # OGC_BT_CAP (default 0.8) since surplus-fed blocks routinely
                # exceed the old 0.4.
                if _TAILW_ACTIVE and allow_defer and _TAILW_RATIO_SEEN >= 1.0:
                    # Hard-defer mode (ratio>=1.0): the main-pass WINDOW is
                    # fixed at _TAILW_MAIN*T and the wave pass is the surplus
                    # consumer -- dynamic budgeting here just lets early
                    # blocks eat the window (measured: prob_40 obj1 9.2k ->
                    # 11.6k).  Keep the uniform window/n share.
                    block_timeout = min(0.4, max(0.02, timelimit * _bt_frac / max(n_total, 1)))
                else:
                    _pool = timelimit * _bt_frac - (time.time() - t_start)
                    block_timeout = min(_BT_CAP, max(0.02, _pool / max(1, n_total - rank)))
            else:
                block_timeout = 0.05
            per_block_start = time.time()
            # Minimum achievable tardiness: even an immediate entry at
            # release_time cannot exit before r_time + proc.
            min_tard = max(0.0, r_time + proc - due)

            # Orientation dedupe: rotations with an identical footprint at
            # every layer are redundant -- search one representative each.
            unique_oi: list[int] = []
            _seen_keys: set = set()
            for _oi in range(n_orient):
                _k = _orient_key(blk_data, _oi)
                if _k not in _seen_keys:
                    _seen_keys.add(_k)
                    unique_oi.append(_oi)

            bay_order = sorted(range(n_bays), key=lambda j: prefs[j], reverse=True)
            if _r9_pen is not None and n_bays > 1:
                # R9c: the per-block micro-budget frequently dies before
                # later bays are even probed (same search-order artifact the
                # r0 pass fixed), so a score term alone cannot rebalance --
                # the starving bay must be probed FIRST.  But a full
                # fill-ascending order overrides preferences everywhere and
                # bleeds obj3 on already-balanced instances (prob_30 +7-12%,
                # 2 reps).  So: only when a real imbalance exists (fill gap
                # > 0.2), promote just the single most under-filled bay to
                # the front and keep the rest preference-ordered.
                # R9 final form: full fill-ascending order (preference as
                # tiebreak), gated on n_bays >= 3.  Evidence (2 reps each):
                # 3-4-bay overloaded instances win big (prob_39 -9~16%,
                # prob_40 -30%: the per-block budget dies before later bays
                # are probed, so the starving bay must come FIRST); 2-bay
                # instances self-balance (final fill gaps 0.04-0.08) and
                # fill-first order only bleeds obj3/locality there
                # (prob_30 +7-12%, 2 reps).  Mid-run gap thresholds were
                # tried (0.2 / 0.3) and behaved worse than this structural
                # gate -- intermittent order flips thrash.
                if n_bays >= 3:
                    _fills = [_bay_st[j] / _bay_cap_st[j] for j in range(n_bays)]
                    bay_order = sorted(range(n_bays),
                                       key=lambda j: (_fills[j], -prefs[j]))

            # -- Concurrency-first pass: try entry == r_time everywhere -------
            # The general scan below enumerates positions x entry-candidates
            # (up to 40 slot checks per position) in gravity order, so under
            # the per-block budget it can exhaust its time in the crowded
            # bottom-left zone and settle for a LATE slot even though an
            # entry at release existed at an open position -- leaving bays
            # spatially underused (measured on v5 solutions: 34-65% average
            # area utilization; big bays 34-41%).  This pass checks each
            # candidate position at the SINGLE entry r_time (one slot check
            # per position) across all bays in preference order.  Entry at
            # release is simultaneously minimum-possible tardiness and
            # maximum concurrency, so under w1/w5-dominant weights a hit
            # here is (near-)optimal; the general scan afterwards can only
            # improve on it and is skipped entirely when the hit is in a
            # most-preferred bay.
            _r0 = [int(r_time)]
            for bay_id in bay_order:
                if found_perfect or time.time() - per_block_start > block_timeout * 0.5:
                    break
                bay             = bays[bay_id]
                placed_in_bay   = bay_placed[bay_id]
                schedule_in_bay = bay_schedule[bay_id]
                for oi in unique_oi:
                    if found_perfect:
                        break
                    blk_bb = _block_bbox(blk_data, oi)
                    lx0_oi, ly0_oi, lx1_oi, ly1_oi = blk_bb
                    if (math.ceil(-lx0_oi) > math.floor(bay.width  - lx1_oi) or
                            math.ceil(-ly0_oi) > math.floor(bay.height - ly1_oi)):
                        continue
                    active_in_bay = [
                        b for b, (a_k, e_k) in zip(placed_in_bay, schedule_in_bay)
                        if e_k > r_time
                    ]
                    candidates = _candidate_positions(
                        bay.width, bay.height, active_in_bay, blk_bb
                    )
                    if len(candidates) > _MAX_POSITIONS:
                        candidates = candidates[:_MAX_POSITIONS]
                    if _NFP_FULL_EFF > 0:
                        candidates = _nfpf_augment(candidates, bay,
                                                   active_in_bay, blk_data, oi, bi)
                    _r0_hits = 0
                    for (cx, cy) in candidates:
                        if time.time() - per_block_start > block_timeout * 0.5:
                            break
                        new_blk = Block(block_id=bi, block_data=blk_data,
                                        x=cx, y=cy, orient_idx=oi)
                        if not bay.contains_block(new_blk):
                            continue
                        entry, exit_t = _find_earliest_slot(
                            new_blk, bay, placed_in_bay, schedule_in_bay,
                            r_time, proc, candidate_entries=_r0
                        )
                        if entry is None:
                            continue
                        tardiness = max(0.0, exit_t - due)
                        score = (_r9_pen[bay_id] if _r9_pen else 0.0) + _placement_score(
                            tardiness, workload, bay_loads, bay_id,
                            s_max - prefs[bay_id], bay_weights, w1, w2, w3,
                            top_y=cy + blk_bb[3], entry=entry
                        )
                        if _W6F > 0:
                            score += w1 * _W6F * _bay_pressure(
                                placed_in_bay, schedule_in_bay, entry, exit_t,
                                bay.width * bay.height)
                        if score < best_score:
                            best_score     = score
                            best_placement = (bay_id, cx, cy, oi, entry, exit_t)
                            if _pe_ok and prefs[bay_id] >= s_max and tardiness <= min_tard + 1e-9:
                                found_perfect = True
                        # R3: score up to _R0K r_time hits per (bay, orient) --
                        # gravity order, so the first is the tightest packing;
                        # extra hits let the score (incl. R2 pressure) choose.
                        _r0_hits += 1
                        if _r0_hits >= _R0K:
                            break

            for bay_id in bay_order:
                if time_exceeded or found_perfect:
                    break
                bay             = bays[bay_id]
                placed_in_bay   = bay_placed[bay_id]
                schedule_in_bay = bay_schedule[bay_id]
                # candidate_entries depends only on (schedule_in_bay, r_time,
                # proc), not on orientation/position -- compute once per bay
                # instead of once per candidate position (see
                # _find_earliest_slot for why each candidate family exists).
                _exits   = {e for _, e in schedule_in_bay}
                _entries = {a for a, _ in schedule_in_bay}
                bay_entry_candidates = sorted(
                    {r_time}
                    | {e for e in _exits if e > r_time}
                    | {e - proc for e in _exits if e - proc > r_time}
                    | {a - proc for a in _entries if a - proc > r_time}
                )[:_MAX_ENTRY_CANDIDATES]

                for oi in unique_oi:
                    if time_exceeded or found_perfect:
                        break
                    blk_bb = _block_bbox(blk_data, oi)
                    lx0_oi, ly0_oi, lx1_oi, ly1_oi = blk_bb
                    # Require a valid integer reference-point position to exist:
                    #   px in [ceil(-lx0), floor(W - lx1)]
                    #   py in [ceil(-ly0), floor(H - ly1)]
                    # If either range is empty there is no integer placement.
                    if (math.ceil(-lx0_oi) > math.floor(bay.width  - lx1_oi) or
                            math.ceil(-ly0_oi) > math.floor(bay.height - ly1_oi)):
                        continue

                    active_in_bay = [
                        b for b, (a_k, e_k) in zip(placed_in_bay, schedule_in_bay)
                        if e_k > r_time
                    ]
                    candidates = _candidate_positions(
                        bay.width, bay.height, active_in_bay, blk_bb
                    )
                    # Position cap: in a crowded bay the bottom-left cross
                    # product explodes (100+ blocks -> 1000s of positions).
                    # The list is sorted left-most/bottom-most first, which
                    # correlates with early feasible slots; cap the tail.
                    if len(candidates) > _MAX_POSITIONS:
                        candidates = candidates[:_MAX_POSITIONS]
                    if _NFP_FULL_EFF > 0:
                        candidates = _nfpf_augment(candidates, bay,
                                                   active_in_bay, blk_data, oi, bi)
                    for (cx, cy) in candidates:
                        _now = time.time()
                        if ((hard_deadline is not None and _now > hard_deadline)
                                or _now - per_block_start > block_timeout):
                            time_exceeded = True
                            break

                        new_blk = Block(block_id=bi, block_data=blk_data,
                                        x=cx, y=cy, orient_idx=oi)
                        if not bay.contains_block(new_blk):
                            continue

                        entry, exit_t = _find_earliest_slot(
                            new_blk, bay, placed_in_bay, schedule_in_bay,
                            r_time, proc, candidate_entries=bay_entry_candidates
                        )
                        if entry is None:
                            continue

                        tardiness = max(0.0, exit_t - due)
                        score = (_r9_pen[bay_id] if _r9_pen else 0.0) + _placement_score(
                            tardiness, workload, bay_loads, bay_id,
                            s_max - prefs[bay_id], bay_weights, w1, w2, w3,
                            top_y=cy + blk_bb[3], entry=entry
                        )
                        if _W6F > 0:
                            score += w1 * _W6F * _bay_pressure(
                                placed_in_bay, schedule_in_bay, entry, exit_t,
                                bay.width * bay.height)
                        if score < best_score:
                            best_score     = score
                            best_placement = (bay_id, cx, cy, oi, entry, exit_t)
                            # Perfect-placement early exit: entry at release
                            # in a most-preferred bay with the minimum
                            # achievable tardiness cannot be improved on the
                            # w1/w3 terms; under tardiness-dominant weights
                            # the remaining obj2/top_y gains are noise.  Stop
                            # searching this block and bank the time -- every
                            # second saved is another block that gets a real
                            # search instead of a forced placement.
                            if (_pe_ok and entry <= r_time
                                    and tardiness <= min_tard + 1e-9
                                    and prefs[bay_id] >= s_max):
                                found_perfect = True
                                break

        # R6: defer-don't-jam.  If this block's best option is already
        # hopeless (or the search found nothing), do NOT commit it mid-order;
        # it would consume capacity every later block needs.  It re-enters in
        # the post-pass (due order, allow_defer=False).
        if _theta is not None and not used_forced:
            _tard_best = (max(0.0, best_placement[5] - due)
                          if best_placement is not None else float("inf"))
            if _tard_best > _theta:
                _deferred.append(bi)
                _defer_slots[bi] = best_placement  # held slot (may be None)
                continue

        # v21f: last-chance hint before force-place.  The prev_assignments
        # fast-path above is SKIPPED under used_forced (time guard), which is
        # exactly when deferred blocks re-enter -- so a deferred block's held
        # slot (merged into prev_assignments by the post-pass caller) was
        # never retried.  One slot check is ~ms and strictly better than
        # falling straight into _force_place's stratified probing.
        _hint_pl = None
        if (_DEF_RESTORE and best_placement is None
                and prev_assignments and bi in prev_assignments):
            _pa2 = prev_assignments[bi]
            _pb2 = Block(block_id=bi, block_data=blk_data,
                         x=int(_pa2["x"]), y=int(_pa2["y"]),
                         orient_idx=_pa2["orient_idx"])
            if bays[_pa2["bay_id"]].contains_block(_pb2):
                _en2, _ex2 = _find_earliest_slot(
                    _pb2, bays[_pa2["bay_id"]],
                    bay_placed[_pa2["bay_id"]], bay_schedule[_pa2["bay_id"]],
                    r_time, proc)
                if _en2 is not None:
                    _hint_pl = (_pa2["bay_id"], int(_pa2["x"]),
                                int(_pa2["y"]), _pa2["orient_idx"],
                                _en2, _ex2)

        if best_placement is None:
            best_placement = _force_place(bi, blocks_data, bays,
                                          bay_placed, bay_schedule, prefs,
                                          t_start=t_start, timelimit=timelimit)
            n_fallback += 1
            # v21f round 2: the hint COMPETES with force-place instead of
            # bypassing it (round 1 bypassed and lost 2-3x: a stale hint slot
            # is feasible-but-late while the v21c-widened force-place finds
            # earlier region-clears; blind adoption also chained deferred
            # blocks into their old mutually-blocking spots).
            if _hint_pl is not None and _hint_pl[4] < best_placement[4]:
                best_placement = _hint_pl

        if used_forced:
            n_forced += 1

        if (_NFP_EFF > 0 and not used_forced
                and (timelimit is None or t_start is None
                     or time.time() - t_start < timelimit * time_guard_frac)):
            best_placement = _slide_tight(bi, blk_data, best_placement,
                                          bays[best_placement[0]],
                                          bay_placed[best_placement[0]],
                                          bay_schedule[best_placement[0]],
                                          _NFP_EFF)

        bay_id, cx, cy, oi, entry, exit_t = best_placement
        final_blk = Block(block_id=bi, block_data=blk_data, x=cx, y=cy, orient_idx=oi)
        bay_placed[bay_id].append(final_blk)
        bay_schedule[bay_id].append((entry, exit_t))
        bay_loads[bay_id] += workload
        if _r9_on:
            _ov9 = min(exit_t, _r9_H) - max(entry, 0)
            if _ov9 > 0:
                _rb9 = final_blk.bounding_rect()
                _bay_st[bay_id] += (_rb9[2] - _rb9[0]) * (_rb9[3] - _rb9[1]) * _ov9

        result[bi] = {
            "block_id":   bi,
            "bay_id":     bay_id,
            "x":          int(round(cx)),
            "y":          int(round(cy)),
            "orient_idx": oi,
            "entry_time": int(round(entry)),
            "exit_time":  int(round(exit_t)),
        }

        if log_interval > 0 and t_start is not None:
            n_done = rank + 1
            if n_done % log_interval == 0 or n_done == n_total:
                elapsed = time.time() - t_start
                loads_str = " ".join(f"b{i}={round(bay_loads[i])}" for i in range(n_bays))
                flag = " [forced]" if used_forced else (" [fallback]" if best_score == float("inf") else "")
                print(f"[Greedy]   {n_done:4d}/{n_total}"
                      f"  block{bi:<4d} -> bay{bay_id} ({cx},{cy}) oi={oi}"
                      f"  t=[{int(round(entry))},{int(round(exit_t))})"
                      f"  loads=[{loads_str}]"
                      f"  fallback={n_fallback}{flag}"
                      f"  {elapsed:.1f}s")

    # R6 post-pass: place deferred blocks last.  allow_defer is off so every
    # one of them commits (force-placing if necessary) -- but without having
    # poisoned the mid-order placements of everyone else first.
    #
    # T1 (wave repack): the serial due-ordered post-pass is what creates the
    # near-empty tardy tail on overloaded instances -- by post-pass time the
    # per-block budget is spent, blocks fall to _force_place's handful of
    # stratified positions, and each queues behind the previous one's
    # region-clear time (measured on prob_39: tail runs at ~1 block/bay vs
    # 12-21 demonstrated during the due horizon).  _wave_place instead places
    # deferred blocks in synchronized waves: probe ONE shared entry time t_w
    # across all bays/orientations/positions (single-candidate slot checks are
    # cheap -- same trick as the r0 pass), advance t_w to the next exit event
    # when nothing more fits.  Leftovers (budget guard, or genuinely no fit)
    # fall back to the exact serial post-pass, so behavior is never worse
    # structurally.  Gate: OGC_TAILW.
    if allow_defer and _deferred:
        print(f"[Greedy] R6 deferred: {len(_deferred)} blocks -> post-pass"
              f" ({'wave' if _TAILW_ACTIVE else 'serial'})")
        _leftover = _deferred
        # Min-size gate: waves only pay off for sizable deferred sets.  Tiny
        # sets (1-4 blocks, typical of ALNS-repair calls into _place_blocks)
        # were triggering up-to-63-event wave loops as pure overhead inside
        # every ALNS iteration (67 micro-invocations observed on prob_40).
        if _TAILW_ACTIVE and len(_deferred) >= _TAILW_MIN:
            _placed_wave, _leftover = _wave_place(
                _deferred, blocks_data, bays,
                bay_placed, bay_schedule, bay_loads,
                _theta if _theta is not None else 0.0,
                t_start, timelimit,
                edd_first=(_TAILW_RATIO_SEEN >= 1.0))
            result.update(_placed_wave)
        if _leftover:
            _def_order = sorted(_leftover,
                                key=lambda i: (blocks_data[i]["due_date"],
                                               blocks_data[i]["processing_time"]))
            _ff = forced_ids
            if _os.environ.get("OGC_DEF_FORCE", "0") == "1":
                _ff = set(forced_ids) | set(_def_order)
            # v21f: offer each deferred block its HELD slot as a hint (the
            # fast-path/pre-force check re-derives the earliest slot for that
            # position on the CURRENT state -- verified, never blind-committed).
            # Caller's own prev_assignments (repair mode) take precedence.
            _hints = ({b: {"bay_id": s[0], "x": s[1], "y": s[2],
                           "orient_idx": s[3]}
                       for b, s in _defer_slots.items() if s is not None}
                      if _DEF_RESTORE else {})
            _prev_merged = {**_hints, **(prev_assignments or {})} or None
            result.update(_place_blocks(
                _def_order, blocks_data, bays,
                bay_placed, bay_schedule, bay_loads,
                w1, w2, w3, _ff,
                prev_assignments=_prev_merged,
                t_start=t_start, log_interval=0,
                timelimit=timelimit, time_guard_frac=time_guard_frac,
                allow_defer=False,
            ))

    return result


# -----------------------------------------------------------------------------
# T1: wave repack of deferred blocks
# -----------------------------------------------------------------------------

def _wave_place(deferred: list[int],
                blocks_data: list[dict],
                bays: list,
                bay_placed: list[list],
                bay_schedule: list[list[tuple[int, int]]],
                bay_loads: list[float],
                theta: float,
                t_start: float | None,
                timelimit: float | None,
                edd_first: bool = False) -> tuple[dict, list[int]]:
    """
    Place deferred blocks in dense synchronized WAVES instead of serially.

    At wave time t_w, every unplaced deferred block (released by t_w) is
    probed across bays (preference-desc, load-asc), orientations, and up to
    _TAILW_POS bottom-left candidate positions, via _find_earliest_slot with
    candidate_entries=[t_w] -- a single cheap slot check per candidate, fully
    ruled on by the existing verified crane/collision machinery.  When a full
    pass over the remaining blocks places nothing, t_w advances to the next
    event (earliest resident exit > t_w, or earliest pending release).

    Start time: t_w0 = min over deferred of max(release_i, due_i+theta-proc_i).
    A block was deferred because its best exit exceeded due+theta at decision
    time, and the state has only gained residents since, so earlier times are
    (heuristically) not worth probing -- this is a probe schedule, not a
    correctness bound; the slot checker rules on every actual placement.

    Within an event, blocks are ordered by proc (desc by default,
    OGC_TAILW_ORD) with due as tiebreak: longer-processing blocks claim the
    tighter-packed positions first so their late exits sit deep, and the
    layer-descent interaction checks in _find_earliest_slot reject any
    combination that would obstruct a resident's later exit.

    Returns (placed_assignments, leftover_ids).  Leftovers occur only when
    the wall-clock guard (0.94 * timelimit) trips or the event cap is hit;
    the caller sends them through the original serial post-pass.
    """
    n_bays = len(bays)
    placed: dict[int, dict] = {}
    remaining = set(deferred)

    if edd_first:
        # Bulk-deferred sets (hard defer-deadline, ratio >= 1.0) contain
        # MIXED dues -- who gets the early waves matters for obj1, so EDD
        # is primary; proc-desc stays as the depth tiebreak within a due.
        order = sorted(deferred, key=lambda i: (blocks_data[i]["due_date"],
                                                -blocks_data[i]["processing_time"]))
    elif _TAILW_ORD == "asc":
        order = sorted(deferred, key=lambda i: (blocks_data[i]["processing_time"],
                                                blocks_data[i]["due_date"]))
    else:
        order = sorted(deferred, key=lambda i: (-blocks_data[i]["processing_time"],
                                                blocks_data[i]["due_date"]))

    t_w = min(max(blocks_data[i]["release_time"],
                  blocks_data[i]["due_date"] + theta - blocks_data[i]["processing_time"])
              for i in deferred)
    t_w = int(math.floor(t_w))
    guard = (t_start + timelimit * 0.94) if (t_start is not None and timelimit) else None

    # Pre-compute per-block valid (bay, orient) combos and bboxes once.
    combos: dict[int, list[tuple[int, int, tuple]]] = {}
    for bi in deferred:
        blk_data = blocks_data[bi]
        lst = []
        for j in range(n_bays):
            bay = bays[j]
            for oi in range(len(blk_data["shape"])):
                bb = _block_bbox(blk_data, oi)
                if (math.ceil(-bb[0]) <= math.floor(bay.width - bb[2]) and
                        math.ceil(-bb[1]) <= math.floor(bay.height - bb[3])):
                    lst.append((j, oi, bb))
        combos[bi] = lst

    n_events = 0
    n_waves = 0
    # Exponential backoff per block: after f consecutive failed probes a
    # block skips the next 2**f events (cap 32).  During the crowded
    # due-horizon period every block fails every ~1-time-unit exit event;
    # backoff makes that period cost a handful of probes per block instead
    # of one full scan per event.
    _fails: dict = {bi: 0 for bi in deferred}
    _skip_until: dict = {bi: 0 for bi in deferred}
    while remaining:
        if guard is not None and time.time() > guard:
            break
        n_events += 1
        if n_events > 400:
            break
        if _os.environ.get("OGC_TAILW_DBG") == "1":
            import time as _t
            print(f"[T1dbg] event {n_events} t_w={t_w} elapsed={_t.time()-t_start:.2f} remaining={len(remaining)}")

        # Free-area prefilter (per event): a bay whose free area at t_w is
        # smaller than a block's AABB can never host it -- skip the slot
        # checks entirely.  This makes events in the crowded due-horizon
        # period nearly free, so the wave loop can sweep many events and
        # spend its slot-check budget only where space has actually opened.
        free_area = []
        for j in range(n_bays):
            occ = 0.0
            for blk_o, (a, e) in zip(bay_placed[j], bay_schedule[j]):
                if a <= t_w < e:
                    rb = blk_o.bounding_rect()
                    occ += (rb[2] - rb[0]) * (rb[3] - rb[1])
            free_area.append(bays[j].width * bays[j].height - occ)

        placed_this_event = 0
        for bi in order:
            if bi not in remaining:
                continue
            if guard is not None and time.time() > guard:
                break
            if _skip_until[bi] > n_events:
                continue
            blk_data = blocks_data[bi]
            if blk_data["release_time"] > t_w:
                continue
            proc = blk_data["processing_time"]
            prefs = blk_data["bay_preferences"]
            # Bay order: preference first (obj3), then lighter load (obj2).
            bay_rank = sorted(range(n_bays), key=lambda j: (-prefs[j], bay_loads[j]))
            checks = 0
            # Scale the per-block cap by the remaining-set size so one event
            # costs a bounded number of slot checks regardless of |deferred|
            # (prob_40: 145 x 80 checks/event ~ 7s in crowded bays).
            cap_eff = max(16, min(_TAILW_CAP, _TAILW_EVB // max(1, len(remaining))))
            done = False
            for j in bay_rank:
                bay = bays[j]
                # Positions must be derived from blocks whose stay overlaps
                # [t_w, t_w+proc) -- bay_placed accumulates every block ever
                # placed, and gravity-sorting candidates from that full list
                # keeps probing the same long-vacated origin cluster while
                # the positions adjacent to CURRENT residents rank below the
                # cap.  (Measured: with the full list, waves cap at 1-3
                # blocks even in empty bays.)
                _present_j = [b for b, (a, e) in zip(bay_placed[j], bay_schedule[j])
                              if a < t_w + proc and e > t_w]
                for (jj, oi, bb) in combos[bi]:
                    if jj != j:
                        continue
                    if free_area[j] < (bb[2] - bb[0]) * (bb[3] - bb[1]):
                        continue
                    poss = _candidate_positions(bay.width, bay.height,
                                                _present_j, bb)[:_TAILW_POS]
                    for (px, py) in poss:
                        checks += 1
                        if checks > cap_eff:
                            break
                        cand = Block(block_id=bi, block_data=blk_data,
                                     x=px, y=py, orient_idx=oi)
                        en, ex = _find_earliest_slot(
                            cand, bay, bay_placed[j], bay_schedule[j],
                            t_w, proc, candidate_entries=[t_w])
                        if en is not None:
                            if _NFP_EFF > 0:
                                _sl_pl = _slide_tight(bi, blk_data,
                                                      (j, px, py, oi, en, ex),
                                                      bay, bay_placed[j],
                                                      bay_schedule[j],
                                                      _NFP_EFF)
                                _j2, px, py, _oi2, en, ex = _sl_pl
                                cand = Block(block_id=bi, block_data=blk_data,
                                             x=px, y=py, orient_idx=oi)
                            bay_placed[j].append(cand)
                            bay_schedule[j].append((en, ex))
                            bay_loads[j] += blk_data["workload"]
                            free_area[j] -= (bb[2] - bb[0]) * (bb[3] - bb[1])
                            placed[bi] = {
                                "block_id":   bi,
                                "bay_id":     j,
                                "x":          int(round(px)),
                                "y":          int(round(py)),
                                "orient_idx": oi,
                                "entry_time": int(round(en)),
                                "exit_time":  int(round(ex)),
                            }
                            done = True
                            break
                    if done or checks > cap_eff:
                        break
                if done or checks > cap_eff:
                    break
            if done:
                remaining.discard(bi)
                placed_this_event += 1
            else:
                _fails[bi] += 1
                _skip_until[bi] = n_events + min(8, 2 ** _fails[bi])

        if placed_this_event:
            n_waves += 1
            if _os.environ.get("OGC_TAILW_DBG") == "1":
                print(f"[T1dbg]   WAVE t_w={t_w} placed={placed_this_event}")
            # NOTE: deliberately no backoff reset here.  Resetting on success
            # re-probed the whole remaining set after every 1-block wave
            # (placements consume space, they don't open it) -- on prob_40
            # (145 deferred, dense exits) that thrash ate the entire wave
            # budget in the crowded window.
        if not remaining:
            break

        # Advance to the next event: earliest resident exit strictly after
        # t_w, or the earliest pending release, whichever is sooner.
        nxt = None
        for j in range(n_bays):
            for (_a, e) in bay_schedule[j]:
                if e > t_w and (nxt is None or e < nxt):
                    nxt = e
        for bi in remaining:
            r = blocks_data[bi]["release_time"]
            if r > t_w and (nxt is None or r < nxt):
                nxt = r
        if nxt is None:
            break
        t_w = int(nxt)

    leftover = [bi for bi in deferred if bi not in placed]
    print(f"[Greedy]   T1 wave repack: placed {len(placed)}/{len(deferred)} "
          f"in {n_waves} wave(s) over {n_events} event(s), leftover={len(leftover)}")
    return placed, leftover


# -----------------------------------------------------------------------------
# Phase 2: repair infeasible blocks
# -----------------------------------------------------------------------------

def _repair(prob_info: dict,
            sol: dict,
            assignments: dict[int, dict],
            bays: list[Bay],
            blocks_data: list[dict],
            w1: float, w2: float, w3: float,
            t_start: float,
            timelimit: float,
            max_passes: int = 10,
            repair_mode: str = "greedy") -> dict[int, dict]:
    """
    Iteratively detect infeasible blocks and repair them.

    Runs up to max_passes rounds of: check_feasibility -> collect violating
    block ids -> re-place them.  Stops early if the solution becomes feasible
    or 98% of timelimit is consumed.

    -- repair_mode="greedy" (default) ------------------------------------------
    Violating blocks are removed from assignments and re-placed using the full
    Phase-1 search (all bays, orientations, positions, time-slots).  The state
    arrays (bay_placed, bay_schedule, bay_loads) are reconstructed from the
    remaining non-violating assignments before each block is re-placed, so the
    search sees the current bay state.

    Cycle detection:
      repaired_counts[bid] tracks how many repair passes have touched block bid.
      If bid appears in a second pass (count > 1) it is added to forced_ids.
      Blocks in forced_ids skip search and go straight to _force_place (empty-
      bay window), which is structurally guaranteed to produce a crane-feasible
      placement.  This breaks cycles where two blocks keep displacing each other.

    Time guard (90% threshold):
      For each block in to_repair, if wall-clock time > 90% of timelimit before
      its turn, it is added to forced_ids.  This ensures all blocks are assigned
      before timeout rather than leaving some unassigned (Stage-1 failure).

    -- repair_mode="simple" -----------------------------------------------------
    Each violating block keeps its current (bay, x, y, orient) and is only
    pushed to the next empty-bay time window via _empty_bay_entry.  Stage-4
    violations (spatial collision) are also reset to position (0, 0).
    Faster than greedy mode, but cannot improve spatial placement quality.

    Parameters
    ----------
    prob_info   : instance JSON dict
    sol         : current solution dict (operations format)
    assignments : current assignment dict (block_id -> assignment dict)
    bays        : Bay objects
    blocks_data : raw block data from prob_info
    w1,w2,w3    : objective weights
    t_start     : wall-clock start time
    timelimit   : total wall-clock time limit
    max_passes  : maximum number of repair iterations
    repair_mode : "greedy" or "simple"

    Returns
    -------
    Updated assignments dict (all blocks assigned)
    """
    from utils import check_feasibility

    repaired_counts: dict[int, int] = {}
    forced_ids:      set[int]       = set()

    for pass_idx in range(max_passes):
        if time.time() - t_start > timelimit * 0.98:
            break

        result = check_feasibility(prob_info, sol)
        if result["feasible"]:
            break

        viols = result["violations"]
        elapsed_r = time.time() - t_start
        print(f"[Greedy] Repair pass {pass_idx+1}: {len(viols)} violation(s)  "
              f"stage={result['stage']}  elapsed={elapsed_r:.1f}s")

        # -- Parse block ids from violation messages ---------------------------
        # Each violation string contains "block <id>" somewhere in the text.
        # Deduplicate while preserving first-occurrence order.
        to_repair: list[int] = []
        seen: set[int] = set()
        for v in viols:
            try:
                bid = int(v.split("block ")[1].split()[0])
                if bid not in seen:
                    seen.add(bid)
                    to_repair.append(bid)
            except (IndexError, ValueError):
                pass

        if not to_repair:
            break

        # Re-place in EDD order so earlier-due blocks get the best slots first
        to_repair.sort(key=lambda b: (blocks_data[b]["due_date"],
                                      blocks_data[b]["processing_time"]))
        n_repl = len(to_repair)

        if repair_mode == "simple":
            # -- Simple mode: adjust only the time window, keep position/orient -
            # Rebuild the per-bay time schedule from all current assignments so
            # that _empty_bay_entry can find a gap with no other blocks present.
            n_bays = len(bays)
            bay_schedule: list[list[tuple[int, int]]] = [[] for _ in range(n_bays)]
            for a in assignments.values():
                bay_schedule[a["bay_id"]].append((a["entry_time"], a["exit_time"]))

            for ri, bid in enumerate(to_repair):
                a      = assignments[bid]
                bay_id = a["bay_id"]
                r_time = blocks_data[bid]["release_time"]
                proc   = blocks_data[bid]["processing_time"]

                # Remove the block's current slot before searching for a new one
                old_slot = (a["entry_time"], a["exit_time"])
                if old_slot in bay_schedule[bay_id]:
                    bay_schedule[bay_id].remove(old_slot)

                entry  = _empty_bay_entry(bay_schedule[bay_id], r_time, proc)
                exit_t = entry + proc

                # Stage-4 (spatial collision): also reset position to (0,0)
                # to eliminate any spatial overlap with other blocks
                x, y, oi = a["x"], a["y"], a["orient_idx"]
                if result["stage"] == 4:
                    x, y = 0, 0

                assignments[bid] = dict(a, x=x, y=y, orient_idx=oi,
                                        entry_time=int(round(entry)),
                                        exit_time=int(round(exit_t)))
                bay_schedule[bay_id].append((entry, exit_t))

                prev_t = f"[{a['entry_time']},{a['exit_time']})"
                new_t  = f"[{entry},{exit_t})"
                tag    = "[s4->(0,0)]" if result["stage"] == 4 else "[time]"
                elapsed_ri = time.time() - t_start
                print(f"[Greedy]   repair {ri+1:3d}/{n_repl}"
                      f"  block{bid:<4d} {tag}"
                      f"  bay{bay_id} ({int(x)},{int(y)})"
                      f"  {prev_t} -> {new_t}"
                      f"  elapsed={elapsed_ri:.1f}s")

        else:
            # -- Greedy mode: full Phase-1 re-search for violating blocks ------
            # Mark repeat offenders as forced before touching assignments, so
            # the flag is active when _place_blocks processes them below.
            for bid in to_repair:
                repaired_counts[bid] = repaired_counts.get(bid, 0) + 1
                if repaired_counts[bid] > 1:
                    forced_ids.add(bid)

            # Snapshot the violating blocks' current assignments BEFORE
            # popping them, so the _place_blocks fast-path can re-test each
            # block's previous (bay, x, y, orient) and the log tags show real
            # deltas.  (Previously the pop happened first, so
            # prev_assignments never contained the block and the documented
            # fast-path was dead code.)
            prev_snapshot = {bid: assignments[bid] for bid in to_repair
                             if bid in assignments}

            # Remove violating blocks from assignments so the state reconstruction
            # below does not include their (now invalid) positions/slots.
            for bid in to_repair:
                assignments.pop(bid, None)

            # Reconstruct bay_placed / bay_schedule / bay_loads from the
            # remaining valid assignments.  This gives _place_blocks an accurate
            # view of which positions and time-slots are already occupied.
            bay_placed, bay_schedule2, bay_loads = _rebuild_bay_state(
                assignments, bays, blocks_data
            )

            for ri, bi in enumerate(to_repair):
                # Time guard: switch to forced path when 90% of timelimit is used.
                # Without this, a slow repair search could exhaust the timelimit
                # before all blocks are placed, causing Stage-1 (assignment) failures.
                if time.time() - t_start > timelimit * max(0.90, _GUARD):
                    forced_ids.add(bi)
                prev_a  = prev_snapshot.get(bi)
                partial = _place_blocks(
                    [bi], blocks_data, bays,
                    bay_placed, bay_schedule2, bay_loads,
                    w1, w2, w3, forced_ids,
                    prev_assignments=prev_snapshot,
                    t_start=t_start, timelimit=timelimit,
                )
                assignments.update(partial)
                new_a       = partial[bi]
                is_forced   = bi in forced_ids
                changed_bay = prev_a and prev_a["bay_id"] != new_a["bay_id"]
                changed_pos = prev_a and (prev_a["x"] != new_a["x"]
                                          or prev_a["y"] != new_a["y"])
                tag = ("[forced]" if is_forced
                       else "[bay]" if changed_bay
                       else "[pos]" if changed_pos
                       else "[time]")
                prev_t = (f"[{int(prev_a['entry_time'])},{int(prev_a['exit_time'])})"
                          if prev_a else "N/A")
                new_t  = f"[{int(new_a['entry_time'])},{int(new_a['exit_time'])})"
                elapsed_ri = time.time() - t_start
                print(f"[Greedy]   repair {ri+1:3d}/{n_repl}"
                      f"  block{bi:<4d} {tag}"
                      f"  bay{new_a['bay_id']} ({int(new_a['x'])},{int(new_a['y'])})"
                      f"  {prev_t} -> {new_t}"
                      f"  elapsed={elapsed_ri:.1f}s")

        sol = {"operations": _build_operations(list(assignments.values()))}

    result = check_feasibility(prob_info, sol)
    status = "feasible" if result["feasible"] else f"INFEASIBLE stage={result['stage']}"
    obj    = f"obj={result['objective']:.0f}" if result["feasible"] else ""
    forced_note = f"  forced={len(forced_ids)}" if forced_ids else ""
    elapsed_done = time.time() - t_start
    print(f"[Greedy] Repair done  |  {status}  {obj}{forced_note}  elapsed={elapsed_done:.1f}s")

    return assignments


# -----------------------------------------------------------------------------
# Phase 3: local-search improvement
# -----------------------------------------------------------------------------

def _improve(
    assignments: dict[int, dict],
    bays: list[Bay],
    blocks_data: list[dict],
    w1: float, w2: float, w3: float,
    t_start: float,
    timelimit: float,
    time_budget_frac: float = 0.95,
    max_sweeps: int = 50,
) -> dict[int, dict]:
    """
    Post-feasibility local search: single-block removal + reinsertion.

    For each block (worst-first: highest tardiness + preference penalty),
    remove it from its current bay's state and re-run the Phase-1 search
    (_place_blocks with prev_assignments fast-path) for that one block.  The
    fast-path re-tests the block's own previous (bay, x, y, orient) via
    _find_earliest_slot against the reduced state, so it is always a valid
    candidate; the full search alongside it can only replace it with a
    strictly lower-scoring (and therefore also crane-feasible) placement.
    This makes every move a monotone improvement -- the caller should still
    run check_feasibility once on the final result as a safety net.

    Stops when a full sweep makes zero moves (local optimum), max_sweeps is
    reached, or time_budget_frac * timelimit of wall-clock time is used.

    Parameters
    ----------
    assignments : current (assumed feasible) assignment dict, mutated in place
                  and also returned
    bays, blocks_data, w1, w2, w3 : same as _place_blocks / _repair
    t_start, timelimit : wall-clock budget (shared with Phase 1/2)
    time_budget_frac   : fraction of timelimit this phase is allowed to use
    max_sweeps         : hard cap on full passes over all blocks

    Returns
    -------
    Updated assignments dict (same object as the input, for convenience)
    """
    n_blocks = len(blocks_data)
    bay_placed, bay_schedule, bay_loads = _rebuild_bay_state(assignments, bays, blocks_data)

    order = list(range(n_blocks))
    deadline = t_start + timelimit * time_budget_frac

    def _badness(bi: int) -> float:
        a = assignments[bi]
        blk_data = blocks_data[bi]
        tardiness = max(0.0, a["exit_time"] - blk_data["due_date"])
        pref_pen  = max(blk_data["bay_preferences"]) - blk_data["bay_preferences"][a["bay_id"]]
        return w1 * tardiness + w3 * pref_pen

    sweep = 0
    n_moved_total = 0
    for sweep in range(1, max_sweeps + 1):
        if time.time() > deadline:
            break

        # Worst-first ordering so the time budget goes to the biggest
        # objective offenders first.
        order.sort(key=_badness, reverse=True)

        n_moved = 0
        for bi in order:
            if time.time() > deadline:
                break

            a      = assignments[bi]
            bay_id = a["bay_id"]
            placed_in_bay = bay_placed[bay_id]

            # Remove bi from its bay's state so the search below sees the
            # same view Phase 1 would have without this block already placed.
            ridx = next(i for i, b in enumerate(placed_in_bay) if b.block_id == bi)
            placed_in_bay.pop(ridx)
            bay_schedule[bay_id].pop(ridx)
            bay_loads[bay_id] -= blocks_data[bi]["workload"]

            # t_start/timelimit/time_guard_frac wire in the same mid-search
            # circuit breaker _place_blocks uses elsewhere, so one slow block
            # late in a sweep can't blow past this phase's own deadline the
            # way an unbounded full search otherwise could.  This is safe
            # here specifically because the fast-path above always evaluates
            # the block's own previous (no-worse) placement first, so cutting
            # the full search short still leaves best_placement set to at
            # least that -- it never falls through to the destructive
            # _force_place fallback in practice.
            partial = _place_blocks(
                [bi], blocks_data, bays,
                bay_placed, bay_schedule, bay_loads,
                w1, w2, w3, forced_ids=set(),
                prev_assignments=assignments,
                t_start=t_start, timelimit=timelimit,
                time_guard_frac=time_budget_frac,
            )
            new_a = partial[bi]
            moved = (new_a["bay_id"], new_a["x"], new_a["y"],
                     new_a["orient_idx"], new_a["entry_time"]) != \
                    (a["bay_id"], a["x"], a["y"], a["orient_idx"], a["entry_time"])
            if moved:
                n_moved += 1
            assignments[bi] = new_a

        n_moved_total += n_moved
        elapsed = time.time() - t_start
        print(f"[Greedy]   improve sweep {sweep}: {n_moved} move(s)  elapsed={elapsed:.1f}s")
        if n_moved == 0:
            break

    print(f"[Greedy] Improve done  |  sweeps={sweep}  total_moves={n_moved_total}  "
          f"elapsed={time.time() - t_start:.1f}s")
    return assignments


# -----------------------------------------------------------------------------
# Build operations dict from assignments
# -----------------------------------------------------------------------------

def _build_operations(assignments: list[dict]) -> dict:
    """
    Build the "operations" dict from a flat list of assignment dicts.

    Groups operations by integer time-point into buckets, sorts each bucket
    so that EXIT operations precede ENTRY operations at the same time, and
    within each type sorts by block_id for deterministic ordering.

    Bucket tuple format: (sort_key, type_str, block_id, bay_id, x, y, orient_idx)
      sort_key = 0 for EXIT  -> sorts before
      sort_key = 1 for ENTRY -> sorts after
    The sort key ensures EXIT-before-ENTRY without explicit type-string comparison.

    The returned dict maps str(time_int) -> list of operation dicts, ordered as
    required by check_feasibility (EXIT ops first within each time-point).
    """
    buckets: dict[int, list[tuple]] = {}
    for a in assignments:
        t_entry = int(a["entry_time"])
        t_exit  = int(a["exit_time"])
        bid     = a["block_id"]
        bay     = a["bay_id"]
        buckets.setdefault(t_exit,  []).append((0, "EXIT",  bid, bay, None,    None,    None))
        buckets.setdefault(t_entry, []).append((1, "ENTRY", bid, bay, a["x"], a["y"], a["orient_idx"]))

    operations: dict[str, list[dict]] = {}
    for t in sorted(buckets):
        ops = sorted(buckets[t], key=lambda x: (x[0], x[2]))
        result = []
        for _, kind, bid, bay, x, y, orient_idx in ops:
            op: dict = {"type": kind, "block_id": bid, "bay_id": bay}
            if kind == "ENTRY":
                op["x"] = x
                op["y"] = y
                op["orient_idx"] = orient_idx
            result.append(op)
        operations[str(t)] = result
    return operations


# -----------------------------------------------------------------------------
# CLI run
# -----------------------------------------------------------------------------

def parallel_seed_worker(prob_info, timelimit, strategy):
    import time
    from utils import check_feasibility
    sol = greedyalgorithm(prob_info, timelimit=timelimit, improve=False, strategy=strategy)
    chk_start = time.monotonic()
    check = check_feasibility(prob_info, sol)
    chk_cost = time.monotonic() - chk_start
    return sol, check, chk_cost

if __name__ == "__main__":
    import argparse
    import json
    import pathlib
    from collections import defaultdict
    from utils import check_feasibility

    parser = argparse.ArgumentParser(description="EDD greedy algorithm smoke test")
    parser.add_argument("instance", help="path to instance JSON file")
    parser.add_argument("--timelimit", type=float, default=60.0,
                        help="wall-clock time limit in seconds (default: %(default)s)")
    parser.add_argument("--repair", choices=["greedy", "simple"], default="greedy",
                        help="repair mode (default: %(default)s)")
    args = parser.parse_args()

    inst_file = pathlib.Path(args.instance)

    with open(inst_file) as f:
        prob_info = json.load(f)

    t0  = time.time()
    sol = greedyalgorithm(prob_info, timelimit=args.timelimit, repair_mode=args.repair)
    elapsed = time.time() - t0

    result = check_feasibility(prob_info, sol)

    n_assigned = sum(1 for ops in sol["operations"].values()
                     for op in ops if op["type"] == "ENTRY")
    print(f"Instance : {prob_info['name']}")
    print(f"Elapsed  : {elapsed:.3f}s")
    print(f"Assigned : {n_assigned} / {len(prob_info['blocks'])} blocks")
    print(f"Feasible : {result['feasible']}  (stage={result['stage']})")
    if result["feasible"]:
        print(f"Objective: {result['objective']:.2f}  "
              f"(obj1={result['obj1']:.1f}, obj2={result['obj2']:.1f}, obj3={result['obj3']:.1f})")
    else:
        for v in result["violations"][:10]:
            print(f"  VIOLATION: {v}")
