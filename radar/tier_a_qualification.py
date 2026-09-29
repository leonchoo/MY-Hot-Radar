"""
Tier-A qualification logic.

This module encodes the 5-condition Tier-A qualification rule from
Radar-5A spec section 3:

  A. Publisher identity       - the source is a primary authority
                                 (government body, constitutional body,
                                 official regulator, etc.) AND the
                                 endpoint domain is verifiably owned by
                                 that authority.
  B. Primary-source relevance - content is actual press release /
                                 official statement / public
                                 announcement / official notice that
                                 the public would consume as
                                 authoritative on a topical event.
                                 NOT FAQ / placeholder / generic
                                 operational page / courtesy visit /
                                 HR / tender / job vacancy.
  C. Stable machine-readable  - exposes RSS / Atom / official API.
                                 NOT a hand-crafted HTML listing.
  D. Stability                - repeated fetches succeed and return
                                 bit-identical (or near-identical)
                                 content. NOT intermittent.
  E. Source independence      - the Tier-A feed is NOT a republisher
                                 of any Tier-B source, AND no Tier-B
                                 source republishes the Tier-A feed
                                 wholesale.

Why a separate module?  The qualification logic must be testable
without hitting the live network.  Each condition is a pure function
that takes observed evidence and returns True/False, plus a reason
string.  The pipeline:

    probe_candidate(...) -> CandidateEvidence
    qualify(candidate)    -> QualificationDecision

All tests in radar/tests/test_tier_a.py use fixture CandidateEvidence
objects, not network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class QualificationStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    NEEDS_FURTHER_VALIDATION = "NEEDS_FURTHER_VALIDATION"


@dataclass
class CandidateEvidence:
    """All the evidence needed to qualify a single candidate source.

    Populated by the probe script (radar/tests/fixtures or a separate
    probe CLI), then passed to qualify().

    Every field is optional so that partial probe results can still be
    fed in.  qualify() will check each present field and decide.
    """

    source_name: str
    publisher: str = ""
    country: str = ""
    official_domain: str = ""

    # C: Stable machine-readable access
    endpoint: str = ""
    access_method: str = ""           # e.g. "RSS 2.0", "Atom 1.0"
    is_reachable: Optional[bool] = None
    returns_parseable_feed: Optional[bool] = None
    feed_item_count: Optional[int] = None

    # A: Publisher identity
    is_official_domain: Optional[bool] = None
    publisher_is_primary_authority: Optional[bool] = None

    # B: Primary-source relevance (per-item)
    # fraction_placeholder      - items that are template placeholders
    # fraction_faq               - items that are help-desk FAQ
    # fraction_press_or_announce - items that are real press/announcement
    # fraction_admin_or_hr       - items that are admin ops / HR / tender
    fraction_placeholder: Optional[float] = None
    fraction_faq: Optional[float] = None
    fraction_press_or_announce: Optional[float] = None
    fraction_admin_or_hr: Optional[float] = None

    # D: Stability
    stability_pass_count: Optional[int] = None   # number of successful identical fetches
    stability_total_count: Optional[int] = None   # total fetches
    is_dormant: Optional[bool] = None            # True if feed is months-stale

    # E: Source independence
    is_syndicating_tier_b: Optional[bool] = None  # republishes Tier-B?
    is_republished_by_tier_b: Optional[bool] = None  # republished by Tier-B?

    # Free-form notes from the probe operator
    notes: str = ""


@dataclass
class QualificationDecision:
    """The result of evaluating one CandidateEvidence against the 5 rules."""
    status: QualificationStatus
    conditions_passed: list = field(default_factory=list)
    conditions_failed: list = field(default_factory=list)
    reason: str = ""

    @property
    def is_qualified(self) -> bool:
        return self.status == QualificationStatus.QUALIFIED


# ----------------------------------------------------------------------------
# Condition evaluators.  Each is a pure function over the evidence.
# ----------------------------------------------------------------------------

def _identity_ok(ev: CandidateEvidence) -> tuple[bool, str]:
    """A. Publisher identity.

    The source must be a primary authority AND the domain must be
    verifiably the authority's own domain.  Either both fields are
    True, or the function fails (because we cannot establish identity).
    """
    if ev.is_official_domain is False:
        return False, "A.identity: domain is NOT an official domain"
    if ev.publisher_is_primary_authority is False:
        return False, "A.identity: publisher is NOT a primary authority"
    if ev.is_official_domain is None or ev.publisher_is_primary_authority is None:
        return False, "A.identity: insufficient evidence to confirm publisher identity"
    return True, "A.identity: publisher is primary authority on official domain"


def _relevance_ok(ev: CandidateEvidence) -> tuple[bool, str]:
    """B. Primary-source relevance.

    The content mix must be dominated by real press / announcement
    content.  We require fraction_press_or_announce > 0.5 AND
    fraction_placeholder + fraction_faq < 0.5.

    Conservative threshold: more than half the items must be press /
    announcement, AND less than half can be placeholder or FAQ.
    Admin/HR/tenders are allowed but reduce press fraction.
    """
    if ev.fraction_press_or_announce is None:
        return False, "B.relevance: no press/announce fraction observed"
    if ev.fraction_placeholder is None or ev.fraction_faq is None:
        return False, "B.relevance: placeholder/faq fractions missing"

    if ev.fraction_placeholder >= 0.5:
        return False, f"B.relevance: {ev.fraction_placeholder:.0%} placeholders"
    if ev.fraction_faq >= 0.5:
        return False, f"B.relevance: {ev.fraction_faq:.0%} FAQ/help-desk"
    if ev.fraction_press_or_announce < 0.5:
        return False, (
            f"B.relevance: only {ev.fraction_press_or_announce:.0%} "
            f"press/announcement content"
        )
    return True, (
        f"B.relevance: {ev.fraction_press_or_announce:.0%} press/announcement content"
    )


def _access_ok(ev: CandidateEvidence) -> tuple[bool, str]:
    """C. Stable machine-readable access."""
    if ev.is_reachable is False:
        return False, "C.access: endpoint not reachable"
    if ev.returns_parseable_feed is False:
        return False, "C.access: feed is not parseable"
    if ev.is_reachable is None or ev.returns_parseable_feed is None:
        return False, "C.access: insufficient evidence on reachability/parse"
    if ev.feed_item_count is not None and ev.feed_item_count < 1:
        return False, "C.access: feed has zero items"
    return True, (
        f"C.access: {ev.access_method} feed reachable, "
        f"{ev.feed_item_count} items"
    )


def _stability_ok(ev: CandidateEvidence) -> tuple[bool, str]:
    """D. Stability.

    At least 2 of 2 (or 3 of 3) probe attempts must succeed and be
    bit-identical (same SHA-256).  We require stability_pass_count >=
    2.  Also, the feed must NOT be dormant (last item within the last
    90 days) - a stable-but-dormant feed is still not useful as
    Tier-A.
    """
    if ev.stability_pass_count is None or ev.stability_total_count is None:
        return False, "D.stability: insufficient stability probe data"
    if ev.stability_pass_count < 2:
        return False, (
            f"D.stability: only {ev.stability_pass_count}/"
            f"{ev.stability_total_count} probes succeeded"
        )
    if ev.is_dormant:
        return False, "D.stability: feed is dormant (last item > 90 days old)"
    return True, (
        f"D.stability: {ev.stability_pass_count}/{ev.stability_total_count} "
        f"probes stable, feed active"
    )


def _independence_ok(ev: CandidateEvidence) -> tuple[bool, str]:
    """E. Source independence."""
    if ev.is_syndicating_tier_b is True:
        return False, "E.independence: source republishes Tier-B content"
    if ev.is_republished_by_tier_b is True:
        return False, "E.independence: source is republished wholesale by Tier-B"
    if ev.is_syndicating_tier_b is None or ev.is_republished_by_tier_b is None:
        return False, "E.independence: insufficient independence evidence"
    return True, "E.independence: independent of Tier-B sources"


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------

def qualify(ev: CandidateEvidence) -> QualificationDecision:
    """Evaluate a candidate against the 5 Tier-A conditions.

    Returns:
      - QUALIFIED             if all 5 conditions pass
      - NOT_QUALIFIED         if any of A, C, D fails (these are the
                              "hard" conditions - without identity,
                              access, or stability there is nothing
                              to qualify)
      - NEEDS_FURTHER_VALIDATION
                             if A, C, D, E pass but B (primary-source
                             relevance) is borderline - e.g. the feed
                             is mixed (press + admin), or has only a
                             small number of items so we cannot
                             confidently estimate the fraction.
    """
    passed, failed = [], []

    for label, fn in [
        ("A.identity", _identity_ok),
        ("B.relevance", _relevance_ok),
        ("C.access", _access_ok),
        ("D.stability", _stability_ok),
        ("E.independence", _independence_ok),
    ]:
        ok, msg = fn(ev)
        (passed if ok else failed).append((label, msg))

    # Hard conditions: any failure -> NOT_QUALIFIED
    hard_failures = [
        label for (label, _msg) in failed
        if label.startswith(("A.", "C.", "D."))
    ]
    if hard_failures:
        return QualificationDecision(
            status=QualificationStatus.NOT_QUALIFIED,
            conditions_passed=passed,
            conditions_failed=failed,
            reason="; ".join(msg for _, msg in failed),
        )

    # Borderline: B fails but E passes -> NEEDS_FURTHER_VALIDATION
    if any(label.startswith("B.") for label, _ in failed):
        return QualificationDecision(
            status=QualificationStatus.NEEDS_FURTHER_VALIDATION,
            conditions_passed=passed,
            conditions_failed=failed,
            reason=(
                "Identity + access + stability + independence OK, but "
                "primary-source relevance is borderline. See B.relevance "
                "reason: " + "; ".join(msg for label, msg in failed
                                        if label.startswith("B."))
            ),
        )

    # All five passed
    return QualificationDecision(
        status=QualificationStatus.QUALIFIED,
        conditions_passed=passed,
        conditions_failed=failed,
        reason="All 5 Tier-A conditions satisfied",
    )
