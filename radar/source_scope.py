"""
Radar-5B — Source Scope & Content Nature classification.

This module SEPARATES three orthogonal questions that Radar-5A conflated
in its single 5-condition rule:

  1. Authority:  is the publisher a primary authority on official
                  domain? (Tier-A candidate status)
  2. Scope:      what SUBJECT AREA does this source cover?
                  (ELECTION, EDUCATION, FINANCE, ...)
  3. Relevance:  is the source's scope + content useful for a
                  GENERAL Malaysian news radar?
                  (HIGH / MEDIUM / LOW / UNKNOWN)

Plus:

  4. Content nature distribution per source:
     what CATEGORIES of items does the feed actually carry?
     (PRESS, NEWS, ADMIN_NOTICE, REGULATORY_NOTICE, TENDER, HR,
      CORPORATE, PUBLIC_SERVICE, UNKNOWN)

  5. Registration decision:
     given authority + scope + relevance, should this source enter
     MY Hot Radar's general source registry?

The KEY design rule (per Radar-5B spec section 11):

    A source can be:
      - authority_tier = "A"            (passes the 5-condition rule)
      - source_scope = "NICHE"          (narrow subject area)
      - radar_relevance = "LOW"         (low value for general radar)
      - registration_decision = "NOT_REGISTERED"
    ... all at once.  Authority does NOT auto-imply high relevance.

This module is intentionally:

  - Pure functions over evidence objects.
  - Testable without network calls (tests use fixture evidence).
  - HEURISTIC, not probabilistic (per spec section 15).
  - Independent of radar/tier_a_qualification.py and the existing
    verification / momentum / classification engines.

Architecture map:

    Radar-5A                     Radar-5B
    ----------                   ----------
    tier_a_qualification.py      source_scope.py          <-- this file
        |                             |
        | authority                   | scope / nature / relevance
        v                             v
    authority_tier = "A"          source_scope = "..."
        + radar_relevance = "..."
        + registration_decision = "..."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================================
# Enums
# ============================================================================

class SourceScope(str, Enum):
    """What SUBJECT AREA does this source cover?

    NOT a judgment of importance.  A source can be ELECTION-scoped and
    still be HIGH or LOW relevance depending on what MY Hot Radar cares
    about (general news).

    The values are deliberately coarse.  Adding finer scopes (e.g.
    SPORTS, TECHNOLOGY) requires an independent batch that adds
    evidence and tests for each new value.
    """
    GENERAL_NEWS = "GENERAL_NEWS"      # general Malaysian news outlet
    GOVERNMENT_NEWS = "GOVERNMENT_NEWS"  # government press releases on
                                          # general topics
    REGULATORY = "REGULATORY"          # regulatory body decisions,
                                          # circulars, rulings
    ELECTION = "ELECTION"              # election commission,
                                          # electoral boundaries, results
    EDUCATION = "EDUCATION"            # ministry of education, schools
    HEALTH = "HEALTH"                  # ministry of health, hospitals
    FINANCE = "FINANCE"                # finance ministry, central bank
    CORPORATE = "CORPORATE"            # corporate / state-owned enterprise
                                          # own-program PR
    NICHE = "NICHE"                    # very narrow scope (one bank,
                                          # one university, etc.)
    UNKNOWN = "UNKNOWN"


class RadarRelevance(str, Enum):
    """Is this source's scope + content useful for MY Hot Radar's
    GENERAL radar?

    HIGH    - covers general topics the radar surfaces regularly
    MEDIUM  - covers a specific high-interest domain (election,
              education, finance)
    LOW     - scope is narrow / self-promotional / niche
    UNKNOWN - insufficient evidence to classify

    This is a HEURISTIC, not a probability of user interest.
    """
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ContentNature(str, Enum):
    """Per-item content category.  Used to compute the distribution
    of item types in a feed.

    Multiple items in a feed can have different ContentNature values;
    a source's scope/relevance is computed from the DISTRIBUTION.
    """
    PRESS = "PRESS"                        # official press release,
                                            # media statement
    NEWS = "NEWS"                          # news item about an event
                                            # (may be brief)
    ADMIN_NOTICE = "ADMIN_NOTICE"          # counter openings,
                                            # courtesy visits, internal ops
    REGULATORY_NOTICE = "REGULATORY_NOTICE"  # rule/regulation/circular
    TENDER = "TENDER"                      # procurement notice
    HR = "HR"                              # job vacancy / personnel
    CORPORATE = "CORPORATE"                # own-program PR (sponsorship,
                                            # awards, internal events)
    PUBLIC_SERVICE = "PUBLIC_SERVICE"      # FAQ, helpline, public guidance
    PLACEHOLDER = "PLACEHOLDER"            # template/empty/test content
    UNKNOWN = "UNKNOWN"


class RegistrationDecision(str, Enum):
    """Should this source enter MY Hot Radar's source registry?"""
    REGISTERED = "REGISTERED"
    NOT_REGISTERED = "NOT_REGISTERED"
    NEEDS_FURTHER_VALIDATION = "NEEDS_FURTHER_VALIDATION"


