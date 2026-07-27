"""
emit.py -- solution-dict emission in the official wire format.

{"operations": {str(day): [op, ...]}} with, per day, every EXIT listed before
any ENTRY (Stage-5 replay requirement).  All numbers are ints.  Under the
conservative-footprint invariant any same-type order within a day is
crane-safe, so ops are emitted in block-id order for determinism.
"""

from __future__ import annotations

from collections import defaultdict


def build_solution(placements) -> dict:
    """placements: iterable of oracle.Placement (all bays)."""
    exits = defaultdict(list)
    entries = defaultdict(list)
    for p in sorted(placements, key=lambda p: p.block_id):
        entries[p.entry].append({
            "type": "ENTRY", "block_id": int(p.block_id), "bay_id": int(p.bay_id),
            "x": int(p.x), "y": int(p.y), "orient_idx": int(p.orient_idx),
        })
        exits[p.exit].append({
            "type": "EXIT", "block_id": int(p.block_id), "bay_id": int(p.bay_id),
        })
    operations = {}
    for day in sorted(set(exits) | set(entries)):
        operations[str(int(day))] = exits.get(day, []) + entries.get(day, [])
    return {"operations": operations}
