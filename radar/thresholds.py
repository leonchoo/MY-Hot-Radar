"""
Centralised thresholds.

If a number is used in dedup, verification, classification, or momentum: it
belongs here. This file is the single place to read or change heuristics.

These values are MY Hot Radar MVP internal heuristics. They are NOT a
claimed industry standard. See NEWS_RADAR.md and VERIFICATION_RULES.md.
"""

from __future__ import annotations

# --- dedup thresholds ---
TITLE_JACCARD_THRESHOLD = 0.55       # token-set Jaccard >= this -> strong title match
KEYWORD_OVERLAP_THRESHOLD = 0.50     # smaller-keyword-set overlap >= this -> strong keyword match
ENTITY_MIN_OVERLAP = 2               # shared named entities needed for entity-based merge
ENTITY_MIN_SHARE = 0.0               # share floor; 0.0 = trust the overlap count alone
EVENT_WINDOW_DAYS = 7                # publication-day window within which stories may cluster

# --- verification thresholds ---
# Independent sources needed for CONFIRMED. Tiers A or B only.
CONFIRMED_MIN_INDEPENDENT_SOURCES = 2
# A topic touching only social is at most SOCIAL BUZZ.
# A topic with media coverage that fails verification stays REPORTED.
# We further require that >= 2 different source_types for CONFIRMED.

# --- momentum thresholds ---
RISING_GROWTH_FACTOR = 1.5           # current / previous >= this -> RISING
HOT_MENTION_FLOOR = 5                # minimum current_mentions to be HOT
RISING_MENTION_FLOOR = 3             # minimum current_mentions to be RISING
COOLING_DECLINE_FACTOR = 0.75        # current / previous <= this -> COOLING (only if previously HOT/RISING)

# --- classification windows (in hours, for "BREAKING") ---
BREAKING_MAX_HOURS_SINCE_FIRST_SEEN = 3
BREAKING_MIN_PLATFORM_DIVERSITY = 2  # at least N distinct platforms/sources in <=3h window

# --- how many topics go into the human-visible report ---
RADAR_REPORT_TOP_N = 25
