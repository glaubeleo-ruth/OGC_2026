"""
controller.py -- ALNS main loop for the OGC 2026 shipyard solver.

Wires together the four already-built ALNS modules (state.py, evaluate.py,
destroy.py, repair.py) and deadline.py into a single entry point:

    run(prob_info, seed_sol, deadline) -> dict   # wire-format solution
    (deadline: an alns.deadline.Deadline, not a plain float -- see below)

Design summary (see the task report for the full rationale):

- Seed: `seed_sol` (produced upstream by baseline_greedy.greedyalgorithm)
  becomes the starting incumbent. It is re-verified via `evaluate.objective`
  before being trusted.
- Random walk with a persistent `current_state`, not a from-best hill climb:
  each iteration destroys/repairs a clone of `current_state` (the last
  ACCEPTED state), not `best_state`.
- Acceptance: simulated annealing. Accept any improving-or-equal candidate;
  accept a worse-but-feasible candidate with probability
  exp(-(candidate_value - current_value) / temperature), where temperature
  cools geometrically over elapsed/timelimit. Infeasible candidates are
  always rejected.
- Operator selection: roulette-wheel over adaptive weights, one weight per
  destroy operator (4) and one per repair choice (2: "greedy", "milp").
  Weights are blended after every iteration with a tiered reward
  (new-best > accepted > rejected) using `weight = decay*weight +
  (1-decay)*reward`.
- `best_state`/`best_value` always track the best FEASIBLE solution seen,
  independent of what SA currently holds as "current".
- Time governor (WATCHDOG_SPEC.md): a shared `alns.deadline.Deadline`
  (monotonic-clock) is threaded through the whole call chain. A tail slice
  -- sized from a MEASURED `est_check_cost`, not a blind fraction alone --
  reserves room for the final `check_feasibility` re-verify + serialize; no
  new iteration starts once inside that tail window. This bounds when a new
  iteration may START, but NOT uncapped work inside one already in flight --
  that's what `deadline.check()` calls and the `DeadlineExceeded` handler
  (which BREAKS, not continues) are for; see deadline.py's module docstring.
- Safety: every iteration body is wrapped in its own try/except (log +
  continue on a generic error; break on DeadlineExceeded), and the whole
  loop is wrapped again at the top level so any unexpected error still falls
  through to returning the best feasible incumbent found so far, or
  `seed_sol` unchanged if nothing better and feasible was ever produced.

baseline/ is not a package -- this module adds baseline/ to sys.path the
same way alns/state.py, alns/evaluate.py, alns/destroy.py and alns/repair.py
already do, so it works whether it's imported as `alns.controller`, run as
a script, or imported after baseline/ has already been put on sys.path by
something else.
"""

import math
import os
import random
import sys
import time

_BASELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASELINE_DIR not in sys.path:
    sys.path.insert(0, _BASELINE_DIR)

import utils  # noqa: E402  (import after sys.path fixup, by design)

try:
    from alns.state import SolutionState  # noqa: E402
    from alns import evaluate, destroy, repair  # noqa: E402
    from alns.deadline import DeadlineExceeded  # noqa: E402
except ImportError:  # pragma: no cover - alternate import path (run as a script from alns/)
    from state import SolutionState  # noqa: E402
    import evaluate, destroy, repair  # noqa: E402
    from deadline import DeadlineExceeded  # noqa: E402


# ---------------------------------------------------------------------------
# Tunables (documented here rather than buried inline)
# ---------------------------------------------------------------------------

# Was 0.05 / 0.5. Widened after a 40-instance sweep (post timelimit-overrun
# fixes) still showed one instance (prob_12, 250 blocks) finishing 2.61s over
# a 60s budget. Root cause: `stop_new_iter_at` only bounds when a NEW
# iteration is allowed to *start* -- it doesn't bound the cost of the parts of
# an in-flight iteration that aren't individually time-capped, chiefly
# `evaluate.objective()`'s full `utils.check_feasibility` re-verify (cost
# scales with instance size, not bounded by remaining_time) plus destroy/
# clone overhead. A single iteration that starts just before the cutoff can
# still run long on those uncapped parts. Doubling the tail (and raising the
# floor) gives that last iteration more room to finish inside the true
# deadline rather than past it -- the direct tradeoff is fewer ALNS
# iterations per run, which is the right side to err on: a timeout scores
# identically to an infeasible or crashed solution.
_TAIL_FRACTION = 0.10      # reserve the last 10% of timelimit for final verify/return
_TAIL_FLOOR_S = 1.0        # ...but never less than this many seconds

