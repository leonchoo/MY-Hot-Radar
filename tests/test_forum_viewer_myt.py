#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 8A regression test — Forum Viewer MYT timestamp rendering.

The bug:
    The original `formatTimestamp()` in index.js and topic.js used
    `iso.replace("T", " ").replace(/Z$/, "").substring(0, 19)` which
    strips the "Z" but does NOT add 8 hours. Result: "2026-10-01T07:15:40Z"
    displayed as "2026-10-01 07:15:40" (i.e. UTC displayed as if it were MYT).

The fix:
    A single shared formatter (forum/viewer/format.js) using
    `Intl.DateTimeFormat` with `timeZone: "Asia/Kuala_Lumpur"`. All three
    Viewer pages (index, topic, human_tips) now route their UTC ISO
    timestamps through this single function.

This test does NOT mock a browser — it parses the real served
`/static/format.js` and executes it under Node.js with the same Intl
APIs available in Chromium. If this passes, the page will render
correctly in any browser regardless of the user's system timezone.

Run with:
    python -m unittest tests.test_forum_viewer_myt
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent


def _node_executable() -> str:
    return "node"


def _fetch_format_js() -> str:
    """Fetch the live `/static/format.js` from the running viewer."""
    with urllib.request.urlopen("http://127.0.0.1:8081/static/format.js", timeout=5) as resp:
        return resp.read().decode("utf-8")


def _run_format_js(input_iso: str, function: str = "formatMyt") -> str:
    """Fetch the live `/static/format.js` from the running viewer and run
    `MYT_FORMAT.<function>(input_iso)` under Node.js, returning the
    stringified result.

    Requires the viewer to be running on http://127.0.0.1:8081.
    """
    import json
    js_code = _fetch_format_js()
    script = (
        "const window = {};\n"
        + js_code
        + f"\nconsole.log(JSON.stringify(window.MYT_FORMAT.{function}({json.dumps(input_iso)})));"
    )
    proc = subprocess.run(
        [_node_executable(), "-e", script],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"node failed: {proc.stderr}")
    out = proc.stdout.strip()
    if not out:
        raise RuntimeError(f"empty output. stderr={proc.stderr}")
    return json.loads(out)


def json_quote(s: str) -> str:
    """Serialize a Python string as a JSON literal (used inside JS source)."""
    import json
    return json.dumps(s)


VIEWER_REQUIRED_HOST = "http://127.0.0.1:8081"


