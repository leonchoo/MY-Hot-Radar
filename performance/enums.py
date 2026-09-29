"""Enums for Performance Intelligence."""

from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    """Distinguishes own content from market / competitor content."""
    OWN = "OWN"
    MARKET = "MARKET"


class Platform(str, Enum):
    WEBSITE = "WEBSITE"
    FACEBOOK = "FACEBOOK"
    INSTAGRAM = "INSTAGRAM"
    TIKTOK = "TIKTOK"
    YOUTUBE = "YOUTUBE"
    X = "X"
    OTHER = "OTHER"


class PerformanceClass(str, Enum):
    """Descriptive momentum / velocity class.

    These are LABELS, not predictions. They describe what the
    observation shows, not what the content will become.
    """
    EARLY_SPIKE = "EARLY_SPIKE"
    FAST_GROWTH = "FAST_GROWTH"
    STEADY_GROWTH = "STEADY_GROWTH"
    LATE_BREAKOUT = "LATE_BREAKOUT"
    COOLING = "COOLING"
    STABLE = "STABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class InsightScope(str, Enum):
    OWN = "OWN"
    MARKET = "MARKET"
    COMPARISON = "COMPARISON"
