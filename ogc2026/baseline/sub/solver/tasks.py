"""
tasks.py -- typed work units of the 4-core execution model (design Part VI).

The conductor schedules these in strict priority order: marginal cores buy
*exactness* before throughput (T9).  v0 executes the ladder sequentially in
conductor.py; the dataclasses are the wire format for the forked worker pool
(fork context only, copy-on-write instance state, sequential fallback when
fork is unavailable -- guard rails carried over from the legacy contract).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Priority(IntEnum):
    ORACLE = 1     # initial / repacking pass of one bay
    RESCUE = 2     # exact-polygon (then exact-layer) re-search of a rejected
                   # zero-tardiness window -- runs BEFORE any delay is accepted
    CLUSTER = 3    # budgeted exact CP-SAT conflict repair (work-stealing unit)
    BOUND = 4      # cumulative-relaxation LB: certificates + master cuts
    AUDIT = 5      # utils.check_feasibility on a would-be incumbent
    POLISH = 6     # Z2/Z3 micro-reassignment / k-best pool exploration


@dataclass(frozen=True)
class OracleTask:
    bay_id: int
    assignment_version: int
    rng_seed: int = 0
    priority: Priority = Priority.ORACLE


@dataclass(frozen=True)
class RescueTask:
    bay_id: int
    block_id: int
    window: tuple            # (e0, e1)
    priority: Priority = Priority.RESCUE


@dataclass(frozen=True)
class ClusterTask:
    bay_id: int
    block_ids: tuple
    window: tuple            # (e0, e1); grows with remaining budget
    budget_s: float = 1.0
    priority: Priority = Priority.CLUSTER


@dataclass(frozen=True)
class BoundTask:
    bay_id: int              # -1 = pooled (instance triage)
    block_ids: tuple
    priority: Priority = Priority.BOUND


@dataclass(frozen=True)
class AuditTask:
    solution: dict = field(hash=False)
    priority: Priority = Priority.AUDIT
