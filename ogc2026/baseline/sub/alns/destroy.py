"""
destroy.py -- ALNS destroy operators for the OGC 2026 shipyard solver.

Each operator has the signature

    def <name>(state: SolutionState, rng_seed: int, k: int) -> list[int]

and MUTATES `state` in place by calling `state.remove(...)` internally
(the operator never clones `state` itself -- cloning is the caller's
decision). Each operator returns the list of block_ids it removed.

If `k >= len(state.assignments)`, every currently-assigned block is
removed (there is no over-large-k error case, callers may safely pass an
oversized k to mean "destroy everything").

All randomness goes through a local `random.Random(rng_seed)` instance --
these operators never read or mutate the global `random` module state, so
repeated calls with the same seed on equivalent states are reproducible.

baseline/ is not a package -- this module adds baseline/ to sys.path the
same way alns/state.py does, so it works whether it's imported as
`alns.destroy`, run as a script, or imported after baseline/ has already
been put on sys.path by something else.
"""

import os
import sys

_BASELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASELINE_DIR not in sys.path:
    sys.path.insert(0, _BASELINE_DIR)

import random

import utils

from alns.state import SolutionState


def _cap(state: SolutionState, k: int) -> int:
    """Clamp k to the number of currently-assigned blocks (never negative)."""
    return max(0, min(k, len(state.assignments)))


# ---------------------------------------------------------------------------
# 1. worst_tardiness
# ---------------------------------------------------------------------------

def worst_tardiness(state: SolutionState, rng_seed: int, k: int) -> list[int]:
    """
    Remove the `min(k, len(state.assignments))` currently-assigned blocks
    with the largest tardiness.

    Tardiness for block `bid` is `max(0, exit_time - due_date)`, where
    `exit_time` comes from `state.assignments[bid]["exit_time"]` and
    `due_date` comes from `state.blocks_data[bid]["due_date"]`.

    Blocks are ranked by tardiness descending; ties are broken by
    ascending block_id for determinism. `rng_seed` is accepted (and
    unused) purely for signature/API consistency with the other
    operators -- this operator is fully deterministic given `state` and
    `k`.

    Mutates `state` via `state.remove(...)` and returns the removed
    block_ids in removal order (worst tardiness first).
    """
    n = _cap(state, k)
    if n == 0:
        return []

    def tardiness(bid: int) -> float:
        a = state.assignments[bid]
        due = state.blocks_data[bid]["due_date"]
        return max(0.0, a["exit_time"] - due)

    ranked = sorted(state.assignments.keys(), key=lambda bid: (-tardiness(bid), bid))
    victims = ranked[:n]
    state.remove(victims)
    return victims


# ---------------------------------------------------------------------------
# 2. random_k
# ---------------------------------------------------------------------------

def random_k(state: SolutionState, rng_seed: int, k: int) -> list[int]:
    """
    Uniformly sample `min(k, len(state.assignments))` block_ids (without
    replacement) from `state.assignments.keys()` using
    `random.Random(rng_seed).sample(...)`, remove them from `state`, and
    return the sampled block_ids (in the order `sample()` returns them).

    Keys are sorted before sampling so that the candidate order fed to
    `sample()` is deterministic across Python versions/runs (dict
    iteration order is insertion order in CPython, but sorting removes
    any dependence on how `state.assignments` was built).
    """
    n = _cap(state, k)
    if n == 0:
        return []

    rng = random.Random(rng_seed)
    candidates = sorted(state.assignments.keys())
    victims = rng.sample(candidates, n)
    state.remove(victims)
    return victims


# ---------------------------------------------------------------------------
# 3. bay_day
# ---------------------------------------------------------------------------

