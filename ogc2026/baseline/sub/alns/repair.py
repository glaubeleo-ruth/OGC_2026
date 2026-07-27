"""
repair.py -- ALNS repair operators built on top of the greedy placement
kernel (`baseline_greedy._place_blocks`) and, optionally, a bounded
single-bay OR-Tools CP-SAT repack.

baseline/ is not a package -- baseline/myalgorithm.py does a bare
`import baseline_greedy`, so baseline/ is expected to be on sys.path.  This
module adds it before importing sibling modules so it works whether it's
run as a script, imported as `alns.repair`, or imported after baseline/ has
already been added to sys.path by something else (matches the convention
already used by alns/state.py and alns/evaluate.py).

Solver choice: OR-Tools CP-SAT, not Gurobi. This module originally used
gurobipy, but the Gurobi install available in this environment is a
restricted/size-limited license -- it rejects any model above a small
variable/constraint count, which in practice meant nearly every call on a
realistic bay size failed with `GurobiError: Model too large for
size-limited license` and fell through to the greedy fallback anyway, after
still paying for the collision scan and partial model build first. CP-SAT
is already a pinned dependency (`ortools==9.15.6755` in ogc2026_env.yml, so
guaranteed present wherever this runs, including the eval server) with no
license or size restriction, and its boolean-variable-plus-conflict-
constraint structure is a natural fit for this exact model (one bool per
block-candidate, `AddExactlyOne` per block, `AddAtMostOne` per colliding
pair) -- see `_milp_repack_impl` for the formulation, unchanged from the
Gurobi version except for the solver API itself.

Public contract
----------------
- `greedy_repair(state, removed, timelimit=None) -> SolutionState`
    Re-inserts `removed` block_ids into `state` via
    `baseline_greedy._place_blocks`, in EDD order. Mutates `state` in place
    and returns it.

- `milp_repack(state, bay_id, time_cap, deadline=None) -> SolutionState`
    Bounded single-bay MILP repack via OR-Tools CP-SAT. ALWAYS returns a
    state with internally consistent assignments; falls back to
    `greedy_repair` if OR-Tools is unavailable, the model raises, times out,
    or fails to find a feasible solution -- see its docstring for the exact
    scoped-down formulation implemented here and why. `deadline` (optional
    alns.deadline.Deadline, WATCHDOG_SPEC.md) additionally bounds the
    needs_disjoint scan and guards the final check_feasibility re-verify --
    see _milp_repack_impl's docstring.
"""

import os
import sys
import time

_BASELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASELINE_DIR not in sys.path:
    sys.path.insert(0, _BASELINE_DIR)

import baseline_greedy  # noqa: E402  (import after sys.path fixup, by design)
import utils  # noqa: E402

try:
    from alns.state import SolutionState  # noqa: E402  (matches destroy.py's convention)
except ImportError:  # pragma: no cover - alternate import path (run as a script from alns/)
    from state import SolutionState  # noqa: E402

try:
    from ortools.sat.python import cp_model
    _ORTOOLS_AVAILABLE = True
except ImportError:
    _ORTOOLS_AVAILABLE = False


# Bound for milp_repack's greedy_repair fallback (OR-Tools unavailable/
# raised/found no solution within time_cap). This path re-inserts every
# block CURRENTLY IN THE BAY (not just a small destroy batch --
# state.remove(bay_block_ids) above), so on a busy bay it's the same
# unbounded-single-block-search risk greedy_repair's own docstring
# describes, just over many more blocks at once -- worth a real cap even
# though this path should fire far less often now than it did under the
# size-limited Gurobi license.
_MILP_FALLBACK_GREEDY_TIME_CAP_S = 3.0


# -----------------------------------------------------------------------------
# greedy_repair
# -----------------------------------------------------------------------------

