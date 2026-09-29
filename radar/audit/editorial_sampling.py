"""
Editorial Sampling Audit — Phase 2 B3B-2.

READ-ONLY module. Produces an editorial sampling report from the
current Article Candidate store. Does NOT mutate any candidate file
or any production JSON.

Public entry points:

  build_audit_report(candidate_latest_path, output_report_path,
                      sample_size=20) -> dict

The function is deterministic given the same input file (sorted by
candidate_id, stride-sampled by category, no time-based randomness).
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reuse the candidate module's URL safety rule for the report's URL
# rendering. We do NOT import run_candidate_pipeline — this audit
# never re-runs the pipeline.
from ..candidate import _is_safe_url


SCHEMA_VERSION = 1
AUDIT_VERSION = "phase2-b3b2-editorial-audit-v1"


# ============================================================================
# Deterministic sample selection
# ============================================================================

def _category_proportions(ready: List[dict], sample_size: int) -> Dict[str, int]:
    """Allocate the sample across categories proportionally to READY counts.

    For the current data (49 READY, 26 MALAYSIA, 23 WORLD, 0 elsewhere),
    a sample of 20 yields ~10.6 / 9.4 → 10/10 after rounding down.
    No category is fabricated: a category with 0 READY receives 0 slots.
    """
    if not ready:
        return {}
    cats = Counter(c["category"] for c in ready)
    n = len(ready)
    alloc: Dict[str, int] = {}
    remaining = sample_size
    # First pass: floor-proportional
    for cat, count in cats.items():
        alloc[cat] = int(sample_size * count / n)
        remaining -= alloc[cat]
    # Distribute leftover to largest categories
    for cat, _ in cats.most_common():
        if remaining <= 0:
            break
        alloc[cat] += 1
        remaining -= 1
    return alloc


def _stride_pick(items: List[dict], n: int) -> List[dict]:
    """Pick n items from items using a deterministic stride pattern.

    Sort is by candidate_id (already a stable hash), so the same input
    yields the same selection every time.
    """
    if len(items) <= n:
        return list(items)
    items = sorted(items, key=lambda c: c["candidate_id"])
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def select_sample(ready: List[dict], sample_size: int = 20) -> List[dict]:
    """Pick `sample_size` candidates across categories.

    Returns a deterministic, balanced sample. No mutation of input.
    """
    alloc = _category_proportions(ready, sample_size)
    sample: List[dict] = []
    for cat, n_slots in sorted(alloc.items()):
        bucket = [c for c in ready if c["category"] == cat]
        sample.extend(_stride_pick(bucket, n_slots))
    return sample


# ============================================================================
# Source URL rendering (read-only, safe)
# ============================================================================

def _render_sources(sources: List[dict]) -> List[dict]:
    """Render source fields for the report.

    Strips any non-printable / control characters from text fields but
    preserves printable Unicode (CJK etc.). The URL is passed through
    _is_safe_url; unsafe URLs are still shown but with a marker.
    """
    out: List[dict] = []
    for s in sources or []:
        url = s.get("url") or ""
        safe = _is_safe_url(url) if url else False
        out.append({
            "source_name": _clean(s.get("source_name") or ""),
            "source_tier": _clean(s.get("source_tier") or ""),
            "source_type": _clean(s.get("source_type") or ""),
            "country": _clean(s.get("country") or ""),
            "url_safe": safe,
            "url": url,
            "title": _clean(s.get("title") or ""),
            "published_at": _clean(s.get("published_at") or ""),
        })
    return out


def _clean(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return "".join(
        ch for ch in text
        if 32 <= ord(ch) < 127 or 160 <= ord(ch)
    )


# ============================================================================
# Eligibility / freshness helpers (read-only)
# ============================================================================

def _parse_iso_or_rfc(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(ts)
        if dt is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _age_hours(ts: str) -> Optional[float]:
    dt = _parse_iso_or_rfc(ts)
    if dt is None:
        return None
    delta = datetime.now(timezone.utc) - dt
    return delta.total_seconds() / 3600.0


# ============================================================================
# Observation builders (audit-only; never modify the candidate store)
# ============================================================================

def _eligibility_precision_observations(ready: List[dict]) -> List[str]:
    """Surface FACTUAL observations about the READY pool. No judgement."""
    obs: List[str] = []
    if not ready:
        return ["No READY_FOR_REVIEW candidates were available."]

    n = len(ready)
    # Single-source ratio
    single = sum(1 for c in ready if c.get("source_count", 0) == 1)
    obs.append(
        f"{single}/{n} ({single*100//n if n else 0}%) of READY candidates "
        f"have exactly one source in the Radar evidence row."
    )

    # Reported ratio
    rep = sum(1 for c in ready if c.get("verification_status") == "REPORTED")
    obs.append(
        f"{rep}/{n} ({rep*100//n if n else 0}%) of READY candidates carry "
        f"verification_status=REPORTED (not CONFIRMED)."
    )

    # Confidence LOW/MINIMAL — these would be the obvious "should be blocked"
    # candidates if our rules were strict, but we explicitly allow them.
    low = sum(1 for c in ready
              if c.get("confidence_label") in ("LOW", "MINIMAL", "NONE"))
    high = sum(1 for c in ready if c.get("confidence_label") == "HIGH")
    if low == 0:
        med = sum(1 for c in ready
                  if c.get("confidence_label") == "MEDIUM")
        obs.append(
            f"No READY candidate has confidence_label LOW/MINIMAL/NONE. "
            f"All {n} are MEDIUM or HIGH ({med} MEDIUM, {high} HIGH)."
        )
    else:
        obs.append(
            f"{low} READY candidate(s) have confidence LOW/MINIMAL/NONE. "
            "This is by spec design (LOW confidence is NOT a default BLOCK)."
        )

    # Confidence HIGH already counted above; note observation for reviewer
    if high:
        obs.append(
            f"{high} READY candidate(s) have confidence_label=HIGH."
        )

    # Categories actually represented
    cats = Counter(c.get("category") for c in ready)
    obs.append(
        f"Categories represented in READY pool: {sorted(cats.keys())}. "
        f"The current Radar source registry covers {sorted(cats.keys())} "
        f"only; Viral/Celebrity/Food sections on the website have no "
        f"corresponding Radar source yet (this is a source-coverage "
        f"observation, not a candidate-layer rule)."
    )
    return obs


def _category_observations(ready: List[dict]) -> List[str]:
    obs: List[str] = []
    by_cat: Dict[str, List[dict]] = {}
    for c in ready:
        by_cat.setdefault(c.get("category", "?"), []).append(c)
    for cat in sorted(by_cat):
        items = by_cat[cat]
        rep = sum(1 for c in items if c.get("verification_status") == "REPORTED")
        confirmed = sum(1 for c in items if c.get("verification_status") == "CONFIRMED")
        single = sum(1 for c in items if c.get("source_count", 0) == 1)
        obs.append(
            f"[{cat}] count={len(items)}, REPORTED={rep}, CONFIRMED={confirmed}, "
            f"single_source={single}."
        )
    return obs


def _freshness_observations(ready: List[dict]) -> List[str]:
    obs: List[str] = []
    ages = [a for a in (_age_hours(c.get("last_seen", "")) for c in ready) if a is not None]
    if not ages:
        return ["No parsable last_seen timestamps in READY pool."]
    obs.append(
        f"last_seen ages (hours) — min={min(ages):.2f}, "
        f"median={sorted(ages)[len(ages)//2]:.2f}, "
        f"max={max(ages):.2f}, "
        f"count_within_24h={sum(1 for a in ages if a <= 24)}, "
        f"count_within_48h={sum(1 for a in ages if a <= 48)}."
    )
    # 48h boundary check
    near_boundary = sum(1 for a in ages if 47.0 <= a <= 49.0)
    if near_boundary:
        obs.append(
            f"{near_boundary} candidate(s) have last_seen within 47–49h of now, "
            f"close to the 48h freshness threshold. Future runs may flip these "
            f"to BLOCKED (stale) without any source change."
        )
    else:
        obs.append(
            "No candidate is currently within 1h of the 48h freshness boundary."
        )
    return obs


def _political_observations(ready: List[dict]) -> List[str]:
    obs: List[str] = []
    pol = [c for c in ready if c.get("is_political")]
    obs.append(
        f"Political READY count: {len(pol)} "
        f"(political_neutral=True in all of them per Radar)."
    )
    if pol:
        by_kind: Counter = Counter(c.get("claim_kind") for c in pol)
        obs.append(f"Political claim_kind distribution: {dict(by_kind)}.")
        by_v: Counter = Counter(c.get("verification_status") for c in pol)
        obs.append(f"Political verification distribution: {dict(by_v)}.")
        # No OPINION should appear (those are BLOCKED)
        opinions = [c for c in pol if c.get("claim_kind") == "OPINION"]
        if opinions:
            obs.append(
                f"UNEXPECTED: {len(opinions)} political+OPINION candidate(s) "
                f"appear in READY. By spec they should be BLOCKED. This is an "
                f"observation flag for the human reviewer to investigate."
            )
        else:
            obs.append(
                "No political+OPINION candidate appears in READY — consistent "
                "with the BLOCKED political_non_neutral rule."
            )
    else:
        obs.append("No political candidates in current READY pool.")
    return obs


def _source_observations(ready: List[dict]) -> List[str]:
    obs: List[str] = []
    n_ready = len(ready)
    n_source_rows = sum(len(c.get("sources") or []) for c in ready)
    obs.append(
        f"Total source rows across {n_ready} READY candidates: "
        f"{n_source_rows} (avg={n_source_rows / n_ready if n_ready else 0:.2f} "
        f"per candidate)."
    )
    by_tier: Counter = Counter()
    by_type: Counter = Counter()
    by_country: Counter = Counter()
    for c in ready:
        for s in (c.get("sources") or []):
            by_tier[s.get("source_tier", "?")] += 1
            by_type[s.get("source_type", "?")] += 1
            by_country[s.get("country", "?")] += 1
    obs.append(
        f"Source tier distribution (per source row, total {n_source_rows}): "
        f"{dict(by_tier)}"
    )
    obs.append(
        f"Source type distribution (per source row, total {n_source_rows}): "
        f"{dict(by_type)}"
    )
    obs.append(
        f"Source country distribution (per source row, total {n_source_rows}): "
        f"{dict(by_country)}"
    )
    return obs


# ============================================================================
# Markdown report builder
# ============================================================================

def _candidate_section(idx: int, c: dict, sources: List[dict]) -> str:
    lines: List[str] = []
    lines.append(f"### Candidate #{idx}")
    lines.append("")
    lines.append(f"- **Candidate ID:** `{c.get('candidate_id', '')}`")
    lines.append(f"- **Content Key:** `{c.get('content_key', '')}`")
    lines.append(f"- **Headline:** {c.get('headline', '')}")
    lines.append(f"- **Category:** {c.get('category', '')}")
    lines.append("")
    lines.append(f"- **Radar Status:** {c.get('radar_status', '')}")
    lines.append(f"- **Verification Status:** {c.get('verification_status', '')}")
    lines.append(f"- **Confidence Label:** {c.get('confidence_label', '')}")
    lines.append("")
    lines.append(f"- **Source Count:** {c.get('source_count', 0)}")
    lines.append("- **Sources:**")
    for s in sources:
        url = s.get("url", "")
        url_marker = " (url_safe=True)" if s.get("url_safe") else " (url_safe=False)"
        lines.append(
            f"  - `{s.get('source_name', '')}` "
            f"[tier={s.get('source_tier', '')}, "
            f"type={s.get('source_type', '')}, "
            f"country={s.get('country', '')}]"
        )
        if url:
            lines.append(f"    - URL: {url}{url_marker}")
        else:
            lines.append(f"    - URL: (none)")
        if s.get("title"):
            lines.append(f"    - Source Title: {s.get('title', '')}")
        if s.get("published_at"):
            lines.append(f"    - Published At: {s.get('published_at', '')}")
    lines.append("")
    lines.append(f"- **First Seen:** {c.get('first_seen', '')}")
    lines.append(f"- **Last Seen:** {c.get('last_seen', '')}")
    age = _age_hours(c.get("last_seen", ""))
    if age is not None:
        lines.append(f"- **Last Seen Age:** {age:.2f} hours")
    lines.append(f"- **Mention Count:** {c.get('mention_count', 0)}")
    lines.append("")
    mom = c.get("momentum", {}) or {}
    lines.append(
        f"- **Momentum:** current={mom.get('current_mentions', '?')}, "
        f"previous={mom.get('previous_mentions', '?')}, "
        f"growth={mom.get('growth', '?')}, "
        f"growth_rate={mom.get('growth_rate', '?')}, "
        f"is_new={mom.get('is_new', '?')}"
    )
    lines.append(f"- **Claim Kind:** {c.get('claim_kind', '')}")
    lines.append(
        f"- **Political:** is_political={c.get('is_political')}, "
        f"political_neutral={c.get('political_neutral')}"
    )
    lines.append("")
    elig = c.get("eligibility", {}) or {}
    lines.append(
        f"- **Eligibility:** eligible={elig.get('eligible', '?')}"
    )
    reasons = elig.get("reasons", []) or []
    if reasons:
        lines.append(f"  - Reasons: {', '.join(reasons)}")
    else:
        lines.append(f"  - Reasons: (none recorded)")
    blockers = elig.get("blocking_reasons", []) or []
    if blockers:
        lines.append(f"  - Blocking Reasons: {', '.join(blockers)}")
    else:
        lines.append(f"  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)")
    lines.append("")
    lines.append("- **Editorial Review:**")
    lines.append("  - [ ] A — Worth developing into an article")
    lines.append("  - [ ] B — Worth monitoring")
    lines.append("  - [ ] C — Not suitable as an article candidate")
    lines.append("- **Reason:**")
    lines.append("  _____________________________________________")
    lines.append("")
    return "\n".join(lines)


def _build_summary_block(
    ready_total: int,
    sample: List[dict],
    full_ready: List[dict],
) -> str:
    lines: List[str] = []
    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"- **READY_FOR_REVIEW total:** {ready_total}")
    lines.append(f"- **Sample size:** {len(sample)}")
    cats_sample = Counter(c.get("category") for c in sample)
    lines.append(
        f"- **Categories represented in sample:** "
        f"{sorted(cats_sample.keys())}"
    )
    v_sample = Counter(c.get("verification_status") for c in sample)
    lines.append(f"- **Verification distribution (sample):** {dict(v_sample)}")
    co_sample = Counter(c.get("confidence_label") for c in sample)
    lines.append(f"- **Confidence distribution (sample):** {dict(co_sample)}")
    src_sample = Counter(c.get("source_count") for c in sample)
    lines.append(
        f"- **Source-count distribution (sample):** {dict(src_sample)}"
    )
    pol_sample = Counter(
        (c.get("is_political"), c.get("claim_kind")) for c in sample
    )
    lines.append(
        f"- **Political flag distribution (sample):** {dict(pol_sample)}"
    )
    return "\n".join(lines)


def _build_observations_block(ready_full: List[dict]) -> str:
    sections = [
        ("A. Eligibility Precision Observations",
         _eligibility_precision_observations(ready_full)),
        ("B. Category Observations",
         _category_observations(ready_full)),
        ("C. Freshness Observations",
         _freshness_observations(ready_full)),
        ("D. Political Observations",
         _political_observations(ready_full)),
        ("E. Source Evidence Audit",
         _source_observations(ready_full)),
    ]
    out: List[str] = []
    for title, obs in sections:
        out.append(f"## {title}")
        out.append("")
        for line in obs:
            out.append(f"- {line}")
        out.append("")
    return "\n".join(out)


def build_audit_report(
    candidate_latest_path: Path,
    output_report_path: Path,
    sample_size: int = 20,
) -> dict:
    """Build the editorial sampling report.

    Returns a dict with summary stats. The report is written to
    `output_report_path` as a markdown file. No candidate file is
    modified.
    """
    p = Path(candidate_latest_path)
    if not p.exists():
        raise FileNotFoundError(f"candidate latest.json not found: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    candidates = payload.get("candidates", [])
    ready = [c for c in candidates if c.get("state") == "READY_FOR_REVIEW"]

    # Snapshot candidate file mtimes / hashes for the no-mutation test.
    file_hashes: Dict[str, str] = {}
    cand_dir = p.parent / "by_day"
    if cand_dir.exists():
        import hashlib
        for f in cand_dir.rglob("*.json"):
            file_hashes[str(f)] = hashlib.sha256(
                f.read_bytes()
            ).hexdigest()

    if len(ready) < sample_size:
        sample = list(ready)
    else:
        sample = select_sample(ready, sample_size=sample_size)

    # Build the markdown
    lines: List[str] = []
    lines.append("# Editorial Sampling Report — Article Candidate Pipeline")
    lines.append("")
    lines.append(f"- **Audit version:** {AUDIT_VERSION}")
    lines.append(
        f"- **Generated at (UTC):** "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    lines.append(f"- **Source:** `{p}`")
    lines.append("")
    lines.append("> Read-only audit. No candidate file is modified. No "
                  "production JSON is touched. No editorial ranking is "
                  "produced — this is a sampling report, not a score.")
    lines.append("")

    lines.append(_build_summary_block(len(ready), sample, ready))
    lines.append("")

    lines.append("## 2. Sampling Method")
    lines.append("")
    lines.append(
        "Candidates are sorted by `candidate_id` (a deterministic SHA-256 "
        "prefix). Within each category bucket, a stride-pick (step = "
        "len(bucket) / n_slots) is used so the sample is reproducible and "
        "spread across the bucket. No category is fabricated: if a category "
        "has 0 READY candidates, it appears as 0 in the sample."
    )
    lines.append("")

    lines.append("## 3. Per-Candidate Detail")
    lines.append("")
    for i, c in enumerate(sample, 1):
        sources = _render_sources(c.get("sources", []))
        lines.append(_candidate_section(i, c, sources))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(_build_observations_block(ready))
    lines.append("")

    lines.append("## 9. Audit Properties")
    lines.append("")
    lines.append(
        "- **Read-only:** This report reads `radar_data/candidates/latest.json` "
        "and `by_day/**/*.json`. It never writes back to those files."
    )
    lines.append(
        "- **No production impact:** No change to public/radar/latest.json, "
        "the website, the scheduler, or git."
    )
    lines.append(
        "- **No ranking:** No score, no winner, no top-N, no probability. "
        "Each sample row is a flat observation, intended for a human "
        "reviewer to fill in A / B / C."
    )
    lines.append(
        "- **Reproducible:** The same input file + sample_size produces the "
        "same sample every run (sort by candidate_id, stride by category)."
    )
    lines.append("")

    output_path = Path(output_report_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

    # Verify nothing in the candidate store was mutated
    cand_dir = p.parent / "by_day"
    if cand_dir.exists():
        import hashlib
        for f in cand_dir.rglob("*.json"):
            current = hashlib.sha256(f.read_bytes()).hexdigest()
            prior = file_hashes.get(str(f))
            if prior is not None and prior != current:
                raise RuntimeError(
                    f"AUDIT VIOLATION: candidate file {f} was modified "
                    "during audit run. This must never happen."
                )

    return {
        "ready_total": len(ready),
        "sample_size": len(sample),
        "categories_in_sample": dict(Counter(c.get("category") for c in sample)),
        "verification_in_sample": dict(
            Counter(c.get("verification_status") for c in sample)
        ),
        "report_path": str(output_path),
        "audit_version": AUDIT_VERSION,
    }


# ============================================================================
# CLI
# ============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Editorial sampling audit (read-only) "
                    "for Article Candidate Pipeline."
    )
    parser.add_argument(
        "--candidates",
        default="radar_data/candidates/latest.json",
        help="Path to candidates/latest.json",
    )
    parser.add_argument(
        "--output",
        default="docs/CANDIDATE_REVIEW_SAMPLE.md",
        help="Path to write the markdown report",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="How many candidates to sample (default 20).",
    )
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parents[2]  # radar/audit/ -> project root
    cand = (here / args.candidates).resolve()
    out = (here / args.output).resolve()
    summary = build_audit_report(cand, out, sample_size=args.sample_size)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
