"""
Top-level test runner for the Performance & Market Intelligence P1 package.

Usage from project root:

    python -m performance.tests.run_all

Each test module is run in its own subprocess so state can't leak
between them, and each is individually observable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    modules = [
        "performance.tests.test_performance",
        "performance.tests.test_story",
        "performance.tests.test_adapters",
        "performance.tests.test_android_bridge",
        "performance.tests.test_real_adapter_persistence",
        "performance.tests.test_dual_snapshot",
        "performance.tests.test_category_extraction",
        "performance.tests.test_category_propagation",
    ]
    failures = []
    for mod in modules:
        print(f"\n=== {mod} ===")
        try:
            r = subprocess.run(
                [sys.executable, "-m", mod],
                capture_output=True, text=True,
                cwd=str(ROOT), timeout=300,
            )
        except subprocess.TimeoutExpired:
            failures.append((mod, "timeout"))
            print(f"FAIL {mod} (timeout)")
            continue
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            failures.append((mod, f"exit {r.returncode}"))
    print()
    if failures:
        print(f"{len(failures)} test module(s) failed: {failures}")
        return 1
    print("ALL PERFORMANCE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
