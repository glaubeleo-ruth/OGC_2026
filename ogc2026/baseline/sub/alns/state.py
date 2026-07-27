"""
state.py -- SolutionState: a mutable wrapper around a flat assignment dict
that keeps derived bay occupancy (bay_placed / bay_schedule / bay_loads) in
sync, for use by ALNS destroy/repair operators.

baseline/ is not a package -- baseline/myalgorithm.py does a bare
`import baseline_greedy`, so baseline/ is expected to be on sys.path.  This
module adds it before importing sibling modules so it works whether it's
run as a script, imported as `alns.state`, or imported after baseline/ has
already been added to sys.path by something else.
"""

import os
import sys

_BASELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASELINE_DIR not in sys.path:
    sys.path.insert(0, _BASELINE_DIR)

import baseline_greedy
import utils


class SolutionState:
    """
    Wraps a flat `{block_id: assignment}` dict together with the derived
    per-bay occupancy structures (`bay_placed`, `bay_schedule`, `bay_loads`)
    that baseline_greedy's placement primitives (`_find_earliest_slot`,
    `_candidate_positions`, etc.) expect to operate on.

    An "assignment" dict has keys: block_id, bay_id, x, y, orient_idx,
    entry_time, exit_time -- the same shape `_rebuild_bay_state` and
    `_build_operations` already consume in baseline_greedy.py.

    Bay state is fully rebuilt (via `baseline_greedy._rebuild_bay_state`)
    on every remove/insert/clone call.  These training instances are small,
    so this is cheap enough; no incremental bookkeeping is attempted here.
    """

    def __init__(self, prob_info: dict, assignments: dict[int, dict]):
        self.prob_info = prob_info
        self.blocks_data = prob_info["blocks"]
        self.bays = [utils.Bay.from_dict(d, i) for i, d in enumerate(prob_info["bays"])]

        # Store a shallow copy so mutating self.assignments never mutates a
        # dict the caller still holds a reference to.
        self.assignments: dict[int, dict] = dict(assignments)

        self._rebuild()

    # -------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------

    def _rebuild(self) -> None:
        """Recompute bay_placed / bay_schedule / bay_loads from self.assignments."""
        self.bay_placed, self.bay_schedule, self.bay_loads = (
            baseline_greedy._rebuild_bay_state(self.assignments, self.bays, self.blocks_data)
        )

    # -------------------------------------------------------------------
    # Construction
    # -------------------------------------------------------------------

    @classmethod
    def from_operations(cls, prob_info: dict, solution: dict) -> "SolutionState":
        """
        Reconstruct a flat assignments dict from the wire-format
        `{"operations": {"<time>": [op, ...]}}` solution (the only thing
        baseline_greedy.greedyalgorithm() returns) and build a SolutionState
        from it.

        For each block_id we expect exactly one ENTRY op (giving bay_id, x,
        y, orient_idx, entry_time = int(time_key)) and exactly one EXIT op
        (giving exit_time = int(time_key)).  If a block is missing either
        op, or its ENTRY/EXIT bay_id disagree, this raises ValueError --
        that indicates a malformed solution, not a recoverable case.
        """
        operations = solution["operations"]

        entries: dict[int, dict] = {}
        exits: dict[int, dict] = {}

        for time_key, ops in operations.items():
            t = int(time_key)
            for op in ops:
                bid = op["block_id"]
                if op["type"] == "ENTRY":
                    if bid in entries:
                        raise ValueError(f"block {bid} has more than one ENTRY op")
                    entries[bid] = {
                        "bay_id": op["bay_id"],
                        "x": op["x"],
                        "y": op["y"],
                        "orient_idx": op["orient_idx"],
                        "entry_time": t,
                    }
                elif op["type"] == "EXIT":
                    if bid in exits:
                        raise ValueError(f"block {bid} has more than one EXIT op")
                    exits[bid] = {
                        "bay_id": op["bay_id"],
                        "exit_time": t,
                    }
                else:
                    raise ValueError(f"unknown op type {op['type']!r} for block {bid}")

        assignments: dict[int, dict] = {}
        all_ids = set(entries) | set(exits)
        for bid in all_ids:
            if bid not in entries:
                raise ValueError(f"block {bid} has an EXIT op but no ENTRY op")
            if bid not in exits:
                raise ValueError(f"block {bid} has an ENTRY op but no EXIT op")
            e, x = entries[bid], exits[bid]
            if e["bay_id"] != x["bay_id"]:
                raise ValueError(
                    f"block {bid}: ENTRY bay_id={e['bay_id']} != EXIT bay_id={x['bay_id']}"
                )
            assignments[bid] = {
                "block_id": bid,
                "bay_id": e["bay_id"],
                "x": e["x"],
                "y": e["y"],
                "orient_idx": e["orient_idx"],
                "entry_time": e["entry_time"],
                "exit_time": x["exit_time"],
            }

        return cls(prob_info, assignments)

    # -------------------------------------------------------------------
    # Mutation (consumed by future destroy/repair operators)
    # -------------------------------------------------------------------

    def remove(self, block_ids: list[int]) -> dict[int, dict]:
        """
        Pop `block_ids` out of self.assignments, rebuild bay state from
        whatever remains, and return the removed assignment dicts (keyed by
        block_id) so a destroy operator can hand them to a repair operator.
        """
        removed: dict[int, dict] = {}
        for bid in block_ids:
            removed[bid] = self.assignments.pop(bid)
        self._rebuild()
        return removed

    def insert_many(self, assignments: list[dict]) -> None:
        """
        Add many assignments with a SINGLE bay-state rebuild at the end,
        instead of one rebuild per insert.  With k removed blocks and n total,
        per-insert rebuilding costs O(k*n) Block constructions; this is O(n).
        """
        for a in assignments:
            self.assignments[a["block_id"]] = a
        self._rebuild()

    def insert(self, assignment: dict) -> None:
        """
        Add a single assignment (block_id/bay_id/x/y/orient_idx/entry_time/
        exit_time) into self.assignments and rebuild bay state.
        """
        self.assignments[assignment["block_id"]] = assignment
        self._rebuild()

    # -------------------------------------------------------------------
    # Output / copying
    # -------------------------------------------------------------------

    def to_operations(self) -> dict:
        """Convert the current assignments into the wire-format operations dict."""
        return baseline_greedy._build_operations(list(self.assignments.values()))

    def clone(self) -> "SolutionState":
        """
        Return an independent SolutionState with a copy of self.assignments
        and its own freshly-rebuilt bay state, so mutating the clone never
        affects the original.
        """
        return SolutionState(self.prob_info, dict(self.assignments))
