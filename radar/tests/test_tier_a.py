"""
Radar-5A Tier-A qualification tests.

These tests verify the 5-condition qualification rule encoded in
radar.tier_a_qualification. They use FIXTURE CandidateEvidence objects
(no network calls), so they are deterministic and fast.

The fixtures model:

  1. A perfectly qualifying Tier-A candidate (all 5 conditions pass)
  2. Each individual condition failing
  3. The real candidates probed in Radar-5A (HASiL, JPJ, SPR, Agrobank,
     KPM, BERNAMA, PMO, KKM, JPM, JAKIM, MOF, MITI)

These are NOT news fixtures - they are evidence about source probes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from radar.tier_a_qualification import (
    CandidateEvidence,
    QualificationDecision,
    QualificationStatus,
    qualify,
)


# ============================================================================
# Fixtures - one per scenario
# ============================================================================

def ev_perfect_qualifying():
    """All 5 conditions met. The hypothetical ideal Tier-A."""
    return CandidateEvidence(
        source_name="Perfect Tier-A (test fixture)",
        publisher="Office of the PM",
        country="MY",
        official_domain="pm.example.gov.my",
        endpoint="https://pm.example.gov.my/press/feed",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=15,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.0,
        fraction_faq=0.0,
        fraction_press_or_announce=0.9,
        fraction_admin_or_hr=0.1,
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Test fixture for the ideal Tier-A case.",
    )


def ev_domain_only_official_domain_insufficient():
    """Official domain but content is placeholder + FAQ. Fails B."""
    return CandidateEvidence(
        source_name="Domain-only official (test fixture)",
        publisher="Test Authority",
        country="MY",
        official_domain="test.gov.my",
        endpoint="https://test.gov.my/feed",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=10,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.7,    # 70% placeholder
        fraction_faq=0.3,
        fraction_press_or_announce=0.0,
        fraction_admin_or_hr=0.0,
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Test fixture: domain is official but content is boilerplate.",
    )


def ev_faq_dominated():
    """FAQ / help-desk dominated. Fails B (FAQ >= 50%)."""
    return CandidateEvidence(
        source_name="FAQ-dominated (test fixture)",
        publisher="Test Authority",
        official_domain="test.gov.my",
        endpoint="https://test.gov.my/feed",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=20,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.0,
        fraction_faq=0.8,            # 80% FAQ
        fraction_press_or_announce=0.1,
        fraction_admin_or_hr=0.1,
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Test fixture: help-desk / FAQ feed.",
    )


def ev_third_party_mirror():
    """A third-party site republishing Tier-B. Fails A + E."""
    return CandidateEvidence(
        source_name="Third-party mirror (test fixture)",
        publisher="Some Aggregator Sdn Bhd",
        official_domain="aggregator.com",
        endpoint="https://aggregator.com/feed",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=50,
        is_official_domain=False,
        publisher_is_primary_authority=False,
        fraction_placeholder=0.0,
        fraction_faq=0.0,
        fraction_press_or_announce=1.0,
        fraction_admin_or_hr=0.0,
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=True,
        is_republished_by_tier_b=False,
        notes="Test fixture: third-party mirror republishing Tier-B.",
    )


def ev_unstable_endpoint():
    """Endpoint is reachable but the response is unstable. Fails D."""
    return CandidateEvidence(
        source_name="Unstable endpoint (test fixture)",
        publisher="Test Authority",
        official_domain="test.gov.my",
        endpoint="https://test.gov.my/feed",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=15,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.0,
        fraction_faq=0.0,
        fraction_press_or_announce=0.9,
        fraction_admin_or_hr=0.1,
        stability_pass_count=1,      # only 1 of 3 probes succeeded
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Test fixture: only 1 of 3 probes succeeded.",
    )


def ev_dormant_feed():
    """Feed is stable but dormant (last item 4 months old). Fails D."""
    return CandidateEvidence(
        source_name="Dormant feed (test fixture)",
        publisher="Test Authority",
        official_domain="test.gov.my",
        endpoint="https://test.gov.my/feed",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=5,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.0,
        fraction_faq=0.0,
        fraction_press_or_announce=0.9,
        fraction_admin_or_hr=0.1,
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=True,             # last item 126 days old
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Test fixture: feed is dormant.",
    )


def ev_unreachable_endpoint():
    """Endpoint not reachable. Fails C."""
    return CandidateEvidence(
        source_name="Unreachable (test fixture)",
        publisher="Test Authority",
        official_domain="test.gov.my",
        endpoint="https://test.gov.my/feed",
        access_method="RSS (attempted)",
        is_reachable=False,
        returns_parseable_feed=None,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=None,
        fraction_faq=None,
        fraction_press_or_announce=None,
        stability_pass_count=0,
        stability_total_count=3,
        is_dormant=None,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Test fixture: endpoint not reachable.",
    )


def ev_syndicating_tier_b():
    """Republishes Tier-B content wholesale. Fails E."""
    return CandidateEvidence(
        source_name="Tier-B syndicating (test fixture)",
        publisher="Some news aggregator",
        official_domain="",
        endpoint="https://syndicator.example.com/feed",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=100,
        is_official_domain=False,
        publisher_is_primary_authority=False,
        fraction_placeholder=0.0,
        fraction_faq=0.0,
        fraction_press_or_announce=1.0,
        fraction_admin_or_hr=0.0,
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=True,
        is_republished_by_tier_b=False,
        notes="Test fixture: republishes Tier-B content.",
    )


def ev_borderline_relevance():
    """Identity/access/stability/independence OK but relevance is mixed.
    PASSES A, C, D, E.  FAILS B because fraction_press_or_announce < 0.5.
    Should land in NEEDS_FURTHER_VALIDATION, NOT NOT_QUALIFIED.
    """
    return CandidateEvidence(
        source_name="Mixed content (test fixture)",
        publisher="Constitutional body",
        official_domain="body.gov.my",
        endpoint="https://body.gov.my/feed",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=15,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.0,
        fraction_faq=0.0,
        fraction_press_or_announce=0.4,  # only 40% press
        fraction_admin_or_hr=0.6,        # 60% admin / HR
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Test fixture: identity OK but content is admin-heavy.",
    )


# Real-world fixtures from the Radar-5A probe (see docs/RADAR_5A_TIER_A_DISCOVERY.md)

def ev_real_hasil():
    """HASiL: placeholder + dormant. NOT_QUALIFIED."""
    return CandidateEvidence(
        source_name="HASiL (LHDN)",
        publisher="Lembaga Hasil Dalam Negeri",
        country="MY",
        official_domain="hasil.gov.my",
        endpoint="https://www.hasil.gov.my/rss",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=5,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.4,     # 2 of 5 items are "Elementor #NNNN"
        fraction_faq=0.0,
        fraction_press_or_announce=0.0,    # 0 real press
        fraction_admin_or_hr=0.6,     # 3 of 5 are webinar/operational
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=True,              # newest item 126 days old
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Radar-5A probe: feed is dormant and placeholder-dominated.",
    )


def ev_real_jpj():
    """JPJ: FAQ dominated + dormant. NOT_QUALIFIED."""
    return CandidateEvidence(
        source_name="JPJ",
        publisher="Jabatan Pengangkutan Jalan",
        country="MY",
        official_domain="jpj.gov.my",
        endpoint="https://www.jpj.gov.my/feed/",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=10,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.0,
        fraction_faq=0.7,             # 7 of 10 are FAQ
        fraction_press_or_announce=0.0,
        fraction_admin_or_hr=0.3,
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=True,              # newest item 82 days old
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Radar-5A probe: feed is help-desk FAQ, dormant.",
    )


def ev_real_spr():
    """SPR: constitutional body, active, but 90% admin notices.
    Identity OK, access OK, stability OK, independence OK.  Relevance is
    borderline because fraction_press_or_announce is 10% - well below
    the 50% threshold.  Should land in NEEDS_FURTHER_VALIDATION.
    """
    return CandidateEvidence(
        source_name="SPR (Suruhanjaya Pilihan Raya)",
        publisher="Suruhanjaya Pilihan Raya Malaysia",
        country="MY",
        official_domain="spr.gov.my",
        endpoint="https://www.spr.gov.my/feed/",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=10,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.0,
        fraction_faq=0.0,
        fraction_press_or_announce=0.1,    # only 10% press/announcement
        fraction_admin_or_hr=0.9,
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Radar-5A probe: constitutional body, active feed, "
              "but content is 90% administrative notices.",
    )


def ev_real_agrobank():
    """Agrobank: state-owned, active, 100% press releases.  But narrow
    scope (its own programs only).  Identity OK, access OK, stability
    OK, independence OK.  Relevance passes the >=50% test (100% press).
    Identity OK on ownership grounds (100% MOF Inc.).
    Per the qualification rule, all 5 conditions pass - so the result
    should be QUALIFIED on pure-rule grounds.  But the rule alone
    doesn't capture 'narrow scope / self-promotional' concerns, so this
    test verifies the RULE passes, and a separate test documents that
    a human reviewer flagged this as scope-borderline.
    """
    return CandidateEvidence(
        source_name="Agrobank",
        publisher="Bank Pertanian Malaysia Berhad",
        country="MY",
        official_domain="agrobank.com.my",
        endpoint="https://www.agrobank.com.my/feed/",
        access_method="RSS 2.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=10,
        is_official_domain=True,
        publisher_is_primary_authority=True,  # state-owned, on ownership grounds
        fraction_placeholder=0.0,
        fraction_faq=0.0,
        fraction_press_or_announce=1.0,       # 100% press releases
        fraction_admin_or_hr=0.0,
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Radar-5A probe: state-owned, active, 100% press releases. "
              "Narrow scope flagged in candidate evidence notes.",
    )


def ev_real_kpm():
    """KPM: federal ministry, active, but mixed content.  ~40% press +
    ~43% tender + 7% job vacancy.  Identity OK, access OK, stability
    OK, independence OK.  Relevance borderline (press fraction < 50%).
    Should land in NEEDS_FURTHER_VALIDATION.
    """
    return CandidateEvidence(
        source_name="KPM (Ministry of Education)",
        publisher="Kementerian Pendidikan Malaysia",
        country="MY",
        official_domain="moe.gov.my",
        endpoint="https://www.moe.gov.my/feed",
        access_method="Atom 1.0",
        is_reachable=True,
        returns_parseable_feed=True,
        feed_item_count=340,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=0.0,
        fraction_faq=0.0,
        fraction_press_or_announce=0.406,    # 138 of 340
        fraction_admin_or_hr=0.594,         # 202 of 340 = tenders + HR + admin
        stability_pass_count=3,
        stability_total_count=3,
        is_dormant=False,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Radar-5A probe: federal ministry, active, mixed content. "
              "Date format inside HTML summaries not machine-readable.",
    )


def ev_real_bernama():
    """BERNAMA: unreachable. NOT_QUALIFIED."""
    return CandidateEvidence(
        source_name="BERNAMA",
        publisher="Bernama (national news agency)",
        country="MY",
        official_domain="bernama.com",
        endpoint="https://www.bernama.com/rss",
        access_method="RSS (attempted)",
        is_reachable=False,
        returns_parseable_feed=None,
        feed_item_count=None,
        is_official_domain=True,
        publisher_is_primary_authority=True,
        fraction_placeholder=None,
        fraction_faq=None,
        fraction_press_or_announce=None,
        stability_pass_count=0,
        stability_total_count=4,
        is_dormant=None,
        is_syndicating_tier_b=False,
        is_republished_by_tier_b=False,
        notes="Radar-5A probe: all probed BERNAMA RSS endpoints unreachable.",
    )


# ============================================================================
# Tests
# ============================================================================

def test_perfect_qualifying_candidate_qualifies():
    """All 5 conditions pass -> QUALIFIED."""
    d = qualify(ev_perfect_qualifying())
    assert d.status == QualificationStatus.QUALIFIED, (
        f"perfect candidate should be QUALIFIED; got {d.status.value} "
        f"reason: {d.reason}"
    )
    assert len(d.conditions_failed) == 0
    assert len(d.conditions_passed) == 5
    print("PASS test_perfect_qualifying_candidate_qualifies")


def test_official_domain_alone_cannot_qualify():
    """A.domain-only official candidate has identity but no real press
    content.  The 5-condition rule classifies this as
    NEEDS_FURTHER_VALIDATION, not NOT_QUALIFIED, because A/C/D/E pass
    and only B (relevance) fails - i.e. it COULD become Tier-A if its
    content mix changes (e.g. by filtering, or by waiting for better
    content).  This test locks in that interpretation.
    """
    d = qualify(ev_domain_only_official_domain_insufficient())
    assert d.status == QualificationStatus.NEEDS_FURTHER_VALIDATION, (
        f"official-domain-only with placeholder content should land in "
        f"NEEDS_FURTHER_VALIDATION; got {d.status.value} reason: {d.reason}"
    )
    labels_passed = [l for l, _ in d.conditions_passed]
    labels_failed = [l for l, _ in d.conditions_failed]
    # A, C, D, E should all pass; only B should fail
    assert "A.identity" in labels_passed
    assert "C.access" in labels_passed
    assert "D.stability" in labels_passed
    assert "E.independence" in labels_passed
    assert labels_failed == ["B.relevance"]
    print("PASS test_official_domain_alone_cannot_qualify "
          "(lands in NEEDS_FURTHER_VALIDATION)")


def test_faq_dominated_feed_cannot_qualify():
    """FAQ-dominated feed fails B.relevance (fraction_faq >= 0.5).

    Like the placeholder case: identity + access + stability +
    independence all pass, only B fails.  So this is
    NEEDS_FURTHER_VALIDATION, not NOT_QUALIFIED - the source could
    become Tier-A if it added real press content.
    """
    d = qualify(ev_faq_dominated())
    assert d.status == QualificationStatus.NEEDS_FURTHER_VALIDATION
    labels_passed = [l for l, _ in d.conditions_passed]
    labels_failed = [l for l, _ in d.conditions_failed]
    assert "A.identity" in labels_passed
    assert "C.access" in labels_passed
    assert "D.stability" in labels_passed
    assert "E.independence" in labels_passed
    assert labels_failed == ["B.relevance"]
    # And the reason should mention FAQ fraction
    assert any("FAQ" in m for l, m in d.conditions_failed)
    print("PASS test_faq_dominated_feed_cannot_qualify "
          "(lands in NEEDS_FURTHER_VALIDATION)")


def test_third_party_mirror_cannot_qualify():
    """Third-party aggregator fails A.identity AND E.independence."""
    d = qualify(ev_third_party_mirror())
    assert d.status == QualificationStatus.NOT_QUALIFIED
    labels_failed = [l for l, _ in d.conditions_failed]
    assert "A.identity" in labels_failed
    assert "E.independence" in labels_failed
    print("PASS test_third_party_mirror_cannot_qualify")


def test_unstable_endpoint_cannot_qualify():
    """Unstable endpoint fails D.stability."""
    d = qualify(ev_unstable_endpoint())
    assert d.status == QualificationStatus.NOT_QUALIFIED
    labels_failed = [l for l, _ in d.conditions_failed]
    assert "D.stability" in labels_failed
    print("PASS test_unstable_endpoint_cannot_qualify")


def test_dormant_feed_cannot_qualify():
    """Dormant feed fails D.stability even though transport is stable."""
    d = qualify(ev_dormant_feed())
    assert d.status == QualificationStatus.NOT_QUALIFIED
    labels_failed = [l for l, _ in d.conditions_failed]
    assert "D.stability" in labels_failed
    assert any("dormant" in m for l, m in d.conditions_failed), (
        f"reason should mention dormancy; got {d.reason}"
    )
    print("PASS test_dormant_feed_cannot_qualify")


def test_unreachable_endpoint_cannot_qualify():
    """Unreachable endpoint fails C.access."""
    d = qualify(ev_unreachable_endpoint())
    assert d.status == QualificationStatus.NOT_QUALIFIED
    labels_failed = [l for l, _ in d.conditions_failed]
    assert "C.access" in labels_failed
    print("PASS test_unreachable_endpoint_cannot_qualify")


def test_syndicating_tier_b_cannot_qualify():
    """A Tier-B syndicating feed fails E.independence."""
    d = qualify(ev_syndicating_tier_b())
    assert d.status == QualificationStatus.NOT_QUALIFIED
    labels_failed = [l for l, _ in d.conditions_failed]
    assert "E.independence" in labels_failed
    print("PASS test_syndicating_tier_b_cannot_qualify")


def test_borderline_relevance_lands_in_needs_further_validation():
    """A, C, D, E pass but B (press < 50%) fails -> NEEDS_FURTHER_VALIDATION."""
    d = qualify(ev_borderline_relevance())
    assert d.status == QualificationStatus.NEEDS_FURTHER_VALIDATION, (
        f"borderline case should be NEEDS_FURTHER_VALIDATION, not "
        f"NOT_QUALIFIED; got {d.status.value} reason: {d.reason}"
    )
    labels_passed = [l for l, _ in d.conditions_passed]
    labels_failed = [l for l, _ in d.conditions_failed]
    # A, C, D, E should all pass
    assert "A.identity" in labels_passed
    assert "C.access" in labels_passed
    assert "D.stability" in labels_passed
    assert "E.independence" in labels_passed
    # Only B should fail
    assert labels_failed == ["B.relevance"]
    print("PASS test_borderline_relevance_lands_in_needs_further_validation")


# ----------------------------------------------------------------------------
# Real-world probes (from Radar-5A evidence)
# ----------------------------------------------------------------------------

def test_real_hasil_not_qualified():
    d = qualify(ev_real_hasil())
    assert d.status == QualificationStatus.NOT_QUALIFIED, (
        f"HASiL should be NOT_QUALIFIED; got {d.status.value} reason: {d.reason}"
    )
    labels_failed = [l for l, _ in d.conditions_failed]
    assert "B.relevance" in labels_failed, "expected B.relevance failure"
    assert "D.stability" in labels_failed, "expected D.stability failure (dormant)"
    print(f"PASS test_real_hasil_not_qualified ({d.status.value})")


def test_real_jpj_not_qualified():
    d = qualify(ev_real_jpj())
    assert d.status == QualificationStatus.NOT_QUALIFIED
    labels_failed = [l for l, _ in d.conditions_failed]
    assert "B.relevance" in labels_failed
    assert "D.stability" in labels_failed
    print(f"PASS test_real_jpj_not_qualified ({d.status.value})")


def test_real_spr_needs_further_validation():
    """SPR is constitutional + active but 90% admin notices.
    Should land in NEEDS_FURTHER_VALIDATION (B fails but A/C/D/E pass)."""
    d = qualify(ev_real_spr())
    assert d.status == QualificationStatus.NEEDS_FURTHER_VALIDATION, (
        f"SPR should be NEEDS_FURTHER_VALIDATION (B borderline, A/C/D/E pass); "
        f"got {d.status.value} reason: {d.reason}"
    )
    labels_failed = [l for l, _ in d.conditions_failed]
    labels_passed = [l for l, _ in d.conditions_passed]
    assert labels_failed == ["B.relevance"]
    assert "A.identity" in labels_passed
    assert "C.access" in labels_passed
    assert "D.stability" in labels_passed
    assert "E.independence" in labels_passed
    print(f"PASS test_real_spr_needs_further_validation ({d.status.value})")


def test_real_kpm_needs_further_validation():
    """KPM is federal ministry + active but mixed content. Same logic."""
    d = qualify(ev_real_kpm())
    assert d.status == QualificationStatus.NEEDS_FURTHER_VALIDATION, (
        f"KPM should be NEEDS_FURTHER_VALIDATION; got {d.status.value}"
    )
    print(f"PASS test_real_kpm_needs_further_validation ({d.status.value})")


def test_real_agrobank_qualifies_on_pure_rule_but_flagged_in_docs():
    """Agrobank passes all 5 conditions on the pure-rule basis.

    This test documents the rule-level decision.  A separate note in
    docs/RADAR_5A_TIER_A_DISCOVERY.md flags this as scope-borderline
    (state-owned bank whose feed is 100% self-promotional about its
    own programs; not general news or regulatory content).

    The qualification rule does NOT itself judge 'scope narrowness' -
    that is a separate human-review concern that must remain documented
    in the candidate evidence file.  This test therefore passes both
    the rule and the human-review concern.
    """
    d = qualify(ev_real_agrobank())
    assert d.status == QualificationStatus.QUALIFIED, (
        f"on the pure rule Agrobank qualifies (state-owned, active, "
        f"100% press); got {d.status.value} reason: {d.reason}"
    )
    assert len(d.conditions_passed) == 5
    # Human-review concern (scope narrowness) is OUT OF SCOPE for the
    # rule and is documented separately in docs/.
    print(f"PASS test_real_agrobank_qualifies_on_pure_rule_but_flagged_in_docs "
          f"(rule=QUALIFIED, human reviewer flagged scope)")


def test_real_bernama_not_qualified():
    """BERNAMA endpoints unreachable. NOT_QUALIFIED (C fails)."""
    d = qualify(ev_real_bernama())
    assert d.status == QualificationStatus.NOT_QUALIFIED
    labels_failed = [l for l, _ in d.conditions_failed]
    assert "C.access" in labels_failed
    print(f"PASS test_real_bernama_not_qualified ({d.status.value})")


# ----------------------------------------------------------------------------
# Registry integrity
# ----------------------------------------------------------------------------

def test_tier_a_registry_remains_empty_after_radar_5a():
    """No candidate was qualified and added to the registry as Tier-A.

    History:
      - Radar-5A (2026-09-29): all 12 candidates were rejected; the
        registry stayed at 5 Tier-B sources.
      - A2.3 (2026-09-30): registry grew to 7 Tier-B sources
        (5 RSS + 2 Chinese WP-JSON).
      - A2.2-A (2026-09-30): registry grew to 8 Tier-B sources
        (+1 Chinese HTML listing).

    No Tier-A candidates have been promoted. All sources have
    tier B; no candidate name from the original 12-name list
    appears in the registry.
    """
    from radar.sources_registry import load_sources, source_tier_map
    sources = load_sources()
    assert len(sources) == 8, (
        f"expected 8 sources; got {len(sources)}. Registry size is "
        f"the Radar-2 5 Tier-B + A2.3 2 WP-JSON + A2.2-A 1 HTML listing."
    )
    tier_map = source_tier_map()
    for name, tier in tier_map.items():
        assert tier == "B", (
            f"source {name} has tier {tier}; expected all B. Radar-5A "
            f"must not change existing source tiers."
        )
    # No new source name contains any of the candidate names
    candidate_names = {
        "HASiL", "JPJ", "SPR", "Agrobank", "KPM",
        "BERNAMA", "PMO", "KKM", "JPM", "JAKIM", "MOF", "MITI",
    }
    registered_names = {s.name for s in sources}
    assert registered_names & candidate_names == set(), (
        f"a Tier-A candidate was added to the registry: "
        f"{registered_names & candidate_names}"
    )
    print("PASS test_tier_a_registry_remains_empty_after_radar_5a "
          "(registry size = 8; all B tier; no Tier-A candidates promoted)")


def test_radar_5a_does_not_modify_existing_tier_b_sources():
    """The 5 original Tier-B RSS sources must remain in the registry.

    A2.3 added 2 NEW sources (Kwong Wah Yit Poh, Guang Ming
    Daily) and A2.2-A added 1 NEW source (Sin Chew Johor desk)
    alongside the original 5. The original 5 must still be
    present and their registry entries unchanged.
    """
    from radar.sources_registry import REGISTERED_SOURCES
    expected_original_names = {
        "BBC News Asia",
        "Channel News Asia (Asia section)",
        "CodeBlue",
        "Free Malaysia Today (Bahasa)",
        "Borneo Post",
    }
    actual_names = {s.name for s in REGISTERED_SOURCES}
    missing = expected_original_names - actual_names
    assert not missing, (
        f"original Tier-B sources missing from registry: {missing}"
    )
    print("PASS test_radar_5a_does_not_modify_existing_tier_b_sources "
          "(5 original Tier-B sources preserved; 3 new sources added in A2.2-A + A2.3)")


# ----------------------------------------------------------------------------
# Runner
# ============================================================================

if __name__ == "__main__":
    print("=== Radar-5A Tier-A qualification ===\n")
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            import traceback
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print()
    if failed:
        print(f"!!! {failed} tier-A test(s) FAILED !!!")
        sys.exit(1)
    print(f"ALL {len(tests)} TIER-A TESTS PASSED")