# ============================================================================
# Evidence
# ============================================================================

@dataclass
class ContentDistribution:
    """Per-feed content-nature counts observed at probe time.

    All fields are fractions in [0.0, 1.0]; sum should be <= 1.0
    (UNKNOWN absorbs anything uncategorised).  Constructed from the
    raw item-by-item classification.
    """
    n_items: int = 0
    fraction_press: float = 0.0
    fraction_news: float = 0.0
    fraction_admin_notice: float = 0.0
    fraction_regulatory_notice: float = 0.0
    fraction_tender: float = 0.0
    fraction_hr: float = 0.0
    fraction_corporate: float = 0.0
    fraction_public_service: float = 0.0
    fraction_placeholder: float = 0.0
    fraction_unknown: float = 0.0

    @property
    def fraction_event_oriented(self) -> float:
        """Sum of content that describes actual events / decisions:
        press + news + regulatory_notice.

        Tenders, HR, admin notices, corporate PR are operational
        and do NOT count as 'event-oriented content'.
        """
        return (self.fraction_press
                + self.fraction_news
                + self.fraction_regulatory_notice)


@dataclass
class SourceScopeEvidence:
    """All evidence needed to determine a source's scope + relevance +
    registration decision.

    Populated by a probe, then fed into classify_scope() and
    decide_registration().
    """
    source_name: str
    publisher: str = ""

    # From Radar-5A: did the 5-condition rule pass?
    authority_tier: Optional[str] = None   # "A", "B", "C", "D", "E", "F"
    authority_qualifies: Optional[bool] = None  # True if Radar-5A says Tier-A

    # The observed content distribution (from probe)
    content_distribution: ContentDistribution = field(
        default_factory=ContentDistribution)

    # Is the source primary for general news (i.e. would a general
    # Malaysian news reader recognise this outlet)?
    is_general_news_outlet: Optional[bool] = None

    # Is the source's content primarily about its OWN organisation
    # (self-promotional, own-program PR)?
    is_self_promotional: Optional[bool] = None

    # Operator notes (free form, not used in rules)
    notes: str = ""


# ============================================================================
# Pure-function classifiers
# ============================================================================

def classify_scope(ev: SourceScopeEvidence) -> SourceScope:
    """Determine source scope from publisher identity + content evidence.

    Rules (in priority order):
      1. If is_general_news_outlet = True -> GENERAL_NEWS
      2. If publisher matches known election authority (SPR) -> ELECTION
      3. If publisher matches known education authority (KPM/MoE) -> EDUCATION
      4. If publisher matches known finance ministry / central bank -> FINANCE
      5. If publisher matches known regulatory body + fraction_regulatory > 0.3
         -> REGULATORY
      6. If is_self_promotional = True and content is mostly CORPORATE
         (fraction_corporate > 0.5) -> CORPORATE
      7. If the content is dominated by tenders / HR / admin -> NICHE
         (because the surface is "official" but the content is
         administrative, not news-relevant)
      8. Otherwise -> UNKNOWN
    """
    # Rule 1
    if ev.is_general_news_outlet is True:
        return SourceScope.GENERAL_NEWS

    pub = ev.publisher.lower()
    cd = ev.content_distribution

    # Rule 2: election authority
    if any(k in pub for k in ["pilihan raya", "election commission",
                              "spr"]):
        return SourceScope.ELECTION

    # Rule 3: education authority
    if any(k in pub for k in ["pendidikan", "education", "kpm", "moe"]):
        return SourceScope.EDUCATION

    # Rule 4: finance ministry / central bank
    if any(k in pub for k in ["kewangan", "treasury", "bank negara",
                              "mof", "finance"]):
        return SourceScope.FINANCE

    # Rule 5: regulatory body + actual regulatory content
    if any(k in pub for k in ["suruhanjaya", "badan kawal selia",
                              "regulator", "regulatory commission"]):
        if cd.fraction_regulatory_notice > 0.3:
            return SourceScope.REGULATORY

    # Rule 6: self-promotional corporate
    if ev.is_self_promotional is True and cd.fraction_corporate > 0.5:
        return SourceScope.CORPORATE

    # Rule 7: administrative / tender / HR-dominated "official" feed
    op_fraction = (cd.fraction_tender + cd.fraction_hr
                   + cd.fraction_admin_notice)
    if op_fraction > 0.7:
        return SourceScope.NICHE

    return SourceScope.UNKNOWN


