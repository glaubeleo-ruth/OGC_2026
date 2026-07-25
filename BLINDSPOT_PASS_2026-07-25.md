# OGC 2026 — Blindspot Pass (2026-07-25)

**Target:** the O1+O6 clean-slate pipeline landing in `ogc2026/baseline/solver/`.
**Snapshot under test:** version **v0.3-O1O6**, copied from `ogc2026/baseline/` at
2026-07-25 13:07 KST into
`scratchpad/snap_v0.3-O1O6/` (tom is editing `solver/` live; all measurements below
are against the frozen copy). Ground truth: the snapshot's `utils.py`. Instances:
`train/prob_*.json`. Interpreter: conda env `ogc2026` (Python 3.12, ortools 9.15,
shapely 2.1, numpy 2.1).

Findings continue the F-log at **F8**. Verdicts are per the load-bearing claims in the
pass request, most valuable first. Numbers, not opinions.

---

## Claim 1 — The optimality certificate on prob_1 (obj = 1499 is the GLOBAL optimum)

**VERDICT: CONFIRMED for prob_1 specifically — but the certificate MECHANISM is not a
global-optimum certificate in general (see F8).**

Reproduced the exact solve (`api.solve(prob_1, 60)`): master status **OPTIMAL**, raw
z2\* = 157.196 (floors to 157), z3\* = 2, packed z1 = 0, obj = 7·157 + 200·2 = **1499**,
`utils.check_feasibility` feasible, stage 5, obj1=0/obj2=157/obj3=2. Wall 2.07 s.
Weights w1=29091, w2=7, w3=200; 2 bays (51×20=1020, 54×18=972).

Three attack surfaces, each measured:

**(a) Floor-vs-scaling.** The master minimises the *un-floored* scaled z2
(`round(w2)*z2_micro + …`), while the true objective floors z2. I proved this can
diverge by up to (w2−1) in principle, then measured it. Exact DP over the true
assignment-layer objective — `w2·floor(|u₀L₀−u₁L₁|) + w3·z3` with **rational** u_j
(Fraction), same compatibility as the master — gives min = **1499** at L₀=4535,
floor(z2)=157, z3=2. Identical to the master. Generalised to the other small 2-bay
instances: prob_1/4/8/22 the master's micro-scaled argmin equals the true floored
optimum, **gap = 0** on all. The floor/scaling gap did **not** bite on any tested
instance. CONFIRMED, with the caveat in "what makes this −1" below.

**(b) Compatible-bays restriction.** On prob_1 **all 100 blocks are compatible with
both bays — 0 excluded pairs** — so the restriction excludes nothing and cannot have
dropped the optimum. Generalised: across all 40 instances there are **108 excluded
(block,bay) pairs**, and re-testing every one against `utils` geometry (exact polygon
`bounding_rect` + `check_entry` on an empty bay, all orientations) yields **0 false
exclusions**. `fits_bay`'s conservative raster (RESOLUTION=4) never wrongly rejects a
legally-placeable pair. CONFIRMED.

**(c) Fluid capacity (rho=1.0).** The DP in (a) carries **no capacity constraint** and
still returns 1499 = the master's capacity-constrained optimum, so the constraint was
**not binding** on prob_1 and cut off nothing. CONFIRMED.

Because the assignment-layer optimum (1499) is a valid lower bound on the Z2/Z3 cost of
any z1=0 solution, w1=29091 makes every z1>0 solution cost ≥29091 ≫ 1499, and a z1=0
solution at exactly 1499 exists and is audited — **1499 is rigorously the global optimum
of prob_1.**

### F8 (SOUNDNESS of the *claim*, not a wrong-answer bug) — "certified optimum" is a fluid lower bound that is unachievable on ≥5 train instances

The master's "OPTIMAL" certifies only the Z2/Z3 assignment optimum under the fluid
relaxation; it says **nothing** about z1-packability, and the LBBD gap-closing machinery
that is supposed to bridge that (`theta_j`, `tardiness_cuts`) is **scaffolded but not
wired into the objective** — `_solve_cpsat` minimises `w2·z2 + w3·pref_pen` only;
`tardiness_cuts` are stored and never applied. Measured consequence — pack the master's
*exact* certified assignment with no repair:

