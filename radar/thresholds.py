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
ENTITY_MIN_SHARE = 0.20              # share floor; A2.3.2 Guard B: 0.0 was vacuous, raised to require
                                     # at least 20% of the smaller entity set to be shared.
                                     # Rationale (see docs/CHINESE_DEDUP_GUARD_DESIGN.md Investigation 1):
                                     # PH-Bersatu case had eo/smaller = 2/11 = 0.18, which falls
                                     # below this 0.20 floor and correctly fails the entity-share check.
                                     # Real same-event merges like Hasmah (eo=2, smaller=3, share=0.67)
                                     # and intra-FMT analyst articles (share=0.5+) remain well above.
EVENT_WINDOW_DAYS = 7                # publication-day window within which stories may cluster
# A2.3.2 Guard C — entity-path date strictness
ENTITY_PATH_REQUIRE_DATE_BOTH_SIDES = True
                                     # If True (default), the entity-overlap merge path requires
                                     # BOTH sides to have a known date (published_at OR URL-derived).
                                     # If only one side has a date, fail-closed (return False).
                                     # If both sides have dates, fall back to _same_event_window.
                                     # If neither side has a date, permissive fallback (return True)
                                     # is preserved to avoid breaking historical behavior on
                                     # adapters that produce sparse dates.

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
