# Chimera entry — submit-safety panel (2026-07-25 evening)

Gate for the first real submission (FINALE_PLAN Phase 2). Protocol: chimera
`myalgorithm.algorithm` at timelimit=60, one subprocess per run, hard 80 s
external timeout, sequential, verdict by `utils.check_feasibility` only.
N=5 on the timing-sensitive overloaded trio, N=1 elsewhere; failures
re-panelled after each fix. Run by Claude per the standing eva protocol.

## Two -1 classes found and fixed during the gauntlet

1. **prob_40 overrun (5/5 reps, walls 61.4–63.1 s):** the legacy line's
   near-constant salvage overhead (+3.6 s over a 34.3 s raw grant) breaks
   through its 0.93·t−1 discipline at the small slices the chimera hands it.
   First fix: discount the slice (×0.85 − 3 s) → prob_40 clean (57.5–58.3 s).
2. **prob_38 overrun (2/2 reps, walls 66.6/75.5 s) — survived fix 1:** the
   legacy seed construction is **non-preemptible** (~40 s minimum pass on
   this geometry regardless of grant), and no static statistic separates the
   class (prob_38 and prob_40 share n=250). Final fix: the legacy line runs
   in a forked child leading its own process group; the parent SIGKILLs the
   group at the true remaining wall − 1.5 s. A killed hedge forfeits its
   result; it can never overrun the entry.

## Final panel (commit `805613e` + hard-wall fix)

| inst | N | fails | objective (med [min–max]) | wall max |
|---|---|---|---|---|
| prob_1 | 2 | 0 | 1,499 | 44.1 s |
| prob_2 | 1 | 0 | 3,690 | 49.7 s |
| prob_3 | 1 | 0 | 52,060 | 52.9 s |
| prob_4 | 1 | 0 | 16,916 | 52.1 s |
| prob_5 | 1 | 0 | 74,487 | 52.7 s |
| prob_8 | 1 | 0 | 11,252 | 49.9 s |
| prob_14 | 1 | 0 | 255,376 | 52.6 s |
| prob_21 | 6 | 0 | 4.11M [3.79M–6.83M] | 53.4 s |
| prob_26 | 6 | 0 | 27.6M [25.3M–27.9M] | 53.8 s |
| prob_38 | 3 | 0 | 82.1M [82.1M–84.2M] | **57.5 s** |
| prob_40 | 2 | 0 | 5.33M [5.31M–5.35M] | 52.6 s |

(prob_21/26 N pools the pre-fix panel reps — the fixes did not touch those
paths; prob_38/40 rows are post-final-fix only.)

## Verdict: SUBMIT-SAFE

* 0 × −1 across 24 runs post-fix; worst wall 57.5 s (prob_38, kill switch
  engaged) against the 60 s limit.
* The hedge already pays: prob_21 chimera median 4.11M vs 5.28M solver-solo
  (legacy line wins the instance).
* Known cost, accepted for the channel-de-risk submission: on prob_38-class
  instances the fixed 0.55 split + killed hedge wastes the legacy slice
  (82M vs 68.6M solver-solo-at-60). Adaptive split is Phase-3 tuning.
* Not covered here (open before a ranking submission, queue item 7):
  server-parity mode (taskset 4 cores), 900/1800 s spot checks, peak-RSS.

Zip: rebuild via `make_submission.sh` on the final commit; tag
`sub-YYYYMMDD-N` before the email (Leo sends).
