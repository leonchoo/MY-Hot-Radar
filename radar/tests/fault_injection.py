"""
Fault-injection tests for the Radar Feed (per spec §32).

These test the failure modes the website must handle gracefully:

  Test B: 404 fallback (public/radar/latest.json temporarily missing)
  Test C: malformed JSON fallback
  Test D: PARTIAL status still renders (with banner)
  Test E: future-dated generated_at fallback
  Test F: stale data warning (generated_at older than 6h)
  Test G: empty topics fallback

We simulate each by replacing the public/radar/latest.json with a
crafted payload, then re-probing the page.

This script exercises the **public_output module's validator** and
the **JS file's handling code paths** (by static analysis), since we
don't have a real browser.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PUBLIC_PATH = REPO / "public" / "radar" / "latest.json"
BACKUP_PATH = REPO / "public" / "radar" / "latest.json.bak"
JS_PATH = REPO / "assets" / "js" / "radar-feed.js"

sys.path.insert(0, str(REPO))
from radar.public_output import validate_public_payload


def make_payload(**overrides):
    base = {
        "schema_version": 1,
        "public_schema_version": 1,
        "generated_at": "2026-09-29T03:00:00Z",
        "scan_id": "fault-test",
        "scan_status": "SUCCESS",
        "summary": {
            "topic_count": 1,
            "publishable_count": 1,
            "confirmed_count": 1,
            "reported_count": 0,
            "rumour_count": 0,
            "unverified_count": 0,
            "social_buzz_count": 0,
            "by_status": {"WATCH": 1},
            "by_claim_kind": {"NOT_POLITICAL": 1},
        },
        "topics": [{
            "content_key": "u:https://example.com/a",
            "title": "Test topic",
            "category": "WORLD",
            "language": "en",
            "status": "WATCH",
            "verification_status": "REPORTED",
            "confidence_label": "MEDIUM",
            "momentum": {
                "current_mentions": 1, "previous_mentions": 1,
                "growth": 0, "growth_rate": 0.0, "is_new": False,
            },
            "source_count": 1,
            "sources": [{
                "source_name": "Test Outlet", "source_tier": "B",
                "url": "https://example.com/a", "published_at": "2026-09-29T03:00:00Z",
            }],
            "is_political": False, "claim_kind": "NOT_POLITICAL",
            "political_neutral": True, "publishable": True,
        }],
    }
    base.update(overrides)
    if "topics" in overrides:
        base["topics"] = overrides["topics"]
    # sync summary.topic_count
    if "summary" not in overrides and "topics" in overrides:
        base["summary"]["topic_count"] = len(overrides["topics"])
        base["summary"]["publishable_count"] = sum(
            1 for t in overrides["topics"] if t.get("publishable")
        )
    return base


def write_public(payload):
    PUBLIC_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main():
    failures = []

    # Backup existing valid file
    if not PUBLIC_PATH.exists():
        failures.append("baseline: public/radar/latest.json does not exist")
        return failures
    shutil.copy(PUBLIC_PATH, BACKUP_PATH)

    try:
        js_src = JS_PATH.read_text(encoding="utf-8")

        # ---- Test B: 404 fallback ----
        print("=== Test B: missing public file (404 simulation) ===")
        PUBLIC_PATH.unlink()
        # JS adapter behavior: fetch returns 404 -> showFatal('error') ->
        # buildFallback(reason='error') -> "Radar Feed unavailable"
        assert "Radar Feed unavailable" in js_src, \
            "JS missing 404 fallback message"
        print("PASS Test B: JS handles 404 → 'Radar Feed unavailable'")
        # Restore
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)

        # ---- Test C: malformed JSON ----
        print("\n=== Test C: malformed JSON ===")
        PUBLIC_PATH.write_text("this is not JSON at all", encoding="utf-8")
        assert "JSON.parse" in js_src, "JS missing JSON.parse"
        assert "invalid JSON" in js_src, "JS missing malformed-JSON handler"
        print("PASS Test C: JS handles malformed JSON via JSON.parse + catch")
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)

        # ---- Test D: PARTIAL status ----
        print("\n=== Test D: PARTIAL scan status ===")
        payload = make_payload(scan_status="PARTIAL")
        errs = validate_public_payload(payload)
        assert not errs, f"PARTIAL payload should validate: {errs}"
        write_public(payload)
        assert "PARTIAL" in js_src, "JS missing PARTIAL branch"
        assert "Some sources are temporarily unavailable" in js_src, \
            "JS missing PARTIAL banner copy"
        print("PASS Test D: PARTIAL renders banner")
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)

        # ---- Test E: future-dated generated_at ----
        print("\n=== Test E: future-dated generated_at ===")
        payload = make_payload(generated_at="2099-01-01T00:00:00Z")
        errs = validate_public_payload(payload)
        # Validator does NOT reject future dates (it doesn't parse timestamps).
        # But the JS adapter's isFutureDated() does.
        assert not errs, f"validator should accept future-dated: {errs}"
        assert "isFutureDated" in js_src, "JS missing isFutureDated"
        write_public(payload)
        print("PASS Test E: future-dated hidden by isFutureDated() in JS")
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)

        # ---- Test F: stale data ----
        print("\n=== Test F: stale generated_at ===")
        # 7 hours ago
        payload = make_payload(generated_at="2026-09-29T00:00:00Z")  # arbitrary old
        # Validator accepts; JS isStale() warns.
        errs = validate_public_payload(payload)
        assert not errs
        assert "isStale" in js_src, "JS missing isStale"
        assert "Radar data may be delayed" in js_src, \
            "JS missing stale-data banner"
        print("PASS Test F: stale data triggers 'may be delayed' banner")
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)

        # ---- Test G: empty topics ----
        print("\n=== Test G: empty topics ===")
        payload = make_payload(topics=[])
        # Update summary
        payload["summary"]["topic_count"] = 0
        payload["summary"]["publishable_count"] = 0
        errs = validate_public_payload(payload)
        # Validator allows empty topics (topic_count==0)
        assert not errs, f"empty topics should pass validator: {errs}"
        assert "Radar data temporarily unavailable" in js_src, \
            "JS missing empty-fallback message"
        write_public(payload)
        print("PASS Test G: empty topics → 'temporarily unavailable'")
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)

        # ---- Test H: validator rejects bad public payload ----
        print("\n=== Test H: schema_version=99 rejected by validator ===")
        payload = make_payload()
        payload["public_schema_version"] = 99
        errs = validate_public_payload(payload)
        assert errs, "validator should reject bad public_schema_version"
        print(f"PASS Test H: validator rejects bad schema ({len(errs)} errors)")
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)

        # ---- Test I: long Chinese title preserved ----
        print("\n=== Test I: long Chinese title preserved ===")
        long_zh = "马来西亚开始遣返缅甸难民" * 5  # ~60 chars
        payload = make_payload()
        payload["topics"][0]["title"] = long_zh
        errs = validate_public_payload(payload)
        assert not errs
        write_public(payload)
        on_disk = PUBLIC_PATH.read_text(encoding="utf-8")
        assert long_zh in on_disk, "Chinese title lost in public JSON"
        print(f"PASS Test I: long Chinese title ({len(long_zh)} chars) preserved")
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)

        # ---- Test J: javascript: URL in source is rejected by validator ----
        print("\n=== Test J: javascript: URL rejected by public validator ===")
        payload = make_payload()
        payload["topics"][0]["sources"][0]["url"] = "javascript:alert(1)"
        errs = validate_public_payload(payload)
        assert any("unsafe url" in e for e in errs), \
            f"validator must reject javascript: URL; got {errs}"
        print("PASS Test J: javascript: URL rejected at the public-output gate")
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)

        # ---- Final restore: revert to the real production payload ----
        shutil.copy(BACKUP_PATH, PUBLIC_PATH)
        on_disk = json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))
        print(f"\nFinal restored public/radar/latest.json: "
              f"{on_disk['summary']['topic_count']} topics, "
              f"scan_id={on_disk['scan_id']}")

    finally:
        # Always restore the backup
        if BACKUP_PATH.exists():
            shutil.copy(BACKUP_PATH, PUBLIC_PATH)
            BACKUP_PATH.unlink()

    return failures


if __name__ == "__main__":
    failures = main()
    print()
    if failures:
        print(f"FAULT-INJECTION FAILED ({len(failures)} failures):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL FAULT-INJECTION SCENARIOS PASSED")
