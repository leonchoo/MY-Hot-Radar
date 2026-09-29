"""
Performance & Market Intelligence Agent — P1 (Foundation).

This module is the **observation** layer. It does NOT predict,
recommend, scrape, or change the News Radar.

P1 scope:
  * Data models for ContentIdentity, PerformanceSnapshot,
    PerformanceObservation, PerformanceClassification,
    ContentFeatureSnapshot, MarketObservation, Insight.
  * Pure validation (no I/O, no inference of "viral").
  * Deterministic IDs (SHA-256 over canonical inputs).
  * Atomic JSON persistence (separate from Radar / Candidate
    storage; gitignored).
  * Analysis helpers: compute_observation, classify_performance,
    engagement_rate, feature extraction.
  * Synthetic fixture helpers, clearly marked SYNTHETIC.
  * NO crawler, NO API, NO LLM, NO auto-publishing.

All public functions are pure. Persistence is the only side-effecting
layer, separated into PerformanceStore.
"""

from __future__ import annotations

PERFORMANCE_SCHEMA_VERSION = 1

from .enums import (
    InsightScope,
    PerformanceClass,
    Platform,
    SourceType,
)
from .models import (
    ContentFeatureSnapshot,
    ContentIdentity,
    Insight,
    MarketObservation,
    PerformanceObservation,
    PerformanceSnapshot,
)
from .models_validate import (
    validate_content_identity,
    validate_feature_snapshot,
    validate_insight,
    validate_market_observation,
    validate_snapshot,
)
from .validation import ValidationError
from .ids import (
    content_id_for,
    feature_id_for,
    market_observation_id_for,
    observation_id_for,
    snapshot_id_for,
)
from .analysis import (
    classify_late_breakout,
    classify_performance,
    compute_observation,
    engagement_breakdown,
    engagement_rate,
    engagement_total,
    extract_features,
)
from .store import (
    DEFAULT_PERFORMANCE_DATA_DIR,
    PerformanceStore,
    SyntheticFixtureError,
)
from .fixtures import (
    SYNTHETIC_TAG,
    all_synthetic_fixtures,
    make_synthetic_article_a,
    make_synthetic_article_b,
    make_synthetic_article_c,
    make_synthetic_article_d_missing_metrics,
    make_synthetic_market_content,
    make_synthetic_own_content,
)


__all__ = [
    "PERFORMANCE_SCHEMA_VERSION",
    # enums
    "SourceType",
    "Platform",
    "PerformanceClass",
    "InsightScope",
    # models
    "ContentIdentity",
    "PerformanceSnapshot",
    "PerformanceObservation",
    "ContentFeatureSnapshot",
    "MarketObservation",
    "Insight",
    # validation
    "ValidationError",
    "validate_content_identity",
    "validate_snapshot",
    "validate_feature_snapshot",
    "validate_market_observation",
    "validate_insight",
    # ids
    "content_id_for",
    "snapshot_id_for",
    "observation_id_for",
    "feature_id_for",
    "market_observation_id_for",
    # analysis
    "compute_observation",
    "engagement_total",
    "engagement_rate",
    "engagement_breakdown",
    "classify_performance",
    "classify_late_breakout",
    "extract_features",
    # storage
    "DEFAULT_PERFORMANCE_DATA_DIR",
    "PerformanceStore",
    "SyntheticFixtureError",
    # fixtures (test-only)
    "SYNTHETIC_TAG",
    "make_synthetic_article_a",
    "make_synthetic_article_b",
    "make_synthetic_article_c",
    "make_synthetic_article_d_missing_metrics",
    "make_synthetic_own_content",
    "make_synthetic_market_content",
    "all_synthetic_fixtures",
]
