"""
Performance & Market Intelligence Agent — P1 (Foundation) + P2 (Story
Clustering) + P3-A (Adapter Foundation) + Android Bridge (pre-P3-B
design contract).

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

P2 scope (added):
  * StoryCluster — multiple media coverage of the same event.
  * StoryMatch — explainable match result with reasons.
  * PackagingSnapshot — descriptive features of how a publisher
    packaged a single piece of content.
  * StoryComparison — observed performance across cluster members
    (no ranking, no normalization, null-safe).
  * Deterministic same-story matching (no LLM, no embedding API).
  * Deterministic feature extraction for headline / caption / image.
  * SYNTHETIC story-cluster fixtures.

P3-A scope (added):
  * Adapter framework: PublicPerformanceAdapter abstract base.
  * RetrievalStatus enum (AVAILABLE / PARTIAL / UNAVAILABLE /
    RATE_LIMITED / NOT_SUPPORTED / INVALID_SOURCE / ERROR).
  * AdapterCapability enum (what an adapter can actually fetch).
  * DataAccess enum (PUBLIC / PRIVATE / SYNTHETIC).
  * AdapterObservation: per-row normalized observation carrying
    source, source_url, retrieval_status, observed_at, metrics
    (None = unknown / not exposed by source).
  * AdapterResult: batched output with per-row + overall statuses.
  * SyntheticAdapter: fixture-backed adapter for tests + offline dev.
  * BernamaRssAdapter: real, public, no-login adapter for BERNAMA.
  * Quality checks: timestamp validity, published_at <= observed_at,
    metric non-negative, no fake zero, no duplicate content_id in
    one batch, source/platform identity preserved.
  * NO Facebook/Instagram/TikTok/YouTube/X API integration.
  * NO login bypass, NO anti-bot bypass, NO scraping of private data.

Android Bridge scope (added; pre-P3-B design only):
  * Defines the agreed wire shape Android Collector hands to
    MY Hot Radar (AndroidObservationInput).
  * Evidence reference type (SCREENSHOT / UI_TEXT / UI_NODE / OCR /
    COMPOSITE) — metadata only, never binary.
  * Validation rules specific to Android-collected observations.
  * Translation layer AndroidObservationInput -> P3-A
    AdapterObservation (preserving None semantics, publisher
    identity, platform separation).
  * NO actual Android / ADB / Facebook / Instagram / YouTube
    integration code lives in MY Hot Radar.
  * Waits for android-collector's first-stage verification before
    P3-B can be designed.

All public functions are pure. Persistence is the only side-effecting
layer, separated into PerformanceStore.
"""

from __future__ import annotations

PERFORMANCE_SCHEMA_VERSION = 3

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
from .story import (
    JACCARD_HIGH,
    JACCARD_MEDIUM,
    DATE_PROXIMITY_MAX_HOURS,
    IMAGE_TYPES,
    NORMALIZED_COMPARISON_UNAVAILABLE,
    MemberPerformance,
    PackagingSnapshot,
    StoryCategoryPropagation,
    StoryCluster,
    StoryComparison,
    StoryMatch,
    StoryMember,
    build_packaging_snapshot,
    build_story_comparison,
    derive_story_cluster_category,
    extract_headline_features,
    extract_known_entities,
    extract_locations,
    jaccard_similarity,
    match_stories,
    minutes_between,
    normalize_title,
    normalize_title_stemmed,
    story_cluster_id_for,
    timing_offsets,
    validate_packaging_snapshot,
    validate_story_cluster,
)
from .adapters import (
    AdapterCapability,
    AdapterObservation,
    AdapterResult,
    AdapterSourceSpec,
    BERNAMA_PLATFORM,
    BERNAMA_RSS_URL,
    BernamaRssAdapter,
    DataAccess,
    PublicPerformanceAdapter,
    RetrievalStatus,
    SYNTHETIC_ADAPTER_TAG,
    SyntheticAdapter,
    SyntheticAdapterRecord,
    check_observation_quality,
    extract_source_category_from_title,
    validate_adapter_result,
)
from .android_bridge import (
    ANDROID_BRIDGE_SOURCE_PREFIX,
    AndroidObservationInput,
    AndroidValidationIssue,
    Evidence,
    EvidenceType,
    batch_to_adapter_dicts,
    build_adapter_result_from_android_batch,
    derive_content_id,
    to_adapter_observation,
    validate_android_batch,
    validate_android_observation,
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
    # P2 story models
    "StoryCluster",
    "StoryMember",
    "StoryCategoryPropagation",
    "StoryMatch",
    "PackagingSnapshot",
    "StoryComparison",
    "MemberPerformance",
    "NORMALIZED_COMPARISON_UNAVAILABLE",
    "IMAGE_TYPES",
    # validation
    "ValidationError",
    "validate_content_identity",
    "validate_snapshot",
    "validate_feature_snapshot",
    "validate_market_observation",
    "validate_insight",
    "validate_story_cluster",
    "validate_packaging_snapshot",
    # ids
    "content_id_for",
    "snapshot_id_for",
    "observation_id_for",
    "feature_id_for",
    "market_observation_id_for",
    "story_cluster_id_for",
    # analysis
    "compute_observation",
    "engagement_total",
    "engagement_rate",
    "engagement_breakdown",
    "classify_performance",
    "classify_late_breakout",
    "extract_features",
    # P2 helpers
    "match_stories",
    "derive_story_cluster_category",
    "extract_headline_features",
    "extract_locations",
    "extract_known_entities",
    "normalize_title",
    "normalize_title_stemmed",
    "jaccard_similarity",
    "build_packaging_snapshot",
    "build_story_comparison",
    "minutes_between",
    "timing_offsets",
    "JACCARD_HIGH",
    "JACCARD_MEDIUM",
    "DATE_PROXIMITY_MAX_HOURS",
    # P3-A adapter framework
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
    "extract_source_category_from_title",
    "check_observation_quality",
    "validate_adapter_result",
    # Android Bridge (pre-P3-B design)
    "EvidenceType",
    "Evidence",
    "AndroidObservationInput",
    "AndroidValidationIssue",
    "ANDROID_BRIDGE_SOURCE_PREFIX",
    "derive_content_id",
    "to_adapter_observation",
    "batch_to_adapter_dicts",
    "build_adapter_result_from_android_batch",
    "validate_android_observation",
    "validate_android_batch",
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
