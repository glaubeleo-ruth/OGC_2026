# BLINDSPOT PASS 2026-07-27 — parent-side audit ladder (commit 44d5c1e)

**Target:** `/Users/jungwoosuh/Desktop/workspace/03_Projects/OGC_2026/ogc2026/baseline/myalgorithm.py` @ `44d5c1eb16bf80b37a10698559d336a0a1e07c7c`, branch `main`.
**Tree at snapshot:** dirty `M ogc2026/alg_tester/settings.json`; untracked `BLINDSPOT_PASS_2026-07-26_o11_gate_partA.md`, `PROPOSAL_FLUID_COMMAND.md`, `ogc2026/COMMAND_MANUAL.md`, `ogc2026/baseline/results/2026-07-26_submission_lineage.md`, `ogc2026/baseline/results/2026-07-27_submission5_arm_gate_baseline.{csv,md}`, `ogc2026/baseline/submission.zip`. None mine. I wrote only scratch scripts.
**Findings:** F19–F24, continuing F14–F18.

*(This file supersedes an earlier partial draft written at this path by an interrupted incarnation of the same pass — that draft contained F19 only; every result in it replicated and is subsumed here.)*

## Instrument caveat (stated first, per eva)

This machine is not measurement-valid: swap 3.7–5.0 GB of 5–6 GB in continuous use. Consequences applied: claims 1 and 2 were attacked as **logic/path** questions (audit-status and feasibility assertions — contention-immune), and every number was taken **twice**, at swap ≈ 5.0 GB and again at swap ≈ 3.7 GB. All path results replicated bit-identically. All timing results moved in the **conservative** direction on the cleaner run (audit costs fell 1.3–1.7×), so I cite the swap-inflated figures. No reserve breach was measured, so no "needs idle-machine confirmation" escalation is required; the one extrapolated timing claim (F24's crossover point) is labelled as extrapolation.

## Measurements

**M1 — parent audit cost, `utils.check_feasibility` on the exact returned dict, N=3.**

| instance | n | bays | nops | audit, swap 5.0 GB | audit, swap 3.7 GB | stage-1 short-circuit |
|---|---|---|---|---|---|---|
| prob_1 | 100 | 2 | 200 | 0.050 s | 0.034 s | 0.000 s |
| prob_31 | 200 | 4 | 400 | 0.096 s | 0.057 s | 0.000 s |
| prob_20 | 300 | 5 | 600 | 0.161 s | 0.105 s | 0.001 s |
| prob_38 | 250 | 3 | 500 | **0.221 s** | 0.172 s | 0.001 s |

`{"operations": {}}` audits in 0.0001 s. Cost is linear in **n²/n_bays**, not n (prob_38 with 3 bays costs more than prob_20 with 300 blocks in 5 bays); coefficient ≈ 1.0e-5 s (swap-inflated) / 0.6–0.8e-5 s (clean). Dict size is fixed at 2n ops for any complete solution, so the brief's "bigger solution dict" premise for the tail audit is **falsified**: the tail audit and the line-1 audit are the same size on the same instance.

**M2 — kill-drain of the real, unmodified `_run_legacy_hard_walled`, N=3, two runs.** Overshoot past its own `hard_wall`: hung child **+0.525 / +0.537 s**; hung child with a hung fork `Pool(3)` **+0.510 / +0.508 s**; child that answers and exits −1.99 s. The theoretical worst case (`join(0.5)` + `killpg` + `join(2.0)` = 2.5 s) is **not** realized — SIGKILL reaps promptly and the 2.0 s join is never consumed. The setsid/killpg mechanics of 1a02fb2 are sound.

**M3 — 16 forced return paths** (monkeypatched `solver.api.solve` and `_run_legacy_hard_walled`, prob_1, tl=10). No path returned `None`. No path raised. No path emitted an unaudited dict while an **audited-feasible** one existed. Notable: `solver raises|returns None|returns empty` + hedge killed → `{"operations": {}}`; `solver infeasible` + hedge killed → the stage-1-infeasible dict; `tl=3 s` correctly gates the hedge off.

**M4 — the audit gate, swept.** Hedge answers with R seconds of **raw** budget left; audits counted inside `_offer`:

| R | 2.00 | 1.30 | 1.05 | 0.99 | 0.97 | 0.80 | 0.40 |
|---|---|---|---|---|---|---|---|
| audits performed | 1 | 1 | 1 | **0** | **0** | **0** | **0** |

Identical across both runs. The gate is the constant `_remaining() > 1.0`.

**M5 — checker robustness.** 11 malformed inputs: 10 return cleanly; **`block_id` out of range RAISES `IndexError`**. Separately, a 1-block controlled probe: the *same* solution with `operations` keys inserted in time order → stage 2; inserted reversed → stage 1 `"block 0 has no EXIT operation"`. `check_feasibility`'s first pass walks `operations` in **dict insertion order**, and within a time key EXIT must precede ENTRY.

**M6 — last-resort construction sizing.** Single-occupancy serial (one block per bay at a time; offsets accepted only when `utils.Bay.contains_block` agrees; verdict from `check_feasibility`): **12/12 feasible** on prob_1/13/17/20/21/26/27/31/36/38/39/40, build+audit **worst 0.169 s**, i.e. 8.9× inside the 1.5 s reserve. Objectives 5.9e7–2.9e9 (bad — this is −1 insurance, not an objective play).

## Findings

**F19 (−1 RISK, measured, reproduced twice) — the ladder refuses an audit it can afford ~5–19× over, and the kill-drain deterministically parks it 0.03 s inside the refusal window.** `_offer`'s gate is the constant `_remaining() > 1.0`, but `audit_cost` is measured and is 0.034–0.221 s. So for R ∈ (audit_cost, 1.0] the entry declines to audit while the audit fits comfortably — a window **0.78 s wide on prob_38** (affordable 4.5×) and 0.95 s wide on prob_1 (19×). This is not a corner: M2 shows a hedge child that answers just before `hard_wall` costs a **0.51–0.54 s** drain, leaving R = 1.5 − 0.53 = **0.97 s** — inside the window, missing the gate by 0.03 s. On the branch where `best_sol is None` (line 1 dead — exactly the prob_38 class the hedge exists for) the entry then ships an **unaudited** dict with 65% of its reserve unspent. The gate should be `_remaining() > audit_cost + margin`, not a constant.

**F20 (SOUNDNESS, forced and reproduced) — `_audit` collapses "the checker said no" with "the checker could not run", and the resulting mis-rank can ship a known-bad dict while a good one is in hand.** `_audit` returns `(False, None, dt)` for three distinct outcomes: infeasible, non-dict, and *any exception*. `_offer` maps all of them to `_RANK_REJECTED = 1`. But the header's own doctrine says a never-audited candidate is only a *risk* and must outrank a *certain* −1 — and a crashed audit is epistemically "never audited", not "rejected". Forced result: crashing checker + line-1 **feasible** + hedge infeasible arriving at R = 0.90 s → **`algorithm()` returned the infeasible dict** (`feasible=False`) with a genuinely feasible dict in hand. Note the ordering is load-bearing: with both candidates at rank 1 the tie (`1 > 1` false) keeps the first, so the inversion needs the second candidate to reach rank 2 — which the F19 window supplies for free. Fix is a tri-state from `_audit`. **Reachability is the weak link and I did not measure it**: it needs the checker to raise on a solution that is actually feasible, which in competition means an environmental fault (MemoryError/OSError under the server's memory cap) rather than the `IndexError` of M5. Missing measurement: peak RSS of `check_feasibility` on the largest instance against the eval server's cap.

