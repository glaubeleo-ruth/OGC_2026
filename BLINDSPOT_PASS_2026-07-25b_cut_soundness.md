# OGC 2026 — Blindspot Pass (2026-07-25b): LBBD cut-loop certificates

**Target:** the cut loop landed in commit `94cee2d` ("Wire the LBBD cut loop"),
same-day follow-up per Leo's trust gate: the session's claims ("closed
F8/F9/F10", "prob_4 proven optimal", "no regressions") went out one
verification cycle ahead of the evidence. This pass attacks the certificate
premises specifically. Findings continue the F-log at **F11**. Experiments:
`rex_cut_soundness.py` (session scratch), conda env `ogc2026`.

---

## Claim — "prob_4 = 16,916 proven optimal (`master_bound_closed`)"

**VERDICT: REFUTED as stated; the honest claim is optimum ∈ [15,946, 16,916].**

### F11 (SOUNDNESS of the stop rule) — evaluated-but-tardy proposals hide below the "closed" bound

The `master_bound_closed` stop reasoned: "cuts + no-goods only raise the master
bound; once it clears the incumbent, nothing unevaluated can win." True — but
**evaluated** proposals were excluded by no-good on the strength of a *heuristic
packing*, not a proof. A proposal that packed tardy has true cost possibly as
low as its assignment-layer cost (a perfect packer might reach z1=0 on it).

Measured (prob_4 loop replay, 15 iterations, layer costs walk 15,946 → 18,755
in unfloored k-best order as designed):

| iter | layer cost | packed tardy blocks | realized obj |
|---|---|---|---|
| 0 | **15,946** | 2 | 50,332 |
| 1 | **16,254** | 3 | 120,875 |
| 10 | 18,129 | 0 | **16,916** (incumbent) |

Iterations 0 and 1 sit **below** the claimed optimum of 16,916 and were never
refuted — only out-packed. **Fix (landed with this pass):** the loop now tracks
tardy-packed proposals' layer costs; `master_bound_closed` requires none open
below the incumbent, otherwise it reports
`bound_closed_with_open_candidates` with the open minimum. Closing those
candidates for real needs the exact tiers (queue item 4) to either pack them
z1=0 or refute them with a sound conflict cut.

### F12 (floor slack in both stop rules) — bounds overstate by up to w2

The master minimizes **unfloored** micro-scaled z2; `_master_bound` prices its
argmin with `floor(z2*)`. A different assignment can have higher unfloored but
lower floored cost, so every "reached/closed" verdict is exact only to within
one floor granule (≤ w2; = 7 on prob_1/4). Both stop records now carry
`floor_slack = w2`. (Empirically zero on every instance rex's exact DP has
checked — prob_1/4/8/22, F8-a — but the claim must carry the slack.)

### Capacity premise — held on prob_4 (empirical, instance-scoped)

rho=1.0 vs no-capacity master solves are bit-identical on prob_4
(z2* = 2278.971521, z3* = 0 both ways) — the fluid capacity excluded nothing
at this optimum. This does NOT generalize: the max-layer-area form is the
F5-flagged unsound shape, and on instances where it binds, `assignment_lb`
could exceed the true optimum. Unattacked surface; re-test per instance before
trusting an `assignment_lb_reached` on a new instance class.

### F13 (stale certificate fields) — greedy fallback masqueraded as OPTIMAL

`AssignmentMaster.solve` returned the greedy fallback (budget floor / solver
exception) **without resetting** `last_status/last_z2/last_z3`, so a greedy
proposal could inherit "OPTIMAL" + stale z2/z3 from an earlier solve — wrong
info downstream (conductor logs, stop-rule pricing; the stop rules themselves
err conservative with a stale-older bound, so this is a reporting bug, not a
wrong-stop bug). **Fix (landed):** fields reset to `"greedy"`/None on entry.

### theta cuts (prob_7) — UNVERIFIED, not refuted

The replay produced a different proposal trajectory (master_cap 10 vs 8) and
derived 0 cuts, so the two cuts from the 60 s run could not be re-verified at
a longer CP-SAT budget. Their soundness currently rests on the monotonicity
argument + F5's cumulative relaxation only. Open item for the next pass:
persist derived cuts to the info stream so they can be re-attacked offline.

### "No regressions" — downgrade to "no regressions outside timing noise"

The sweep was N=1 under the documented ~14% timing swing (F10 note). The
easy/mid-tier improvements (−37% … −98%) are far outside noise; the
overloaded-tail deltas are indicative only. eva's N≥5 panel is the
decision-grade instrument.

---

## Summary

| # | Finding | Status |
|---|---|---|
| F11 | `master_bound_closed` ignored tardy-evaluated candidates below the bound; prob_4 "proven optimal" refuted → optimum ∈ [15,946, 16,916] | fix landed; true closure needs exact tiers |
| F12 | stop-rule bounds overstate by ≤ w2 (floor granularity) | slack now reported |
| F13 | greedy fallback inherited stale OPTIMAL certificate fields | fix landed |
| — | rho=1.0 capacity premise | held on prob_4; per-instance surface, unattacked in general |
| — | prob_7 theta cuts | unverified (not reproduced); persist cuts for offline attack |