def _viewer_reachable() -> bool:
    try:
        with urllib.request.urlopen(VIEWER_REQUIRED_HOST + "/", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


@unittest.skipUnless(_viewer_reachable(),
                     f"Viewer must be running at {VIEWER_REQUIRED_HOST}")
class TestViewerMytFormatter(unittest.TestCase):
    """Run the served `format.js` against the spec test cases.

    These mirror the manual `node -e` tests run during Phase 8A and
    serve as the canonical regression suite.
    """

    # ---- spec test cases ---------------------------------------------

    def test_spec_case_a_07_15_40Z_to_15_15_40(self):
        # The exact case 彪哥 reported: 07:15:40 displayed incorrectly.
        self.assertEqual(
            _run_format_js("2026-10-01T07:15:40Z"),
            "2026-10-01 15:15:40 MYT",
        )

    def test_spec_case_b_cross_day(self):
        # Cross-day rollover (Sep 30 23:15 UTC → Oct 1 07:15 MYT).
        self.assertEqual(
            _run_format_js("2026-09-30T23:15:40Z"),
            "2026-10-01 07:15:40 MYT",
        )

    def test_spec_case_c_midnight(self):
        # Midnight UTC → 08:00 MYT.
        self.assertEqual(
            _run_format_js("2026-10-01T00:00:00Z"),
            "2026-10-01 08:00:00 MYT",
        )

    # ---- edge: month rollover ----------------------------------------

    def test_edge_month_rollover(self):
        self.assertEqual(
            _run_format_js("2026-10-31T20:00:00Z"),
            "2026-11-01 04:00:00 MYT",
        )

    def test_edge_year_rollover(self):
        self.assertEqual(
            _run_format_js("2026-12-31T20:00:00Z"),
            "2027-01-01 04:00:00 MYT",
        )

    # ---- edge: leap year ---------------------------------------------

    def test_leap_year_feb_28_to_feb_29(self):
        self.assertEqual(
            _run_format_js("2028-02-28T20:00:00Z"),
            "2028-02-29 04:00:00 MYT",
        )

    def test_leap_year_feb_29_to_mar_1(self):
        self.assertEqual(
            _run_format_js("2028-02-29T20:00:00Z"),
            "2028-03-01 04:00:00 MYT",
        )

    # ---- bad input handling ------------------------------------------

    def test_empty_string(self):
        self.assertEqual(_run_format_js(""), "")

    def test_null_value(self):
        # Pass actual `null` to the JS function (not the string "null").
        script = (
            "const window = {};\n"
            + _fetch_format_js()
            + "\nconsole.log(JSON.stringify(window.MYT_FORMAT.formatMyt(null)));"
        )
        proc = subprocess.run(
            [_node_executable(), "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        import json
        self.assertEqual(json.loads(proc.stdout.strip()), "")

    def test_garbage_string(self):
        self.assertEqual(_run_format_js("not a date"), "—")

    def test_no_Z_suffix_rejected(self):
        # Defensive: input without "Z" must NOT be parsed as local time,
        # otherwise we'd silently corrupt every API that returns naive ISO.
        self.assertEqual(_run_format_js("2026-10-01T07:15:40"), "—")

    # ---- double-conversion prevention --------------------------------

    def test_double_conversion_prevented(self):
        # If a previously-formatted MYT string is fed back into the
        # formatter, it must NOT shift again (which would produce
        # "2026-10-01 23:15:40 MYT").
        once = _run_format_js("2026-10-01T07:15:40Z")
        self.assertEqual(once, "2026-10-01 15:15:40 MYT")
        # Feeding the result back must NOT double-shift.
        twice = _run_format_js(once)
        self.assertEqual(twice, "—")  # no Z suffix → rejected

    # ---- date-only / time-only helpers -------------------------------

    def test_format_myt_date(self):
        self.assertEqual(
            _run_format_js("2026-10-01T07:15:40Z", function="formatMytDate"),
            "2026-10-01 MYT",
        )

    def test_format_myt_time(self):
        self.assertEqual(
            _run_format_js("2026-10-01T07:15:40Z", function="formatMytTime"),
            "15:15:40 MYT",
        )

    # ---- served pages include format.js ------------------------------

    def test_index_html_includes_format_js(self):
        with urllib.request.urlopen(VIEWER_REQUIRED_HOST + "/", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        self.assertIn('/static/format.js', body,
                      "Forum home page must include format.js before its own JS")
        # format.js MUST come BEFORE index.js (load order)
        self.assertLess(body.index('/static/format.js'), body.index('/static/index.js'))

    def test_topic_html_includes_format_js(self):
        with urllib.request.urlopen(VIEWER_REQUIRED_HOST + "/topic.html?id=T_ae36733de0f4cf3e", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        self.assertIn('/static/format.js', body)
        self.assertLess(body.index('/static/format.js'), body.index('/static/topic.js'))

    def test_human_tips_html_includes_format_js(self):
        with urllib.request.urlopen(VIEWER_REQUIRED_HOST + "/human_tips.html", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        self.assertIn('/static/format.js', body)
        self.assertLess(body.index('/static/format.js'), body.index('/static/human_tips.js'))

    # ---- no broken formatter left in page JS -------------------------

    def test_index_js_does_not_strip_z(self):
        """Defensive: the original bug was `iso.replace(/Z$/, "")`.
        The new index.js must NOT contain that pattern."""
        with urllib.request.urlopen(VIEWER_REQUIRED_HOST + "/static/index.js", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        self.assertNotIn('replace(/Z$/', body,
                         "index.js must not strip 'Z' suffix")
        # The delegation MUST be present
        self.assertIn('MYT_FORMAT.formatMyt', body)

    def test_topic_js_does_not_strip_z(self):
        with urllib.request.urlopen(VIEWER_REQUIRED_HOST + "/static/topic.js", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        self.assertNotIn('replace(/Z$/', body)
        self.assertIn('MYT_FORMAT.formatMyt', body)

    def test_human_tips_js_does_not_strip_z(self):
        with urllib.request.urlopen(VIEWER_REQUIRED_HOST + "/static/human_tips.js", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        # human_tips.js had `let hh = h + 8` arithmetic — that was the
        # secondary bug. The new code must delegate to MYT_FORMAT.
        self.assertNotIn('let hh = h + 8', body)
        self.assertIn('MYT_FORMAT.formatMyt', body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