_K_MIN = 2                 # destroy size lower bound
_K_MAX_CAP = 6             # destroy size upper bound cap (8 -> 6: smaller repairs, more iterations)

_REWARD_NEW_BEST = 1.0
_REWARD_ACCEPTED = 0.5
_REWARD_REJECTED = 0.0
_WEIGHT_DECAY = 0.85       # weight = decay*weight + (1-decay)*reward

_SA_T0_FRACTION = 0.03     # initial temperature ~= 3% of starting incumbent value
_SA_T0_FALLBACK = 1000.0   # used when the incumbent value is inf (seed infeasible)
_SA_T_MIN_FRACTION = 0.02  # final temperature ~= 2% of initial temperature

_FAST_REJECT_TEMP_MULT = 50.0   # fast-reject threshold: bound > mult * temperature
_FAST_REJECT_FLOOR = 100.0      # ...and at least this absolute margin

_GREEDY_REPAIR_ATTEMPT_LABEL = "greedy"
_MILP_REPAIR_ATTEMPT_LABEL = "milp"

_MILP_TIME_CAP_MAX_S = 1.0
_MILP_TIME_CAP_FLOOR_S = 0.2

# Tightened from 5.0/0.3: with the surrogate-objective controller the repair
# call IS the per-iteration cost, and k <= 6 blocks never need 5s -- the v5
# kernel's per-block budget clamps to <= 0.2s/block anyway.  Smaller caps =
# more ALNS iterations in the same budget, which empirically matters more
# than deeper individual repairs.
_GREEDY_REPAIR_TIME_CAP_MAX_S = 1.5
_GREEDY_REPAIR_TIME_CAP_FLOOR_S = 0.2


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _weighted_choice(rng: random.Random, weights: list[float]) -> int:
    """Roulette-wheel pick of an index into `weights` (all entries > 0)."""
    return rng.choices(range(len(weights)), weights=weights, k=1)[0]


def _temperature(elapsed_fraction: float, t0: float, t_min: float) -> float:
    """Geometric cooling from t0 (frac=0) down to t_min (frac=1)."""
    frac = min(1.0, max(0.0, elapsed_fraction))
    if t0 <= 0:
        return max(t_min, 1e-9)
    ratio = t_min / t0 if t0 > 0 else 0.0
    if ratio <= 0:
        # degenerate fallback: linear interpolation
        return max(t0 * (1.0 - frac) + t_min * frac, 1e-9)
    return max(t0 * (ratio ** frac), 1e-9)


def _apply_repair(
    repair_choice: str,
    candidate: SolutionState,
    removed_ids: list[int],
    milp_bay_counter: list[int],
    deadline,
    rng_seed: int,
) -> set[int]:
    """
    Repair `candidate` (which currently has `removed_ids` absent) and return
    the set of block_ids "touched" by the repair (used for the optional
    tardiness pre-filter).

    "greedy": straight `repair.greedy_repair` re-insertion of `removed_ids`.

    "milp": `greedy_repair` first (guarantees `removed_ids` are fully
    re-inserted -- milp_repack only ever re-times whatever is CURRENTLY in
    one bay, it does not know about blocks removed by an unrelated destroy
    call), then `repair.milp_repack` re-times a round-robin-chosen occupied
    bay as a local polish pass on top. This ordering also respects
    repair.py's documented constraint ("do not call a destroy op on the
    same blocks milp_repack will handle") since by the time milp_repack
    runs, nothing is mid-removal -- the state is fully assigned again.

    `deadline` (alns.deadline.Deadline, WATCHDOG_SPEC.md) replaces the old
    plain `remaining_time: float` -- its `.remaining()` feeds the same
    per-call time-cap formulas as before, and it's passed straight through
    to `repair.milp_repack` so the MILP path's own hot spots (needs_disjoint
    scan, final re-verify) are bounded too.
    """
    touched_ids: set[int] = set(removed_ids)

    # Bounded, not unbounded: greedy_repair's own docstring flags that a
    # single block's full search can take 10-16s by itself in a busy bay.
    # `deadline.remaining()` is the whole ALNS run's remaining budget, not a
    # per-call one, so cap it the same way the MILP path below already does
    # -- without this, one repair call can (and empirically did: up to +202s
    # on a 60s budget across the training set) blow past the controller's own
    # deadline before its next `stop_new_iter_at` check ever runs.
    # k-scaled: repairing k blocks doesn't need a k-independent budget.
    # ~0.15s per block, clamped, and never more than 20% of what remains.
    greedy_time_cap = min(_GREEDY_REPAIR_TIME_CAP_MAX_S,
                          max(_GREEDY_REPAIR_TIME_CAP_FLOOR_S, 0.15 * len(removed_ids)),
                          max(_GREEDY_REPAIR_TIME_CAP_FLOOR_S, deadline.remaining() * 0.2))
    
    if repair_choice == "force_tardy":
        repair.force_place_tardy(candidate, removed_ids, timelimit=greedy_time_cap)
    elif repair_choice == "greedy_area":
        repair.greedy_repair_area(candidate, removed_ids, timelimit=greedy_time_cap)
    elif repair_choice == "greedy_random":
        repair.greedy_repair_random(candidate, removed_ids, timelimit=greedy_time_cap, rng_seed=rng_seed)
    elif repair_choice == "greedy_volume":
        repair.greedy_repair_volume(candidate, removed_ids, timelimit=greedy_time_cap)
    else:
        repair.greedy_repair(candidate, removed_ids, timelimit=greedy_time_cap)

    if repair_choice == _MILP_REPAIR_ATTEMPT_LABEL:
        occupied_bays = sorted({a["bay_id"] for a in candidate.assignments.values()})
        if occupied_bays:
            bay_id = occupied_bays[milp_bay_counter[0] % len(occupied_bays)]
            milp_bay_counter[0] += 1
            time_cap = min(_MILP_TIME_CAP_MAX_S, max(_MILP_TIME_CAP_FLOOR_S, deadline.remaining() * 0.2))
            repair.milp_repack(candidate, bay_id, time_cap, deadline)
            touched_ids |= {bid for bid, a in candidate.assignments.items() if a["bay_id"] == bay_id}

    return touched_ids


