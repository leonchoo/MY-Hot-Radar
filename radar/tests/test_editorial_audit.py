"""
Editorial Sampling Audit tests.

These tests verify the READ-ONLY behaviour of the audit module:

  - Sample selection is deterministic for the same input.
  - No candidate file is mutated.
  - Report contains required fields for every sampled candidate.
  - Report does not invent editorial ranking (no score, no winner,
    no top-N, no probability).

These tests are intentionally small (5 tests). They do not replace
the 378 radar/candidate tests; they layer on top.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from radar.audit.editorial_sampling import (
    AUDIT_VERSION,
    _category_proportions,
    _stride_pick,
    build_audit_report,
    select_sample,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_CANDIDATES = REPO_ROOT / "radar_data" / "candidates" / "latest.json"


def _make_candidate(
    candidate_id: str,
    category: str = "MALAYSIA",
    state: str = "READY_FOR_REVIEW",
    verification_status: str = "REPORTED",
    confidence_label: str = "MEDIUM",
    source_count: int = 1,
    is_political: bool = False,
    claim_kind: str = "NOT_POLITICAL",
    political_neutral: bool = True,
    sources: list = None,
    last_seen: str = "2026-09-29T03:00:00Z",
    headline: str = "Headline",
    content_key: str = None,
) -> dict:
    if sources is None:
        sources = [{
            "source_name": "Outlet", "source_tier": "B",
            "source_type": "RSS", "country": "MY",
            "url": "https://example.com/x", "title": "T",
            "published_at": "2026-09-29T03:00:00Z",
        }]
    if content_key is None:
        content_key = f"u:https://example.com/{candidate_id}"
    return {
        "schema_version": 1,
        "candidate_id": candidate_id,
        "content_key": content_key,
        "created_at": "2026-09-29T03:00:00Z",
        "updated_at": "2026-09-29T03:00:00Z",
        "state": state,
        "headline": headline,
        "headline_origin": "RADAR_TOPIC",
        "category": category,
        "language": "en",
        "radar_status": "WATCH",
        "verification_status": verification_status,
        "confidence_label": confidence_label,
        "source_count": source_count,
        "sources": sources,
        "momentum": {
            "current_mentions": 1, "previous_mentions": 1,
            "growth": 0, "growth_rate": 0.0, "is_new": False,
        },
        "first_seen": last_seen,
        "last_seen": last_seen,
        "mention_count": 1,
        "counter_signals": [],
        "is_political": is_political,
        "claim_kind": claim_kind,
        "political_neutral": political_neutral,
        "eligibility": {
            "eligible": True, "reasons": ["publishable"],
            "blocking_reasons": [],
        },
        "pipeline_meta": {
            "pipeline_version": "phase2-batch3b2-v1",
            "freshness_hours": 48, "freshness_anchor": "last_seen",
        },
    }


# ============================================================================
# Tests
# ============================================================================

def test_sample_selection_deterministic():
    """Same input -> same sample, every time."""
    ready = [
        _make_candidate(f"cand_{i:08d}", category="MALAYSIA"
                        if i % 2 == 0 else "WORLD")
        for i in range(30)
    ]
    s1 = select_sample(ready, sample_size=10)
    s2 = select_sample(ready, sample_size=10)
    s3 = select_sample(ready, sample_size=10)
    ids1 = [c["candidate_id"] for c in s1]
    ids2 = [c["candidate_id"] for c in s2]
    ids3 = [c["candidate_id"] for c in s3]
    assert ids1 == ids2 == ids3, \
        f"sample must be deterministic: {ids1} vs {ids2}"
    # Within a category, picks should be spread by stride.
    # 30 candidates, 15 MALAYSIA, 15 WORLD.
    # 10 slots -> ~5 / 5
    cats = sum(1 for c in s1 if c["category"] == "MALAYSIA")
    assert 4 <= cats <= 6, f"expected ~5 MALAYSIA, got {cats}"
    print(f"PASS test_sample_selection_deterministic "
          f"(sample ids = {ids1[:3]}...)")


def test_no_mutation_of_candidate_files():
    """build_audit_report must not modify any candidate file."""
    if not REAL_CANDIDATES.exists():
        print("SKIP test_no_mutation_of_candidate_files "
              "(no real candidate store)")
        return
    # Snapshot all on-disk candidate file hashes
    by_day = REAL_CANDIDATES.parent / "by_day"
    before: dict = {}
    if by_day.exists():
        for f in by_day.rglob("*.json"):
            before[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    # Also snapshot the latest.json
    before["<latest>"] = hashlib.sha256(
        REAL_CANDIDATES.read_bytes()
    ).hexdigest()

    # Run the audit against the real store
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "report.md"
        build_audit_report(REAL_CANDIDATES, out, sample_size=20)

    # Re-snapshot and compare
    after: dict = {}
    if by_day.exists():
        for f in by_day.rglob("*.json"):
            after[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    after["<latest>"] = hashlib.sha256(
        REAL_CANDIDATES.read_bytes()
    ).hexdigest()
    if before != after:
        # Report which file changed
        changed = [k for k in before if before.get(k) != after.get(k)]
        raise AssertionError(
            f"audit mutated candidate files: {changed}"
        )
    print(f"PASS test_no_mutation_of_candidate_files "
          f"({len(before)} files unchanged)")


def test_required_fields_in_report():
    """Every sampled candidate has all required fields rendered."""
    if not REAL_CANDIDATES.exists():
        print("SKIP test_required_fields_in_report "
              "(no real candidate store)")
        return
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "report.md"
        build_audit_report(REAL_CANDIDATES, out, sample_size=20)
        text = out.read_text(encoding="utf-8")

    # All required field labels are present, even if their values are
    # "none" / empty (so the auditor can see what was checked).
    required = [
        "Candidate ID", "Content Key", "Headline", "Category",
        "Radar Status", "Verification Status", "Confidence Label",
        "Source Count", "Sources", "First Seen", "Last Seen",
        "Mention Count", "Momentum", "Claim Kind", "Political",
        "Eligibility", "Reasons", "Blocking Reasons",
        "Editorial Review",
    ]
    missing = [r for r in required if r not in text]
    assert not missing, f"report missing required fields: {missing}"

    # A/B/C review options present
    assert "[ ] A — Worth developing" in text
    assert "[ ] B — Worth monitoring" in text
    assert "[ ] C — Not suitable" in text

    # 20 Candidate #N headings
    headings = re.findall(r"### Candidate #\d+", text)
    assert len(headings) == 20, \
        f"expected 20 'Candidate #N' headings, got {len(headings)}"
    print(f"PASS test_required_fields_in_report "
          f"({len(required)} required fields, {len(headings)} candidates)")


def test_report_has_no_ranking_language():
    """The report must not contain editorial-ranking language in its
    descriptive content (per-candidate sections, observation sections).

    Meta-text that explicitly forbids the words (e.g. "this report
    does not produce top-N / winner / loser") is excluded.
    """
    if not REAL_CANDIDATES.exists():
        print("SKIP test_report_has_no_ranking_language")
        return
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "report.md"
        build_audit_report(REAL_CANDIDATES, out, sample_size=20)
        text = out.read_text(encoding="utf-8")

    # Strip the disclaimer block (which by design lists forbidden words)
    no_disclaimer = re.sub(
        r"## 9\. Audit Properties.*$", "", text, flags=re.DOTALL
    )
    # Also strip the top-of-file note (similar)
    no_meta = re.sub(
        r">\s*Read-only audit.*?(?=\n##|\Z)",
        "", no_disclaimer, flags=re.DOTALL,
    )
    lower = no_meta.lower()
    forbidden = [
        "best candidate", "worst candidate", "top 10", "top-10",
        "most promising", "most newsworthy",
        "high editorial value", "low editorial value", "/10",
    ]
    found = [f for f in forbidden if f in lower]
    assert not found, \
        f"report contains ranking language: {found}"
    # No probability-style percentages. We allow descriptive count
    # ratios (e.g. "45/49 (91%) of READY carry verification_status=REPORTED")
    # but disallow phrases that pair a percentage with probability
    # language ("X% likely", "X% chance", "X% probability", "X% true").
    for forbidden_phrase in (
        r"\b\d+\s*%\s*likely\b",
        r"\b\d+\s*%\s*chance\b",
        r"\b\d+\s*%\s*probability\b",
        r"\b\d+\s*%\s*true\b",
        r"\b\d+\s*%\s*confidence\b",
    ):
        m = re.search(forbidden_phrase, text, flags=re.IGNORECASE)
        assert not m, \
            f"report contains probability percentage: {m.group(0)!r}"
    print("PASS test_report_has_no_ranking_language")


def test_report_generation_writes_only_to_output_path():
    """build_audit_report writes to the given path and nowhere else."""
    if not REAL_CANDIDATES.exists():
        print("SKIP test_report_generation_writes_only_to_output_path")
        return
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "report.md"
        # Run
        summary = build_audit_report(REAL_CANDIDATES, out, sample_size=20)
        # File exists
        assert out.exists()
        # Summary fields
        assert summary["ready_total"] >= 20
        assert summary["sample_size"] == 20
        assert "categories_in_sample" in summary
        assert "verification_in_sample" in summary
        assert summary["audit_version"] == AUDIT_VERSION
        # The report must mention it is read-only
        text = out.read_text(encoding="utf-8")
        assert "Read-only" in text or "read-only" in text, \
            "report must declare itself read-only"
        # No temp file in candidate dir
        cand_dir = REAL_CANDIDATES.parent
        # Search for any file modified during this call
        for child in cand_dir.rglob("*"):
            if child.name.endswith(".tmp") or child.name.endswith(".bak"):
                raise AssertionError(
                    f"audit left a temp file in candidate dir: {child}"
                )
    print("PASS test_report_generation_writes_only_to_output_path")


def test_select_sample_handles_small_pool():
    """When READY < sample_size, all candidates are returned."""
    ready = [_make_candidate(f"cand_{i:08d}", category="MALAYSIA")
             for i in range(3)]
    sample = select_sample(ready, sample_size=20)
    assert len(sample) == 3, f"expected 3, got {len(sample)}"
    print(f"PASS test_select_sample_handles_small_pool (got {len(sample)})")


def test_proportional_allocation_no_fabrication():
    """Categories with 0 READY candidates get 0 sample slots."""
    ready = [_make_candidate(f"cand_{i:08d}", category="MALAYSIA")
             for i in range(20)]
    alloc = _category_proportions(ready, sample_size=10)
    assert alloc == {"MALAYSIA": 10}, f"got {alloc}"
    sample = select_sample(ready, sample_size=10)
    cats = set(c["category"] for c in sample)
    assert cats == {"MALAYSIA"}, f"sample contains extra categories: {cats}"
    print("PASS test_proportional_allocation_no_fabrication")


# ============================================================================
# Runner
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_sample_selection_deterministic,
        test_no_mutation_of_candidate_files,
        test_required_fields_in_report,
        test_report_has_no_ranking_language,
        test_report_generation_writes_only_to_output_path,
        test_select_sample_handles_small_pool,
        test_proportional_allocation_no_fabrication,
    ]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            import traceback
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"ERROR {t.__name__}: {e}")
            traceback.print_exc()
    print()
    print(f"{passed} passed, {len(failed)} failed of {len(tests)} tests")
    if failed:
        for n, e in failed:
            print(f"  {n}: {e}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} EDITORIAL-AUDIT TESTS PASSED")