def greedy_repair(
    state: SolutionState,
    removed: list[int],
    timelimit: float | None = None,
) -> SolutionState:
    """
    Re-insert `removed` block_ids into `state` using
    `baseline_greedy._place_blocks`, reusing state's current
    bay_placed/bay_schedule/bay_loads (which already reflect the partial
    solution -- the removed blocks are already absent, per the destroy
    operator contract).

    Ordering matches baseline_greedy's own Phase-1 EDD convention:
    sorted by (due_date, processing_time).

    `prev_assignments=state.assignments` is passed so `_place_blocks`'s
    repair fast-path can try each block's old position first when it's
    still feasible; blocks not present in state.assignments (i.e. exactly
    the ones just removed) are handled fine by the full search per
    `_place_blocks`'s docstring.

    Mutates `state` in place (bay_placed/bay_schedule/bay_loads are updated
    by `_place_blocks`, then each `state.insert(...)` call rebuilds those
    same structures from `state.assignments` from scratch -- redundant but
    harmless, matching how state.py already works). Returns `state` for
    chaining convenience.

    `t_start` is always set to "now" (not left None) before calling
    `_place_blocks`, regardless of whether `timelimit` is given. This matters:
    `_place_blocks`'s own mid-search time guard is gated on
    `t_start is not None AND timelimit is not None` -- passing `t_start=None`
    (as this function used to, unconditionally) silently disables that guard
    even when a caller supplies a real `timelimit`, letting a single block's
    full search run unbounded in a busy bay (empirically: 10-16s for one
    block on a training instance). `timelimit=None` still means "no bound",
    same as before -- only `t_start` changed.
    """
    if not removed:
        return state

    blocks_data = state.blocks_data
    weights = state.prob_info["weights"]
    w1, w2, w3 = weights["w1"], weights["w2"], weights["w3"]

    ordered = sorted(removed, key=lambda i: (blocks_data[i]["due_date"], blocks_data[i]["processing_time"]))

    new_assignments = baseline_greedy._place_blocks(
        ordered,
        blocks_data,
        state.bays,
        state.bay_placed,
        state.bay_schedule,
        state.bay_loads,
        w1, w2, w3,
        forced_ids=set(),
        prev_assignments=state.assignments,
        t_start=time.time(),
        log_interval=0,
        timelimit=timelimit,
    )

    state.insert_many(list(new_assignments.values()))

    return state


def greedy_repair_area(
    state: SolutionState,
    removed: list[int],
    timelimit: float | None = None,
) -> SolutionState:
    """
    Re-insert `removed` block_ids into `state` using `baseline_greedy._place_blocks`,
    but sorted by Bounding Box Area descending (largest blocks placed first).
    """
    if not removed:
        return state

    blocks_data = state.blocks_data
    weights = state.prob_info["weights"]
    w1, w2, w3 = weights["w1"], weights["w2"], weights["w3"]

    def area(bid: int) -> float:
        bdata = blocks_data[bid]
        min_x, min_y, max_x, max_y = baseline_greedy._block_bbox(bdata, 0)
        return (max_x - min_x) * (max_y - min_y)

    ordered = sorted(removed, key=lambda i: (-area(i), blocks_data[i]["processing_time"]))

    new_assignments = baseline_greedy._place_blocks(
        ordered,
        blocks_data,
        state.bays,
        state.bay_placed,
        state.bay_schedule,
        state.bay_loads,
        w1, w2, w3,
        forced_ids=set(),
        prev_assignments=state.assignments,
        t_start=time.time(),
        log_interval=0,
        timelimit=timelimit,
    )

    state.insert_many(list(new_assignments.values()))

    return state


def greedy_repair_random(
    state: SolutionState,
    removed: list[int],
    timelimit: float | None = None,
    rng_seed: int = 42,
) -> SolutionState:
    """
    Re-insert `removed` block_ids into `state` using `baseline_greedy._place_blocks`,
    but sorted randomly to inject pure spatial diversity.
    """
    import random
    if not removed:
        return state

    blocks_data = state.blocks_data
    weights = state.prob_info["weights"]
    w1, w2, w3 = weights["w1"], weights["w2"], weights["w3"]

    rng = random.Random(rng_seed)
    ordered = list(removed)
    rng.shuffle(ordered)

    new_assignments = baseline_greedy._place_blocks(
        ordered,
        blocks_data,
        state.bays,
        state.bay_placed,
        state.bay_schedule,
        state.bay_loads,
        w1, w2, w3,
        forced_ids=set(),
        prev_assignments=state.assignments,
        t_start=time.time(),
        log_interval=0,
        timelimit=timelimit,
    )

    state.insert_many(list(new_assignments.values()))

    return state


