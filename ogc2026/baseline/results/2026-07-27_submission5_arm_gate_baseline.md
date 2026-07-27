# submission_5 arm — stamped server-parity baseline on the O11 gate train set (P0(b))

**Stamp:** 2026-07-27, git HEAD `02080f2` (dirty working tree — see caveat below;
no commit exists at any submission timestamp, per
`results/2026-07-26_submission_lineage.md`). **Pipeline evaluated: legacy entry
only** — `legacy_entry.algorithm(prob_info, 60)` called directly, in its own
subprocess, per instance per rep. The solver line (`solver/api.solve`) was
**not invoked at all** in this run (no chimera hedge, no fork-and-race). This
is a single-arm measurement, not a head-to-head.

Dirty-tree files at HEAD (none touch solver/ alns/ myalgorithm.py
baseline_greedy.py utils.py, and none were written to by this task):
`ogc2026/alg_tester/settings.json` (modified, pre-existing, not mine),
`BLINDSPOT_PASS_2026-07-26_o11_gate_partA.md`, `PROPOSAL_FLUID_COMMAND.md`,
`ogc2026/COMMAND_MANUAL.md`, `ogc2026/baseline/results/2026-07-26_submission_lineage.md`,
`ogc2026/baseline/submission.zip` (all untracked, pre-existing from prior
sessions).

## 1. Arm identification and its caveat (explicit, as instructed)

The frozen submission_5 arm = `ogc2026/baseline/legacy_entry.py` (mtime
2026-07-25 21:02), the legacy ALNS pipeline hard-walled by the chimera
(`myalgorithm.py`, mtime 2026-07-25 21:39) at commit `1a02fb2`. Diffed
`legacy_entry.py` byte-for-byte against `git show 356c40e:.../myalgorithm.py`
(the pre-chimera `myalgorithm.py`, one commit before the chimera switch at
`805613e`): **the only difference is the header comment line** ("myalgorithm.py"
vs "legacy_entry.py (was myalgorithm.py — the legacy ALNS pipeline,
unchanged)"). Confirms `legacy_entry.py`'s `algorithm()` body is
byte-identical to what `myalgorithm.py` was immediately before the chimera
switch.

**Caveat, stated per the brief:** byte-equivalence to the actually-submitted
2026-07-24 08:20:19 UTC zip (submission_5) rests on the hedge-freeze
discipline recorded in commit messages and code comments, **not on a git
tag** — none exists. Worse, per the lineage doc's own process finding: the
repo's initial commit (2026-07-25 18:39:18 +0900 = 2026-07-25 09:39:18 UTC)
**postdates** submission_5's acceptance (2026-07-24 08:20:19 UTC) by about a
day. So even the earliest commit in this repo did not exist yet when
submission_5 was accepted — there is **no git artifact anywhere, at any
commit, that is provably the submission_5 tree.** `legacy_entry.py` is the
best available reconstruction (the "legacy ALNS portfolio, byte-for-byte the
pre-switch `myalgorithm.py`" per the chimera's own header comment,
independently confirmed above), but this is a discipline-based claim, not a
cryptographic one.

**Also note:** the hard-wall wrapper (`_run_legacy_hard_walled` in
`myalgorithm.py`, added at commit `1a02fb2`, 2026-07-25 21:47) **postdates**
submission_5 (2026-07-24) — submission_5 as actually submitted had **no**
external kill-switch protection around the legacy line. This run therefore
calls `legacy_entry.algorithm` directly and unwrapped, which is the faithful
reproduction of what submission_5 actually was, not of how the current
standing chimera protects it today.

## 2. Protocol as run

- Instances: prob_21, 26, 27, 31, 38, 40 (`train/prob_N.json`).
- Timelimit: 60 s. Hard external timeout: 65 s (`subprocess.run(timeout=65)`
  around each rep — enforced externally per CLAUDE.md, independent of
  whatever internal watchdog `legacy_entry.py` itself runs).
- Reps: N = 3 per instance (per this task's explicit spec; below the N ≥ 5
  bar CLAUDE.md sets for ship/no-ship verdicts — this table supports P0(b)
  and the ratio finalization below, not an independent ship/no-ship call on
  the legacy arm itself).