| inst | cert (z2\*,z3\*) | cert_obj | master-assignment packed as-is | z1=0 packable? | best z1=0 achievable |
|---|---|---|---|---|---|
| prob_2 | (144.6, 15) | 3690 | z1=0, z2=144, z3=15 | **YES** | 3690 (gap 0) |
| prob_8 | (2413, 8) | 11252 | — | (gap 0) | 11252 |
| prob_3 | (2330.8, 105) | 39050 | **z1=18**, z2=2330, z3=105 | **NO** | 82760 (gap 43710) |
| prob_4 | (2279, 0) | 15946 | **z1=4**, z2=2278, z3=0 | **NO** | 50332 (gap 34386) |
| prob_5 | (2534.9, 127) | 36788 | — | (z1=0 real, high z2/z3) | 81407 (gap 44619) |
| prob_6 | (3211.9, 60) | 31477 | — | — | 78191 (gap 46714) |
| prob_7 | (2215.3, 86) | 28405 | — | — | 87843 (gap 59438) |

On prob_3–7 the shipped z1=0 solution costs **2–3× the certified "optimum"** because that
assignment is geometrically un-packable without tardiness (the fluid rho=1.0 admitted it).
The O6 story — "polish the packed solution toward the master's certified (Z2\*,Z3\*)" — is
polishing toward an **unreachable target** on the majority of easy instances. The
certificate is a valid (loose) lower bound, not an optimum. This is a *messaging /
design-claim* soundness issue, not a wrong-answer bug: the shipped solutions remain
feasible and correctly priced.

---

## Claim 2 — Polish soundness (never creates tardiness, never worsens the exact objective)

**VERDICT: CONFIRMED.** Differential audit on 7 instances spanning easy, moderate, and
overloaded/degenerate regimes (prob_1, 12, 14, 21, 38, 40 + prob_3 via full pass). For
every instance, snapshotting `by_bay` immediately before and after `polish_assignment`
and pricing both with `objective.py` AND auditing both with `utils.check_feasibility`:

- **z1 (tardiness) never increased** by polish (identical before/after on all 7).
- **exact objective never increased** (monotone non-worsening); it strictly improved on
  prob_12 (224563→192307) and prob_14 (308490→300481) by trading z2 up for z3 down under
  exact floor pricing.
- **feasibility never broken** (utils feasible before ⇒ feasible after, all 7).
- **internal objective == utils objective** to the unit on every final solution (AGREE).

The zero-window construction (`entry ∈ [release, due−proc]` ⇒ exit ≤ due) makes "no new
tardiness" hold by construction, and the exact floor-priced acceptance gate (`net < −1e-9`)
matches utils. Confirmed empirically including the degenerate-placement path
(prob_38/40 have degenerate blocks; polish left them untouched, 0 moves, no violation).

---

## Claim 3 — "The seed IS the Z3=0 probe"

**VERDICT: CONFIRMED.** The greedy assignment `argmax_{j∈compat} prefs[j]` is exactly the
per-block z3 minimiser because z3 = Σ(pref_max − prefs[assigned]) is **separable per
block**. Measured seed z3 vs the theoretical per-block minimum on 9 instances
(prob_1,5,9,14,17,21,32,37,39): **exact match on all 9**. z3=0 is realised precisely when
every block's top-preference bay is compatible (prob_1,5,37,39 → z3=0); when z3>0
(prob_9=244, 14=113, 17=97, 21=179, 32=205) it is *forced* by excluded pairs, and the
greedy still picks the minimum-penalty compatible bay. Ties never inflate z3 (equal
preference ⇒ equal penalty). No silent z3>0. (Caveat: the per-block minimum is over the
*compatible* set; because false exclusions = 0 (Claim 1b), the compatible set is not
artificially shrunk, so this minimum is the true per-block z3 optimum.)

---