def classify_relevance(scope: SourceScope,
                       ev: SourceScopeEvidence) -> RadarRelevance:
    """Determine how relevant this source is to MY Hot Radar's GENERAL
    Malaysian news radar.

    Rules (heuristic, threshold-based):
      GENERAL_NEWS                -> HIGH
      GOVERNMENT_NEWS + mostly PRESS/NEWS -> HIGH
      GOVERNMENT_NEWS + mostly ADMIN/HR -> MEDIUM
      ELECTION                    -> MEDIUM  (elections are tracked but
                                                election-period only)
      EDUCATION                   -> MEDIUM  (education policy matters,
                                                but tender/HR noise)
      REGULATORY + mostly REGULATORY_NOTICE -> MEDIUM
      FINANCE                     -> MEDIUM  (broad relevance but narrow
                                                topic scope)
      CORPORATE + fraction_event > 0.3    -> LOW (self-promotional)
      CORPORATE + fraction_event <= 0.3   -> LOW
      NICHE                       -> LOW
      UNKNOWN                     -> UNKNOWN

    Note: these thresholds are documented in docs/RADAR_5B_SCOPE_RELEVANCE.md
    and are NOT calibrated against user behavior data.  They are
    engineering rules for a radar system, not editorial judgments.
    """
    cd = ev.content_distribution

    if scope == SourceScope.GENERAL_NEWS:
        return RadarRelevance.HIGH

    if scope == SourceScope.GOVERNMENT_NEWS:
        if cd.fraction_event_oriented > 0.5:
            return RadarRelevance.HIGH
        return RadarRelevance.MEDIUM

    if scope == SourceScope.ELECTION:
        return RadarRelevance.MEDIUM

    if scope == SourceScope.EDUCATION:
        # Education ministry with mostly admin/tender content has LOW
        # news value per item (tender decisions are not general news).
        if cd.fraction_event_oriented > 0.4:
            return RadarRelevance.MEDIUM
        return RadarRelevance.LOW

    if scope == SourceScope.REGULATORY:
        if cd.fraction_regulatory_notice > 0.3:
            return RadarRelevance.MEDIUM
        return RadarRelevance.LOW

    if scope == SourceScope.FINANCE:
        return RadarRelevance.MEDIUM

    if scope == SourceScope.CORPORATE:
        return RadarRelevance.LOW

    if scope == SourceScope.NICHE:
        return RadarRelevance.LOW

    return RadarRelevance.UNKNOWN


