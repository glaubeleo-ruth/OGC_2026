<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/banner_dark.png">
  <img src="docs/banner.png" alt="The Grand Shipyard Puzzle — Optimization Grand Challenge 2026, Team SANDLE. A hybrid exact/metaheuristic solver for spatial block scheduling in shipyard bays.">
</picture>

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![OR-Tools](https://img.shields.io/badge/OR--Tools-CP--SAT-4285F4?logo=google&logoColor=white)
![Gurobi](https://img.shields.io/badge/Gurobi-MIP-DD2113)
![Xpress](https://img.shields.io/badge/FICO-Xpress-0A6CB5)
![Method](https://img.shields.io/badge/LBBD-matheuristic-6f42c1)
![Method](https://img.shields.io/badge/ALNS-portfolio-2a78d6)

</div>

---

## Impact at a glance

| | |
|---|---|
| **Objective reduction** | **1–2 orders of magnitude** on the official hidden evaluation set, first accepted entry → final result (P3: 61.6M → 220K, −99.6%; P6: 602M → 41.9M, −93%) |
| **Reliability** | **100% feasibility** — zero rejected solutions across every accepted evaluation and all 40 training instances |
| **Optimality** | Proven-optimal certificates on structured instances (LBBD master bound closed); certified lower bounds elsewhere |
| **Robustness** | Entry point engineered to **never crash, never time out, never return unverified work** — hard watchdogs, process-group kills, audited fallbacks |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/results_dark.png">
  <img src="docs/results.png" alt="Hidden-set score progression and train-set sweep" width="100%">
</picture>

## The problem

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/instance_prob1_dark.png">
  <img src="docs/instance_prob1.png" alt="Training instance prob_1: bays, block footprints, and time windows" width="100%">
</picture>

A shipyard has `m` fixed rectangular bays. Each of `n` ship blocks is a 3D
object made of stacked polygonal (possibly non-convex) layers, with a release
date, processing time, due date, workload, and per-bay preference scores. For
every block the algorithm must simultaneously decide:

1. **which bay** it goes to,
2. its **position and orientation** inside the bay,
3. its **ENTRY day**, and
4. its **EXIT day**,

such that blocks never overlap in space while co-resident in a bay. The
objective blends tardiness (Z1), workload balance across bays (Z2), and bay
preference (Z3) — so every placement decision couples a hard geometric packing
problem with a scheduling problem. One instance, one process, **60 seconds**.
Full formal statement: [`ogc2026/problem-statement.pdf`](ogc2026/problem-statement.pdf).

**In plain terms:** imagine Tetris, except the pieces are ship sections the
size of buildings, they're irregular polygons rather than squares, each one
arrives on its own date and must leave by a deadline — and pieces you place
today take up floor space for days, blocking tomorrow's arrivals. Choosing
*where* a block sits and *when* it enters are one decision, not two:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/concepts_block_dark.png">
  <img src="docs/concepts_block.png" alt="Anatomy of a block: stacked polygonal layers, shown with its eight allowed orientations" width="100%">
</picture>

## Solution architecture — "CHIMERA"

Two independently engineered solver lines run inside one time budget; the best
*independently verified* result wins per instance:

```mermaid
flowchart LR
    I["Instance JSON<br/>bays · blocks · weights"] --> E["CHIMERA entry<br/>myalgorithm.py"]
    E -->|"~55% of time budget"| S
    E -->|"remaining wall-clock"| L
    subgraph S["Clean-slate solver (solver/)"]
        M["LBBD assignment master<br/>Z2/Z3-exact + cuts"] <--> O["Per-bay packing oracle<br/>raster occupancy engine"]
        O --> R["Repair & rescue tiers<br/>exact polygon · CP-SAT"]
    end
    subgraph L["Legacy line (alns/)"]
        A["ALNS portfolio<br/>destroy / repair operators"]
    end
    S --> IN["Incumbent store"]
    L --> IN
    IN --> G{"Audit ladder<br/>utils.check_feasibility"}
    G -->|"best verified"| OUT["Solution<br/>ENTRY / EXIT operations"]
```

**Line 1 — exact-flavored matheuristic** (`solver/`): logic-based Benders
decomposition. A Z2/Z3-exact assignment master generates bay assignments;
per-bay packing oracles running on a conservative-raster spatio-temporal
occupancy engine either certify them or return cuts. Project-and-repair sits
inside the oracle; exact-polygon and CP-SAT rescue tiers recover what the
raster abstraction loses. On structured instances the master bound *closes* —
the solution ships with an optimality certificate.

**Line 2 — adaptive large neighborhood search** (`alns/`): a destroy/repair
operator portfolio, kept byte-for-byte stable as the hedge for instance
classes the newer pipeline has never seen. The hidden set is not the training
set — the architecture prices that in.

**The audit ladder**: nothing reaches the output without passing the official
feasibility checker *in the parent process, on the exact dict being returned*.
A verified incumbent always outranks an unverified one; if the ladder is empty,
a last-resort feasible construction is built and audited inside a reserved
time tail. The entry point never raises and never returns `None`.

### The two engines, in plain terms

**ALNS** (adaptive large neighborhood search) improves a schedule the way you'd
rearrange a full closet: take a few things out, put everything back more
cleverly, keep the result if it's better — thousands of times a minute, with
the "adaptive" part learning *which* removal and reinsertion moves are paying
off on this particular instance:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/concepts_alns_dark.png">
  <img src="docs/concepts_alns.png" alt="ALNS illustrated in three panels: a current schedule with two late blocks, a destroy step removing some placements, and a repair step reinserting everything so all blocks fit" width="100%">
</picture>

**LBBD** (logic-based Benders decomposition) splits the problem between a
planner and a foreman. The planner solves the easy half exactly — *who goes to
which bay, and when* — ignoring geometry. The foreman then tries to physically
pack each bay's blocks. When a plan doesn't fit, the foreman reports back
*why*, as a new constraint the planner can never violate again. Each round the
plan gets more realistic, and when a plan packs and matches the planner's
bound, the solution is **provably optimal** — no better schedule exists:

```mermaid
flowchart LR
    M["Assignment master — the planner<br/><i>solves bay assignment + timing exactly,<br/>geometry ignored</i>"]
    O["Packing oracle — the foreman<br/><i>tries to physically place each bay's<br/>blocks, day by day</i>"]
    M -->|"proposed plan"| O
    O -->|"doesn't fit: here's a constraint<br/>ruling that plan out (a cut)"| M
    O -->|"fits, and matches the<br/>planner's bound"| C["Certified schedule<br/>provably optimal"]
```

## Results

### The output, animated

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/schedule_prob1_dark.gif">
  <img src="docs/schedule_prob1.gif" alt="Animated day-by-day playback of the solver's certified-optimal schedule for training instance prob_1: blocks entering and leaving two bays over 52 days" width="640">
</picture>
</div>

The solver's **certified-optimal schedule** for training instance prob_1
(objective 1,499), played back day by day: 100 irregular blocks flow through
two bays over 52 days — entering at their assigned position and orientation
(orange on their entry day), coexisting without overlap, and exiting when
processed. Regenerate with [`docs/make_schedule_gif.py`](docs/make_schedule_gif.py).

### Official hidden-set evaluations

Submissions are scored by the organizers on **six hidden instances (P1–P6)**,
disjoint from the 40 published training instances. Four submissions were
accepted, then the standing CHIMERA entry received the official final
evaluation. Every run returned a feasible solution on all six instances.
Best score per instance in **bold**:

| Submission | Date (UTC) | P1 | P2 | P3 | P4 | P5 | P6 |
|---|---|---:|---:|---:|---:|---:|---:|
| #2 — first accepted | Jul 21 | 280,494 | 62,696 | 61,634,834 | 36,957,614 | 220,176,080 | 601,627,045 |
| #4 | Jul 23 | 26,150 | 37,748 | 515,798 | 11,570,444 | 34,867,084 | 57,616,192 |
| #5 — frozen hedge | Jul 24 | **11,280** | **31,368** | **186,910** | **8,462,228** | 20,226,241 | 52,808,786 |
| #6 — CHIMERA | Jul 25 | **11,280** | 32,068 | 376,241 | 10,854,126 | **18,630,178** | 52,828,500 |
| **Final** — CHIMERA, official evaluation | Jul 29 | **11,280** | 32,068 | 220,494 | 9,289,080 | 18,663,403 | **41,948,328** |

From the first accepted submission to the final result: **−96% (P1), −49%
(P2), −99.6% (P3), −75% (P4), −92% (P5), −93% (P6)**. The final evaluation of
the same CHIMERA zip came in materially better than its Jul 25 evaluation on
P3/P4/P6 (−41%/−14%/−21%) — consistent with the run-to-run timing
nondeterminism documented on overloaded instances. Across all evaluations the
per-instance bests still split between the two lines — the frozen hedge on
P2/P3/P4, CHIMERA on P5/P6 — exactly the trade-off the two-line architecture
was designed to navigate.

### Train-set benchmark (40 instances, 60 s limit)

The clean-slate solver's v0 → v0.4 (LBBD cut loop) progression, measured under
a fixed protocol (one subprocess per instance, hard external timeout, verdict
by the official checker only — never the solver's own claim):

- **40/40 feasible, zero failures** — v0's hard timeouts on prob_38/40
  eliminated; worst wall-clock 52.03 s against a 54.8 s internal budget.
- vs v0: **36 improved, 2 fixed from infeasible, 2 exact ties, 0 regressions**;
  median improvement on changed instances ≈ **−80%**.
- **prob_4 solved to proven optimality**; three instances stop at a certified
  optimum in under 3 seconds instead of idling out the budget.

## Engineering rigor

The part that doesn't show up in a score table:

- **Measurement discipline.** Every benchmark in
  [`ogc2026/baseline/results/`](ogc2026/baseline/results/) is a stamped report:
  git commit, environment, machine-load telemetry, N per instance, and
  explicit provenance caveats. Timing-sensitive claims required N≥5 reps;
  single-rep numbers are labeled indicative, never shippable evidence.
- **Adversarial gating.** Submission candidates passed a submit-safety
  gauntlet that hunted for failure classes — it caught two distinct
  time-limit-overrun bugs pre-submission (one requiring a forked process
  group with a hard SIGKILL watchdog, because the legacy seed construction
  was non-preemptible).
- **Trust boundaries.** The solver's internal claims are never trusted: the
  official feasibility checker is the only oracle, run in the parent on the
  exact object returned. A checker crash is treated as "unknown," ranked
  below any verified result.
- **Hedged deployment.** The previous known-good submission stayed frozen and
  byte-identical as a fallback line inside the new entry — regression risk on
  unseen instance classes was priced in, not hoped away.

## What this project demonstrates

**Optimization:** logic-based Benders decomposition · MIP assignment models ·
CP-SAT repair · ALNS metaheuristics · computational geometry (non-convex
polygon packing, raster occupancy engines) · bound certification.

**Engineering:** hard real-time budget governance · subprocess isolation and
watchdogs · reproducible benchmarking · failure-mode hunting · risk-hedged
release management.

## Glossary

<details>
<summary><b>Every term in this README, in one line each</b> (click to expand)</summary>
<br>

| Term | Plain meaning |
|---|---|
| **Block scheduling** | Deciding where and when each ship section occupies shared factory floor space — packing and calendar planning as one problem. |
| **Feasible solution** | A schedule that breaks no rules: no overlaps, no block placed before its release date, everything inside its bay. |
| **Objective** | The score being minimized: lateness penalties + uneven workload + ignoring bay preferences. Lower is better. |
| **Tardiness** | How many days a block finishes past its due date. |
| **Heuristic** | A method that finds good solutions fast without guaranteeing the best one. |
| **Metaheuristic** | A general strategy (like ALNS) for steering heuristics out of dead ends. |
| **ALNS** | Adaptive large neighborhood search — repeatedly remove part of a solution and rebuild it better, learning which moves work. |
| **MIP** | Mixed-integer programming — exact optimization over yes/no decisions, solved here by Gurobi. |
| **CP-SAT** | Google's constraint-programming solver; used here to repair small conflict clusters exactly. |
| **LBBD** | Logic-based Benders decomposition — a planner solves the abstract problem exactly, a foreman checks physical reality, and each failure becomes a permanent constraint (*cut*). |
| **Matheuristic** | A hybrid that embeds exact methods (MIP/CP) inside a heuristic search — the design of this solver. |
| **Incumbent** | The best verified solution found so far; the one you'd submit if time ran out now. |
| **Lower bound** | A proven "no solution can score better than X." When the incumbent hits it, optimality is certified. |
| **Certificate** | Proof that a solution is optimal (bound met) — not just "we couldn't find better." |
| **Feasibility audit** | Re-checking every candidate with the official checker before trusting it — the solver's word is never enough. |
| **Hidden set** | The six secret instances (P1–P6) the organizers score submissions on — disjoint from the 40 published training instances. |

</details>

## Repository guide

| Path | Contents |
|---|---|
| `ogc2026/SANDLE_FINAL_SUBMISSION/` | Final submitted algorithm (entry + solver + ALNS lines) |
| `ogc2026/baseline/` | Development working copies and the stamped results archive |
| `ogc2026/baseline/results/` | Lab reports: sweeps, A/B audits, submission lineage |
| `ogc2026/alg_tester/` | Official algorithm tester app (PyQt UI) |
| `ogc2026/rig/` | Linux benchmark rig: full-train gauntlet + forced-kill tests |
| `docs/` | README figures and the scripts that generate them |
| `train/`, `past/` | Training instances & prior editions — local-only, not in this repo |

## Reproduce

```bash
conda env create -f ogc2026/ogc2026_env.yml   # Miniforge recommended
conda activate ogc2026

# interactive tester (official tool)
cd ogc2026/alg_tester && python alg_tester_app.py

# full 40-instance gauntlet on Linux (~85 min): see ogc2026/rig/RIG_SETUP.md
```

---

<div align="center">
<sub>Team SANDLE · Optimization Grand Challenge 2026 · built by Jungwoo Suh</sub>
</div>