**F21 (−1 RISK) — clause (2) of the header is vacuous: there is no parent-side last-resort construction, so the "reserve exists to pay for that audit" rationale funds nothing on precisely the paths that need it.** The only "last-resort construction" is `solver/api.py`'s `last_construction`, which reaches the parent as line 1's ordinary return value. When line 1 is dead (raises, returns `None`, or returns `{"operations": {}}`) *and* the hedge is SIGKILLed, the ladder returns `{"operations": {}}` — a certain −1 — with **100% of the 1.5 s reserve unspent and no construction attempted**. Forced and confirmed in M3 (three variants). The compounding argument matters more than the mechanism: the two failure conditions are not independent. Line 1 fails to bank an audited incumbent when the seed pass cannot complete a feasible pack inside its ~19 s slice, and the hedge gets killed when its non-preemptible seed needs ~40 s — both are the *same* instance property (dense, hard-to-pack). The two lines fail **together**, on exactly the class the hedge was built to cover, and the ladder's terminal rung is an empty dict.

**F22 (OPPORTUNITY, measured — the cheapest −1 removal on the table) — a feasible last resort costs 0.169 s worst case out of a 1.5 s reserve.** Single-occupancy serial placement is **12/12 feasible** across prob_1/13/17/20/21/26/27/31/36/38/39/40 including every n=250 and n=300 instance, at build+audit ≤ 0.169 s (M6). Wiring it as a genuine clause-(2) rung converts F21's certain −1 into a scored (poor) result. Expected rank impact under R − nb: zero on any instance where either line already works — it never competes with `best_sol`, it only occupies the terminal rung. Its whole value is the tail: one hidden instance of the prob_38 class turning from −1 into 2.9e9 is worth more than any objective refinement, because −1 is unbounded downside and a bad score is bounded. **Caveat:** my builder is a 40-line throwaway, and it took three iterations to get right — see F23 for why. A shipped version must reuse `solver/emit.build_solution` rather than hand-roll emission.

