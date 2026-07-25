# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

This is a contest submission (OGC 2026, prior year's problem) for a Pure Car and Truck Carrier
(PCTC) deck-loading/routing problem. Given a "deck graph" (nodes = parking positions, a root
"gate" node = 0) and a set of origin-destination demands (cars to load at port `o` and unload at
port `q`), the algorithm decides where each car parks and the loading/unloading/rehandling routes
at each port, minimizing total cost (a fixed cost per route move plus distance traveled). The core
solver is a MIP built with Gurobi, exposed to Python via a C-ABI shared library.

`readme.md` (Korean) describes the submission format and lists the required files; the algorithm
is invoked in two steps: build the shared library, then call it from Python.

## Build

Requires Gurobi installed locally, with `GUROBI_HOME` set (e.g.
`export GUROBI_HOME=/opt/gurobi1200/linux64`).

```bash
./build.sh
```

This compiles `function.cpp` and `myalgorithm.cpp` (C++17, `-O3 -fPIC`) and links against
`-lgurobi_c++ -lgurobi120` from `$GUROBI_HOME`, producing `lib_myalgorithm.so`. Intermediate `.o`
files are cleaned up automatically; the script `set -e`s so it aborts on the first failed step.

Note: `Base.hpp` includes `./json.hpp` (expects an nlohmann::json single-header amalgamation) but
no code in this repo actually uses the `json` alias yet — that header must be present alongside
the others for the build to succeed, even though it isn't currently checked in.

There is no test suite, linter, or CI config in this repo — validation is done by running the
algorithm and checking feasibility (see below).

## Running / validating

`myalgorithm.py::algorithm(prob_info, timelimit=60)` loads `lib_myalgorithm.so` via `ctypes`,
converts `prob_info` (a dict with keys `N`, `E`, `K`, `P`, `F`, `LB` — see `util.py` docstrings)
into flat C arrays, calls the exported `solve(...)` function, and parses the flat output arrays
back into a `solution` dict of the form `{port_idx: [[route, demand_index], ...], ...}`.

`util.py::check_feasibility(prob_info, solution)` is the organizer-provided validator: it replays
every route against the deck graph and node-occupancy state to check route validity (simple paths,
edges exist in `E`), correct loading/unloading/rehandling order, and that per-port demand
allocations match what's expected, then reports `{feasible, obj, infeasibility}`. Use this to
verify any change to the solver's output construction. `util.py` also has plain-Python reference
implementations of BFS/Dijkstra/path-backtracking used for sanity-checking distances.

Because the output buffers passed into `solve()` are pre-sized by the Python side using an
estimated upper bound on route/path-node counts (`max_num_routes`, `max_total_route_len` in
`myalgorithm.py`), changes to how routes are generated in C++ must stay within these bounds or the
Python-allocated ctypes arrays will overflow.

## Architecture

Call chain: `myalgorithm.py` (ctypes) → `solve()` in `myalgorithm.cpp` (extern "C" entry point) →
helper functions in `function.cpp`/`function.hpp`.

- **`Base.hpp`** — shared type aliases (`PortId`, `NodeId`, `Distance`, `Demand`, `Cost`, all
  `int`), `INF`/`TOL` constants, and `idx2`/`idx3` flat-array index helpers used throughout for
  encoding multi-dimensional (p, q, i) indices into 1D vectors (since Gurobi variables and outputs
  are stored as flat `vector<GRBVar>`/`vector<int>`, not multi-dim arrays).
- **`Graph.hpp`** — `Node` struct for the deck graph: `_accessible`, `_position` (BFS order used to
  orient routing: loading moves along position-ascending routes, unloading along
  position-descending routes), `_pred`, `_dist` (BFS distance from the root/gate node), and
  `_neighborVec`.
- **`myalgorithm.cpp` (`solve`)** — orchestrates one end-to-end solve:
  1. Reconstructs `nodeVec` (graph) and demand vectors from the flat input arrays.
  2. Runs `getBFSOrientation` to assign `_position`/`_dist`/`_pred` from the root node.
  3. Builds Gurobi decision variables: `x_pqi` (car loaded at port p, unloaded at port q, occupies
     node i), `y_pi` (node i accessible from root while port p is being processed), `z_pqr`
     (demand split routing p→r via intermediate q).
  4. Calls `formulate` to add these variables/constraints to the Gurobi model, sets a time budget
     (`time_limit` minus elapsed time minus a fixed `postprocessingTime` reserve), tunes Gurobi
     params (barrier method + no crossover for the root LP, `NoRelHeurTime` heuristic gated by a
     problem-size threshold, absolute MIP gap of `2 - TOL`, heuristics proportion, a solution pool
     of size 1), then calls `model.optimize()`.
  5. Calls `get_solution` to translate the Gurobi solution back into per-port route lists, which
     are flattened into the `out_*` arrays for Python to read back.
- **`function.cpp`/`function.hpp`** — implementation of the above helpers plus:
  `getAccessibilityInfo` (derives node accessibility for a port from `x_pqi`), `getDemandIdVec`
  (splits/tracks demand quantities across `z_pqr`), and `getUnloadingRoute` (walks the graph to
  build an actual unloading path for a node).
- **`myalgorithm.py`** — Python/C++ boundary: defines `ctypes` argtypes for `solve`, flattens
  `prob_info` into C arrays, pre-allocates output buffers sized from problem data, and reassembles
  the flat outputs into the nested `solution` dict format expected by `util.py`.
- **`util.py`** — organizer-provided: `check_feasibility` (solution validator/objective scorer) and
  reference `bfs`/`dijkstra`/`path_backtracking` implementations operating on plain adjacency-list
  graphs with a `node_allocations` occupancy array (-1 = empty, else = demand index occupying that
  node).

When modifying the C++ solver, keep `myalgorithm.hpp`'s `extern "C" void solve(...)` signature,
`myalgorithm.py`'s ctypes argtypes, and the output buffer sizing assumptions all in sync — they
must agree on argument order and array layout since there's no runtime type checking across the
ctypes boundary.