def decide_registration(scope: SourceScope,
                        relevance: RadarRelevance,
                        authority_qualifies: Optional[bool]) -> RegistrationDecision:
    """Combine scope + relevance + authority into a registration decision.

    Rules:
      - If authority_qualifies is False: NOT_REGISTERED (per Radar-5A
        hard-fail rule)
      - GENERAL_NEWS + HIGH + authority_qualifies -> REGISTERED
      - MEDIUM + HIGH relevance + scope is broad (GOVERNMENT_NEWS) ->
        REGISTERED
      - Anything else with relevance LOW -> NOT_REGISTERED
      - MEDIUM but narrow scope (CORPORATE, NICHE) -> NOT_REGISTERED
      - UNKNOWN relevance -> NEEDS_FURTHER_VALIDATION

    Note: registration is for MY Hot Radar's GENERAL source registry.
    A source that doesn't get registered may still be useful for a
    domain-specific radar in the future; this decision only governs
    the current general registry.
    """
    if authority_qualifies is False:
        return RegistrationDecision.NOT_REGISTERED

    # High relevance + broad scope = good fit for general radar
    if scope in (SourceScope.GENERAL_NEWS,) and relevance == RadarRelevance.HIGH:
        return RegistrationDecision.REGISTERED

    if scope == SourceScope.GOVERNMENT_NEWS and relevance == RadarRelevance.HIGH:
        return RegistrationDecision.REGISTERED

    # Narrow scope / self-promotional / niche -> not for general radar
    if scope in (SourceScope.NICHE, SourceScope.CORPORATE):
        return RegistrationDecision.NOT_REGISTERED

    if relevance == RadarRelevance.LOW:
        return RegistrationDecision.NOT_REGISTERED

    if relevance == RadarRelevance.UNKNOWN:
        return RegistrationDecision.NEEDS_FURTHER_VALIDATION

    # MEDIUM relevance + broad-but-not-general scope -> NE further validation
    return RegistrationDecision.NEEDS_FURTHER_VALIDATION


# ============================================================================
# Combined API
# ============================================================================

@dataclass
class ScopeAssessment:
    """The combined result of classifying a source's scope, relevance,
    and registration decision.
    """
    source_name: str
    scope: SourceScope
    relevance: RadarRelevance
    registration_decision: RegistrationDecision
    reason: str = ""

    @property
    def is_registered(self) -> bool:
        return self.registration_decision == RegistrationDecision.REGISTERED


def assess_source(ev: SourceScopeEvidence) -> ScopeAssessment:
    """Run all three classifiers and return a combined ScopeAssessment.

    The `reason` field carries a short human-readable explanation
    suitable for logs or reports.
    """
    scope = classify_scope(ev)
    relevance = classify_relevance(scope, ev)
    decision = decide_registration(scope, relevance,
                                   ev.authority_qualifies)
    reason = (
        f"scope={scope.value} (from publisher+content), "
        f"relevance={relevance.value} "
        f"(event_fraction={ev.content_distribution.fraction_event_oriented:.0%}), "
        f"decision={decision.value}"
    )
    return ScopeAssessment(
        source_name=ev.source_name,
        scope=scope,
        relevance=relevance,
        registration_decision=decision,
        reason=reason,
    )


# ============================================================================
# Per-item content classifier (heuristic, multi-language)
# ============================================================================