def bay_day(state: SolutionState, rng_seed: int, k: int) -> list[int]:
    """
    Clustered removal within a single bay: simulates "clear out a cluster
    of a bay's near-simultaneous occupants."

    Logic:
      1. Build the list of bay_ids that currently have >= 1 assigned
         block. If none (state.assignments is empty), return [].
      2. Using `random.Random(rng_seed)`, pick one bay uniformly at
         random from that list (bays sorted ascending before sampling,
         for determinism).
      3. Using the same RNG, pick one pivot block uniformly at random
         from the blocks assigned to that bay (block_ids sorted
         ascending before sampling).
      4. Rank every block assigned to that bay (including the pivot) by
         temporal distance to the pivot's schedule window:
             dist(b) = |entry_time(b) - entry_time(pivot)|
                       + |exit_time(b) - exit_time(pivot)|
         ascending, ties broken by ascending block_id. The pivot itself
         has dist == 0 and therefore always ranks first.
      5. Remove the first `min(k, blocks_in_that_bay)` blocks in that
         ranking.

      Only one bay is ever touched -- if the chosen bay has fewer than
      k assigned blocks, this removes however many it has and does NOT
      spill into other bays.

    Mutates `state` via `state.remove(...)` and returns the removed
    block_ids in the ranked (closest-to-pivot-first) order.
    """
    if not state.assignments:
        return []

    rng = random.Random(rng_seed)

    bay_to_blocks: dict[int, list[int]] = {}
    for bid, a in state.assignments.items():
        bay_to_blocks.setdefault(a["bay_id"], []).append(bid)

    candidate_bays = sorted(bay_to_blocks.keys())
    chosen_bay = rng.choice(candidate_bays)

    bay_blocks = sorted(bay_to_blocks[chosen_bay])
    pivot = rng.choice(bay_blocks)
    pivot_a = state.assignments[pivot]
    pivot_entry, pivot_exit = pivot_a["entry_time"], pivot_a["exit_time"]

    def dist(bid: int) -> float:
        a = state.assignments[bid]
        return abs(a["entry_time"] - pivot_entry) + abs(a["exit_time"] - pivot_exit)

    n = min(k, len(bay_blocks))
    ranked = sorted(bay_blocks, key=lambda bid: (dist(bid), bid))
    victims = ranked[:n]
    state.remove(victims)
    return victims


# ---------------------------------------------------------------------------
# 4. related (Shaw removal)
# ---------------------------------------------------------------------------