**F23 (−1 RISK, latent; a trap for any future emitter) — `utils.check_feasibility` is not total, and it is sensitive to `operations` key *insertion* order.** Two independently confirmed behaviours: (i) `block_id` out of range raises `IndexError` rather than returning infeasible — the checker is not total, which is why every call site must stay wrapped (all current ones are: `_audit`, `incumbent.audit_and_update`); (ii) the first pass walks `operations` in **dict insertion order**, so an otherwise-identical solution whose keys were inserted out of time order is reported `Stage1: block N has no EXIT operation`, and within a time key EXIT must precede ENTRY. Both bugs bit my throwaway builder and produced convincing-looking stage-1 and stage-5 "infeasibilities" on 5/8 instances that were pure emission artifacts. This is not currently a live defect — the shipped emitter is correct and both pickle (hedge pipe) and JSON preserve dict order, so **the parent audits the same ordering the server will see**, which is a genuine confirmation of the ladder's "exact dict about to be returned" premise. It is filed because it is a live trap for F22's implementation.

**F24 (claim-3 caveat, measured) — the "measured reserve" is inert at every scale that exists, and the one path where it would matter is the one path where its input is destroyed.** `max(1.5, 1.6·audit_cost + 0.4)` exceeds its 1.5 s floor only when `audit_cost > 0.6875 s`; the worst measured audit is **0.221 s** (prob_38, swap-inflated). So on all 40 train instances the reserve is *exactly* the flat 1.5 s of commit 1a02fb2 and the adaptive term never fires — the added complexity is currently unexercised code. Extrapolating M1's n²/n_bays law, `audit_cost` reaches the 1.0 s gate at n²/n_bays ≈ 100k on the conservative coefficient (≈125–170k on the clean run) — e.g. n ≈ 450–600 depending on bay count, versus a train maximum of 20.8k. *Credit where due:* the design is self-consistent there — the adaptive term (65k) engages before the 1.5 s floor becomes insufficient (≈150k), so the ordering is right. The defect is the **provenance** of the measurement: `audit_cost` is taken from line 1's audit, and when line 1 returns `api.solve`'s unaudited `last_construction`, the parent audit short-circuits at stage 1 in **0.001 s** (M1). The adaptive term therefore collapses to the flat 1.5 s **exactly on the line-1-failed path** — the same path where the hedge is the whole entry and where the tail audit is the only audit that will ever run. The reserve should be sized by an instance statistic (n²/n_bays) or by a floor, not by a measurement that is 221× too small precisely when it is load-bearing.