- Server-parity mode, macOS limitations recorded honestly: `OMP_NUM_THREADS=1`,
  `OPENBLAS_NUM_THREADS=1` exported (plus `MKL_NUM_THREADS=1`,
  `NUMEXPR_NUM_THREADS=1` for completeness — this codebase uses neither MKL
  nor numexpr as far as observed, added defensively). **No `taskset`
  equivalent was applied** — Darwin has no cgroups/taskset analog readily
  available, so this run had access to all 8 logical cores (`hw.ncpu=8`,
  `hw.physicalcpu=8`) rather than a pinned 4-core (`0-3`) slice. This is a
  real parity gap, not a rounding error: `legacy_entry.py` internally forks
  a multiprocessing pool for its seed portfolio (see its own header comment
  on `_fork_context`), so the *number of OS processes* it can run
  concurrently was materially larger here than the shipped 4-core rule
  would allow. Effects run in both directions — more cores can finish a
  seed portfolio faster (helping wall-time margin) or contend harder inside
  a single process (hurting it) — so no directional correction is applied;
  this is reported as an open limitation, not adjusted for.
- Each rep is a fresh top-level Python process invoking a one-shot runner
  that imports `legacy_entry`, calls `algorithm(prob, 60)`, then calls
  `utils.check_feasibility` on the result — feasibility is checked, not
  assumed, exactly as CLAUDE.md requires.