def greedy_repair_volume(
    state: SolutionState,
    removed: list[int],
    timelimit: float | None = None,
) -> SolutionState:
    """
    Re-insert `removed` block_ids into `state` using `baseline_greedy._place_blocks`,
    but sorted by Space-Time Volume (Area * Processing Time) descending.
    """
    if not removed:
        return state

    blocks_data = state.blocks_data
    weights = state.prob_info["weights"]
    w1, w2, w3 = weights["w1"], weights["w2"], weights["w3"]

    def volume(bid: int) -> float:
        bdata = blocks_data[bid]
        min_x, min_y, max_x, max_y = baseline_greedy._block_bbox(bdata, 0)
        area = (max_x - min_x) * (max_y - min_y)
        return area * bdata["processing_time"]

    ordered = sorted(removed, key=lambda i: (-volume(i), blocks_data[i]["due_date"]))

    new_assignments = baseline_greedy._place_blocks(
        ordered,
        blocks_data,
        state.bays,
        state.bay_placed,
        state.bay_schedule,
        state.bay_loads,
        w1, w2, w3,
        forced_ids=set(),
        prev_assignments=state.assignments,
        t_start=time.time(),
        log_interval=0,
        timelimit=timelimit,
    )

    state.insert_many(list(new_assignments.values()))

    return state


def force_place_tardy(
    state: SolutionState,
    removed: list[int],
    timelimit: float | None = None,
) -> SolutionState:
    """
    Force-placement repair aimed squarely at tardiness.

    Re-inserts `removed` block_ids one at a time via
    `baseline_greedy._place_blocks`, ordered by ASCENDING slack
    (`slack = due_date - release_time - processing_time`), tie-broken by
    due_date. Slack is exactly "how much room this block has before it is
    forced to be tardy": the tightest-slack blocks go in FIRST, while the bay
    just opened up by a trap-aware destroy is still empty, so they claim the
    earliest crane-feasible exit slot. Later, looser blocks pack in around
    them.

    Two deliberate differences from `greedy_repair`:
      * slack ordering instead of EDD (due_date, proc) -- EDD orders by
        deadline alone; slack also accounts for how late a block is released
        and how long it occupies the bay, which is what actually drives
        whether it CAN make its due date here.
      * `prev_assignments=None` -- do NOT offer each block its previous
        (bay, x, y, orient) as a fast-path first choice. A block that a
        trap-aware destroy just freed was tardy precisely because its old
        slot trapped it; re-pinning it there defeats the point. A fresh full
        search lets it find its new earliest-exit position.

    `_placement_score` is dominated by `w1 * tardiness` (w1 ~ 29091 vs w2 ~ 7,
    w3 ~ 200 on prob_1), so "the slot the kernel picks" is already "the
    least-tardy slot" -- this operator just controls WHICH blocks get first
    pick of it. Mutates `state` in place and returns it.
    """
    if not removed:
        return state

    blocks_data = state.blocks_data
    weights = state.prob_info["weights"]
    w1, w2, w3 = weights["w1"], weights["w2"], weights["w3"]

    def slack(bid: int) -> int:
        b = blocks_data[bid]
        return b["due_date"] - b["release_time"] - b["processing_time"]

    ordered = sorted(removed, key=lambda i: (slack(i), blocks_data[i]["due_date"]))

    new_assignments = baseline_greedy._place_blocks(
        ordered,
        blocks_data,
        state.bays,
        state.bay_placed,
        state.bay_schedule,
        state.bay_loads,
        w1, w2, w3,
        forced_ids=set(),
        prev_assignments=None,
        t_start=time.time(),
        log_interval=0,
        timelimit=timelimit,
    )

    state.insert_many(list(new_assignments.values()))

    return state


