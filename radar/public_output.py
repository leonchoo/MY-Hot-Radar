"""
Public Radar Output — website-facing export of validated Radar data.

Reads the **validated internal** latest output (`radar_data/output/latest.json`)
and produces a **stripped public schema** safe to serve to the website
without leaking:

  * Internal execution metadata
  * Scheduler internals
  * File-system paths
  * Debug / trace data
  * Lock / process IDs
  * Environment variables
  * API keys / tokens

The public output is the ONLY thing the website should fetch.

Public schema is intentionally smaller than the internal schema. The
website must NOT recompute verification / confidence / momentum /
publishability — it only renders what Radar has already decided.

Architecture:

    radar.pipeline.run_scan()
        ↓
    radar.output.build_output()                  ← Phase 2 B3A
        ↓ writes to radar_data/output/latest.json
    radar.public_output.build_public_payload()   ← Phase 2 B3B-1 (this file)
        ↓ writes to public/radar/latest.json
    Website JS adapter fetches /radar/latest.json
        ↓
    website renders Radar topic cards

Public file path: ``public/radar/latest.json``

This file is intended to be committed to Git so Cloudflare Pages can
serve it as a static asset. (See docs/RADAR_PHASE2_WEBSITE_FEED.md for
the deployment strategy discussion.)

The public JSON schema:

    {
      "schema_version": 1,
      "public_schema_version": 1,
      "generated_at": "...",
      "scan_id": "...",
      "scan_status": "SUCCESS" | "PARTIAL" | "FAILED",
      "summary": {
        "topic_count": int,
        "publishable_count": int,
        "confirmed_count": int,
        "reported_count": int,
        "rumour_count": int,
        "unverified_count": int,
        "social_buzz_count": int,
        "by_status": {...},
        "by_claim_kind": {...}
      },
      "topics": [
        {
          "content_key": "...",
          "title": "...",
          "category": "...",
          "language": "...",
          "status": "...",
          "verification_status": "...",
          "confidence_label": "...",
          "momentum": {...},
          "source_count": int,
          "sources": [
            {
              "source_name": "...",
              "source_tier": "A"|"B"|...,
              "url": "...",
              "published_at": "..."
            }
          ],
          "is_political": bool,
          "claim_kind": "...",
          "political_neutral": bool,
          "publishable": bool
        }
      ]
    }

Internal-only fields (NOT in public schema):

    confidence_score       -- heuristic; not shown as probability
    publishability_reasons -- internal-only audit trail
    counter_signals        -- detailed counter-signal data (kept internal)
    canonical_url          -- not exposed to avoid URL inference attacks
    classification_reasons -- internal-only
    statuses_seen          -- internal-only
    first_seen / last_seen -- internal timestamps; freshness shown via
                              generated_at only
    mention_count          -- internal count (source_count is enough for UI)
    summary                -- removed; freshness indicator uses generated_at
    story summary / body   -- never exposed (no AI summary by spec)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PUBLIC_SCHEMA_VERSION = 1
INTERNAL_SCHEMA_VERSION = 1

# Hard limit on public output size. Prevents accidental leakage if the
# internal latest.json ever blows up. The website can stream/process
# this much comfortably on mobile.
MAX_TOPICS_PER_PUBLIC = 200
MAX_SOURCE_EVIDENCE_PER_TOPIC = 10

# Topic status mapping for public output.
# We pass through the existing Status enum values: BREAKING / RISING /
# HOT / WATCH / COOLING. The website CSS maps each to a visual badge.
VALID_STATUSES = {"BREAKING", "RISING", "HOT", "WATCH", "COOLING"}

# Verification status values used on the website (display labels).
VALID_VERIFICATIONS = {"CONFIRMED", "REPORTED", "SOCIAL_BUZZ", "UNVERIFIED", "RUMOUR"}

# Claim kinds produced by the politics module.
VALID_CLAIM_KINDS = {"EVENT", "CLAIM", "OPINION", "NOT_POLITICAL"}

# Source tiers. The public schema only emits A / B / C / D / E / F
# but the JS adapter must NOT trust an arbitrary string from the JSON.
VALID_TIERS = {"A", "B", "C", "D", "E", "F"}

# URL safety (mirror the JS adapter rules).
# Reject anything that isn't http(s) or relative-protocol https.
# We do NOT allow javascript:, data:, file:, blob:, vbscript:, etc.
ALLOWED_URL_SCHEMES = ("http://", "https://")

# Default locations.
DEFAULT_INTERNAL_PATH = Path("radar_data/output/latest.json")
DEFAULT_PUBLIC_PATH = Path("public/radar/latest.json")


class PublicOutputError(Exception):
    """Raised when public output cannot be produced (validation failure)."""


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------

def is_safe_url(url: str) -> bool:
    """Return True iff the URL is safe to render as <a href>.

    Rules (mirror the JS adapter; both must agree):

    * Must be a string.
    * Must be non-empty.
    * Must start with http:// or https:// (case-insensitive).
    * Must not contain whitespace (including \n, \t, \r, space) or
      control characters (ord < 32 or ord == 127).
    * Must be < 2048 characters (browser URL practical limit).
    """
    if not isinstance(url, str):
        return False
    if not url:  # empty string
        return False
    if len(url) >= 2048:
        return False
    # Reject whitespace and control chars (BEFORE stripping leading
    # whitespace — otherwise \n / \t / \r would slip past our check).
    for ch in url:
        if ch.isspace():
            return False
        o = ord(ch)
        if o < 32 or o == 127:
            return False
    lower = url.lower()
    if not (lower.startswith("http://") or lower.startswith("https://")):
        return False
    return True


def sanitize_url(url: str) -> str:
    """Return the URL only if safe; else empty string."""
    return url if is_safe_url(url) else ""


# ---------------------------------------------------------------------------
# Field-level sanitization
# ---------------------------------------------------------------------------

def _safe_str(value: Any, max_len: int = 500) -> str:
    """Coerce to a safe plain string (no HTML/JS injection)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    # Strip control chars and clamp length. Do NOT HTML-escape here —
    # the website uses textContent which already escapes; this is a
    # belt-and-braces hardening step.
    cleaned = "".join(ch for ch in value if 32 <= ord(ch) < 127 or ord(ch) >= 160)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    # Clamp to a sane range so the UI can't be tripped up.
    if v < 0 or v > 100_000_000:
        return default
    return v