- Peak RSS via `resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss`
  (bytes on Darwin) — **measurement caveat**: 11 of the 18 reps were
  collected inside one persistent driver process before a mid-task restart
  (forced by a coordinator interruption — the first attempt ran too long in
  one foreground call and was restructured into per-rep calls, per
  instruction). `RUSAGE_CHILDREN.ru_maxrss` is a **running high-water mark
  across all children of that one process**, not additive per child, so
  several of those 11 rows read back `0.0 MB` delta (a later, smaller-peak
  child doesn't move an already-higher watermark) — those zeros are a
  measurement artifact, not evidence of zero memory use. The 7 reps
  collected as one-shot processes (prob_31 rep 3; all of prob_38, prob_40)
  give a clean per-rep reading: **52–201 MB**, comfortably below the 12 GB
  submit-safety threshold regardless of which reading is trusted.

## 3. Per-rep results

Full CSV: `results/2026-07-27_submission5_arm_gate_baseline.csv` (18 rep
rows + 6 MEDIAN + 6 WORST summary rows).

| instance | rep | status | feasible | objective | obj1 | obj2 | obj3 | wall (s) | margin vs 54 s | peak RSS (MB) |
|---|---|---|---|---|---|---|---|---|---|---|
| prob_21 | 1 | OK | True | 4,026,693 | 271 | 1475 | 2658 | 52.45 | +1.55 | 200.8 |
| prob_21 | 2 | OK | True | 4,079,159 | 273 | 1655 | 2818 | 52.29 | +1.71 | 0.0* |
| prob_21 | 3 | OK | True | 4,085,699 | 273 | 2084 | 2833 | 52.39 | +1.61 | 0.0* |
| prob_26 | 1 | OK | True | 26,167,425 | 1907 | 1042 | 4894 | 53.76 | +0.24 | 0.0* |
| prob_26 | 2 | OK | True | 27,421,144 | 2001 | 2023 | 4851 | 53.55 | +0.45 | 0.0* |
| prob_26 | 3 | OK | True | 27,555,628 | 2015 | 719 | 4564 | 53.57 | +0.43 | 0.0* |
| prob_27 | 1 | OK | True | 57,694,086 | 4242 | 2150 | 2828 | 53.40 | +0.60 | 0.0* |
| prob_27 | 2 | OK | True | 54,494,571 | 3997 | 1685 | 2998 | 53.42 | +0.58 | 0.0* |
| prob_27 | 3 | OK | True | 56,099,915 | 4119 | 2244 | 2942 | 53.34 | +0.66 | 0.0* |
| prob_31 | 1 | OK | True | 28,007,145 | 1881 | 5557 | 10903 | 53.66 | +0.34 | 0.0* |
| prob_31 | 2 | OK | True | 28,088,359 | 1888 | 6146 | 10851 | 53.54 | +0.46 | 0.0* |
| prob_31 | 3 | OK | True | 29,311,766 | 1973 | 3962 | 11213 | **54.22** | **−0.22** | 166.7 |
| prob_38 | 1 | OK | True | 133,323,229 | 9869 | 5776 | 5761 | **54.01** | **−0.01** | 114.0 |
| prob_38 | 2 | **TIMEOUT** | **FALSE (−1)** | **−1** | **−1** | **−1** | **−1** | **65.01** | **−11.01** | 51.9 |
| prob_38 | 3 | OK | True | 123,308,784 | 9132 | 1764 | 5161 | **54.09** | **−0.09** | 171.0 |
| prob_40 | 1 | OK | True | 5,329,616 | 7814 | 7503 | 8475 | **55.14** | **−1.14** | 169.5 |
| prob_40 | 2 | OK | True | 5,118,025 | 7477 | 4155 | 9747 | 53.83 | +0.17 | 105.7 |
| prob_40 | 3 | OK | True | 5,193,461 | 7610 | 3035 | 8812 | 53.90 | +0.10 | 167.7 |

\* batched-process RSS-watermark artifact, see §2 — not zero, unresolved by
this measurement method.

**LB gap column:** omitted from the table above (reported `n/a-legacy-arm`
in the CSV) — this run has no matching Stage-T bound of its own. rex's
`Σ LB_T`/`Σ plan_T` certificates (used in §5 below) were computed under the
**solver line's** master assignment, a different bay partition than
whatever `legacy_entry.py`'s EDD-greedy assigns internally; fabricating an
"LB gap" by pairing them with this arm's obj1 would conflate two different
assignments' bookkeeping — exactly the trap rex's own finding C5 warns
against. None was computed; §5 handles the cross-arm question explicitly
and flags the same trap.

### Medians (N=3, or N=2-valid where flagged) and worst wall

| instance | median obj1 | median objective | median wall (s) | worst wall (s) | feasible reps |
|---|---|---|---|---|---|
| prob_21 | 273 | 4,079,159 | 52.39 | 52.45 | 3/3 |
| prob_26 | 2001 | 27,421,144 | 53.57 | 53.76 | 3/3 |
| prob_27 | 4119 | 56,099,915 | 53.40 | 53.42 | 3/3 |
| prob_31 | 1888 | 28,088,359 | 53.66 | **54.22** | 3/3 |
| prob_38 | 9500.5† | 128,316,006.5† | 54.05† | **65.01 (TIMEOUT)** | **2/3** |
| prob_40 | 7610 | 5,193,461 | 53.90 | **55.14** | 3/3 |

† prob_38: median computed from the **2 feasible reps only** (n=3, 1 −1).
Do not read this as a clean N=3 median — 1/3 of reps on this instance did
not return a result at all.

## 4. Escalation — loud, as required

**prob_38 rep 2 is a genuine −1: TIMEOUT at the 65 s hard external wall,
1/3 reps (33%).** `legacy_entry.algorithm` did not return within
timelimit(60) + 5 s and was killed by the external harness. Recorded as
objective = −1, obj1/2/3 = −1, feasible = False, exactly per CLAUDE.md's
"Timeout, crash, or None scores −1 — recorded as −1, never as a missing
row."

**5 of 18 reps (28%) breach the 0.90×timelimit = 54 s margin threshold:**
prob_31 rep 3 (54.22 s), prob_38 rep 1 (54.01 s), prob_38 rep 2 (65.01 s,
the −1 above), prob_38 rep 3 (54.09 s), prob_40 rep 1 (55.14 s). None of
these overran the 65 s hard external timeout except rep 2, so 4 of the 5
returned a feasible result — but all breach the margin CLAUDE.md's verdict
rule treats as automatically SUBMIT-UNSAFE ("wall > 0.90×timelimit
anywhere").

**This is not a new bug — it reproduces, independently, exactly the failure
class commit `1a02fb2`'s message documents** ("prob_40 ... walls 61.4–63.1s
... and prob_38 ... legacy seed construction is non-preemptible, ~40s
minimum regardless of grant; walls 66.6–75.5s"), now confirmed under thread
caps on a different measurement instrument (this task's harness, not the
original eva gauntlet) and on the specific O11 gate panel rather than the
full 40-instance sweep. It **also confirms why the hard-wall wrapper
(setsid + SIGKILL group, added at `1a02fb2`) is load-bearing**: the raw,
unwrapped legacy arm — i.e., submission_5 exactly as it was actually
submitted, before that wrapper existed — is not clean at timelimit 60 on
this gate set. Anyone considering resurrecting the bare legacy line without
that wrapper would be reintroducing a live −1 class.

**Open uncertainty this task does not resolve:** submission_5 was accepted
on the hidden P1–P6 set with "Feasible solution found" on all six, zero −1
(per `results/2026-07-26_submission_lineage.md`). That is consistent with
either (a) the hidden instances not resembling prob_38/40's profile, (b) the
real eval server having different timing headroom than this 8-core,
untethered Mac, or (c) submission_5 simply not drawing the unlucky seed-path
branch that trips 1/3 of the time here (N=1 per hidden instance in the
actual submission — no repetition to average over). No claim is made about
which; flagging it is the honest stopping point.

## 5. Finalizing rex's part-A ratios (BLINDSPOT_PASS_2026-07-26_o11_gate_partA.md)

Rex's ratio is **obj1 (raw block-tardy-days) divided by Σ plan_T / Σ LB_T**
(also in raw block-tardy-days) — *not* `w1·obj1` divided by those, because
`w1` cancels (rex's own note: "w1 cancels in the ratios"). The task brief's
"recompute shipped w1·obj1 ... and set them against Stage-T" is read here as
"recompute the shipped-side quantity, using w1 from the instance JSON to
confirm unit consistency" — the ratio itself must stay in matched units or
it silently reproduces exactly the C5 trap rex flagged (conflating LB/plan/
weighted bookkeeping "would have produced a fake 10.1× 'exact' result").
Both `w1·obj1` (dollar-weighted, for scale/context) and the raw-unit ratio
are reported below; the ratio column is the raw-unit one.

**w1 per instance** (confirmed from `train/prob_N.json`, matches rex's
`w1·obj1` values exactly when applied to his obj1 column — e.g.
362 × 13333 = 4,826,546 ✓, 8407 × 667 = 5,607,469 ✓): prob_21/26/27/31/38 →
13333; prob_40 → 667.

| inst | **Col A: legacy submission_5 arm** median obj1 | Col A w1·obj1 | **Col B: v0.4 solver panel** obj1 @ `9a824ba` | Col B w1·obj1 | Σ LB_T | Σ plan_T | A: obj1/plan_T | A: obj1/LB_T | B: obj1/plan_T | B: obj1/LB_T |
|---|---|---|---|---|---|---|---|---|---|---|
| 21 | 273 | 3,639,909 | 362 | 4,826,546 | 39 | 78 | 3.50× | 7.00× | 4.64× | 9.3× |
| 26 | 2001 | 26,679,333 | 1623 | 21,639,459 | 55 | 159 | 12.59× | 36.38× | 10.21× | 29.5× |
| 27 | 4119 | 54,918,627 | 4480 | 59,731,840 | 210 | 368 | 11.19× | 19.61× | 12.17× | 21.3× |
| 31 | 1888 | 25,172,704 | 2468 | 32,905,844 | 214 | 352 | 5.36× | 8.82× | 7.01× | 11.5× |
| 38 | 9500.5† | 126,670,167† | 5100 | 67,998,300 | 396 | 584 | 16.27×† | 24.00×† | 8.73× | 12.9× |
| 40 | 7610 | 5,075,870 | 8407 | 5,607,469 | 124 | 280 | 27.18× | 61.37× | 30.02× | 67.8× |

**Column A baselines against:** this task's own N=3 (N=2-valid on prob_38)
measurement of the frozen submission_5 / legacy-ALNS arm, run directly by
eva, this stamp. **Column B baselines against:** the v0.4 clean-slate solver
panel, `results/2026-07-25_solver_v0.4_lbbd_full_sweep.csv` @ `9a824ba`,
transcribed from rex's pass (not re-run here, per instruction not to re-run
CP solves).

Geomean, Column A: **10.27×** to Σ plan_T (range 3.50×–27.18×), **20.05×**
to Σ LB_T (range 7.00×–61.37×). Geomean, Column B (rex's original): 10.1×
to plan (4.64×–30.0×), 19.7× to LB (9.3×–67.8×).

**Methodological flag, stated as loudly as rex's own C5:** Column A is
**not a valid realization-gap certificate for the legacy arm.** `Σ LB_T`
and `Σ plan_T` are Stage-T quantities computed under the **solver line's**
own master assignment (a specific bay partition chosen by `solver/
assignment.py`) — rex is explicit that this is "a certified floor on Z1 for
**that assignment**," not a universal floor. `legacy_entry.py` uses an
entirely different assignment mechanism (EDD-greedy placement with
fallback repair, no LBBD, no CP-SAT bay master). There is no logical
guarantee that a bound certified for one pipeline's bay partition lower-
bounds a different pipeline's tardiness under a different partition. Column
A's ratios are reported here because the task instructed the comparison and
because they turn out to be informative (see below) — but they are **not**
a second, independent certificate of the O11 headroom claim. Only Column B
pairs a pipeline's shipped result with a Stage-T bound computed on that
same pipeline's own assignment, and only Column B is a sound headroom
measurement.

**What Column A is useful for, despite the mismatch:** it lands in
almost exactly the same numeric neighborhood as Column B — geomean 10.27×
vs 10.1× to plan, 20.05× vs 19.7× to LB, same per-instance ordering (prob_40
highest in both, prob_21 lowest in both). This is a coincidence worth
noting, not a proof: two structurally different pipelines, evaluated
against a bound that is only rigorously valid for one of them, land in the
same order of magnitude. It does not add certificate weight to rex's
verdict, but it gives no reason to doubt it either — nothing here points
toward the 100²–100³× claim, and the closest either column comes to the
~3× kill line is Column A's prob_21 at **3.50×** (even closer to the kill
line than Column B's 4.64× on the same instance) — still comfortably above
3×, so the kill criterion remains **not triggered**, with a slightly
narrower margin than previously recorded.

## 6. Verdict

**Does the legacy-arm baseline change rex's conclusion (headroom certified
at 4.6×–30× vs plan, ~3× kill NOT triggered, 10²–10³× claim falsified)? NO —
it does not change the conclusion, and the "provisional" tag on rex's pass
is now resolved.**

Reasoning:
1. This run tested **only** the legacy arm, in isolation, with no solver
   line invoked. Nothing here re-measures or contradicts rex's Stage-T
   numbers for the solver line, which were left untouched per instruction.
2. The cross-arm ratio (Column A) is methodologically invalid as an
   independent certificate (§5) — it cannot "change" rex's conclusion
   because it is not commensurable with it. What it *can* do is fail to
   contradict it, and it doesn't: it lands within ~2% of Column B's geomean
   on both plan and LB, nowhere near 100×, and the ~3× kill line is still
   not crossed (nearest approach 3.50×, narrower than the 4.64× previously
   recorded but still > 3).
3. **P0(b)'s real contribution is orthogonal to the ratio question**: it
   establishes, for the first time, that the frozen submission_5 arm itself
   — run exactly as it was actually submitted, with no hard-wall — is not
   clean at timelimit 60 on this specific gate panel (1 outright −1 on
   prob_38, 5/18 reps breaching the 0.90× margin across prob_31/38/40).
   That is an escalation-grade finding about the legacy arm's own
   robustness, independent of and orthogonal to the O11 fluid-command
   headroom question rex's pass was scoped to. It does not bear on whether
   the fluid-command architecture is worth building; it bears on whether
   the legacy hedge line is currently safe to run unwrapped, and the answer
   (confirmed here, matching the commit-message history) is no — which is
   exactly why `1a02fb2` wraps it.

**FINAL.** Rex's part-A verdict — headroom certified at 4.6×–30× (geomean
10.1×) vs Σ plan_T, 9.3×–67.8× (geomean 19.7×) vs Σ LB_T, the ~3× kill
criterion not triggered (nearest miss 4.64×, now corroborated at 3.50× from
an orthogonal, methodologically-caveated angle), and the proposed
10²–10³× claim falsified with certificates on all six gate instances — is
**no longer provisional.** P0(b) is discharged. Separately and additionally:
the legacy submission_5 arm, run unwrapped exactly as originally submitted,
is **submit-unsafe at timelimit 60 on this gate panel** (1 −1 / 18 reps, 5/18
margin breaches) — a live finding for anyone touching the hedge line, not a
finding about the O11 architecture.

---
*Measured by eva. Scripts (scratch, throwaway):*
`/private/tmp/claude-501/-Users-jungwoosuh-Desktop-workspace-03-Projects-OGC-2026/6332b06e-d056-4262-9589-90fb10c82042/scratchpad/run_one_legacy.py`,
`.../run_rep.py`, `.../driver.py` (first, partially-completed batched attempt —
superseded by per-rep calls after a coordinator interruption; its 11 valid
completed reps for prob_21/26/27/31(×2) were kept as-collected, matching the
exact protocol, per instruction).