def related(state: SolutionState, rng_seed: int, k: int) -> list[int]:
    """
    Shaw/related removal: greedily grows a removal set starting from one
    random seed block, repeatedly adding the remaining assigned block
    that is most "related" (smallest relatedness distance) to ANY block
    already in the removal set.

    Relatedness distance between blocks a and b is the sum of three
    weighted terms (lower sum = more related, all weights == 1.0):

      1. same_bay term (weight 1.0):
           0.0 if a and b are assigned to the same bay_id, else 1.0.

      2. due_date term (weight 1.0):
           |due_a - due_b| / max_due_span
         where due_a/due_b come from state.blocks_data[bid]["due_date"]
         and max_due_span = max(due_dates) - min(due_dates) over all
         *currently assigned* blocks. If max_due_span == 0 (all equal
         or only one block), this term is 0.0 for every pair.

      3. spatial term (weight 1.0):
           if a and b are in the SAME bay:
               (|x_a - x_b| + |y_a - y_b|) / (bay_width + bay_height)
             where bay_width/bay_height are that bay's dimensions
             (state.bays[bay_id].width / .height).
           if a and b are in DIFFERENT bays:
               1.0  (treated as maximally spatially distant --
                     cross-bay pairs never benefit from the spatial term)

      distance(a, b) = same_bay_term + due_date_term + spatial_term

    Algorithm:
      1. If state.assignments is empty, return [].
      2. n = min(k, len(state.assignments)); if n == 0, return [].
      3. seed = `random.Random(rng_seed).choice(sorted(state.assignments))`
         (block_ids sorted ascending before the random choice, for
         determinism). removed_set = {seed}.
      4. While len(removed_set) < n:
           for every remaining block r (assigned, not yet in
           removed_set), compute
               best(r) = min(distance(r, m) for m in removed_set)
           pick the r with the smallest best(r); ties broken by
           ascending block_id. Add it to removed_set.
      5. Remove all of removed_set from `state` via `state.remove(...)`.

    Returns the removed block_ids in the order they were added to the
    removal set (seed first).

    Mutates `state` via `state.remove(...)`.
    """
    if not state.assignments:
        return []

    n = _cap(state, k)
    if n == 0:
        return []

    rng = random.Random(rng_seed)
    all_ids = sorted(state.assignments.keys())
    seed = rng.choice(all_ids)

    removed_order = [seed]
    removed_set = {seed}
    remaining = set(all_ids) - removed_set

    due_dates = [state.blocks_data[bid]["due_date"] for bid in all_ids]
    max_due_span = max(due_dates) - min(due_dates) if due_dates else 0.0

    def distance(bid_a: int, bid_b: int) -> float:
        a = state.assignments[bid_a]
        b = state.assignments[bid_b]

        same_bay_term = 0.0 if a["bay_id"] == b["bay_id"] else 1.0

        due_a = state.blocks_data[bid_a]["due_date"]
        due_b = state.blocks_data[bid_b]["due_date"]
        due_term = (abs(due_a - due_b) / max_due_span) if max_due_span > 0 else 0.0

        if a["bay_id"] == b["bay_id"]:
            bay = state.bays[a["bay_id"]]
            span = bay.width + bay.height
            spatial_term = (
                (abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])) / span if span > 0 else 0.0
            )
        else:
            spatial_term = 1.0

        return same_bay_term + due_term + spatial_term

    while len(removed_set) < n:
        best_bid = None
        best_dist = None
        # Iterating `remaining` in ascending block_id order and only
        # replacing on a strictly smaller distance means ties are
        # naturally broken by the smallest block_id.
        for r in sorted(remaining):
            d = min(distance(r, m) for m in removed_set)
            if best_dist is None or d < best_dist:
                best_dist = d
                best_bid = r
        removed_order.append(best_bid)
        removed_set.add(best_bid)
        remaining.discard(best_bid)

    state.remove(removed_order)
    return removed_order


# ---------------------------------------------------------------------------
# 5. large_block_destroy
# ---------------------------------------------------------------------------

def large_block_destroy(state: SolutionState, rng_seed: int, k: int) -> list[int]:
    """
    Remove the `min(k, len(state.assignments))` currently-assigned blocks
    with the largest spatial-temporal footprint (Bounding Box Area * Processing Time).
    """
    import baseline_greedy
    
    n = _cap(state, k)
    if n == 0:
        return []

    def volume(bid: int) -> float:
        bdata = state.blocks_data[bid]
        min_x, min_y, max_x, max_y = baseline_greedy._block_bbox(bdata, 0) # proxy area using orient_idx 0
        area = (max_x - min_x) * (max_y - min_y)
        return area * bdata["processing_time"]

    ranked = sorted(state.assignments.keys(), key=lambda bid: (-volume(bid), bid))
    victims = ranked[:n]
    state.remove(victims)
    return victims


# ---------------------------------------------------------------------------
# 6. congested_bay_destroy
# ---------------------------------------------------------------------------

