# O11 — Fluid-Command Architecture: schedule-first realization on mass-tardiness instances

**v2, 2026-07-26** — revised after the champion-review (all seven objections accepted;
see Revision Log at the end). Target: a large, *measured-before-believed* objective
reduction on the instance class carrying ~99% of our shipped objective mass
(the 8.5M / 20M / 53M-class cases). Status: **contained experiment. Not integrated,
not submitted, no dependent code built until the falsification gate passes.**

**GATE PART A ADJUDICATED (2026-07-27, FINAL — eva P0(b) baseline stamped):** headroom
certified at 4.6×–30× (geomean 10.1×; certified ceiling 9.3×–67.8×); ~3× kill NOT
triggered; the 10²–10³× magnitude claim FALSIFIED with certificates on all six gate
instances. **Part B is HALTED as written** per F18 (the residual gap is geometric, not
temporal) and F15 (Stage T is a −1 risk at shipped thread budgets). Measured better
lever: F17 (congestion-aware assignment, 6/6 end-to-end win, 9.4–54.5%). See
BLINDSPOT_PASS_2026-07-26_o11_gate_partA.md and
results/2026-07-27_submission5_arm_gate_baseline.md. Next step is a discussion-level
re-scope decision, not a build.

## Motivation

Our shipped objectives on tail instances are ~10²–10³× above the energetic lower bound.
Measured basis: per-layer fluid load ≤ 0.56 on every sampled instance (F4); daily peak
utilization ≤ ~1.04 with only ~4 days above capacity on prob_40 (pass #3-C); energetic
excess ≈ 10² displaced block-days ≈ 10⁴–10⁵ objective, versus 5–7M shipped.
**Provenance caveat (v2.1):** the "8.5M / 20M / 53M-class" and "5–7M shipped" figures
have no stamped table in `results/` — recording frozen submission_5's per-instance
results is gate prerequisite P0 below. For scale reference, the solver arm's own
stamped v0.4 panel (`results/2026-07-25_solver_v0.4_lbbd_full_sweep.csv` @ 9a824ba)
puts the tail at: prob_38 68.6M, prob_27 60.8M, prob_31 35.5M, prob_26 22.2M,
prob_39 20.2M, prob_40 5.67M, prob_21 5.28M. The
hypothesis: this tardiness is manufactured by chronological greedy construction (an
unplaced block delays, occupies later days, delays more blocks — a cascade), not forced
by capacity. No amount of repair polishing a cascaded schedule recovers 100×; the
schedule itself must come from somewhere else.

## Key Insight (restated with v2 precision)

The per-layer cumulative CP-SAT we already run as a lower bound (III.2, F5 form)
produces, alongside its bound, **a capacity-feasible candidate schedule** — per-block
entry days respecting every layer's aggregate area in every period at (near-)minimal
fluid tardiness. We currently discard it. Fluid-Command keeps it as a *command* for
geometry to attempt. It is explicitly **not** an executable plan: area-feasibility does
not imply packability (shape tiling, crane paths, conservative footprints, overhangs all
sit outside the relaxation). Whether the realization gap is small is the experiment's
question, not the architecture's premise.

## Mathematical Formulation

Per bay j with assigned set S_j (from the existing master):

  **Stage T (temporal command), two-stage lexicographic solve:**
    (T1)  min Σ w1·T_i  s.t. per-layer cumulatives, e_i ∈ [r_i, H], T_i ≥ e_i+p_i−d_i, T_i ≥ 0
    (T2)  among T1-optimal (or T1-cost-capped) schedules: min peak per-day
          conservative-footprint load, then load smoothing — the geometry-aware
          tie-break (review obj. 7): fluid ties are broken toward realizable days,
          never left to solver arbitrariness.

  **Bookkeeping discipline (review obj. 4):** three quantities are tracked separately
  and never conflated —
    LB_j        = CP BestObjectiveBound  (a bound in all cases);
    plan_cost_j = objective of the returned schedule ê  (= LB_j only if status OPTIMAL);
    realized_j  = utils-verified Z1 after realization.
  The only global gap claim permitted: **realized_j − LB_j.**

  **Stage G (geometric realization):** for t = 0..H, place the cohort {i : ê_i = t}
  via the bitset engine (contested-first); on failure of block b:
    (1) exact-polygon rescue at day ê_b (tier 1 — exists);
    (2) [post-gate only] cluster CP over the local window, entry ∈ [ê_b, ê_b+δ],
        min Σ w1·T_i (tiers 2–3 — stubs today; see gate);
    (3) accept the locally-minimal delay. Per-block repair costs are recorded as
        **attribution** (diagnostic decomposition of realized − plan). They are NOT
        summed into any certificate (review obj. 5): repairs interact through shared
        time-space; only realized_j − LB_j is a certified global statement.

  **Assignment coupling (review obj. 6 — soundness fix):**
    θ_j ≥ (certified relaxation bounds only): LB_j(S_j) and its tightenings.
    Realized costs enter the master ONLY as evaluated-assignment optimality cuts in
    no-good form — binding when y matches S_j exactly, vacuous otherwise — plus the
    incumbent. A realized (upper-bound) cost must never constrain θ for any other
    assignment: that is the F8 disease, and v1 of this document contained it.

## Search Space

Temporal: exact CP over the fluid polytope + tie-break stage (small: ≤ 80 intervals,
≤ 4 cumulative resources, horizon ≤ ~100). Geometric: per-day cohorts (far smaller than
post-cascade packing). Repair: local windows δ ≤ ~5 days, grown with budget. Command
revision: no-goods on failing cohort compositions (in-bay LBBD) — post-gate.
**F11 discipline carried over:** a cohort that fails *heuristic* realization is
excluded-not-refuted — exactly the F11 shape. Command-revision no-goods are heuristic
excludes; any "realized-optimal" claim must track open excluded cohorts below the
incumbent and report `bound_closed_with_open_candidates`, never `closed`.

## Neighborhood Design

Within-day order: largest conservative stamp / fewest anchors first. Repair windows grow
monotonically (III.1 discipline). Command revision replaces the failing day's cohort
composition, not individual placements — the temporal layer negotiates in its own
vocabulary.

## Incremental Evaluation Strategy

Unchanged engine (bitset tests, O(1) Z-deltas, utils as gate). Stage T adds one CP solve
per (bay, assignment-version): seconds, cached, warm-started. New streamed metrics:
per-day realized-vs-commanded rate, and realized − LB per bay into eva's gap column.

## Expected Complexity

Stage T: seconds to OPTIMAL on train-size bays (status recorded when not). Stage G:
≤ n placements + repairs. One fluid-command pass ≈ current seed-pass wall. Fits the
existing conductor and budget mechanics.

## Expected Bottlenecks (now ordered by the review's risk ranking)

(1) **Realization failures that are NOT local** — wide/concave/crane-blocking shapes can
make an underloaded day unpackable and conflicts can percolate; this is the main
technical risk and the gate's central measurement, not an implementation detail.
(2) Absent repair machinery — cluster/tuck are stubs; the gate runs on raster + tier-1
rescue only, precisely to measure how much is left for them to do.
(3) Fluid-blind command geometry — mitigated but not removed by the T2 tie-break.
(4) CP status FEASIBLE (not OPTIMAL) on large bays under budget — handled by the
three-quantity bookkeeping, never by conflation.

## Scalability

Stage T linear-ish in n per bay; long hidden budgets flow into command revision and
larger windows — a monotone long-budget consumer (kills F10-class idling) *if* the gate
passes.

## Hidden-Test Robustness

No instance-fitted constants; command derived per instance. Triage-gated to
wide-slack / high-Z1 instances; easy-tier certificate path untouched. Structurally
no-worse: incumbent store + existing construction remain; a failed realization forfeits
nothing. Ship criterion below governs any leaderboard exposure.

## Falsification gate (adopted from the champion-review — REQUIRED before any build)

**Prerequisite P0 (blocking — discovered v2.1):** no per-instance table for frozen
submission_5 exists in `results/` today; the comparison target of this gate is
therefore unevaluable as recorded. Before any gate run, eva persists a stamped
submission_5 baseline — either transcribed from the acceptance reply email's
per-instance statuses or re-measured by running the frozen zip under server-parity
limits — to `results/`. While at it, sanity-check the gate's instance set against
that table: the stamped v0.4 solver panel puts prob_27 (60.8M) and prob_31 (35.5M)
above prob_21/40; if submission_5's mass agrees, add or swap them in.

**Sequencing (cheapest kill first):** part A runs Stage T alone — LB_j, plan_cost_j,
CP status per bay vs the submission_5 baseline (this preserves v1's headroom
certification: if plan_cost is within ~3× of shipped Z1, the revolution is a mirage
and parts B onward never run; expected 10²–10³× below). Only if part A shows headroom
does part B build the contained realization harness (raster + tier-1) and measure
items 2–6.

Fixed-work experiment on prob_21 / 26 / 38 / 40, quiet machine, **N ≥ 3**, server-parity
limits (4 pinned cores, thread caps), comparison target = **frozen submission_5 recorded
results** (never the drifted hedge). Report per instance:

1. LB_j (BestObjectiveBound), plan_cost_j, CP status — separately;
2. fraction of blocks AND of workload realized exactly on command day
   (raster + tier-1 rescue only);
3. verified residual Z1 (utils);
4. **largest connected time-space conflict component** — the direct test of the
   "exceptions are local and small" premise;
5. rescue success rate;
6. wall, peak RSS, feasibility under parity limits.

**Kill criterion:** conflicts regularly spanning large fractions of a bay, or best
verified realization failing to deliver a material, repeatable improvement over
submission_5 — then the local-repair premise is false: file the finding, stop, and the
cluster/tuck build proceeds (if at all) on its independent F2/F9 justification with no
O11 assumptions.

**Build order if the gate passes:** tie-break stage T2 → cluster CP with entry vars
(sized by the measured conflict components) → tuck where overhang share demands it →
command revision loop. Each lands behind the standard cadence (tom → eva → rex).

## Ship criterion

Solver-arm-only until it passes the full standing gauntlet: no failures, and **no
per-instance regression against frozen submission_5** on the held-out/incident panel.
The chimera incident stands as precedent: a technically feasible ensemble lost rank by
taxing the proven engine; Fluid-Command earns exposure through the same door as
everything else.

## What would beat this?

A team commanding with geometry-aware capacity (per-layer strip/energetic relaxations
instead of area) realizes with fewer repairs — that is our own III.2 tightening and
slots into Stage T. A team jointly optimizing assignment + command in one model wins
where our no-good feedback is slow — mitigated by warm starts. A pure-geometry virtuoso
still loses this class if the gate's premise holds: the 100× lives in the schedule.
And if the gate's premise fails, the honest winner is whoever measured it first.

---

## Revision Log

- **v2.1 (2026-07-26), repo-reconciliation pass:** (a) flagged that the motivation's
  shipped-mass figures and the gate's submission_5 comparison target have no stamped
  table in `results/` — added blocking prerequisite P0 (eva records the submission_5
  baseline) and an instance-set sanity check against it (v0.4 panel suggests
  prob_27/31 belong in the set); (b) split the gate into part A (Stage-T-only headroom
  check, preserving v1's ~3× kill criterion at near-zero build cost) and part B (the
  realization experiment); (c) applied the F11 lesson to command-revision no-goods
  (heuristic excludes must be tracked open, `bound_closed_with_open_candidates` form,
  per BLINDSPOT_PASS_2026-07-25b).
- **v2 (2026-07-26), after champion-review — all seven objections accepted:**
  (1) "executable temporal plan" → capacity-feasible *candidate* schedule; realization
  gap is the experiment's question. (2) 40% headroom demoted from guarantee to
  hypothesis; conflict-component size added as its direct test. (3) cluster/tuck
  recognized as the main technical risk, not detail; gate runs on tier-1 only, build
  deferred behind the gate. (4) LB / plan cost / CP status separated; conflation
  forbidden. (5) Σ local repair costs reclassified as attribution; only realized − LB
  is a certified gap. (6) **soundness fix:** realized costs removed from θ; θ carries
  certified relaxation bounds only; realized enters as evaluated-assignment no-good
  optimality cuts — v1's feedback loop was F8-class unsound as written. (7) lexicographic
  geometry-aware tie-break (peak load, smoothing) added to Stage T.
- v1 (2026-07-26): original proposal.