# -----------------------------------------------------------------------------
# milp_repack
# -----------------------------------------------------------------------------

def milp_repack(
    state: SolutionState,
    bay_id: int,
    time_cap: float,
    deadline=None,
) -> SolutionState:
    """
    Bounded, single-bay MILP repack of the blocks currently assigned to
    `bay_id`, via OR-Tools CP-SAT. Falls back to `greedy_repair` (always
    feasible, per state.py's own guarantees plus a final check_feasibility
    re-verify here) whenever OR-Tools is unavailable, the model raises,
    times out, finds nothing, or its result turns out infeasible under the
    true crane-collision rules. This fallback path is the hard requirement:
    this function must never return a broken/partially-applied state and
    must never raise out to the caller.

    `deadline` : optional alns.deadline.Deadline (WATCHDOG_SPEC.md). Passed
    through to `_milp_repack_impl`, which uses it to (a) bound the
    needs_disjoint collision scan at inner-loop granularity, not just the
    outer loop, and (b) skip the final whole-state check_feasibility
    re-verify entirely if it plausibly can't finish before the deadline --
    see `_milp_repack_impl`'s docstring for both.

    Scoped-down formulation actually implemented (deliberately narrower
    than the "full pairwise candidate-position exclusion" scope sketched in
    the task brief):

      For each block currently in `bay_id`, keep its (bay_id, x, y,
      orient_idx) FIXED at its current placement (i.e. do not re-search
      candidate positions/orientations at all -- that full spatial search
      is exactly what `greedy_repair`/`baseline_greedy._place_blocks`
      already does well, and re-deriving it as a MILP variable set adds a
      lot of pairwise-geometry-exclusion machinery for a small, single-bay
      instance that is unlikely to move the needle). The MILP only decides
      each block's ENTRY TIME among a small discrete candidate set (the
      block's current entry_time, its release_time, and every other block's
      exit_time within the bay that is >= release_time -- the same
      candidate-entry universe `_find_earliest_slot` enumerates), subject
      to a time-disjointness pairwise exclusion applied ONLY to pairs of
      blocks whose FIXED footprints actually spatially collide (checked
      once, up front, via `utils.check_collisions` on their fixed
      x/y/orient_idx -- not per candidate, since position doesn't change).
      Footprint-disjoint pairs are left unconstrained and may legitimately
      overlap in time, exactly as they could in the original solution (two
      blocks sitting side by side in the same bay coexist in time all the
      time -- requiring universal time-disjointness was tried first and
      immediately over-constrained the model into infeasibility on this
      test instance, since the seed solution already has several
      time-overlapping, footprint-disjoint block pairs in the same bay).
      For colliding pairs, time-disjointness is the correct and exact
      exclusion (two blocks with overlapping fixed footprints can never
      coexist, regardless of chosen entry times). This proxy is a
      necessary-but-not-sufficient condition for true crane-rule
      feasibility (it doesn't model entry/exit sweep interactions between
      footprint-disjoint blocks at different heights) -- the final
      whole-state `check_feasibility` re-verify in step (e) below is the
      authoritative safety net that catches anything this proxy misses
      before ever committing the result.

      Objective: minimize total tardiness sum(max(0, entry+proc-due) *
      choice_var) over candidates -- tardiness per (block, candidate) is a
      known constant once the candidate entry_time is fixed, so this is a
      straight linear objective, no max() needed inside the solver.

    This is the simpler-but-real fallback formulation the task brief
    explicitly allows in lieu of the full candidate-position + pairwise
    spatial-exclusion MILP, chosen because: (1) position/orientation search
    is already well handled by the greedy kernel and re-encoding it as MILP
    variables adds substantial candidate-generation and pairwise
    check_collisions/check_entry/check_exit bookkeeping for uncertain
    payoff on a 2-bay/10-block instance, and (2) fixed-position
    time-disjointness is a clean, exactly-correct exclusion rule (not an
    approximation of geometry -- it's implied by the fixed footprints truly
    not moving), which keeps the "never return a broken state" requirement
    easy to satisfy with high confidence, with the mandatory
    check_feasibility re-verify as the final safety net regardless.
    """
    bay_block_ids = [bid for bid, a in state.assignments.items() if a["bay_id"] == bay_id]
    if not bay_block_ids:
        return state

    if not _ORTOOLS_AVAILABLE:
        print(f"[milp_repack] bay={bay_id}: ortools unavailable -> greedy fallback")
        import random
        fallback_choices = [greedy_repair, greedy_repair_area, greedy_repair_random, greedy_repair_volume]
        chosen_fallback = random.choice(fallback_choices)
        return chosen_fallback(state, bay_block_ids, timelimit=_MILP_FALLBACK_GREEDY_TIME_CAP_S)

    removed_assignments = state.remove(bay_block_ids)

    try:
        result_state = _milp_repack_impl(state, bay_id, bay_block_ids, removed_assignments, time_cap, deadline)
        if result_state is not None:
            print(f"[milp_repack] bay={bay_id}: MILP path taken "
                  f"({len(bay_block_ids)} blocks, time_cap={time_cap}s)")
            return result_state
    except Exception as exc:
        print(f"[milp_repack] bay={bay_id}: MILP raised {type(exc).__name__}: {exc} -> greedy fallback")
    else:
        print(f"[milp_repack] bay={bay_id}: MILP found no usable/feasible result -> greedy fallback")

    # Fallback: make sure the bay's blocks are absent (they may have been
    # partially re-inserted by a failed MILP attempt before an exception),
    # then hand off to greedy_repair for a guaranteed-feasible result.
    for bid in bay_block_ids:
        if bid in state.assignments:
            state.remove([bid])
    import random
    fallback_choices = [greedy_repair, greedy_repair_area, greedy_repair_random, greedy_repair_volume]
    chosen_fallback = random.choice(fallback_choices)
    return chosen_fallback(state, bay_block_ids, timelimit=_MILP_FALLBACK_GREEDY_TIME_CAP_S)