def trap_aware(state: SolutionState, rng_seed: int, k: int) -> list[int]:
    """
    Tardy-seeded "open the exit corridor" removal.

    The dominant tardiness cases in these instances are blocks that COULD
    exit before their due date (release + processing <= due) but are held in
    the bay far past it because neighbouring blocks trap their crane exit
    path (the j>=k swept-collision rule). A plain worst_tardiness removal
    lifts the tardy block out but, on re-insert into the SAME still-congested
    bay, it just gets re-trapped. This operator instead removes the tardy
    block together with the bay neighbours most likely to be trapping it, so
    a subsequent force-placement repair has room to slot it out earlier.

    Selection:
      1. seed = the most-tardy currently-assigned block (ties -> smallest id).
         If nothing is tardy, fall back to plain worst-tardiness ranking
         (still useful churn for the SA walk).
      2. Restrict to seed's bay. Rank the other blocks in that bay by a
         "trap score": how much their schedule overlaps seed's occupancy
         window [release_seed, exit_seed] (a block present while the seed
         wants to be leaving is a candidate trapper), with a large bonus if
         its FIXED footprint actually spatially collides with the seed's
         (those are the blocks whose upper layers can sweep the seed's exit).
      3. Remove seed + the top (k-1) trappers.

    Only seed's bay is ever touched. Mutates `state` via `state.remove(...)`
    and returns the removed block_ids (seed first).
    """
    n = _cap(state, k)
    if n == 0:
        return []

    def tardiness(bid: int) -> float:
        a = state.assignments[bid]
        return max(0.0, a["exit_time"] - state.blocks_data[bid]["due_date"])

    ranked = sorted(state.assignments.keys(), key=lambda bid: (-tardiness(bid), bid))
    seed = ranked[0]

    # No tardiness anywhere -> degrade to worst_tardiness (deterministic).
    if tardiness(seed) <= 0.0:
        victims = ranked[:n]
        state.remove(victims)
        return victims

    a_seed = state.assignments[seed]
    bay_id = a_seed["bay_id"]
    bd_seed = state.blocks_data[seed]
    bay_obj = state.bays[bay_id]

    # Seed's desired occupancy window: from when it could enter (release) to
    # when it actually leaves today. Trappers are blocks alive inside it.
    w_lo = bd_seed["release_time"]
    w_hi = a_seed["exit_time"]

    seed_blk = utils.Block(block_id=seed, block_data=bd_seed,
                           x=a_seed["x"], y=a_seed["y"], orient_idx=a_seed["orient_idx"])

    def trap_score(bid: int) -> float:
        a = state.assignments[bid]
        lo = max(w_lo, a["entry_time"])
        hi = min(w_hi, a["exit_time"])
        overlap = max(0, hi - lo)
        blk = utils.Block(block_id=bid, block_data=state.blocks_data[bid],
                          x=a["x"], y=a["y"], orient_idx=a["orient_idx"])
        collide = 1 if utils.check_collisions(bay_obj, [seed_blk, blk]) else 0
        return overlap + 100000.0 * collide

    others = [bid for bid in state.assignments
              if bid != seed and state.assignments[bid]["bay_id"] == bay_id]
    others.sort(key=lambda bid: (-trap_score(bid), bid))
    victims = [seed] + others[: n - 1]
    state.remove(victims)
    return victims