**Process note (not numbered).** The built `ogc2026/baseline/submission.zip` contains `myalgorithm.py` at 5341 bytes / mtime 2026-07-25 21:39 — that is the **1a02fb2 chimera, not the 10833-byte audit ladder**. It does contain `solver/` (74 entries), and ortools is imported lazily inside functions (`solver/assignment.py:45`, `solver/bounds.py:40`) behind a documented greedy fallback, so the ImportError route to "line 1 raises" is not live. Stale build artifact only — `make_submission.sh` rebuilds it — but if that zip were ever shipped, the entire ladder would be silently absent.

## What would beat this?

An entry whose terminal rung is a *feasible construction* rather than an empty dict. Under R − nb the ladder's ordering above the terminal rung is already close to optimal — F19 and F20 cost a handful of unaudited returns in narrow windows, and M3 shows the top of the ladder is genuinely uncloberrable. But the bottom rung is `{"operations": {}}`, and any competitor who spends 0.2 s on a trivially-feasible serial schedule has strictly dominated us on the whole tail of the hidden set, at zero cost everywhere else. That is F22, and it is one function. Second: a competitor who *doesn't split the budget* gets ~2× the search time on every instance where the hedge adds nothing — which, on the v0.4 sweep's own evidence (solver ≥ legacy on all 40 train), is every instance we can currently see. The hedge is priced as insurance against unseen classes; F21 shows it is currently insurance that pays out an empty dict on the class it was bought for.

## What makes this −1 on a hidden instance?

The concrete story needs one instance property: dense enough packing that the solver's seed pass cannot bank an audited incumbent inside its ~19 s slice. That single property then fires both failures at once. Line 1 returns `api.solve`'s `last_construction`, which the parent audits infeasible in 0.001 s — killing the adaptive reserve (F24) and leaving `best_sol = None`. The legacy hedge inherits the wall, and being the same non-preemptible ~40 s seed that walls prob_38 at 66.6/75.5 s, it gets SIGKILLed. The hedge forfeits (correctly), and the ladder returns the stage-1-infeasible line-1 dict, or `{"operations": {}}` if line 1 raised — certain −1, with the 1.5 s reserve untouched (F21). The near-miss variant is worse because it looks fine: the hedge answers *just* before `hard_wall`, the 0.53 s drain lands the entry at R = 0.97 s, the constant 1.0 s gate refuses an audit that costs 0.17 s, and the entry ships an unaudited hedge dict (F19) — which is a coin-flip rather than a certainty, and which no log will flag. Separately and independently: the parent's `_remaining()` uses the **raw** timelimit with no 0.93 safety factor, so the gate permits an audit to *start* with 1.001 s left; on a hidden instance beyond n²/n_bays ≈ 100k that audit costs more than 1.0 s and the entry overruns the raw limit by itself. That last one is extrapolation, not measurement — train tops out at 20.8k.

## Verdict table

