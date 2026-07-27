#!/usr/bin/env python3
"""Run one instance against an unpacked submission dir and print one JSON row.

Usage: run_one.py <unzipped_submission_dir> <prob_json> <timelimit_seconds>

The row is printed to stdout as a single line starting with ROW: so the shell
runner can grep it out of any solver chatter. Exit code 0 even on infeasible —
the row carries the verdict; a non-zero exit means harness/crash (-1 class).
"""
import json
import os
import resource
import sys
import time


def main() -> int:
    subdir, prob_path, tl = sys.argv[1], sys.argv[2], float(sys.argv[3])
    sys.path.insert(0, os.path.abspath(subdir))
    os.chdir(subdir)  # submission code may open relative paths

    import utils  # noqa: E402  (from the submission dir)
    from myalgorithm import algorithm  # noqa: E402

    with open(prob_path) as f:
        prob = json.load(f)

    t0 = time.monotonic()
    sol = algorithm(prob, tl)
    wall = time.monotonic() - t0

    try:
        res = utils.check_feasibility(prob, sol)
        feasible = bool(res.get("feasible"))
        row = {
            "feasible": feasible,
            "objective": res.get("objective"),
            "obj1": res.get("obj1"),
            "obj2": res.get("obj2"),
            "obj3": res.get("obj3"),
        }
    except Exception as e:  # checker crash on returned dict = -1 class
        row = {"feasible": False, "objective": None, "checker_error": repr(e)}

    ru_self = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    ru_kids = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # ru_maxrss is kilobytes on Linux, bytes on macOS
    to_mb = (1024.0 * 1024.0) if sys.platform == "darwin" else 1024.0
    row.update(
        {
            "prob": os.path.basename(prob_path),
            "timelimit": tl,
            "wall": round(wall, 2),
            "wall_ratio": round(wall / tl, 4),
            "peak_rss_mb": round(max(ru_self, ru_kids) / to_mb, 1),
        }
    )
    print("ROW:" + json.dumps(row), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