def tardy_relocate(state: SolutionState, rng_seed: int, k: int) -> list[int]:
    """
    Tardy<->donor swap seed. With every other block fixed, the greedy seed's
    slot for a tardy block is already locally optimal -- so removing the tardy
    block alone (or with arbitrary trappers) and re-inserting reconstructs the
    same tardiness. The only way to let a tardy block T exit/enter earlier is
    to also move whatever is holding its slot. This operator removes T
    together with a DONOR block D chosen to be (a) a real trapper of T (its
    fixed footprint collides with T's, so its layers can sweep T's crane
    path) and (b) able to absorb the disruption (D currently has slack --
    room before its own due date). Paired with `force_place_tardy` (which
    re-inserts tightest-slack-first), T is placed first into the slot D just
    vacated, and D re-packs around it. Under the controller's SA acceptance a
    net trade that cuts T's tardiness by even 1 unit (~29091) easily pays for
    a small increase in D's tardiness / Z2 / Z3.

    Removes exactly {T, D} when a colliding donor with slack exists; if T has
    no colliding same-bay neighbour it falls back to {T} plus the nearest
    same-bay blocks up to k (so the operator always returns a usable set).
    """
    n = _cap(state, k)
    if n == 0:
        return []

    def tardiness(bid: int) -> float:
        a = state.assignments[bid]
        return max(0.0, a["exit_time"] - state.blocks_data[bid]["due_date"])

    ranked = sorted(state.assignments.keys(), key=lambda bid: (-tardiness(bid), bid))
    seed = ranked[0]
    if tardiness(seed) <= 0.0:
        victims = ranked[:n]
        state.remove(victims)
        return victims

    a_seed = state.assignments[seed]
    bay_id = a_seed["bay_id"]
    bay_obj = state.bays[bay_id]
    seed_blk = utils.Block(block_id=seed, block_data=state.blocks_data[seed],
                           x=a_seed["x"], y=a_seed["y"], orient_idx=a_seed["orient_idx"])

    # Donor candidates: same-bay blocks whose fixed footprint collides with the
    # tardy block (true crane-path trappers) and that carry slack to spare.
    def donor_slack(bid: int) -> int:
        a = state.assignments[bid]
        return state.blocks_data[bid]["due_date"] - a["exit_time"]

    donors = []
    for bid, a in state.assignments.items():
        if bid == seed or a["bay_id"] != bay_id:
            continue
        blk = utils.Block(block_id=bid, block_data=state.blocks_data[bid],
                          x=a["x"], y=a["y"], orient_idx=a["orient_idx"])
        if utils.check_collisions(bay_obj, [seed_blk, blk]):
            donors.append(bid)

    if donors:
        # Prefer the donor with the MOST slack (best able to absorb a bump),
        # tie-broken by smallest id for determinism.
        donors.sort(key=lambda bid: (-donor_slack(bid), bid))
        victims = [seed, donors[0]]
        state.remove(victims)
        return victims

    # No colliding donor -> fall back to nearest same-bay blocks (spatial),
    # still seeded on the tardy block.
    others = [bid for bid in state.assignments
              if bid != seed and state.assignments[bid]["bay_id"] == bay_id]

    def dist(bid: int) -> float:
        a = state.assignments[bid]
        return abs(a["x"] - a_seed["x"]) + abs(a["y"] - a_seed["y"])

    others.sort(key=lambda bid: (dist(bid), bid))
    victims = [seed] + others[: n - 1]
    state.remove(victims)
    return victims


def congested_bay_destroy(state: SolutionState, rng_seed: int, k: int) -> list[int]:
    """
    Identifies the bay with the highest average tardiness among its assigned blocks,
    and removes `min(k, blocks_in_that_bay)` random blocks strictly from that bay.
    """
    if not state.assignments:
        return []
        
    bay_to_tardiness = {}
    bay_to_blocks = {}
    
    for bid, a in state.assignments.items():
        bay_id = a["bay_id"]
        due = state.blocks_data[bid]["due_date"]
        tardiness = max(0.0, a["exit_time"] - due)
        
        bay_to_tardiness.setdefault(bay_id, []).append(tardiness)
        bay_to_blocks.setdefault(bay_id, []).append(bid)
        
    if not bay_to_blocks:
        return []
        
    # Find bay with highest average tardiness
    worst_bay = None
    worst_avg = -1.0
    # Sorting bays ensures deterministic tie-breaking
    for bay_id in sorted(bay_to_blocks.keys()):
        avg_t = sum(bay_to_tardiness[bay_id]) / len(bay_to_tardiness[bay_id])
        if avg_t > worst_avg:
            worst_avg = avg_t
            worst_bay = bay_id
            
    bay_blocks = bay_to_blocks[worst_bay]
    n = min(k, len(bay_blocks))
    if n == 0:
        return []
        
    rng = random.Random(rng_seed)
    candidates = sorted(bay_blocks)
    victims = rng.sample(candidates, n)
    state.remove(victims)
    return victims