| # | Claim | Verdict | Number |
|---|---|---|---|
| 1 | No return path emits an unaudited solution while an **audited-feasible** one exists anywhere in the run | **HOLDS** | 16/16 forced paths; never None, never raised. `best_sol` is written only in `_offer`'s audit-pass branch and read first at the return ladder — no clobber path exists. Order-preservation through pickle+JSON confirmed, so the audit really is on the returned dict. *Caveat:* the weaker and more useful property — "never emit a known-bad dict while a good one is in hand" — is **REFUTED** by F20. |
| 2 | The unaudited final fallback is reachable only when the reserve is spent **AND** nothing audited-feasible exists | **REFUTED** (on the "reserve spent" conjunct) | Audit refused at R = 0.99 s while it costs 0.034–0.221 s and 0.97 s of the 1.5 s reserve remains — 65% unspent (F19, reproduced twice). And on solver-dead + hedge-killed the entry returns `{"operations": {}}` with **100%** of the reserve unspent and no construction attempted (F21). tom's forced-kill 4 cases did not cover: solver-raises + hedge-killed, solver-infeasible + hedge-killed, the R ∈ (audit_cost, 1.0] window, or a raising audit. |
| 3 | `max(1.5, 1.6·measured_audit + 0.4)` still suffices for the tail audit at t=60 on the n=250 class | **HOLDS-WITH-CAVEAT** | Suffices with **6.8× headroom** on prob_38 (1.5 s vs 0.221 s swap-inflated; 8.7× on the clean run), and the kill-drain takes only 0.51–0.54 s of it. Both attacked premises are falsified in the design's favour: dict size is fixed at 2n, and swap-inflated costs are conservative. Caveats (F24): the adaptive term is **inert** (never fires below audit 0.6875 s; max measured 0.221 s), so the reserve is de facto the flat 1.5 s of 1a02fb2; cost scales as **n²/n_bays**, not n; and the measurement source collapses to 0.001 s exactly on the line-1-failed path where the tail audit is the only audit. |

## Files

- Progress log (append-only, survives disconnects): `/private/tmp/claude-501/-Users-jungwoosuh-Desktop-workspace-03-Projects-OGC-2026/6332b06e-d056-4262-9589-90fb10c82042/scratchpad/rex_progress_audit_ladder.txt`
- Scratch scripts (throwaway, rex's): `rex_audit_cost.py` (M1), `rex_killdrain.py` (M2), `rex_paths.py` (M3), `rex_paths2.py` (M4, M5), `rex_lastresort3.py` (M6) — same scratchpad directory.
- No solver, `alns/`, `myalgorithm.py`, `baseline_greedy.py`, `utils.py`, or `results/` file was read-modified or written by rex.

---

*Persisted verbatim by the architect session on rex's behalf (rex's harness cannot write report files), 2026-07-27. Supersedes the partial F19-only draft previously at this path.*

---

## Cold follow-up — working tree after F19–F24 package and F17 commit

**Snapshot:** 2026-07-27. `HEAD` is `00437ce` (F17 arm);
`ogc2026/baseline/myalgorithm.py` is modified but uncommitted. This addendum
is a source/path review, not a new performance measurement: the manual's
no-measurement-while-editing rule is therefore preserved. `py_compile` passes
for `myalgorithm.py`, `solver/api.py`, and `solver/congestion.py`; syntax is
not a release test.

**F25 (−1 RISK, arithmetic path proof) — F21 remains reachable despite the
new serial constructor.** The code first reserves 1.5 s, then hard-kills the
hedge, and only starts the serial constructor when `_affordable(2)` holds.
For the actual `prob_38` shape, `n=250`, `bays=3`, hence
`est_audit = 1e-5 * 250^2 / 3 = 0.20833 s`; `_affordable(2)` therefore
requires strictly more than `2 * 0.20833 + 0.6 = 1.01667 s` remaining. M2's
already-measured 0.510–0.537 s kill drain leaves only 0.963–0.990 s from the
1.5-s tail reserve. Thus on the exact F21 branch (solver raises/no incumbent,
hedge killed) the new code skips `_serial_construction` and returns the empty
placeholder again. This is not a concern about the serial schedule's
feasibility; it is a reachability failure caused by charging the 0.6-s
kill-drain margin twice: once before starting the hedge and again after the
kill has already happened.