def _public_source_evidence(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert one internal source-evidence dict to a public-safe one.

    Returns None if the row is unusable (no safe URL, bad tier, etc.).
    """
    if not isinstance(raw, dict):
        return None

    name = _safe_str(raw.get("source_name"), max_len=120)
    if not name:
        return None

    tier = _safe_str(raw.get("source_tier"), max_len=2).upper()
    if tier not in VALID_TIERS:
        # Unknown tier — drop this source row but keep the topic.
        return None

    url = sanitize_url(_safe_str(raw.get("url"), max_len=2048))
    if not url:
        # Missing/invalid URL is a hard filter: a source without a
        # clickable link should not appear in the public feed.
        return None

    published_at = _safe_str(raw.get("published_at"), max_len=64)
    # published_at is allowed to be empty (some sources don't provide one).

    return {
        "source_name": name,
        "source_tier": tier,
        "url": url,
        "published_at": published_at,
    }


def _public_topic(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert one internal topic dict to a public-safe topic dict.

    Returns None if the topic is unusable (missing required fields).
    """
    if not isinstance(raw, dict):
        return None

    content_key = _safe_str(raw.get("content_key"), max_len=512)
    if not content_key:
        return None

    title = _safe_str(raw.get("title"), max_len=400)
    if not title:
        return None

    category = _safe_str(raw.get("category"), max_len=64)
    language = _safe_str(raw.get("language"), max_len=8)
    status = _safe_str(raw.get("status"), max_len=16).upper()
    if status not in VALID_STATUSES:
        status = "WATCH"

    verification = _safe_str(raw.get("verification_status"), max_len=20).upper()
    if verification not in VALID_VERIFICATIONS:
        verification = "REPORTED"

    confidence_label = _safe_str(raw.get("confidence_label"), max_len=16).upper()
    # Don't reject unknown labels — the website handles unknowns.

    momentum_raw = raw.get("momentum")
    momentum: Dict[str, Any] = {}
    if isinstance(momentum_raw, dict):
        momentum = {
            "current_mentions": _safe_int(momentum_raw.get("current_mentions")),
            "previous_mentions": _safe_int(momentum_raw.get("previous_mentions")),
            "growth": _safe_int(momentum_raw.get("growth"), default=0),
            "growth_rate": (
                float(momentum_raw["growth_rate"])
                if isinstance(momentum_raw.get("growth_rate"), (int, float))
                else 0.0
            ),
            "is_new": bool(momentum_raw.get("is_new")),
        }

    sources_raw = raw.get("sources") or []
    sources: List[Dict[str, Any]] = []
    if isinstance(sources_raw, list):
        for s in sources_raw:
            if len(sources) >= MAX_SOURCE_EVIDENCE_PER_TOPIC:
                break
            pub = _public_source_evidence(s)
            if pub is not None:
                sources.append(pub)

    # A topic MUST have at least one safe source URL to be public.
    if not sources:
        return None

    is_political = bool(raw.get("is_political"))
    claim_kind = _safe_str(raw.get("claim_kind"), max_len=20).upper()
    if claim_kind not in VALID_CLAIM_KINDS:
        claim_kind = "NOT_POLITICAL"
    political_neutral = bool(raw.get("political_neutral"))

    publishable = bool(raw.get("publishable"))

    return {
        "content_key": content_key,
        "title": title,
        "category": category,
        "language": language,
        "status": status,
        "verification_status": verification,
        "confidence_label": confidence_label,
        "momentum": momentum,
        "source_count": len(sources),
        "sources": sources,
        "is_political": is_political,
        "claim_kind": claim_kind,
        "political_neutral": political_neutral,
        "publishable": publishable,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_public_payload(payload: Dict[str, Any]) -> List[str]:
    """Return a list of error strings. Empty list == valid.

    Checks:

    * Top-level required keys + types.
    * public_schema_version == 1.
    * scan_status in {SUCCESS, PARTIAL, FAILED}.
    * topics is a list.
    * Unique content_key across topics.
    * Each topic has safe title, valid status, valid verification, etc.
    * Each topic has at least one source with safe URL.
    * No field of unexpected type.
    """
    errs: List[str] = []

    if not isinstance(payload, dict):
        return ["payload is not a dict"]

    for key in ("schema_version", "public_schema_version", "generated_at",
                "scan_id", "scan_status", "summary", "topics"):
        if key not in payload:
            errs.append(f"missing top-level key: {key}")

    if payload.get("schema_version") != INTERNAL_SCHEMA_VERSION:
        errs.append(f"schema_version must be {INTERNAL_SCHEMA_VERSION}")
    if payload.get("public_schema_version") != PUBLIC_SCHEMA_VERSION:
        errs.append(f"public_schema_version must be {PUBLIC_SCHEMA_VERSION}")

    scan_status = payload.get("scan_status")
    if scan_status not in ("SUCCESS", "PARTIAL", "FAILED"):
        errs.append(f"invalid scan_status: {scan_status!r}")

    if not isinstance(payload.get("topics"), list):
        errs.append("topics must be a list")

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        errs.append("summary must be a dict")
    else:
        for k in ("topic_count", "publishable_count", "confirmed_count",
                  "reported_count", "rumour_count", "unverified_count",
                  "social_buzz_count", "by_status", "by_claim_kind"):
            if k not in summary:
                errs.append(f"summary missing key: {k}")

    # Per-topic checks.
    if isinstance(payload.get("topics"), list):
        seen_keys: set = set()
        for i, t in enumerate(payload["topics"]):
            prefix = f"topics[{i}]"
            if not isinstance(t, dict):
                errs.append(f"{prefix}: not a dict")
                continue
            ck = t.get("content_key")
            if not isinstance(ck, str) or not ck:
                errs.append(f"{prefix}: missing content_key")
            elif ck in seen_keys:
                errs.append(f"{prefix}: duplicate content_key {ck!r}")
            else:
                seen_keys.add(ck)

            if t.get("status") not in VALID_STATUSES:
                errs.append(f"{prefix}: invalid status {t.get('status')!r}")
            if t.get("verification_status") not in VALID_VERIFICATIONS:
                errs.append(f"{prefix}: invalid verification {t.get('verification_status')!r}")
            if t.get("claim_kind") not in VALID_CLAIM_KINDS:
                errs.append(f"{prefix}: invalid claim_kind {t.get('claim_kind')!r}")

            sources = t.get("sources")
            if not isinstance(sources, list) or not sources:
                errs.append(f"{prefix}: no sources")
            else:
                for j, s in enumerate(sources):
                    sp = f"{prefix}.sources[{j}]"
                    if not isinstance(s, dict):
                        errs.append(f"{sp}: not a dict")
                        continue
                    if not is_safe_url(s.get("url", "")):
                        errs.append(f"{sp}: unsafe url")
                    if s.get("source_tier") not in VALID_TIERS:
                        errs.append(f"{sp}: invalid tier")

            # publishable True with political_neutral False is contradictory;
            # the Radar engine should never emit it. Public validator flags
            # it so a future bug is caught immediately.
            if t.get("publishable") and t.get("is_political") \
                    and not t.get("political_neutral"):
                errs.append(
                    f"{prefix}: publishable=True but political non-neutral"
                )

    # topic_count must equal len(topics).
    if isinstance(payload.get("topics"), list) and isinstance(summary, dict):
        try:
            actual = len(payload["topics"])
            declared = int(summary.get("topic_count", -1))
            if declared != actual:
                errs.append(
                    f"summary.topic_count={declared} != len(topics)={actual}"
                )
        except (TypeError, ValueError):
            pass

    return errs


# ---------------------------------------------------------------------------
# Build public payload
# ---------------------------------------------------------------------------

def build_public_payload(internal_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an internal Radar output payload to a public-safe payload.

    This is the **single transformation point** between the internal
    schema (rich, audit-grade) and the public schema (lean, website-safe).

    Raises ``ValueError`` if the internal payload is too broken to
    convert (e.g. completely missing topics, no schema_version).
    """
    if not isinstance(internal_payload, dict):
        raise ValueError("internal payload must be a dict")

    if internal_payload.get("schema_version") != INTERNAL_SCHEMA_VERSION:
        raise ValueError(
            f"internal schema_version must be {INTERNAL_SCHEMA_VERSION}; "
            f"got {internal_payload.get('schema_version')!r}"
        )

    scan_status_raw = internal_payload.get("scan_status", "UNKNOWN")
    # Coerce to public-safe enum.
    if scan_status_raw not in ("SUCCESS", "PARTIAL", "FAILED"):
        scan_status = "PARTIAL"  # treat unknown as partial
    else:
        scan_status = scan_status_raw

    topics_raw = internal_payload.get("topics") or []
    if not isinstance(topics_raw, list):
        raise ValueError("internal topics must be a list")

    # Convert each topic; silently drop topics we cannot safely expose.
    public_topics: List[Dict[str, Any]] = []
    skipped = 0
    for raw in topics_raw:
        if len(public_topics) >= MAX_TOPICS_PER_PUBLIC:
            skipped += 1
            continue
        pt = _public_topic(raw)
        if pt is None:
            skipped += 1
            continue
        public_topics.append(pt)

    # Build summary from what we ACTUALLY emitted, not what the
    # internal summary claims. The internal summary could be stale or
    # inconsistent; the public summary must match the public topic list
    # by construction.
    by_status: Dict[str, int] = {}
    by_claim_kind: Dict[str, int] = {}
    confirmed = reported = rumour = unverified = social_buzz = 0
    publishable = 0
    for t in public_topics:
        s = t["status"]
        by_status[s] = by_status.get(s, 0) + 1
        ck = t["claim_kind"]
        by_claim_kind[ck] = by_claim_kind.get(ck, 0) + 1
        v = t["verification_status"]
        if v == "CONFIRMED":
            confirmed += 1
        elif v == "REPORTED":
            reported += 1
        elif v == "RUMOUR":
            rumour += 1
        elif v == "UNVERIFIED":
            unverified += 1
        elif v == "SOCIAL_BUZZ":
            social_buzz += 1
        if t["publishable"]:
            publishable += 1

    public_payload = {
        "schema_version": INTERNAL_SCHEMA_VERSION,
        "public_schema_version": PUBLIC_SCHEMA_VERSION,
        "generated_at": _safe_str(
            internal_payload.get("generated_at"), max_len=64
        ),
        "scan_id": _safe_str(internal_payload.get("scan_id"), max_len=128),
        "scan_status": scan_status,
        "summary": {
            "topic_count": len(public_topics),
            "publishable_count": publishable,
            "confirmed_count": confirmed,
            "reported_count": reported,
            "rumour_count": rumour,
            "unverified_count": unverified,
            "social_buzz_count": social_buzz,
            "by_status": by_status,
            "by_claim_kind": by_claim_kind,
        },
        "topics": public_topics,
    }
    return public_payload


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def _atomic_write_json(target: Path, payload: Dict[str, Any]) -> None:
    """Atomically write payload as JSON to target.

    Same algorithm as ``radar.output._atomic_write_json`` but kept
    independent here so the public_output module has no internal
    dependency on ``radar.output`` (cleaner import graph).

    Order:
      1. Open temp file in the SAME directory (so os.replace is atomic).
      2. Write JSON.
      3. flush + fsync (best-effort).
      4. os.replace(temp, target).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=target.name + ".",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_path_str)
    try:
        # Python json.dump with ensure_ascii=False keeps unicode as-is
        # so Chinese / Malay / English all survive verbatim.
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(
                payload,
                f,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                separators=(",", ": "),
            )
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # Some filesystems (e.g. CI runners) reject fsync. That
                # is OK — os.replace is still atomic on POSIX/Windows.
                pass
        os.replace(tmp_path, target)
    except Exception:
        # Best-effort cleanup of the temp file.
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Build + write public output
# ---------------------------------------------------------------------------

def build_public_output(
    internal_path: Path = DEFAULT_INTERNAL_PATH,
    public_path: Path = DEFAULT_PUBLIC_PATH,
) -> Dict[str, Any]:
    """Read internal latest.json, build public payload, write atomically.

    Returns the public payload (post-validation).

    Raises ``PublicOutputError`` on any failure (file missing, malformed
    JSON, validator rejects the payload). The previous valid
    ``public_path`` file is preserved on any failure — the write is
    skipped if validation fails.
    """
    if not internal_path.exists():
        raise PublicOutputError(
            f"internal latest.json not found at {internal_path}; "
            "cannot produce public output"
        )

    try:
        raw = internal_path.read_text(encoding="utf-8")
    except OSError as e:
        raise PublicOutputError(
            f"could not read internal latest.json: {e}"
        ) from e

    try:
        internal_payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PublicOutputError(
            f"internal latest.json is not valid JSON: {e}"
        ) from e

    if not isinstance(internal_payload, dict):
        raise PublicOutputError("internal latest.json root must be a dict")

    try:
        public_payload = build_public_payload(internal_payload)
    except ValueError as e:
        raise PublicOutputError(f"could not build public payload: {e}") from e

    # Hard validator. This is the **website-side contract**: if this
    # fails, the website is NOT given the file.
    errs = validate_public_payload(public_payload)
    if errs:
        raise PublicOutputError(
            "public payload validation failed: "
            + "; ".join(errs[:5])
            + (f" (+{len(errs)-5} more)" if len(errs) > 5 else "")
        )

    # Atomically write. If this raises (disk full, permission denied,
    # etc.) the previous public_path file stays intact.
    try:
        _atomic_write_json(public_path, public_payload)
    except OSError as e:
        raise PublicOutputError(
            f"could not write public output to {public_path}: {e}"
        ) from e

    return public_payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    """CLI entry point.

    Usage:
        python -m radar.public_output
        python -m radar.public_output --internal path/to/latest.json
        python -m radar.public_output --public path/to/output.json
        python -m radar.public_output --dry-run   # do not write; print summary

    Exit codes:
        0 = public payload built + validated + written
        1 = public payload build / write failed (previous public file preserved)
        2 = CLI usage error
    """
    parser = argparse.ArgumentParser(
        prog="radar.public_output",
        description=(
            "Convert internal radar latest.json into a public-safe "
            "JSON artifact for the website. NEVER leaks internal "
            "metadata; the website MUST consume only this artifact."
        ),
    )
    parser.add_argument(
        "--internal", type=str, default=str(DEFAULT_INTERNAL_PATH),
        help="Path to internal latest.json (default: %(default)s)",
    )
    parser.add_argument(
        "--public", type=str, default=str(DEFAULT_PUBLIC_PATH),
        help="Path to write public JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build + validate but do not write the public file",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Only validate the existing public file; do not rebuild",
    )
    args = parser.parse_args(argv)

    public_path = Path(args.public)
    internal_path = Path(args.internal)

    if args.check:
        if not public_path.exists():
            print(f"ERROR: public file does not exist: {public_path}",
                  file=sys.stderr)
            return 1
        try:
            existing = json.loads(public_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"ERROR: public file is not valid JSON: {e}",
                  file=sys.stderr)
            return 1
        errs = validate_public_payload(existing)
        if errs:
            print(f"ERROR: public file failed validation:",
                  file=sys.stderr)
            for e in errs[:10]:
                print(f"  - {e}", file=sys.stderr)
            return 1
        print(json.dumps({
            "public_path": str(public_path),
            "schema_version": existing.get("schema_version"),
            "public_schema_version": existing.get("public_schema_version"),
            "topic_count": existing.get("summary", {}).get("topic_count"),
            "valid": True,
        }, indent=2))
        return 0

    try:
        if args.dry_run:
            # Build only, no write.
            raw = internal_path.read_text(encoding="utf-8")
            internal_payload = json.loads(raw)
            public_payload = build_public_payload(internal_payload)
            errs = validate_public_payload(public_payload)
            if errs:
                print(f"DRY-RUN FAIL ({len(errs)} errors):", file=sys.stderr)
                for e in errs[:10]:
                    print(f"  - {e}", file=sys.stderr)
                return 1
            print(json.dumps({
                "dry_run": True,
                "topic_count": public_payload["summary"]["topic_count"],
                "publishable_count": public_payload["summary"]["publishable_count"],
                "by_status": public_payload["summary"]["by_status"],
                "by_claim_kind": public_payload["summary"]["by_claim_kind"],
                "would_write_to": str(public_path),
                "public_schema_version": PUBLIC_SCHEMA_VERSION,
            }, indent=2))
            return 0

        payload = build_public_output(
            internal_path=internal_path,
            public_path=public_path,
        )
        print(json.dumps({
            "schema_version": payload["schema_version"],
            "public_schema_version": payload["public_schema_version"],
            "public_path": str(public_path),
            "scan_id": payload["scan_id"],
            "scan_status": payload["scan_status"],
            "generated_at": payload["generated_at"],
            "topic_count": payload["summary"]["topic_count"],
            "publishable_count": payload["summary"]["publishable_count"],
            "by_status": payload["summary"]["by_status"],
            "by_claim_kind": payload["summary"]["by_claim_kind"],
        }, indent=2))
        return 0
    except PublicOutputError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # pragma: no cover (defensive)
        print(f"UNEXPECTED ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