def classify_content(title: str, summary: str = "") -> ContentNature:
    """Heuristic content-nature classifier for a single item.

    Multi-language (Malay + English).  Order-sensitive because some
    keywords (e.g. "majlis") can appear in CORPORATE or NEWS depending
    on the surrounding words.

    This is a HEURISTIC.  It is NOT a probability of any user-facing
    classification.  Used only to compute the ContentDistribution of
    a feed for scope/relevance assessment.
    """
    t = (title + " " + summary).lower()
    t_stripped = t.strip()

    # TENDER first (overlaps with ministry / construction)
    if re.search(r"(sebut\s*harga|tender|keputusan\s*tender|jadual\s*tender|"
                  r"buka\s*tender|tender\s*terbuka|tender\s*tertutup|"
                  r"procurement\s*tender)", t):
        return ContentNature.TENDER

    # HR (job vacancy / personnel / MySTEP)
    if re.search(r"(iklan\s*kekosongan|kekosongan\s*jawatan|tawaran\s*jawatan|"
                  r"panggilan\s*temu\s*duga|personel\s*mystep|lowongan|"
                  r"hiring\s*now|job\s*vacancy|vacancies|recruitment|"
                  r"jawatan\s*kosong)", t):
        return ContentNature.HR

    # ADMIN_NOTICE: counter openings, courtesy visits, internal ops
    if re.search(r"(pembukaan\s*kaunter|kaunter\s*pendaftaran|"
                  r"kunjungan\s*hormat|lawatan\s*hormat|"
                  r"waktu\s*operasi|cuti\s*am|cuti\s*umum|"
                  r"notis\s*operasi|notis\s*pentadbiran|"
                  r"terima\s*kunjungan|pembukaan\s*reruai|"
                  r"kunjung\s*hormat)", t):
        return ContentNature.ADMIN_NOTICE

    # PUBLIC_SERVICE: FAQ / helpline / general public guidance / scam alert
    if re.search(r"(bagaimana\s*cara|faq|soalan\s*lazim|soalan\s*umum|"
                  r"khidmat\s*pelanggan|talian\s*umum|cara\s*menggunakan|"
                  r"how\s*to\s*install|aduan|help\s*desk|"
                  r"deepfake\s*scam|awas\s*scam)", t):
        return ContentNature.PUBLIC_SERVICE

    # PLACEHOLDER
    if re.match(r"^elementor\s*#\d+", t_stripped) or re.search(
            r"\bhello\s*world\b", t_stripped):
        return ContentNature.PLACEHOLDER

    # CORPORATE: own-program PR (English + Malay)
    if re.search(r"(engages|empowers|receives|strengthens|forges|"
                  r"allocates|channels|partnership|strategic\s*collaboration|"
                  r"launches|launched|signs\s*mou|mou\s*signing|sponsors?|"
                  r"awarded|awards)", t):
        return ContentNature.CORPORATE
    if re.search(r"(majlis\s*(pelancaran|perasmian|graduasi|konvokesyen|"
                  r"pembukaan|penutup|sambutan)|karnival|"
                  r"hari\s*(kebangsaan|merdeka|pekerja|pendidik|guru)|"
                  r"konvokesyen)", t):
        return ContentNature.CORPORATE

    # REGULATORY_NOTICE (rule / regulation / circular)
    if re.search(r"(pemberitahuan\s*pekeliling|pekeliling|garis\s*panduan|"
                  r"perintah|akta|peraturan|amendment|pindaan|"
                  r"surat\s*pekeliling)", t):
        return ContentNature.REGULATORY_NOTICE

    # PRESS (explicit "press release" / "media statement")
    if re.search(r"(kenyataan\s*media|press\s*release|kenyataan\s*akhbar|"
                  r"siaran\s*media|media\s*release|media\s*statement|"
                  r"official\s*statement|official\s*announcement)", t):
        return ContentNature.PRESS

    # Bank/ministry corporate-program PR fallback (own-program announcements
    # not caught by PRESS keyword).  These are still CORPORATE not NEWS.
    if re.search(r"(agrobank\s+(engages|empowers|receives|strengthens|"
                  r"allocates|channels|forges|and))", t):
        return ContentNature.CORPORATE

    # NEWS: has Malaysia-relevant event / decision language
    if re.search(r"(malaysia|mahathir|anwar|sultan|perdana\s*menter|"
                  r"mengumumkan|menyatakan|menjelaskan|menggesa|"
                  r"sidang\s*media|program\s*dapur|"
                  r"pemantauan|pemerkasaan)", t):
        return ContentNature.NEWS

    return ContentNature.UNKNOWN


def build_content_distribution(
        items: list[tuple[str, str]]) -> ContentDistribution:
    """Build a ContentDistribution from (title, summary) tuples."""
    from collections import Counter
    n = len(items)
    if n == 0:
        return ContentDistribution(n_items=0)
    counts: Counter = Counter()
    for title, summary in items:
        counts[classify_content(title, summary)] += 1
    return ContentDistribution(
        n_items=n,
        fraction_press=counts.get(ContentNature.PRESS, 0) / n,
        fraction_news=counts.get(ContentNature.NEWS, 0) / n,
        fraction_admin_notice=counts.get(ContentNature.ADMIN_NOTICE, 0) / n,
        fraction_regulatory_notice=counts.get(ContentNature.REGULATORY_NOTICE, 0) / n,
        fraction_tender=counts.get(ContentNature.TENDER, 0) / n,
        fraction_hr=counts.get(ContentNature.HR, 0) / n,
        fraction_corporate=counts.get(ContentNature.CORPORATE, 0) / n,
        fraction_public_service=counts.get(ContentNature.PUBLIC_SERVICE, 0) / n,
        fraction_placeholder=counts.get(ContentNature.PLACEHOLDER, 0) / n,
        fraction_unknown=counts.get(ContentNature.UNKNOWN, 0) / n,
    )