## Claim 4 — Deadline discipline after O1+O6 (walls on the margin-breach set)

**VERDICT: CONFIRMED — no −1 risk. No wall exceeded 54 s.** Full `api.solve` at
timelimit=60 (internal budget = 60·0.93−1 = **54.8 s**):

| inst | wall (s) | feasible | full pass |
|---|---|---|---|
| prob_21 | **51.96** | True | skipped (budget 2.8s < 9.5s) |
| prob_26 | 50.89 | True | skipped |
| prob_33 | 50.03 | True | skipped |
| prob_36 | 48.58 | True | skipped |
| prob_38 | 49.14 | True | skipped |
| prob_40 | 49.02 | True | skipped |

Tightest is prob_21 at 51.96 s, still 2.8 s inside budget. On all six, `seed+repair`
consumes the budget (anytime, per-move deadline polls) and the full pass is cleanly
**skipped by the pre-flight budget guard** (`deadline.remaining() > expected`) — no
aborted-mid-pack waste at 60 s. At 180 s (below) the guard instead lets it start and
**abort**. The reserve (`1.5·t_audit1 + 1 + 0.02·n`) is measured on this run so it scales
with server slowness. No overrun observed.

---

## Claim 5 — OPPORTUNITY sweep (measured objective left on the table under R−nb)

### F9 (OPPORTUNITY) — the O1/full pass is inert or *regressive* on easy instances; the LBBD gap is never closed

On prob_3 the full pass (master CP-SAT + re-pack + repair + polish) produced obj **92900**,
**worse** than plain seed+repair's **82760**. The IncumbentStore correctly keeps 82760
(no shipped regression), but the entire O1 machinery contributed *negative* value and
burned budget. Because the master objective omits `theta_j`/tardiness cuts (F8), the
certified↔realized gap (43k–59k on prob_3–7) is never closed by any loop — the pipeline's
only gap-narrowing tool is greedy `repair_tardiness`, which on prob_3 lands 2× above the
lower bound. **What's on the table:** on the easy tier where ranks are decided by Z2/Z3
dust (prior pass §1), the pipeline ships 2–3× the certifiable-lower-bound assignment cost.
A competitor that actually closes the LBBD gap (real conflict/tardiness cuts, or per-bay
exact packing feedback into the master) wins these outright.

### F10 (OPPORTUNITY / −1-adjacent waste) — the only consumer of a long budget is anytime repair; once it converges the surplus is idle

`prob_21` at timelimit **180 s**: best_obj = **5277656**, **bit-identical** to the 60 s
run (5277656). Repair+polish converge by ~50 s (47 moves then no improving move); the
full pass then **aborts** (returns None, discarded) and the remaining **~110 s is idle**.
`prob_26` at 180 s *does* improve — 22168638 vs ~23.4M at 60 s (≈5%) — because its repair
is still finding moves at the wall (66 moves vs 55). So the surplus budget is consumed by
**one thing only**: the anytime `repair_tardiness` loop. Where repair converges (prob_21)
there is no other consumer, and the design's long-budget machinery (Part VI: k-best
assignment pool, LBBD cut loop, RNG oracle restarts) is **unimplemented in v0**
(`conductor.run` is a single linear pass). The PDF states hidden limits run "a few minutes
to half an hour"; on any instance where repair converges early the entry forfeits the
surplus. Same 30-min-native blindspot as the 2026-07-24 pass §2, now *measured* on the
O1+O6 build: Δobj(180s − 60s) = **0 on prob_21**, only ~5% on prob_26.