Required repair: model *pre-hedge* and *post-kill* reserve separately. Before
launching legacy, reserve a bounded kill drain plus bounded serial-build plus
audit cost and final slack. After legacy is reaped, gate the terminal rung on
the remaining build+audit+final-slack only; do not demand a second future
kill-drain. Give serial construction its own measured conservative budget
rather than pretending it is an audit. The acceptance test is a forced
`solver raises + hedge SIGKILL` path with an M2-class drain that returns an
audited-feasible serial solution on `prob_38`, inside the raw deadline.

**F26 (release provenance, blocking) — there is no current candidate zip.**
`ogc2026/baseline/submission.zip` and its unpacked `submission/` copy contain
the same old `myalgorithm.py` (SHA-256
`e40e64c5841333e9ff642b75a4f61d4b4cd2f4e31c736af32cfc39c0cc889362`, mtime
2026-07-25 21:39). They do not contain F17 or the uncommitted F19–F24 package.
The current source hash is
`c55af48315df672b23389063be096f4c82a764da9dd793988996d6f52665d8e6`.
Separately, `make_submission.sh` names its output from `git rev-parse --short
HEAD` but does not reject a dirty tree. If invoked now it can create a zip
labelled `00437ce` whose contents include uncommitted audit-ladder code. A
hash-labelled artifact that is not that hash defeats the manual's frozen-
control and gauntlet provenance rules. Commit the intended package first;
make the builder fail on relevant dirt (or encode a dirty content hash); build
only after that; tag only the exact tested commit.

**F27 (process integrity, blocking for a ship decision) — the binding manual
and evidence are still outside version control.** `ogc2026/COMMAND_MANUAL.md`,
the F14–F24 passes, and the baseline result tables are untracked. The manual
has the right rules, but `git ls-files` confirms it is not a reproducible
repository state. The manual's relative `FINALE_PLAN.md` path does exist as
`ogc2026/FINALE_PLAN.md`, but that committed plan still says Phase 1 is "now"
and describes the chimera as near-zero-risk; it has not been reconciled with
the O11 hold, F17 gate, or audit-ladder status. Do not call this a small
documentation nit: a next session following only committed files can
legitimately repeat a falsified O11 procedure or submit the stale zip. Version
the manual, findings, plan update, and frozen-control identity together before
using them as a release gate.

**F28 (verification gap) — the claimed extended forced-path matrix is not
reproducible from the tree.** The tracked test artifacts are only the solver
parity and smoke programs; no test exercises the current `_affordable`,
tri-state audit ordering, serial terminal rung, solver-raises/hedge-killed
case, or a raising parent audit. The previous M3 scripts are external scratch
paths, and predate this modified file. The implementation may have been
checked elsewhere, but it has not been captured as repository evidence. Add a
fast deterministic, mock-clock return-path test before the 60-s smokes; it
must cover F19's boundary, F20 ordering, F25, and the raw-deadline assertion.

**F17 containment note.** The committed default arm is not literally an
unchanged baseline path: `api.solve` imports `congestion` and adds
`info["assign_arm"]` even for baseline. More importantly,
`myalgorithm.py` calls `solve(...)` without an explicit arm, so an ambient
`OGC_ASSIGN_ARM=congestion` changes the submitted entry. For experimental
control, have the production entry pass `assign_arm="baseline"` until the
N≥5 A/B approves the congestion arm; the experiment runner should select the
arm explicitly. This is a containment/provenance issue, not evidence that the
F17 heuristic is bad.

**Follow-up verdict:** **NOT SUBMIT-ELIGIBLE.** F25 leaves a demonstrated
class of solver-dead + hedge-killed paths at certain −1; F26 means no extant
zip represents the candidate source; F27–F28 mean the written gates and their
verification are not reproducible. The right order remains: fix and commit
F25, capture its forced tests, finish the isolated F17 A/B, then build one
clean hash-identical zip and run the manual's Linux-4-core gauntlet.