# ---------------------------------------------------------------------------
# Main loop (isolated so run() can wrap it in one top-level try/except)
# ---------------------------------------------------------------------------

def _run_loop(prob_info: dict, seed_sol: dict, deadline, rng_seed: int = 0xA1A5):
    """
    Returns (best_state_or_None, best_value, iterations_completed).
    Raises nothing intentionally caught here -- callers (run()) must still
    wrap this in a try/except since per-iteration errors are caught inside,
    but a failure before/between iterations (e.g. building the initial
    SolutionState) is allowed to propagate up to run()'s top-level guard.

    `deadline` (alns.deadline.Deadline, WATCHDOG_SPEC.md) replaces the old
    `(timelimit, start)` pair. The tail reservation now incorporates
    `deadline.est_check_cost` (a MEASURED, not guessed, cost of one
    check_feasibility call) rather than a blind fraction alone, and every
    hot-spot call (evaluate.objective, milp_repack via _apply_repair)
    receives `deadline` directly so it can bail BEFORE starting work it
    can't finish, instead of this loop only noticing after the fact.
    """
    loop_start = time.monotonic()
    alns_budget = deadline.remaining()
    tail = max(_TAIL_FLOOR_S, deadline.est_check_cost * 2, _TAIL_FRACTION * alns_budget)
    stop_new_iter_at = deadline.t - tail

    rng = random.Random(rng_seed)  # per-chain seed; default reproduces the historical single-chain runs

    seed_feasible, seed_value, _seed_parts = evaluate.objective(prob_info, seed_sol, deadline)
    state = SolutionState.from_operations(prob_info, seed_sol)

    if seed_feasible:
        best_state = state.clone()
        best_value = seed_value
        current_state = state.clone()
        current_value = seed_value
    else:
        # Defensive per the task contract: the seed is supposed to always be
        # feasible, but if it somehow isn't, we have nothing safe to seed
        # `best_state` with. Still run the loop from this (infeasible)
        # working state -- any feasible candidate found beats "nothing" and
        # will become the new best; run()'s caller falls back to returning
        # seed_sol untouched if we never manage that.
        best_state = None
        best_value = float("inf")
        current_state = state.clone()
        current_value = float("inf")

    n_blocks = len(state.assignments)
    k_min = _K_MIN
    k_max = max(k_min, min(_K_MAX_CAP, n_blocks // 3))

    destroy_ops = [
        ("worst_tardiness", destroy.worst_tardiness),
        ("random_k", destroy.random_k),
        ("bay_day", destroy.bay_day),
        ("related", destroy.related),
        ("large_block", destroy.large_block_destroy),
        ("congested_bay", destroy.congested_bay_destroy),
        # trap_aware / tardy_relocate: re-registered.  The old "zero Z1
        # improvement" benchmark that de-registered them predates the v4/v5
        # placement kernel (searching force-place, per-block budgets,
        # earliness term, full interaction checks) -- destroy-and-reinsert
        # was reconstructing the same solution because the kernel was weak,
        # not because the operators were.  The adaptive weights will demote
        # them again if they still don't pay off.
        ("trap_aware", destroy.trap_aware),
        ("tardy_relocate", destroy.tardy_relocate),
    ]
    destroy_weights = [1.0] * len(destroy_ops)

    # "milp" (_MILP_REPAIR_ATTEMPT_LABEL) removed from the roulette: profiling
    # on the train set showed every call ending in "no usable/feasible result"
    # (its time-disjointness proxy keeps failing the authoritative re-verify
    # on these dense bays) at ~2.7s per attempt including the whole-bay greedy
    # fallback -- pure iteration-budget burn.  The code path stays available;
    # re-add the label if the proxy is fixed to model sweep interactions.
    repair_choices = [_GREEDY_REPAIR_ATTEMPT_LABEL, "greedy_area", "greedy_random", "greedy_volume", "force_tardy"]
    repair_weights = [1.0] * len(repair_choices)

    t0 = _SA_T0_FALLBACK if current_value == float("inf") else max(1.0, _SA_T0_FRACTION * current_value)
    t_min = max(0.01, t0 * _SA_T_MIN_FRACTION)

    milp_bay_counter = [0]
    iter_count = 0

    while True:
        now = time.monotonic()
        if now >= stop_new_iter_at:
            break
        iter_count += 1

        try:
            deadline.check()  # hard stop if we're already past the true deadline

            elapsed_fraction = (now - loop_start) / alns_budget if alns_budget > 0 else 1.0
            temp = _temperature(elapsed_fraction, t0, t_min)

            d_idx = _weighted_choice(rng, destroy_weights)
            r_idx = _weighted_choice(rng, repair_weights)
            d_name, d_fn = destroy_ops[d_idx]
            r_name = repair_choices[r_idx]

            adaptive_k_max = int(k_max - elapsed_fraction * (k_max - k_min))
            adaptive_k_max = max(k_min, adaptive_k_max)
            k = rng.randint(k_min, adaptive_k_max)
            iter_rng_seed = rng.randrange(1 << 30)

            candidate = current_state.clone()

            removed_ids = d_fn(candidate, iter_rng_seed, k)
            if not removed_ids:
                # Nothing to destroy/repair this round (e.g. empty state) --
                # not a real move, so no weight update; just move on.
                continue

            _apply_repair(r_name, candidate, removed_ids, milp_bay_counter, deadline, iter_rng_seed)

            # O(n) surrogate objective: EXACT objective formula with no
            # feasibility replay (evaluate.fast_objective).  The v4+ placement
            # kernel enforces feasibility at construction (bidirectional
            # same-time + full interaction checks), so repaired candidates
            # are feasible by construction; the authoritative
            # check_feasibility runs only when a candidate would become the
            # new best (verify-on-best), plus a periodic drift guard on the
            # SA walk's current state.  This replaces the old
            # full-check-every-iteration scheme (~1-2s/iteration at 300
            # blocks -- 12 iterations per run) and the now-redundant
            # tardiness_delta fast-reject pre-filter.
            reward = _REWARD_REJECTED

            if len(candidate.assignments) != n_blocks:
                cand_value = float("inf")  # repair lost blocks -> reject outright
            else:
                cand_value = evaluate.fast_objective(prob_info, candidate.assignments)

            if cand_value < best_value - 1e-9:
                cand_feasible, cand_true, _cand_parts = evaluate.objective(
                    prob_info, {"operations": candidate.to_operations()}, deadline
                )
                if cand_feasible and cand_true < best_value - 1e-9:
                    best_state = candidate.clone()
                    best_value = cand_true
                    current_state = candidate
                    current_value = cand_true
                    reward = _REWARD_NEW_BEST
                elif cand_feasible:
                    delta = cand_true - current_value
                    if delta <= 0 or current_value == float("inf"):
                        accept = True
                    else:
                        prob = math.exp(-delta / temp) if temp > 1e-9 else 0.0
                        accept = rng.random() < prob
                    if accept:
                        current_state = candidate
                        current_value = cand_true
                        reward = _REWARD_ACCEPTED
                # else: infeasible or deadline-skipped -- rejected
            elif cand_value != float("inf"):
                delta = cand_value - current_value
                if delta <= 0 or current_value == float("inf"):
                    accept = True
                else:
                    prob = math.exp(-delta / temp) if temp > 1e-9 else 0.0
                    accept = rng.random() < prob
                if accept:
                    current_state = candidate
                    current_value = cand_value
                    reward = _REWARD_ACCEPTED

            # Drift guard: the SA walk advances on unverified surrogate
            # values; every 50 iterations re-verify the current state and
            # resync to best if it has drifted infeasible.
            if iter_count % 50 == 0 and best_state is not None:
                cur_feasible, cur_true, _ = evaluate.objective(
                    prob_info, {"operations": current_state.to_operations()}, deadline
                )
                if not cur_feasible:
                    print(f"[alns.controller] drift guard: current state infeasible "
                          f"at iteration {iter_count} -- resyncing to best")
                    current_state = best_state.clone()
                    current_value = best_value
                else:
                    current_value = cur_true

            destroy_weights[d_idx] = _WEIGHT_DECAY * destroy_weights[d_idx] + (1 - _WEIGHT_DECAY) * reward
            repair_weights[r_idx] = _WEIGHT_DECAY * repair_weights[r_idx] + (1 - _WEIGHT_DECAY) * reward

        except DeadlineExceeded as exc:
            # Structural fix (WATCHDOG_SPEC.md), not the old tail-fraction-only
            # mitigation: BREAK, don't continue -- an in-flight iteration that
            # hits this is abandoned outright, falling through to the existing
            # final verify/return path with whatever best_state was already found.
            print(f"[alns.controller] deadline exceeded mid-iteration {iter_count} ({exc}) -- stopping")
            break
        except Exception as exc:  # noqa: BLE001 -- deliberate broad catch per task contract
            print(f"[alns.controller] iteration {iter_count} raised {type(exc).__name__}: {exc} -- skipping")
            continue

    return best_state, best_value, iter_count


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(prob_info: dict, seed_sol: dict, deadline, rng_seed: int = 0xA1A5) -> dict:
    """
    ALNS main loop. See module docstring for the algorithm; see the task
    report for full design rationale.

    `deadline` (alns.deadline.Deadline, WATCHDOG_SPEC.md): the single shared
    monotonic-clock deadline for this whole ALNS phase, created once by
    `myalgorithm.algorithm` and threaded down through `_run_loop` ->
    `_apply_repair` -> repair ops -> `evaluate.objective`. Replaces the old
    plain `timelimit: float` parameter.

    Always returns a wire-format `{"operations": {...}}` solution that has
    been verified feasible via `utils.check_feasibility`, EXCEPT in the one
    unrecoverable case where `seed_sol` itself was already infeasible and
    the loop never managed to produce anything feasible -- in that case
    `seed_sol` is returned unchanged (a caller-level contract violation
    that this module cannot fix, per the task brief).
    """
    best_state = None
    best_value = float("inf")
    iter_count = 0

    try:
        best_state, best_value, iter_count = _run_loop(prob_info, seed_sol, deadline, rng_seed=rng_seed)
    except Exception as exc:  # noqa: BLE001 -- top-level guard, never let this escape run()
        print(f"[alns.controller] run() top-level exception: {type(exc).__name__}: {exc} -- falling back")

    print(f"[alns.controller] completed {iter_count} iteration(s), best_value={best_value}")

    if best_state is not None:
        try:
            ops = best_state.to_operations()
            final_check = utils.check_feasibility(prob_info, {"operations": ops})
            if final_check.get("feasible"):
                return {"operations": ops}
            print(f"[alns.controller] final re-verify failed ({final_check}) -- falling back to seed_sol")
        except Exception as exc:  # noqa: BLE001
            print(f"[alns.controller] final re-verify raised {type(exc).__name__}: {exc} -- falling back to seed_sol")

    return seed_sol


def chain_worker(prob_info, seed_sol, deadline_ts, est_check_cost, chain_seed):
    """Run one independent ALNS chain in a child process.

    Lives HERE (alns package, imported normally via sys.path) rather than in
    myalgorithm because test harnesses commonly load myalgorithm via
    importlib from a temp path -- that breaks pickle-by-qualified-name for
    functions defined in it ("not the same object as myalgorithm.<fn>",
    observed on Leo's Mac).  The alns package's identity is stable.

    deadline_ts is an absolute time.monotonic() timestamp -- CLOCK_MONOTONIC
    is system-wide on Linux/macOS, so the parent's cutoff is valid here.
    Verifies its own result so the parent only re-verifies the one winner.
    """
    try:
        from alns.deadline import Deadline
    except ImportError:
        from deadline import Deadline
    deadline = Deadline(deadline_ts, est_check_cost=est_check_cost)
    result = run(prob_info, seed_sol, deadline, rng_seed=chain_seed)
    try:
        check = utils.check_feasibility(prob_info, result)
        obj = check.get("objective") if check.get("feasible") else None
    except Exception:  # noqa: BLE001
        obj = None
    return result, obj
