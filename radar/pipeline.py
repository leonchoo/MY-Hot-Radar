"""
Radar pipeline orchestrator.

End-to-end Phase 1:
  1. load sources from registry (currently empty - real feeds not wired)
  2. for each enabled source -> adapter -> Story list (failures isolated)
  3. dedup -> Topic list
  4. attach momentum using prior-scan snapshot
  5. attach verification
  6. classify each topic
  7. emit latest.json + latest.md + history snapshot

Manual scan only. No scheduling. No network outside the source adapters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json, os, traceback
from typing import Dict, List, Tuple

from .models import (
    Source, Story, Topic, SourceType, Category, Language,
    VerificationStatus, Status,
)
from .sources.base import FetchError
from .sources.file_source import FileAdapter
from .sources.rss import RSSAdapter
from .sources.public_social import PublicSocialAdapter
from .sources_registry import load_sources
from .dedup import cluster, explain_match
from .verification import attach_verification
from .momentum import attach_momentum
from .classification import classify_all
from .normalize import normalize_title, extract_keywords
from .report import write_report
from .history import read_history_for_id, save_scan


SOURCE_STATUS_TEMPLATE = {
    "name": "",
    "type": "",
    "reliability": 0,
    "tier": "",
    "fetched": 0,
    "duration_ms": 0,
    "ok": False,
    "error": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_category_for(source: Source) -> Category:
    """Pick a category default from the source's declared country.

    Phase 1: only MY -> MALAYSIA, everything else -> WORLD.
    A future batch may add VIRAL / CELEBRITY / FOOD defaults based on
    observed source content distribution.
    """
    if source.country == "MY":
        return Category.MALAYSIA
    return Category.WORLD


def _build_adapter(source: Source, *, category: Category | None = None):
    import os as _os
    # File-source awareness: if the URL is a local path, route to FileAdapter
    # regardless of declared type, so tests can supply local fixtures.
    if source.url.startswith("file://"):
        return FileAdapter(source, category=category or _default_category_for(source))
    if _os.path.isabs(source.url) and _os.path.exists(source.url):
        return FileAdapter(source, category=category or _default_category_for(source))

    if source.type in (SourceType.RSS, SourceType.NEWS_SITE):
        return RSSAdapter(source, category=category or _default_category_for(source))
    if source.type == SourceType.WP_JSON:
        from .sources.wp_json import WpJsonAdapter
        return WpJsonAdapter(source, category=category or _default_category_for(source))
    if source.type == SourceType.HTML_LISTING:
        from .sources.html_listing import (
            HtmlListingAdapter,
            ChinaPressHtmlListingAdapter,
        )
        # China Press uses a structurally different URL/title/timestamp
        # pattern (see A2.2-C). Dispatch to the dedicated subclass so
        # Sin Chew A2.2-A + A2.2-B regression stays green on the parent
        # HtmlListingAdapter class.
        if source.name == "China Press":
            return ChinaPressHtmlListingAdapter(
                source, category=category or _default_category_for(source)
            )
        return HtmlListingAdapter(source, category=category or _default_category_for(source))
    if source.type == SourceType.PUBLIC_SOCIAL:
        return PublicSocialAdapter(source, category=category or _default_category_for(source))
    raise FetchError(f"{source.name}: no adapter available for source type {source.type}")


def run_scan(
    *,
    extra_sources: List[Source] | None = None,
    extra_stories: List[Story] | None = None,
    since_previous: bool = True,
    radar_dir: str | os.PathLike | None = None,
    return_internals: bool = False,
) -> dict:
    """Execute one radar scan. Returns a dict summary suitable for inspection.

    When `return_internals=True`, the returned dict additionally contains:
      - "topics": List[Topic]          (the in-memory Topic objects)
      - "stories_by_id": Dict[str, Story]  (story_id -> Story mapping)
    These keys are NOT present when `return_internals=False` (the default)
    so existing callers are unaffected.
    """
    radar_dir = Path(radar_dir) if radar_dir else Path(__file__).resolve().parents[1] / "radar_data"
    radar_dir.mkdir(parents=True, exist_ok=True)

    sources = load_sources()
    if extra_sources:
        sources = list(sources) + list(extra_sources)

    all_stories: List[Story] = []
    source_status: List[dict] = []
    for src in sources:
        rec = dict(SOURCE_STATUS_TEMPLATE)
        rec["name"] = src.name
        rec["type"] = src.type.value
        rec["reliability"] = src.reliability
        rec["tier"] = src.tier.value
        try:
            adapter = _build_adapter(src)
            t0 = datetime.now(timezone.utc)
            stories = adapter.fetch()
            dt = (datetime.now(timezone.utc) - t0).total_seconds() * 1000.0
            rec["duration_ms"] = int(dt)
            rec["fetched"] = len(stories)
            rec["ok"] = True
            all_stories.extend(stories)
        except FetchError as e:
            rec["error"] = str(e)
        except Exception as e:
            rec["error"] = f"unexpected: {type(e).__name__}: {e}"
            traceback.print_exc()
        finally:
            source_status.append(rec)

    # Direct injection path (used by tests and fixtures, NEVER for production).
    if extra_stories:
        all_stories.extend(extra_stories)
        source_status.append({
            "name": "<direct>",
            "type": "DIRECT",
            "reliability": 3,
            "fetched": len(extra_stories),
            "duration_ms": 0,
            "ok": True,
            "error": None,
        })

    # Normalize titles / keywords for dedup
    for s in all_stories:
        s.normalized_title = normalize_title(s.title)
        s.keywords = extract_keywords(s.title)

    # Cluster into Topics
    topics, story_to_topic = cluster(all_stories)

    # HISTORY: gather prior topics for momentum + previous status
    history_by_id = read_history_for_id(radar_dir)

    # momentum
    attach_momentum(topics, history_by_id)

    # Verification uses per-source reliability AND per-source explicit tier
    # from registered Source objects. Reliability is a calibration knob;
    # tier is a semantic credibility judgment (see VERIFICATION_RULES.md).
    source_reliability = {s.name: s.reliability for s in sources}
    source_tiers = {s.name: s.tier.value for s in sources}
    attach_verification(
        topics, all_stories,
        source_reliability=source_reliability,
        source_tiers=source_tiers,
    )

    # classification (uses prior status if known)
    classify_all(topics, history_by_id)

    # write report + history
    report_paths = write_report(
        radar_dir=radar_dir,
        topics=topics,
        source_status=source_status,
        all_stories=all_stories,
        history_by_id=history_by_id,
    )
    save_scan(radar_dir, topics, scan_meta={
        "started_at": _now_iso(),
        "sources_attempted": len(sources),
        "stories_seen": len(all_stories),
        "topics_produced": len(topics),
    })

    result = {
        "ok": True,
        "topics_count": len(topics),
        "stories_count": len(all_stories),
        "source_status": source_status,
        "report_paths": report_paths,
    }
    if return_internals:
        # Build a stories_by_id map. Story ids may be re-generated
        # by the adapter; we use the existing story.id as the key.
        stories_by_id = {s.id: s for s in all_stories if getattr(s, "id", None)}
        result["topics"] = topics
        result["stories_by_id"] = stories_by_id
    return result


if __name__ == "__main__":
    summary = run_scan()
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
