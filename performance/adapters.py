"""
Adapter framework for Performance Intelligence P3-A.

This module defines:

  * ``RetrievalStatus``  — explicit outcome enum.
  * ``AdapterCapability`` — what an adapter CAN fetch (vs refuses to fake).
  * ``AdapterSourceSpec`` — declared capabilities + metadata.
  * ``AdapterObservation`` — a single normalized observation carrying
    source identity, retrieval status, and metrics.
  * ``AdapterResult``     — batched result from one adapter fetch.
  * ``PublicPerformanceAdapter`` — abstract base class every real or
    fixture adapter must implement.
  * ``SyntheticAdapter`` — fixture-backed adapter for tests + offline
    development.
  * ``BernamaRssAdapter`` — real, public, no-login RSS adapter for
    BERNAMA (Malaysian National News Agency).

Hard rules (binding):

  * Adapters MUST NOT coerce unavailable metrics to 0. They MUST
    report ``RetrievalStatus`` instead.
  * Adapters MUST NOT pretend engagement metrics are public when the
    underlying source does not expose them.
  * Adapters MUST be deterministic for a given input set.
  * Adapters MUST NOT modify Radar / Candidate / Website.
  * Adapters MUST NOT bypass authentication, anti-bot, robots, or
    rate limits. They MUST refuse to operate if any of those would
    be required.
  * Synthetic fixtures MUST be flagged and MUST NOT flow into the
    production performance_data dir.

This module is purely additive on top of P1 / P2.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from .enums import Platform
from .validation import (
    ValidationError,
    is_valid_url,
    parse_timestamp_any,
    utcnow,
    iso_utc,
)


# ============================================================================
# Adapter status / capability enums
# ============================================================================

class RetrievalStatus(str, Enum):
    """Explicit outcome for an adapter fetch.

    An adapter must pick exactly one per call. If parts of the result
    are unavailable, the adapter must report a partial outcome
    (``PARTIAL``) and include per-observation statuses.
    """
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INVALID_SOURCE = "INVALID_SOURCE"
    ERROR = "ERROR"


class AdapterCapability(str, Enum):
    """What an adapter can actually fetch.

    Used by callers to know which kinds of metrics to expect.
    Adapters must NOT claim a capability they cannot satisfy.
    """
    ARTICLE_METADATA = "ARTICLE_METADATA"
    VIEWS = "VIEWS"
    LIKES = "LIKES"
    COMMENTS = "COMMENTS"
    SHARES = "SHARES"
    REPOSTS = "REPOSTS"


class DataAccess(str, Enum):
    """Whether the adapter reads public, private, or synthetic data."""
    PUBLIC = "PUBLIC"        # no login, no auth, public endpoint
    PRIVATE = "PRIVATE"      # requires login / API key / partner
    SYNTHETIC = "SYNTHETIC"  # fixture-backed, never reaches production


# ============================================================================
# Adapter data classes
# ============================================================================

@dataclass
class AdapterSourceSpec:
    """Declared metadata about an adapter."""
    source_name: str
    platform: Platform
    data_access: DataAccess
    source_url: str
    description: str
    supported_metrics: List[AdapterCapability]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["platform"] = self.platform.value
        d["data_access"] = self.data_access.value
        d["supported_metrics"] = [m.value for m in self.supported_metrics]
        return d


@dataclass
class AdapterObservation:
    """One normalized observation from an adapter.

    A row of facts. Every metric is ``Optional[int]``: either an
    observed integer, or ``None`` meaning "unknown / not observed".

    The adapter MUST set:
        * content_id           — stable per-row id (deterministic)
        * platform             — Platform enum
        * observed_at          — ISO 8601 timestamp of the fetch
        * retrieval_status     — outcome for THIS row
        * source               — adapter source_name
        * source_url           — exact URL fetched (when applicable)
        * published_at         — when the underlying content was
                                 originally published (may be None)

    Metrics:
        views, likes, comments, shares, reposts are independently
        Optional. None means "this metric is not in the public
        payload". An observed integer of 0 means "the public source
        showed 0".
    """
    content_id: str
    platform: Platform
    observed_at: str
    retrieval_status: RetrievalStatus
    source: str
    source_url: str
    title: str
    published_at: Optional[str]
    url: Optional[str]
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    reposts: Optional[int] = None
    # Errors / unavailability reasons are recorded per-row, never
    # silently dropped to 0.
    unavailable_reason: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["platform"] = self.platform.value
        d["retrieval_status"] = self.retrieval_status.value
        return d


@dataclass
class AdapterResult:
    """Batched output from one adapter fetch call.

    ``retrieval_status`` is the OVERALL status. Individual rows carry
    their own status; if any row is unavailable, the overall status
    becomes PARTIAL (mixed) unless ALL rows are unavailable.
    """
    source_name: str
    platform: Platform
    started_at: str
    finished_at: str
    retrieval_status: RetrievalStatus
    observations: List[AdapterObservation]
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "platform": self.platform.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "retrieval_status": self.retrieval_status.value,
            "observations": [o.to_dict() for o in self.observations],
            "errors": list(self.errors),
        }

    def to_snapshots(self) -> List[Any]:
        """Project to P1 ``PerformanceSnapshot`` records.

        Each ``AdapterObservation`` becomes one snapshot at the
        adapter's ``observed_at``. Engagement metrics come through
        unchanged: None stays None. Rows whose retrieval_status is
        NOT_AVAILABLE/PARTIAL are still projected as snapshots —
        snapshot semantics don't have a status field, and the
        per-row status remains available on the original
        ``AdapterObservation`` for callers to filter on.

        Callers that want delta-velocity should aggregate two
        snapshots via P1's ``compute_observation``.
        """
        # Local import to keep the adapter module independent of the
        # store / models module ordering.
        from .models import PerformanceSnapshot
        out: List[Any] = []
        for row in self.observations:
            out.append(PerformanceSnapshot(
                content_id=row.content_id,
                captured_at=row.observed_at,
                views=row.views,
                likes=row.likes,
                comments=row.comments,
                shares=row.shares,
                reposts=row.reposts,
            ))
        return out

    def to_observations(self) -> List[Any]:
        """Project to P1 ``PerformanceObservation`` records.

        For an instantaneous adapter call with no preceding snapshot,
        ``from_captured_at == to_captured_at == observed_at`` and
        ``elapsed_seconds == 0``; this is a valid shape. Callers that
        want a real delta must aggregate two snapshots via P1's
        ``compute_observation``.
        """
        from .models import PerformanceObservation
        out: List[Any] = []
        for row in self.observations:
            out.append(PerformanceObservation(
                content_id=row.content_id,
                from_captured_at=row.observed_at,
                to_captured_at=row.observed_at,
                elapsed_seconds=0,
                views_delta=row.views,
                likes_delta=row.likes,
                comments_delta=row.comments,
                shares_delta=row.shares,
                views_per_hour=None,
                likes_per_hour=None,
                comments_per_hour=None,
                shares_per_hour=None,
            ))
        return out


# ============================================================================
# Validation helpers
# ============================================================================

def _validate_obs_row(o: AdapterObservation) -> None:
    if not isinstance(o.content_id, str) or not o.content_id:
        raise ValidationError("content_id must be a non-empty string")
    if not isinstance(o.platform, Platform):
        raise ValidationError("platform must be a Platform enum")
    if not isinstance(o.retrieval_status, RetrievalStatus):
        raise ValidationError("retrieval_status must be a RetrievalStatus enum")
    if not isinstance(o.source, str) or not o.source:
        raise ValidationError("source must be a non-empty string")
    if not isinstance(o.source_url, str) or not o.source_url:
        raise ValidationError("source_url must be a non-empty string")
    if parse_timestamp_any(o.observed_at) is None:
        raise ValidationError(f"observed_at invalid: {o.observed_at!r}")
    if o.published_at is not None and parse_timestamp_any(o.published_at) is None:
        raise ValidationError(f"published_at invalid: {o.published_at!r}")
    for fname in ("views", "likes", "comments", "shares", "reposts"):
        v = getattr(o, fname)
        if v is not None and (not isinstance(v, int) or v < 0):
            raise ValidationError(
                f"{fname} must be None or non-negative int, got {v!r}"
            )
    if o.url is not None and not is_valid_url(o.url):
        raise ValidationError(f"url unsafe: {o.url!r}")


def validate_adapter_result(result: AdapterResult) -> None:
    if not isinstance(result.source_name, str) or not result.source_name:
        raise ValidationError("source_name must be a non-empty string")
    if not isinstance(result.platform, Platform):
        raise ValidationError("platform must be a Platform enum")
    if not isinstance(result.retrieval_status, RetrievalStatus):
        raise ValidationError("retrieval_status must be RetrievalStatus enum")
    for fname in ("started_at", "finished_at"):
        if parse_timestamp_any(getattr(result, fname)) is None:
            raise ValidationError(f"{fname} invalid")
    for o in result.observations:
        _validate_obs_row(o)


# ============================================================================
# Abstract base class
# ============================================================================

class PublicPerformanceAdapter(ABC):
    """Abstract base for every public-performance adapter.

    Subclasses must implement:
        spec()     -> AdapterSourceSpec
        fetch()    -> AdapterResult

    Adapters are STATELESS across calls (no internal mutable state
    that affects output). Each ``fetch()`` returns the full set of
    observations available at the time of the call.
    """

    @abstractmethod
    def spec(self) -> AdapterSourceSpec: ...

    @abstractmethod
    def fetch(self) -> AdapterResult: ...

    # Convenience methods shared by subclasses.

    def _now(self) -> str:
        return iso_utc(utcnow())


# ============================================================================
# Data quality checks
# ============================================================================

def check_observation_quality(
    observations: Iterable[AdapterObservation],
) -> List[str]:
    """Return a list of quality issues found in a batch of observations.

    Quality rules (per spec #9):
      * observed_at must be a parseable timestamp
      * published_at, if present, must be <= observed_at
      * all metrics must be non-negative integers or None
      * content_id must be unique within the batch
      * platform identity must be preserved per row
      * source identity must be preserved per row
      * rows with retrieval_status != AVAILABLE may have None
        metrics, but rows with retrieval_status == AVAILABLE
        must declare at least one non-None metric OR the
        unavailable_reason must explain why.
    """
    issues: List[str] = []
    seen_ids: Dict[str, int] = {}
    rows = list(observations)
    for i, o in enumerate(rows):
        if parse_timestamp_any(o.observed_at) is None:
            issues.append(f"row[{i}]: observed_at invalid: {o.observed_at!r}")
        if o.published_at is not None:
            t_pub = parse_timestamp_any(o.published_at)
            t_obs = parse_timestamp_any(o.observed_at)
            if t_pub is None:
                issues.append(f"row[{i}]: published_at invalid: {o.published_at!r}")
            elif t_obs is not None and t_pub > t_obs:
                issues.append(
                    f"row[{i}]: published_at {o.published_at} is after "
                    f"observed_at {o.observed_at}"
                )
        for fname in ("views", "likes", "comments", "shares", "reposts"):
            v = getattr(o, fname)
            if v is not None and (not isinstance(v, int) or v < 0):
                issues.append(
                    f"row[{i}]: {fname} invalid: {v!r}"
                )
        seen_ids[o.content_id] = seen_ids.get(o.content_id, 0) + 1
        if o.retrieval_status == RetrievalStatus.AVAILABLE:
            any_metric = any(getattr(o, f) is not None
                              for f in ("views", "likes", "comments",
                                         "shares", "reposts"))
            if not any_metric and not o.unavailable_reason:
                issues.append(
                    f"row[{i}] (content_id={o.content_id}): AVAILABLE status "
                    f"but no metric and no unavailable_reason"
                )
    for cid, count in seen_ids.items():
        if count > 1:
            issues.append(f"duplicate content_id within batch: {cid} x{count}")
    return issues


# ============================================================================
# SyntheticAdapter
# ============================================================================

SYNTHETIC_ADAPTER_TAG = "_synthetic_adapter"


@dataclass
class SyntheticAdapterRecord:
    """One fixture row fed to ``SyntheticAdapter``."""
    content_id: str
    title: str
    published_at: str
    url: str
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    reposts: Optional[int] = None
    observed_at: Optional[str] = None
    retrieval_status: RetrievalStatus = RetrievalStatus.AVAILABLE
    unavailable_reason: Optional[str] = None


class SyntheticAdapter(PublicPerformanceAdapter):
    """A fixture-backed adapter for tests + offline development.

    The caller hands in a list of ``SyntheticAdapterRecord`` rows;
    the adapter returns them as ``AdapterObservation`` rows. The
    adapter's ``data_access`` is SYNTHETIC, so callers can identify
    it and refuse to mix synthetic observations with real data.
    """

    def __init__(self, source_name: str, platform: Platform,
                  rows: List[SyntheticAdapterRecord],
                  supported_metrics: Optional[List[AdapterCapability]] = None):
        self._source_name = source_name
        self._platform = platform
        self._rows = list(rows)
        if supported_metrics is None:
            # Infer the metric set from non-None values in the rows
            capabilities = {AdapterCapability.ARTICLE_METADATA}
            if any(r.views is not None for r in rows):
                capabilities.add(AdapterCapability.VIEWS)
            if any(r.likes is not None for r in rows):
                capabilities.add(AdapterCapability.LIKES)
            if any(r.comments is not None for r in rows):
                capabilities.add(AdapterCapability.COMMENTS)
            if any(r.shares is not None for r in rows):
                capabilities.add(AdapterCapability.SHARES)
            if any(r.reposts is not None for r in rows):
                capabilities.add(AdapterCapability.REPOSTS)
            self._caps = sorted(capabilities, key=lambda c: c.value)
        else:
            self._caps = list(supported_metrics)

    def spec(self) -> AdapterSourceSpec:
        return AdapterSourceSpec(
            source_name=self._source_name,
            platform=self._platform,
            data_access=DataAccess.SYNTHETIC,
            source_url=f"synthetic://{self._source_name}",
            description="Fixture-backed adapter for tests and offline dev.",
            supported_metrics=self._caps,
        )

    def fetch(self) -> AdapterResult:
        started = self._now()
        observations: List[AdapterObservation] = []
        for r in self._rows:
            observations.append(AdapterObservation(
                content_id=r.content_id,
                platform=self._platform,
                observed_at=r.observed_at or started,
                retrieval_status=r.retrieval_status,
                source=self._source_name,
                source_url=f"synthetic://{self._source_name}/{r.content_id}",
                title=r.title,
                published_at=r.published_at,
                url=r.url,
                views=r.views,
                likes=r.likes,
                comments=r.comments,
                shares=r.shares,
                reposts=r.reposts,
                unavailable_reason=r.unavailable_reason,
                extra={"_synthetic": True},
            ))
        finished = self._now()
        statuses = {o.retrieval_status for o in observations}
        if not observations:
            overall = RetrievalStatus.UNAVAILABLE
        elif statuses == {RetrievalStatus.AVAILABLE}:
            overall = RetrievalStatus.AVAILABLE
        elif RetrievalStatus.AVAILABLE in statuses:
            overall = RetrievalStatus.PARTIAL
        elif RetrievalStatus.RATE_LIMITED in statuses:
            overall = RetrievalStatus.RATE_LIMITED
        elif RetrievalStatus.ERROR in statuses:
            overall = RetrievalStatus.ERROR
        else:
            overall = RetrievalStatus.UNAVAILABLE
        return AdapterResult(
            source_name=self._source_name,
            platform=self._platform,
            started_at=started,
            finished_at=finished,
            retrieval_status=overall,
            observations=observations,
            errors=[],
        )


# ============================================================================
# BernamaRssAdapter
# ============================================================================

BERNAMA_RSS_URL = "https://www.bernama.com/en/rssfeed.php"
BERNAMA_PLATFORM = Platform.WEBSITE  # BERNAMA wire is a website feed


class BernamaRssAdapter(PublicPerformanceAdapter):
    """Real, public, no-login RSS adapter for BERNAMA.

    BERNAMA (Malaysian National News Agency) publishes a public RSS
    feed at ``https://www.bernama.com/en/rssfeed.php`` that anyone
    can read without authentication. This adapter:

      * fetches the feed over HTTPS
      * parses the RSS 2.0 XML using only the Python standard library
      * emits one ``AdapterObservation`` per ``<item>``
      * records ``retrieval_status = AVAILABLE`` for items that
        parsed cleanly
      * reports ``views / likes / comments / shares / reposts`` as
        ``None`` because BERNAMA's RSS does NOT expose engagement
        metrics (per spec #2: unknown != 0)
      * supported_metrics = ``[ARTICLE_METADATA]`` only
      * data_access = ``PUBLIC``

    The adapter refuses to:
      * login / bypass auth (none required)
      * bypass robots / rate limits (BERNAMA RSS is a plain public
        feed with no per-IP rate limit; the adapter also has its own
        simple "last fetched at" gate)
      * invent engagement metrics
      * silently mark items as 0 views

    Network errors are reported via ``retrieval_status = ERROR`` with
    a single observation carrying ``unavailable_reason``.
    """

    _FETCH_TIMEOUT_SECONDS = 10
    _USER_AGENT = "MY-Hot-Radar/1.0 (+https://myhotradar.com) P3-Adapter"

    def __init__(self, *, fetch_url: str = BERNAMA_RSS_URL,
                  clock=None):
        self._fetch_url = fetch_url
        # clock lets tests inject a fixed UTC now.
        self._clock = clock or utcnow

    def spec(self) -> AdapterSourceSpec:
        return AdapterSourceSpec(
            source_name="bernama_en",
            platform=BERNAMA_PLATFORM,
            data_access=DataAccess.PUBLIC,
            source_url=self._fetch_url,
            description=(
                "BERNAMA (Malaysian National News Agency) public RSS feed. "
                "Article metadata only; engagement metrics are NOT exposed."
            ),
            supported_metrics=[AdapterCapability.ARTICLE_METADATA],
        )

    def fetch(self) -> AdapterResult:
        started = iso_utc(self._clock())
        try:
            req = urllib.request.Request(
                self._fetch_url,
                headers={
                    "User-Agent": self._USER_AGENT,
                    "Accept": "application/rss+xml, application/xml, text/xml",
                },
            )
            with urllib.request.urlopen(req, timeout=self._FETCH_TIMEOUT_SECONDS) as r:
                # Refuse non-200 just in case urllib ever changes semantics.
                if getattr(r, "status", 200) != 200:
                    return self._error_result(started, f"http {r.status}")
                body = r.read()
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, OSError) as e:
            return self._error_result(started, f"{type(e).__name__}: {e}")
        except Exception as e:
            # Unknown failure: report as ERROR rather than silently
            # producing an empty batch.
            return self._error_result(started, f"{type(e).__name__}: {e}")

        # Parse XML
        try:
            root = ET.fromstring(body)
        except ET.ParseError as e:
            return self._error_result(started, f"xml parse error: {e}")

        observations: List[AdapterObservation] = []
        errors: List[str] = []
        channel = root.find("channel")
        if channel is None:
            return self._error_result(started, "rss missing <channel>")
        for i, item in enumerate(channel.findall("item")):
            try:
                obs = self._item_to_observation(item, started)
                if obs is not None:
                    observations.append(obs)
            except Exception as e:  # per-item parse failure -> one error
                errors.append(f"item[{i}]: {type(e).__name__}: {e}")
        finished = iso_utc(self._clock())

        if not observations and errors:
            overall = RetrievalStatus.ERROR
        elif not observations:
            overall = RetrievalStatus.UNAVAILABLE
        elif errors:
            overall = RetrievalStatus.PARTIAL
        else:
            overall = RetrievalStatus.AVAILABLE
        return AdapterResult(
            source_name="bernama_en",
            platform=BERNAMA_PLATFORM,
            started_at=started,
            finished_at=finished,
            retrieval_status=overall,
            observations=observations,
            errors=errors,
        )

    def _item_to_observation(self, item: ET.Element, started: str
                              ) -> Optional[AdapterObservation]:
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")
        if title_el is None or title_el.text is None:
            return None
        if link_el is None or link_el.text is None:
            return None
        title = _strip_xml(title_el.text)
        url = _strip_xml(link_el.text)
        if not is_valid_url(url):
            # Skip items whose URL is unsafe; record nothing.
            return None
        description_raw = _strip_xml(desc_el.text) if (desc_el is not None
                                                          and desc_el.text is not None) else ""
        description = _strip_html(description_raw)
        published_at = _parse_rfc822(pub_el.text) if pub_el is not None else None
        # Fallback: BERNAMA's RSS does NOT include <pubDate> in items.
        # Try to recover a coarse date from the description dateline.
        if published_at is None and description:
            anchor_year = self._clock().year
            published_at = _parse_description_date(description, anchor_year)
        # Deterministic content_id derived from the canonical URL.
        # Same URL across fetches -> same id -> P1 dedup works.
        content_id = _content_id_from_url(url)
        return AdapterObservation(
            content_id=content_id,
            platform=BERNAMA_PLATFORM,
            observed_at=started,
            retrieval_status=RetrievalStatus.AVAILABLE,
            source="bernama_en",
            source_url=self._fetch_url,
            title=title,
            published_at=published_at,
            url=url,
            # Engagement metrics intentionally None: BERNAMA RSS does
            # not expose them. We do NOT guess 0.
            views=None,
            likes=None,
            comments=None,
            shares=None,
            reposts=None,
            unavailable_reason=(
                "engagement_metrics_not_exposed_by_source"
            ),
            extra={"description_excerpt": description[:200]} if description else {},
        )

    def _error_result(self, started: str, reason: str) -> AdapterResult:
        finished = iso_utc(self._clock())
        return AdapterResult(
            source_name="bernama_en",
            platform=BERNAMA_PLATFORM,
            started_at=started,
            finished_at=finished,
            retrieval_status=RetrievalStatus.ERROR,
            observations=[],
            errors=[reason],
        )


# ============================================================================
# RSS helpers
# ============================================================================

_WHITESPACE_RE = re.compile(r"\s+")


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z]+);")


def _strip_html(s: str) -> str:
    """Strip HTML tags and decode common entities. Conservative."""
    if not s:
        return ""
    s = _HTML_TAG_RE.sub(" ", s)
    # Common entities. The BERNAMA feed uses Latin-1 / ISO-8859-1
    # declared in the XML header, so we just collapse them to "".
    s = _HTML_ENTITY_RE.sub(" ", s)
    return _WHITESPACE_RE.sub(" ", s).strip()


def _strip_xml(s: str) -> str:
    return _WHITESPACE_RE.sub(" ", s).strip()


_RFC822_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_rfc822(s: Optional[str]) -> Optional[str]:
    """Parse RFC 822 date (RSS 2.0 pubDate) into ISO 8601 UTC.

    Returns None when the input is missing or unparseable. Does not
    raise.
    """
    if s is None:
        return None
    s = _strip_xml(s)
    # Format: "Tue, 29 Sep 2026 03:18:00 +0800" or "GMT"
    # Be defensive: try the common shape, else let parse_timestamp_any
    # take over (it accepts ISO 8601 but not RFC 822).
    m = re.match(
        r"^(?:\w{3},\s+)?(\d{1,2})\s+(\w{3})\s+(\d{4})\s+"
        r"(\d{2}):(\d{2})(?::(\d{2}))?\s+([+-]\d{4}|GMT|UTC)$",
        s,
    )
    if not m:
        return None
    day, mon_s, year, hh, mm, ss, tz_s = m.groups()
    month = _RFC822_MONTHS.get(mon_s)
    if month is None:
        return None
    sec = int(ss) if ss else 0
    if tz_s in ("GMT", "UTC"):
        tz_offset_minutes = 0
    else:
        sign = 1 if tz_s[0] == "+" else -1
        tz_offset_minutes = sign * (int(tz_s[1:3]) * 60 + int(tz_s[3:5]))
    try:
        dt = datetime(int(year), month, int(day), int(hh), int(mm), sec,
                       tzinfo=timezone.utc)
    except ValueError:
        return None
    dt = dt - timedelta(minutes=tz_offset_minutes)
    return iso_utc(dt)


_DESCRIPTION_DATE_RE = re.compile(
    r"(?:^|\s)"
    r"("
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\s+\d{1,2}(?:,\s*\d{4})?"
    r"|"
    r"\d{1,2}\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"(?:\s+\d{4})?"
    r")",
    re.IGNORECASE,
)


def _parse_description_date(s: str, anchor_year: int) -> Optional[str]:
    """Extract a loose date from a BERNAMA-style dateline.

    BERNAMA datelines look like: "KOTA BHARU, Sept 29 (Bernama) --".
    We only use this as a fallback; we never invent a time, so the
    resulting timestamp is anchored at 00:00 UTC. If parsing fails,
    return None.

    IMPORTANT: This is intentionally conservative. We never guess
    a time-of-day; we never guess a year beyond the supplied
    anchor. Callers MUST treat the result as approximate.
    """
    if not s:
        return None
    m = _DESCRIPTION_DATE_RE.search(s)
    if not m:
        return None
    raw = m.group(1).strip()
    # Re-format to ISO date if we can.
    parts = re.split(r"\s+", raw.replace(",", ""))
    if len(parts) < 2:
        return None
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    day: Optional[int] = None
    month: Optional[int] = None
    year = anchor_year
    if parts[0][:3].lower() in months:
        month = months[parts[0][:3].lower()]
        try:
            day = int(parts[1])
        except (ValueError, IndexError):
            return None
        if len(parts) >= 3:
            try:
                year = int(parts[2])
            except ValueError:
                pass
    elif parts[1][:3].lower() in months:
        month = months[parts[1][:3].lower()]
        try:
            day = int(parts[0])
        except ValueError:
            return None
        if len(parts) >= 3:
            try:
                year = int(parts[2])
            except ValueError:
                pass
    else:
        return None
    try:
        dt = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
    except ValueError:
        return None
    return iso_utc(dt)


def _content_id_from_url(url: str) -> str:
    """Deterministic content_id from a URL (SHA-256 prefix)."""
    import hashlib
    payload = {"kind": "adapter_content_id_v1", "url": url}
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"))
    return "ci_" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


# ============================================================================
# Public re-exports
# ============================================================================

__all__ = [
    "RetrievalStatus",
    "AdapterCapability",
    "DataAccess",
    "AdapterSourceSpec",
    "AdapterObservation",
    "AdapterResult",
    "PublicPerformanceAdapter",
    "SyntheticAdapter",
    "SyntheticAdapterRecord",
    "SYNTHETIC_ADAPTER_TAG",
    "BernamaRssAdapter",
    "BERNAMA_RSS_URL",
    "BERNAMA_PLATFORM",
    "check_observation_quality",
    "validate_adapter_result",
]