**Timing nondeterminism (measurement-discipline note, echoes 2026-07-24 §5).** Because
`repair_tardiness` runs anytime until the wall, the shipped objective is a function of
wall-clock speed. prob_26 at 60 s returned **27.3M** in one run and **23.4M** in another
(same code, same timelimit) — a **14% swing from timing alone** (39 vs 55 completed
moves). Consequence beyond noise: a server that is slower/faster per core than the dev box
will complete a different number of moves and ship a **different objective** — the 0.93
factor bounds the −1 risk but does not stabilise the objective. Any ship/no-ship decision
on overloaded instances needs N≥5 reps (the prior pass's rule), and the leaderboard number
is not reproducible run-to-run.

**Non-findings (premises that did not hold):** the "aborted-full-pass budget waste on
prob_38/40" is not present at 60 s — the full pass is *skipped* pre-flight, not aborted
(0 waste). Pairwise-swap absence from polish is a real gap but I did not size it with a
number this pass; the dominant easy-instance loss is F9's uncloseable LBBD gap, not
single-vs-swap moves. Polish *does* run on non-delayed instances (conductor gates only
`repair_tardiness` on `delayed_initial`; `polish_assignment` runs whenever `use_repair`).

---

## Standing questions

**What would beat this?** On the easy tier (Z2/Z3 decide ranks), a team that *closes the
LBBD gap* — feeding per-bay z1-infeasibility back as real cuts so the master re-optimises
Z2/Z3 over *packable* assignments, or replacing the fluid rho=1.0 relaxation with a
tighter per-bay area-time bound — reaches a z1=0 assignment near the true optimum while
this entry ships 2–3× the lower bound (F8/F9). On any tier, a team with an anytime search
that actually uses the 5–30 min budget beats an entry whose 180 s result equals its 60 s
result (F10). The prob_1-class instances where our certificate is genuinely global will
tie every competent team and differentiate nobody (rank scoring: ties share points).

**What makes this −1 on a hidden instance?** Not the audited output path — every measured
solution is feasible, correctly priced, and produced well inside budget. The residual −1
surfaces are: (i) the floor-vs-scaling gap (F8-a) is proven-bounded but only *empirically*
zero on 5 instances — a pathological hidden instance with large fractional z2 and a
w2-dominant weight could make the master certify (and O6 chase) a slightly-suboptimal
assignment; this costs objective, not feasibility, so at worst a rank slip, never a −1.
(ii) The real −1 risk is unchanged from prior passes and outside this pass's scope: the
4-fork parallel conductor is still unimplemented (v0 is sequential), so the process
topology, thread caps, and fork-fallback that the server will actually execute remain
untested here. F10's idle long-budget is a rank loss, not a −1.

---

## Summary of verdicts

| # | Claim | Verdict | Key numbers |
|---|---|---|---|
| 1 | prob_1 obj=1499 is global optimum | **CONFIRMED** | exact rational DP = 1499; 0 excluded pairs on prob_1; capacity non-binding (DP no-cap = 1499) |
| 1a | floor/scaling ≤ floor granularity | **CONFIRMED (empirical)** | gap=0 on prob_1/4/8/22; theoretical bound (w2−1) never realised |
| 1b | compatible-bays excludes nothing legal | **CONFIRMED** | 108 excluded pairs / 40 inst, **0 false exclusions** vs utils |
| 1c | fluid capacity not binding on prob_1 | **CONFIRMED** | DP without capacity = 1499 |
| — | certificate = global-optimum guarantee (general) | **FALSIFIED → F8** | prob_3 cert 39050 needs z1=18; best z1=0 = 82760 (2.1×) |
| 2 | polish never tardies / never worsens obj | **CONFIRMED** | 7 instances; z1 flat, obj monotone↓, feas preserved, internal==utils |
| 3 | seed = z3-optimal probe | **CONFIRMED** | seed z3 == per-block min on 9/9 |
| 4 | deadline discipline (no wall>54s) | **CONFIRMED** | walls 48.6–52.0 s @60s (budget 54.8); full pass skipped on all 6 |
| 5 | opportunity sweep | **F9, F10** | full pass regressive on prob_3 (92900>82760); prob_21 180s=60s=5277656; prob_26@60s ranged 23.4M–27.3M (timing) |

**New findings:** F8 (certificate is an unachievable fluid lower bound, not a global
optimum; LBBD cuts not wired in), F9 (O1/full pass inert/regressive on easy tier; gap
never closed), F10 (no anytime consumer of long budget — 3× budget, 0 improvement).
