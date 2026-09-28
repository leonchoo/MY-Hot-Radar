"""
Top-level test runner for the Radar Phase 1 package.

Usage from project root:
    python -m radar.tests.run_all

Each test module is run in its own subprocess so state can't leak between
them, and each is individually observable.
"""
from __future__ import annotations

import sys, subprocess, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    modules = [
        "radar.tests.test_dedup",
        "radar.tests.test_verification",
        "radar.tests.test_momentum",
        "radar.tests.test_classification",
        "radar.tests.test_failures",
        "radar.tests.test_real_world",
        "radar.tests.test_evidence",
        "radar.tests.test_stability",
    ]
    failures = []
    for mod in modules:
        print(f"\n=== {mod} ===")
        # Stability tests do real RSS fetches; allow more time. Other
        # modules are pure unit/integration and finish in <30s.
        timeout_s = 300 if mod == "radar.tests.test_stability" else 60
        try:
            r = subprocess.run(
                [sys.executable, "-m", mod],
                capture_output=True, text=True,
                cwd=str(ROOT),
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            failures.append((mod, "timeout"))
            print(f"FAIL {mod} (timeout after {timeout_s}s)")
            continue
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            failures.append((mod, f"exit {r.returncode}"))
    print()
    if failures:
        print(f"{len(failures)} test module(s) failed: {failures}")
        return 1
    print("ALL RADAR TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
