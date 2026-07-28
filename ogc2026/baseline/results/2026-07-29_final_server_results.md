# Final hidden-set results — official server evaluation

**Stamp:** 2026-07-29. **Provenance:** transcribed verbatim from the final
server results message (organizer evaluation of the standing accepted
submission, attempt 6 / CHIMERA entry — the last zip accepted per
`2026-07-26_submission_lineage.md`). No local run produced these numbers.

## Results

All six hidden instances: "Feasible solution found" — zero −1.

| instance | final objective |
|---|---:|
| P1 | 11,280.0 |
| P2 | 32,068.0 |
| P3 | 220,494.0 |
| P4 | 9,289,080.0 |
| P5 | 18,663,403.0 |
| P6 | 41,948,328.0 |

## vs the same entry's Jul 25 evaluation (lineage attempt 6)

| instance | Jul 25 eval | final | delta |
|---|---:|---:|---|
| P1 | 11,280 | 11,280 | tie |
| P2 | 32,068 | 32,068 | tie |
| P3 | 376,241 | 220,494 | **−41%** |
| P4 | 10,854,126 | 9,289,080 | **−14%** |
| P5 | 18,630,178 | 18,663,403 | +0.2% |
| P6 | 52,828,500 | 41,948,328 | **−21%** |

Same submission, materially better P3/P4/P6 — consistent with the known
run-to-run timing nondeterminism on overloaded instances (and/or different
final-evaluation server conditions). Not evidence of a code change.

## vs submission_5 (frozen hedge, best prior scores)

Final beats the hedge's best on **P5 and P6**, ties P1, and trails on
P2/P3/P4. Best-ever per instance across all evaluations: P1 11,280 (tie),
P2 31,368 (#5), P3 186,910 (#5), P4 8,462,228 (#5), P5 18,630,178 (#6
Jul 25 eval), P6 41,948,328 (final).