def _milp_repack_impl(
    state: SolutionState,
    bay_id: int,
    bay_block_ids: list[int],
    removed_assignments: dict[int, dict],
    time_cap: float,
    deadline=None,
) -> SolutionState | None:
    """
    Build and solve the fixed-position / variable-entry-time MILP described
    in milp_repack's docstring. Returns the mutated `state` (with the MILP
    result inserted and re-verified feasible) on success, or None to signal
    "no usable result -- caller should fall back to greedy_repair". Never
    leaves `state` partially mutated with an inconsistent bay -- on any
    early return of None, `state` still has `bay_block_ids` fully absent
    (matching the post-`state.remove(...)` shape the caller already set up).

    `deadline` (WATCHDOG_SPEC.md, optional): used two ways.
      (a) The needs_disjoint collision scan checks `build_deadline` at
          INNER-loop granularity (every 64 pairs, same cadence as the
          constraint-building loop below it), not just once per outer
          `bid_a` -- a single outer step can otherwise still run up to
          len(bay_block_ids)-1 Shapely calls before the next check fires.
      (b) The final whole-state check_feasibility re-verify is skipped
          entirely (treated as "no usable result") if
          `deadline.can_afford_check()` is False, rather than starting a
          check that plausibly can't finish before the deadline.
    """
    blocks_data = state.blocks_data
    bay = state.bays[bay_id]
    weights = state.prob_info["weights"]
    w1 = weights["w1"]

    # -- Build candidate entry-time sets per block, at each block's fixed
    #    (x, y, orient_idx) taken from its removed (pre-repack) placement. --
    fixed_pos: dict[int, tuple[int, int, int]] = {}
    procs: dict[int, int] = {}
    releases: dict[int, int] = {}
    dues: dict[int, int] = {}
    for bid in bay_block_ids:
        a = removed_assignments[bid]
        fixed_pos[bid] = (int(a["x"]), int(a["y"]), int(a["orient_idx"]))
        procs[bid] = blocks_data[bid]["processing_time"]
        releases[bid] = blocks_data[bid]["release_time"]
        dues[bid] = blocks_data[bid]["due_date"]

    # Candidate entry times: each block's own release_time and previous
    # entry_time, plus every other bay block's release_time (a natural set
    # of "interesting" points to slot an entry after), deduplicated and
    # filtered to >= release_time for that block.
    base_times = sorted({releases[bid] for bid in bay_block_ids} |
                         {int(removed_assignments[bid]["entry_time"]) for bid in bay_block_ids})

    candidates: dict[int, list[tuple[int, int, int]]] = {}  # bid -> [(entry, exit, tardiness), ...]
    for bid in bay_block_ids:
        r = releases[bid]
        proc = procs[bid]
        due = dues[bid]
        entries = sorted({t for t in base_times if t >= r} | {r})
        cand_list = []
        for e in entries:
            exit_t = e + proc
            tardiness = max(0, exit_t - due)
            cand_list.append((e, exit_t, tardiness))
        if not cand_list:
            return None
        candidates[bid] = cand_list

    # -- Determine which PAIRS of blocks actually need a time-disjointness
    #    constraint at all. Fixed positions come from a previously-feasible
    #    solution, where blocks routinely coexist in time at NON-overlapping
    #    footprints (e.g. two blocks side by side in the same bay) -- so
    #    requiring full time-disjointness between every pair unconditionally
    #    is wrong and over-constrains the model into infeasibility. Only
    #    pairs whose fixed footprints actually spatially collide (via
    #    utils.check_collisions at their fixed x/y/orient_idx) need to be
    #    kept time-disjoint; footprint-disjoint pairs may overlap in time
    #    exactly as they did in the original solution. This is a necessary
    #    (not sufficient) condition for true crane-rule feasibility --
    #    check_feasibility at the end is still the authoritative safety net
    #    for any residual crane-sweep interaction this proxy misses.
    fixed_blocks: dict[int, utils.Block] = {
        bid: utils.Block(block_id=bid, block_data=blocks_data[bid],
                          x=fixed_pos[bid][0], y=fixed_pos[bid][1], orient_idx=fixed_pos[bid][2])
        for bid in bay_block_ids
    }
    # Wall-clock budget for MODEL CONSTRUCTION (as opposed to the solve
    # itself, which solver.parameters.max_time_in_seconds below already
    # bounds). This is necessary, not defensive: on a busy bay (observed:
    # 164 blocks, 11359 footprint-colliding pairs -> 315M candidate-entry-
    # pair checks in the nested loop below) building the pairwise time-
    # disjointness constraints took 55s by itself, entirely independent of
    # `time_cap`, since CP-SAT's max_time_in_seconds only governs
    # solver.Solve(), not the Python-side AddAtMostOne() calls that happen
    # before it -- this is a property of building the model in Python at
    # all, not specific to which solver eventually runs it. Half of
    # time_cap goes to construction (collision scan + constraint building
    # combined), leaving the rest for solve + extract + the mandatory final
    # check_feasibility re-verify. Exceeding it aborts the MILP attempt
    # (return None) rather than handing the solver a colossal already-built
    # model and hoping the time limit saves the day -- it wouldn't, since
    # the overrun already happened before Solve() was ever called.
    build_deadline = time.time() + max(0.3, float(time_cap) * 0.5)

    needs_disjoint: set[tuple[int, int]] = set()
    scan_pair_count = 0
    for i, bid_a in enumerate(bay_block_ids):
        if time.time() > build_deadline:
            return None
        for bid_b in bay_block_ids[i + 1:]:
            scan_pair_count += 1
            if scan_pair_count % 64 == 0 and time.time() > build_deadline:
                return None
            if utils.check_collisions(bay, [fixed_blocks[bid_a], fixed_blocks[bid_b]]):
                needs_disjoint.add((bid_a, bid_b))

    model = cp_model.CpModel()

    choice = {}  # (bid, cand_idx) -> BoolVar
    for bid in bay_block_ids:
        for ci in range(len(candidates[bid])):
            choice[(bid, ci)] = model.NewBoolVar(f"x_{bid}_{ci}")

    # Exactly one candidate per block.
    for bid in bay_block_ids:
        model.AddExactlyOne(choice[(bid, ci)] for ci in range(len(candidates[bid])))

    # Pairwise time-disjointness exclusion, restricted to footprint-colliding
    # pairs (see needs_disjoint above): two such blocks' chosen [entry,
    # exit_t) intervals must not overlap, since their fixed footprints would
    # otherwise co-occupy the same space at the same time.
    for pair_idx, (bid_a, bid_b) in enumerate(needs_disjoint):
        if pair_idx % 64 == 0 and time.time() > build_deadline:
            return None
        for ci_a, (ea, xa, _) in enumerate(candidates[bid_a]):
            for ci_b, (eb, xb, _) in enumerate(candidates[bid_b]):
                if baseline_greedy._time_overlaps(ea, xa, eb, xb):
                    model.AddAtMostOne([choice[(bid_a, ci_a)], choice[(bid_b, ci_b)]])

    # Objective: minimize total tardiness (linear -- tardiness per
    # candidate is a precomputed constant).
    model.Minimize(sum(
        candidates[bid][ci][2] * choice[(bid, ci)]
        for bid in bay_block_ids
        for ci in range(len(candidates[bid]))
    ))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.1, float(time_cap))
    # This is one bounded-time solve within an otherwise single-threaded
    # algorithm; using the full eval-server core allowance (<=4, per
    # CLAUDE.md) here buys better solution quality within max_time_in_seconds
    # rather than a longer runtime, since the wall-clock bound is fixed
    # regardless of worker count.
    solver.parameters.num_search_workers = 4
    solver.parameters.log_search_progress = False
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    # Extract chosen candidate per block and build assignment dicts.
    chosen: dict[int, dict] = {}
    for bid in bay_block_ids:
        picked = None
        for ci in range(len(candidates[bid])):
            if solver.Value(choice[(bid, ci)]) == 1:
                picked = ci
                break
        if picked is None:
            return None  # shouldn't happen given the ExactlyOne constraint, but be defensive
        x, y, orient_idx = fixed_pos[bid]
        entry, exit_t, _ = candidates[bid][picked]
        chosen[bid] = {
            "block_id": bid,
            "bay_id": bay_id,
            "x": int(round(x)),
            "y": int(round(y)),
            "orient_idx": orient_idx,
            "entry_time": int(round(entry)),
            "exit_time": int(round(exit_t)),
        }

    for assignment in chosen.values():
        state.insert(assignment)

    # Guard the final re-verify with the shared deadline's est_check_cost
    # estimate (WATCHDOG_SPEC.md hot spot #3): if it plausibly can't finish
    # before the deadline, don't attempt it -- discard the MILP result and
    # let the caller's greedy_repair fallback (itself bounded) handle it,
    # rather than risk an uncapped check_feasibility call blowing the
    # budget right at the end of an already-long MILP attempt.
    if deadline is not None and not deadline.can_afford_check():
        for bid in bay_block_ids:
            if bid in state.assignments:
                state.remove([bid])
        return None

    # Final safety net: re-verify the WHOLE current state against the true
    # crane-collision rules. The pairwise time-disjointness exclusion above
    # is a conservative proxy, not a re-implementation of check_entry/
    # check_exit/check_collisions, so this is required, not optional.
    # NOTE: SolutionState.to_operations() returns the unwrapped
    # {"<time>": [op, ...]} mapping (baseline_greedy._build_operations'
    # own return shape), not the {"operations": {...}} wire-format solution
    # dict check_feasibility expects -- wrap it here (matches the
    # convention already established in alns/_smoke_test.py).
    feasible = utils.check_feasibility(
        state.prob_info, {"operations": state.to_operations()}
    )["feasible"]
    if not feasible:
        # Discard the MILP result: remove these block_ids again so the
        # caller's fallback path (greedy_repair) starts from the same
        # clean partial-solution shape it always expects.
        for bid in bay_block_ids:
            if bid in state.assignments:
                state.remove([bid])
        return None

    return state
