"""Model-level validators for Performance Intelligence."""

from __future__ import annotations

from typing import Any

from .enums import (
    InsightScope,
    Platform,
    SourceType,
)
from .models import (
    ContentFeatureSnapshot,
    ContentIdentity,
    Insight,
    MarketObservation,
    PerformanceSnapshot,
)
from .validation import (
    ValidationError,
    is_metric,
    is_valid_url,
    parse_timestamp_any,
    validate_str,
)


def validate_content_identity(c: ContentIdentity) -> None:
    validate_str("content_id", c.content_id, max_len=128)
    if not isinstance(c.source_type, SourceType):
        raise ValidationError("source_type must be a SourceType enum")
    if not isinstance(c.platform, Platform):
        raise ValidationError("platform must be a Platform enum")
    validate_str("publisher", c.publisher, max_len=200)
    if not is_valid_url(c.url):
        raise ValidationError(f"url is not safe: {c.url!r}")
    validate_str("title", c.title, max_len=500)
    validate_str("category", c.category, max_len=64)
    validate_str("topic_type", c.topic_type, max_len=64)
    validate_str("language", c.language, max_len=16)
    if parse_timestamp_any(c.published_at) is None:
        raise ValidationError(
            f"published_at not a valid ISO/RFC2822: {c.published_at!r}"
        )


def validate_snapshot(s: PerformanceSnapshot) -> None:
    validate_str("content_id", s.content_id, max_len=128)
    if parse_timestamp_any(s.captured_at) is None:
        raise ValidationError(f"captured_at not valid: {s.captured_at!r}")
    for fname in ("views", "likes", "comments", "shares", "reposts"):
        v = getattr(s, fname)
        if not is_metric(v):
            raise ValidationError(
                f"{fname} must be None or a non-negative integer, got {v!r}"
            )


def validate_feature_snapshot(f: ContentFeatureSnapshot) -> None:
    validate_str("content_id", f.content_id, max_len=128)
    if parse_timestamp_any(f.captured_at) is None:
        raise ValidationError(f"captured_at not valid: {f.captured_at!r}")
    for name in ("category", "topic_type", "local_relevance",
                 "geographic_scope", "headline_style"):
        validate_str(name, getattr(f, name), max_len=64)
    if f.local_relevance not in ("LOCAL", "NATIONAL", "REGIONAL", "GLOBAL"):
        raise ValidationError(
            f"local_relevance invalid: {f.local_relevance!r}"
        )
    if f.headline_style not in (
        "INFORMATIVE", "QUESTION", "EXCLAMATORY", "QUOTE",
    ):
        raise ValidationError(
            f"headline_style invalid: {f.headline_style!r}"
        )
    if (not isinstance(f.headline_length, int)
            or f.headline_length < 0):
        raise ValidationError("headline_length must be a non-negative int")
    for bf in ("has_person_name", "has_location", "has_number",
               "has_question", "has_quote", "has_time_reference",
               "has_exclamation"):
        if not isinstance(getattr(f, bf), bool):
            raise ValidationError(f"{bf} must be a bool")
    if parse_timestamp_any(f.published_at) is None:
        raise ValidationError(
            f"published_at not valid: {f.published_at!r}"
        )
    if not (0 <= f.publication_hour <= 23):
        raise ValidationError("publication_hour must be 0..23")
    if not (0 <= f.publication_weekday <= 6):
        raise ValidationError("publication_weekday must be 0..6 (Mon=0)")
    for opt in ("radar_status", "radar_verification_status",
                "radar_confidence_label"):
        v = getattr(f, opt)
        if v is not None and (not isinstance(v, str) or len(v) > 64):
            raise ValidationError(f"{opt} must be None or short string")
    if (f.radar_momentum is not None
            and not isinstance(f.radar_momentum, (int, float))):
        raise ValidationError("radar_momentum must be None or numeric")
    if f.radar_source_count is not None:
        if (not isinstance(f.radar_source_count, int)
                or f.radar_source_count < 0):
            raise ValidationError(
                "radar_source_count must be None or non-negative int"
            )


def validate_market_observation(m: MarketObservation) -> None:
    validate_str("observation_id", m.observation_id, max_len=128)
    if not isinstance(m.platform, Platform):
        raise ValidationError("platform must be a Platform enum")
    validate_str("publisher", m.publisher, max_len=200)
    if not is_valid_url(m.content_url):
        raise ValidationError(f"content_url invalid: {m.content_url!r}")
    validate_str("title", m.title, max_len=500)
    if parse_timestamp_any(m.published_at) is None:
        raise ValidationError("published_at not valid")
    if parse_timestamp_any(m.captured_at) is None:
        raise ValidationError("captured_at not valid")
    validate_str("category", m.category, max_len=64)
    validate_str("topic_type", m.topic_type, max_len=64)
    if not isinstance(m.metrics, dict):
        raise ValidationError("metrics must be a dict")
    for k, v in m.metrics.items():
        if not is_metric(v):
            raise ValidationError(
                f"metric {k!r} must be None or non-negative int, got {v!r}"
            )


def validate_insight(i: Insight) -> None:
    validate_str("insight_id", i.insight_id, max_len=128)
    if not isinstance(i.scope, InsightScope):
        raise ValidationError("scope must be an InsightScope enum")
    if parse_timestamp_any(i.generated_at) is None:
        raise ValidationError("generated_at not valid")
    if not isinstance(i.observation_window, dict):
        raise ValidationError("observation_window must be a dict")
    for k in ("from", "to"):
        if k not in i.observation_window:
            raise ValidationError(f"observation_window missing {k!r}")
        if parse_timestamp_any(i.observation_window[k]) is None:
            raise ValidationError(
                f"observation_window.{k} not valid"
            )
    if not isinstance(i.sample_size, int) or i.sample_size < 0:
        raise ValidationError("sample_size must be a non-negative int")
    validate_str("finding", i.finding, max_len=2000)
    if not isinstance(i.evidence, list):
        raise ValidationError("evidence must be a list")
    if not isinstance(i.limitations, list):
        raise ValidationError("limitations must be a list")
