"""
CLI entry point for a manual radar scan.

Usage (from project root):
    python -m radar.scan
    python -m radar.scan --inject-fixture
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .pipeline import run_scan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MY Hot Radar - manual scan")
    parser.add_argument("--radar-dir", default=None,
                        help="Output directory for history + latest.json/latest.md")
    parser.add_argument("--inject-fixture", action="store_true",
                        help="Run a deterministic fixture scan (no network) "
                             "used by tests and onboarding. Safe to invoke "
                             "manually; covers dedup + verification + momentum "
                             "+ classification end-to-end.")
    args = parser.parse_args(argv)

    extra_stories = None
    if args.inject_fixture:
        from .tests.fixtures import fixture_stories
        extra_stories = fixture_stories()

    summary = run_scan(extra_stories=extra_stories, radar_dir=args.radar_dir)
    print(json.dumps({k: v for k, v in summary.items() if k != "source_status"},
                     ensure_ascii=False, indent=2, default=str))
    print("\nSource status:")
    for s in summary["source_status"]:
        print(f"  {s['name']:<26} {s['type']:<14} ok={s.get('ok')}"
              f" fetched={s.get('fetched', 0)}"
              + (f" err={s.get('error')!r}" if s.get("error") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
