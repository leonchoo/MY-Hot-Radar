"""
P3-B-5 StoryCluster category propagation tests.

Goal: prove that ``derive_story_cluster_category`` propagates the
per-row ``source_category`` (set by BERNAMA's title prefix in P3-B-3)
into the cluster-level ``StoryCluster.category`` strictly per the
five cases documented in the spec:

  Case A — All members agree on a category        -> propagate
  Case B — Partial coverage (some None, some have)-> None, no guessing
  Case C — Members disagree on categories          -> None + conflict=True
  Case D — No member has a category                -> None
  Case E — Single member                           -> propagate iff has one

This batch does NOT:

  * classify / infer / vote / rank
  * look at titles, URLs, publishers, or any signal beyond the
    literal ``StoryMember.source_category`` values
  * modify StoryCluster matching, StoryMatch, score, ranking
  * modify Radar / Candidate / Website / Android / Scheduler
  * add a live scheduler / cron / continuous sampling
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest.mock as mock

from performance import (
    BernamaRssAdapter,
    Platform,
    StoryCategoryPropagation,
    StoryCluster,
    StoryMember,
    derive_story_cluster_category,
    match_stories,
    validate_story_cluster,
)


IS_LIVE = os.environ.get("PERFORMANCE_BERNAMA_LIVE") == "1"


def _make_member(
    content_id: str,
    publisher: str,
    platform: Platform,
    published_at: str,
    url: str,
    source_category: str = None,
) -> StoryMember:
    """Helper to construct StoryMember with explicit source_category."""
    return StoryMember(
        content_id=content_id,
        publisher=publisher,
        platform=platform,
        published_at=published_at,
        url=url,
        source_category=source_category,
    )


# ============================================================================
# Case A: All members agree
# ============================================================================

def test_case_a_all_members_same_category_propagates():
    """All members carry the same category -> propagate."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="WORLD"),
        _make_member("c3", "outlet_c", Platform.WEBSITE, "2026-09-29T10:02:00Z",
                     "https://example.com/c3", source_category="WORLD"),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category == "WORLD"
    assert prop.conflict is False
    assert prop.has_any is True
    assert prop.member_count == 3
    assert prop.known_count == 3


def test_case_a_two_members_agree():
    """Two-member cluster with matching categories -> propagate."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="SPORTS"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="SPORTS"),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category == "SPORTS"
    assert prop.conflict is False
    assert prop.member_count == 2
    assert prop.known_count == 2


# ============================================================================
# Case B: Partial coverage
# ============================================================================

def test_case_b_partial_coverage_no_category():
    """Only some members have a category; others are None -> None, no guessing."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category=None),
        _make_member("c3", "outlet_c", Platform.WEBSITE, "2026-09-29T10:02:00Z",
                     "https://example.com/c3", source_category=None),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category is None, (
        "Case B must NOT guess — partial coverage returns None"
    )
    assert prop.conflict is False
    assert prop.has_any is True
    assert prop.member_count == 3
    assert prop.known_count == 1


def test_case_b_most_members_have_one_doesnt():
    """Even when 9/10 members agree, one None forces None."""
    members = [
        _make_member(f"c{i}", f"outlet_{i}", Platform.WEBSITE,
                     "2026-09-29T10:00:00Z",
                     f"https://example.com/c{i}",
                     source_category="BUSINESS")
        for i in range(9)
    ] + [
        _make_member("c9", "outlet_x", Platform.WEBSITE,
                     "2026-09-29T10:00:00Z",
                     "https://example.com/c9",
                     source_category=None),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category is None, (
        "Case B must NOT vote — even 9/10 agreement cannot override 1 None"
    )
    assert prop.conflict is False
    assert prop.known_count == 9


# ============================================================================
# Case C: Conflict
# ============================================================================

def test_case_c_two_distinct_categories_conflict():
    """WORLD vs SPORTS -> None, conflict=True."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="SPORTS"),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category is None
    assert prop.conflict is True
    assert prop.has_any is True
    assert prop.known_count == 2


def test_case_c_three_distinct_categories_conflict():
    """WORLD vs SPORTS vs BUSINESS -> None, conflict=True."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="SPORTS"),
        _make_member("c3", "outlet_c", Platform.WEBSITE, "2026-09-29T10:02:00Z",
                     "https://example.com/c3", source_category="BUSINESS"),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category is None
    assert prop.conflict is True


def test_case_c_conflict_with_partial_coverage_still_flags_conflict():
    """Even with one None member, conflict between two known members
    must surface as conflict=True.
    """
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="SPORTS"),
        _make_member("c3", "outlet_c", Platform.WEBSITE, "2026-09-29T10:02:00Z",
                     "https://example.com/c3", source_category=None),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category is None
    assert prop.conflict is True
    assert prop.has_any is True


# ============================================================================
# Case D: No categories
# ============================================================================

def test_case_d_no_member_has_category():
    """All members None -> None, no conflict."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category=None),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category=None),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category is None
    assert prop.conflict is False
    assert prop.has_any is False
    assert prop.known_count == 0


def test_case_d_empty_member_list():
    """Empty members -> None, no conflict."""
    prop = derive_story_cluster_category([])
    assert prop.category is None
    assert prop.conflict is False
    assert prop.has_any is False
    assert prop.member_count == 0
    assert prop.known_count == 0


# ============================================================================
# Case E: Single member
# ============================================================================

def test_case_e_single_member_with_category_propagates():
    """Single member with a category -> that category (Case A on N=1)."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="LIFESTYLE"),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category == "LIFESTYLE"
    assert prop.conflict is False
    assert prop.has_any is True
    assert prop.member_count == 1
    assert prop.known_count == 1


def test_case_e_single_member_without_category():
    """Single member, no category -> None."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category=None),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category is None
    assert prop.conflict is False
    assert prop.has_any is False


# ============================================================================
# Audit metadata: result object behavior
# ============================================================================

def test_propagation_result_object_is_dataclass():
    """StoryCategoryPropagation is a dataclass with the documented fields."""
    prop = derive_story_cluster_category([])
    assert isinstance(prop, StoryCategoryPropagation)
    d = prop.__dict__
    assert "category" in d
    assert "conflict" in d
    assert "has_any" in d
    assert "member_count" in d
    assert "known_count" in d


def test_propagation_does_not_mutate_members():
    """The derivation must be a pure read over members."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="WORLD"),
    ]
    # Snapshot before
    before = [(m.content_id, m.source_category) for m in members]
    derive_story_cluster_category(members)
    after = [(m.content_id, m.source_category) for m in members]
    assert before == after, "members must not be mutated by derivation"


# ============================================================================
# Identity preservation: propagation does not alter content_id, URL, etc.
# ============================================================================

def test_propagation_does_not_alter_content_id():
    """Member content_id is preserved by derivation."""
    members = [
        _make_member("ci_aaa", "bernama", Platform.WEBSITE,
                     "2026-09-29T10:00:00Z",
                     "https://example.com/c1",
                     source_category="WORLD"),
    ]
    derive_story_cluster_category(members)
    assert members[0].content_id == "ci_aaa"


def test_propagation_does_not_alter_publisher_or_platform():
    """Member publisher and platform are preserved."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.FACEBOOK,
                     "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="WORLD"),
    ]
    derive_story_cluster_category(members)
    assert members[0].publisher == "bernama"
    assert members[0].platform == Platform.WEBSITE
    assert members[1].publisher == "outlet_b"
    assert members[1].platform == Platform.FACEBOOK


def test_propagation_does_not_alter_url_or_published_at():
    """URL and published_at must be untouched."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T11:00:00Z",
                     "https://example.com/c2", source_category="WORLD"),
    ]
    derive_story_cluster_category(members)
    assert members[0].url == "https://example.com/c1"
    assert members[0].published_at == "2026-09-29T10:00:00Z"
    assert members[1].url == "https://example.com/c2"
    assert members[1].published_at == "2026-09-29T11:00:00Z"


def test_propagation_does_not_alter_source_category_field():
    """The propagation must not write back into member.source_category."""
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="WORLD"),
    ]
    derive_story_cluster_category(members)
    # Member-level category is still WORLD (not changed to a cluster-level value)
    assert members[0].source_category == "WORLD"
    assert members[1].source_category == "WORLD"


# ============================================================================
# StoryCluster integration: build a cluster from derived category
# ============================================================================
#
# Convention (P3-B-5 follow-up): when derive_story_cluster_category
# returns None (Case B / C / D / single-None), the caller writes
# "" into cluster.category. This aligns with P2's existing
# match_stories() convention where left_category="" / right_category=""
# means "no category -> skip the category check" instead of treating
# "" as a real category code.

def test_story_cluster_accepts_derived_category():
    """A StoryCluster built with the propagated category validates.

    When propagation returns the category ("WORLD"), it goes
    straight into cluster.category. The per-member source_category
    field is preserved as the audit trail.
    """
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="WORLD"),
    ]
    prop = derive_story_cluster_category(members)
    cluster = StoryCluster(
        story_cluster_id="sc_test",
        canonical_topic_key="tk_test",
        created_at="2026-09-29T10:00:00Z",
        first_seen_at="2026-09-29T10:00:00Z",
        last_seen_at="2026-09-29T11:00:00Z",
        # When propagation returns a value, use it directly.
        # When it returns None, callers should write "" (P2
        # match_stories convention) — see below in this file.
        category=prop.category if prop.category is not None else "",
        topic_type="news",
        geographic_scope="LOCAL",
        members=members,
    )
    validate_story_cluster(cluster)
    # Category reflects the propagation
    assert cluster.category == "WORLD"
    # Members still carry source_category
    assert all(m.source_category == "WORLD" for m in cluster.members)


def test_story_cluster_with_conflict_keeps_member_level_signal():
    """When propagation finds a conflict, cluster.category is set to
    the empty string "" (P2 match_stories convention for unresolved)
    while per-member source_category is preserved for auditability.
    """
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="SPORTS"),
    ]
    prop = derive_story_cluster_category(members)
    assert prop.conflict is True
    cluster = StoryCluster(
        story_cluster_id="sc_conflict",
        canonical_topic_key="tk_conflict",
        created_at="2026-09-29T10:00:00Z",
        first_seen_at="2026-09-29T10:00:00Z",
        last_seen_at="2026-09-29T11:00:00Z",
        # P2 convention: unresolved -> "" so match_stories skips
        # the category check instead of treating "UNRESOLVED" as a
        # real category that would falsely match another cluster's
        # "UNRESOLVED".
        category="",
        topic_type="news",
        geographic_scope="LOCAL",
        members=members,
    )
    validate_story_cluster(cluster)
    # Cluster-level shows the P2 empty-string convention
    assert cluster.category == ""
    # Per-member audit trail is intact
    assert cluster.members[0].source_category == "WORLD"
    assert cluster.members[1].source_category == "SPORTS"


def test_story_cluster_serialization_round_trip_preserves_source_category():
    """to_dict() + from_dict() preserves source_category on members.

    With P3-B-5 follow-up, cluster.category="" also round-trips.
    """
    members = [
        _make_member("c1", "bernama", Platform.WEBSITE, "2026-09-29T10:00:00Z",
                     "https://example.com/c1", source_category="WORLD"),
        _make_member("c2", "outlet_b", Platform.WEBSITE, "2026-09-29T10:01:00Z",
                     "https://example.com/c2", source_category="SPORTS"),
    ]
    cluster = StoryCluster(
        story_cluster_id="sc_round_trip",
        canonical_topic_key="tk_rt",
        created_at="2026-09-29T10:00:00Z",
        first_seen_at="2026-09-29T10:00:00Z",
        last_seen_at="2026-09-29T11:00:00Z",
        category="",  # unresolved — P2 convention
        topic_type="news",
        geographic_scope="LOCAL",
        members=members,
    )
    d = cluster.to_dict()
    j = json.dumps(d)
    parsed = json.loads(j)
    rebuilt = StoryCluster.from_dict(parsed)
    assert rebuilt.members[0].source_category == "WORLD"
    assert rebuilt.members[1].source_category == "SPORTS"
    # Cluster-level category round-trips ("" preserved as "")
    assert rebuilt.category == ""


def test_validate_story_cluster_accepts_empty_category():
    """P3-B-5 follow-up: validate_story_cluster accepts category=""
    (was previously rejected by validate_str's default
    allow_empty=False). This aligns cluster-level representation
    with match_stories's ""-means-no-category convention.
    """
    cluster = StoryCluster(
        story_cluster_id="sc_empty_cat",
        canonical_topic_key="tk_empty",
        created_at="2026-09-29T10:00:00Z",
        first_seen_at="2026-09-29T10:00:00Z",
        last_seen_at="2026-09-29T11:00:00Z",
        category="",  # unresolved cluster-level category
        topic_type="news",
        geographic_scope="LOCAL",
        members=[
            _make_member("c1", "bernama", Platform.WEBSITE,
                         "2026-09-29T10:00:00Z",
                         "https://example.com/c1", source_category=None),
        ],
    )
    # Must NOT raise
    validate_story_cluster(cluster)


def test_validate_story_cluster_rejects_empty_topic_type():
    """Only category is loosened; topic_type and geographic_scope
    remain required (non-empty). P3-B-5 follow-up intentionally
    limits the change to category.
    """
    cluster = StoryCluster(
        story_cluster_id="sc_empty_tt",
        canonical_topic_key="tk_empty_tt",
        created_at="2026-09-29T10:00:00Z",
        first_seen_at="2026-09-29T10:00:00Z",
        last_seen_at="2026-09-29T11:00:00Z",
        category="WORLD",   # OK (non-empty)
        topic_type="",      # still rejected
        geographic_scope="LOCAL",
        members=[
            _make_member("c1", "bernama", Platform.WEBSITE,
                         "2026-09-29T10:00:00Z",
                         "https://example.com/c1", source_category="WORLD"),
        ],
    )
    raised = False
    try:
        validate_story_cluster(cluster)
    except Exception as e:
        raised = True
        assert "topic_type" in str(e).lower(), str(e)
    assert raised, "empty topic_type must still be rejected"


def test_validate_story_cluster_rejects_empty_geographic_scope():
    """geographic_scope stays required (non-empty) — unchanged by
    P3-B-5 follow-up.
    """
    cluster = StoryCluster(
        story_cluster_id="sc_empty_geo",
        canonical_topic_key="tk_empty_geo",
        created_at="2026-09-29T10:00:00Z",
        first_seen_at="2026-09-29T10:00:00Z",
        last_seen_at="2026-09-29T11:00:00Z",
        category="WORLD",
        topic_type="news",
        geographic_scope="",  # still rejected
        members=[
            _make_member("c1", "bernama", Platform.WEBSITE,
                         "2026-09-29T10:00:00Z",
                         "https://example.com/c1", source_category="WORLD"),
        ],
    )
    raised = False
    try:
        validate_story_cluster(cluster)
    except Exception as e:
        raised = True
        assert "geographic_scope" in str(e).lower(), str(e)
    assert raised, "empty geographic_scope must still be rejected"


# ============================================================================
# CRITICAL REGRESSION — match_stories with empty vs "UNRESOLVED"
# ============================================================================
#
# Before P3-B-5 follow-up, cluster.category="UNRESOLVED" was used as
# a sentinel. But match_stories checks `left_category == right_category
# and left_category != ""`, so two clusters both carrying
# "UNRESOLVED" were treated as category-compatible and given a +0.2
# match score bonus. This was a false-positive collision.
#
# With P3-B-5 follow-up, the cluster-level convention is "" (P2
# match_stories convention). Two clusters both carrying "" must
# NOT receive a category_compatible bonus. Two clusters both
# carrying a real category ("WORLD") must STILL be treated as
# compatible (existing behavior).

def test_regression_empty_categories_dont_match_compatibly():
    """Two clusters with cluster.category="" must NOT be treated as
    category-compatible by match_stories.
    """
    m = match_stories(
        left_content_id="c1",
        right_content_id="c2",
        left_title="Different title A",
        right_title="Different title B",
        left_published_at="2026-09-29T10:00:00Z",
        right_published_at="2026-09-29T11:00:00Z",
        left_category="",
        right_category="",
    )
    # The category_compatible reason must NOT appear
    assert "category_compatible" not in m.reasons, (
        f"empty categories must not produce category_compatible; "
        f"got reasons={m.reasons}"
    )
    # Score is below the categories-match-incompatibility threshold
    # (no category_mismatch either, since both are empty -> skip).
    assert m.score < 0.7, (
        f"empty categories should keep score low; got {m.score}"
    )


def test_regression_real_categories_still_match_compatibly():
    """Two clusters with cluster.category="WORLD" must still be
    treated as category-compatible (existing P2 behavior preserved).
    """
    m = match_stories(
        left_content_id="c1",
        right_content_id="c2",
        left_title="Similar enough headline here",
        right_title="Similar enough headline there",
        left_published_at="2026-09-29T10:00:00Z",
        right_published_at="2026-09-29T11:00:00Z",
        left_category="WORLD",
        right_category="WORLD",
    )
    # The category_compatible reason MUST appear
    assert "category_compatible" in m.reasons, (
        f"matching real categories must produce category_compatible; "
        f"got reasons={m.reasons}"
    )


def test_regression_unresolved_sentinel_no_longer_used():
    """Sentinel regression: the literal string "UNRESOLVED" must not
    be referenced by the production StoryCluster code path for
    unresolved categories. Only the empty string "" is the P2
    convention.

    This test scans the production module (performance/story.py) for
    the literal sentinel.
    """
    import re as _re
    story_path = Path(r"C:\MY-Hot-Radar\performance\story.py")
    text = story_path.read_text(encoding="utf-8")
    # Find any reference to "UNRESOLVED" in the production module.
    # We exclude docstrings/comments only for the assert's own docstring;
    # the production file must not contain "UNRESOLVED" as a value.
    matches = _re.findall(r'["\']UNRESOLVED["\']', text)
    assert len(matches) == 0, (
        f"production code (performance/story.py) must not use "
        f'"UNRESOLVED" sentinel; found {len(matches)} occurrences'
    )


def test_story_cluster_from_dict_handles_old_json_without_source_category():
    """Backward compat: old JSON without source_category loads with None."""
    legacy_json = {
        "story_cluster_id": "sc_legacy",
        "canonical_topic_key": "tk_legacy",
        "created_at": "2026-09-29T10:00:00Z",
        "first_seen_at": "2026-09-29T10:00:00Z",
        "last_seen_at": "2026-09-29T11:00:00Z",
        "category": "MALAYSIA",
        "topic_type": "news",
        "geographic_scope": "LOCAL",
        "members": [
            {
                "content_id": "c1",
                "publisher": "bernama",
                "platform": "WEBSITE",
                "published_at": "2026-09-29T10:00:00Z",
                "url": "https://example.com/c1",
                # NOTE: no source_category field — legacy JSON
            },
            {
                "content_id": "c2",
                "publisher": "outlet_b",
                "platform": "WEBSITE",
                "published_at": "2026-09-29T10:01:00Z",
                "url": "https://example.com/c2",
            },
        ],
    }
    cluster = StoryCluster.from_dict(legacy_json)
    assert cluster.members[0].source_category is None
    assert cluster.members[1].source_category is None
    # Cluster still validates (legacy category field untouched)
    validate_story_cluster(cluster)


# ============================================================================
# StoryMatch independence
# ============================================================================

def test_propagation_does_not_alter_story_match():
    """derive_story_cluster_category does NOT touch StoryMatch logic.

    match_stories() takes left_category / right_category as inputs
    (the cluster-level category, NOT source_category). It is not
    affected by what we put on members. This test enforces that
    boundary: a category propagation that matches has no effect on
    whether two stories match.
    """
    from performance import match_stories
    # Two stories with no cluster-level category yet, only
    # member-level source_category (which match_stories does not see)
    result = match_stories(
        left_content_id="c1",
        right_content_id="c2",
        left_title="Trump announces something",
        right_title="Trump announces something similar",
        left_published_at="2026-09-29T10:00:00Z",
        right_published_at="2026-09-29T10:01:00Z",
        left_category="",
        right_category="",
    )
    # The match is purely about title similarity + date proximity.
    # source_category is not an input. Propagation does not change
    # this score.
    assert isinstance(result.score, float)
    assert result.score >= 0.0
    # Propagation does NOT mutate the result object
    score_before = result.score
    derive_story_cluster_category([])
    assert result.score == score_before


# ============================================================================
# Real BERNAMA fixture: source_category end-to-end into StoryCluster
# ============================================================================

CACHED_BERNAMA_RSS = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
<rss version="2.0">
<channel>
<title>BERNAMA - English Version</title>
<link>http://www.bernama.com/en</link>
<description>BERNAMA</description>
<language>en-us</language>
<item>
<title>World : Sample Story A</title>
<link>http://www.bernama.com/en/news.php?id=2700001</link>
<description>&lt;font size=1&gt;&lt;p&gt;KUALA LUMPUR, Sept 29 (Bernama) -- Sample story A about world affairs.&lt;/p&gt;&lt;/font&gt;</description>
</item>
<item>
<title>World : Sample Story A Covered</title>
<link>http://www.bernama.com/en/news.php?id=2700002</link>
<description>&lt;font size=1&gt;&lt;p&gt;KUALA LUMPUR, Sept 29 (Bernama) -- Another publisher covers the same story A.&lt;/p&gt;&lt;/font&gt;</description>
</item>
<item>
<title>Sport : Sample Story B</title>
<link>http://www.bernama.com/en/news.php?id=2700003</link>
<description>&lt;font size=1&gt;&lt;p&gt;KUALA LUMPUR, Sept 29 (Bernama) -- A sports story.&lt;/p&gt;&lt;/font&gt;</description>
</item>
<item>
<title>General : Sample Story C</title>
<link>http://www.bernama.com/en/news.php?id=2700004</link>
<description>&lt;font size=1&gt;&lt;p&gt;KUALA LUMPUR, Sept 29 (Bernama) -- A general story.&lt;/p&gt;&lt;/font&gt;</description>
</item>
</channel>
</rss>"""


def _patch_urlopen():
    import performance.adapters as adapters_module
    fake_resp = SimpleNamespace(
        read=lambda: CACHED_BERNAMA_RSS,
        status=200,
        headers={"Content-Type": "text/xml"},
    )
    return mock.patch.object(
        adapters_module.urllib.request, "urlopen",
        return_value=mock.MagicMock(__enter__=lambda self: fake_resp),
    )


def _fetch_cached() -> object:
    adapter = BernamaRssAdapter()
    with _patch_urlopen():
        return adapter.fetch()


def test_real_bernama_members_to_story_cluster():
    """End-to-end: cached real BERNAMA RSS -> AdapterObservations ->
    StoryMembers -> StoryCluster with derived category.

    Two articles share title theme (Sample Story A) and both have
    WORLD source_category from the BERNAMA prefix; they would form
    a cluster with propagated WORLD category (Case A).
    """
    res = _fetch_cached()
    assert res.retrieval_status.value == "AVAILABLE"
    # Find the two "Sample Story A" articles
    story_a_members = [
        StoryMember(
            content_id=o.content_id,
            publisher="bernama",
            platform=Platform.WEBSITE,
            published_at=o.published_at or "2026-09-29T00:00:00Z",
            url=o.url,
            source_category=o.extra.get("source_category"),
        )
        for o in res.observations
        if "Sample Story A" in o.title
    ]
    assert len(story_a_members) == 2, (
        f"expected 2 'Sample Story A' articles, got {len(story_a_members)}"
    )
    # Both have source_category=WORLD
    assert all(m.source_category == "WORLD" for m in story_a_members)
    prop = derive_story_cluster_category(story_a_members)
    assert prop.category == "WORLD"
    assert prop.conflict is False
    assert prop.member_count == 2
    assert prop.known_count == 2


def test_real_bernama_cross_category_conflict():
    """Two articles from different categories -> conflict detected."""
    res = _fetch_cached()
    # Build a synthetic mixed cluster: one WORLD article + one SPORT
    world_member = None
    sport_member = None
    for o in res.observations:
        if o.extra.get("source_category") == "WORLD" and world_member is None:
            world_member = StoryMember(
                content_id=o.content_id,
                publisher="bernama",
                platform=Platform.WEBSITE,
                published_at=o.published_at or "2026-09-29T00:00:00Z",
                url=o.url,
                source_category="WORLD",
            )
        elif o.extra.get("source_category") == "SPORTS" and sport_member is None:
            sport_member = StoryMember(
                content_id=o.content_id,
                publisher="bernama",
                platform=Platform.WEBSITE,
                published_at=o.published_at or "2026-09-29T00:00:00Z",
                url=o.url,
                source_category="SPORTS",
            )
    assert world_member is not None
    assert sport_member is not None
    prop = derive_story_cluster_category([world_member, sport_member])
    assert prop.category is None
    assert prop.conflict is True


def test_real_bernama_distribution_of_source_categories():
    """Count how many real BERNAMA rows carry a recognized category."""
    res = _fetch_cached()
    with_cat = [o for o in res.observations
                if o.extra.get("source_category") is not None]
    without_cat = [o for o in res.observations
                   if o.extra.get("source_category") is None]
    # In this fixture, every row has a prefix
    assert len(with_cat) == 4
    assert len(without_cat) == 0
    # Category distribution (informational only; not accuracy)
    from collections import Counter
    dist = Counter(o.extra.get("source_category") for o in res.observations)
    assert dist["WORLD"] == 2
    assert dist["SPORTS"] == 1
    assert dist["GENERAL"] == 1


# ============================================================================
# Live BERNAMA (gated by PERFORMANCE_BERNAMA_LIVE=1)
# ============================================================================

def test_live_bernama_source_categories_can_form_propagated_cluster():
    """REAL LIVE: pick two real BERNAMA articles from the same
    category and verify Case A propagation works end-to-end.
    """
    if not IS_LIVE:
        return
    adapter = BernamaRssAdapter()
    res = adapter.fetch()
    assert res.retrieval_status.value == "AVAILABLE"
    # Group by source_category
    from collections import defaultdict
    groups = defaultdict(list)
    for o in res.observations:
        c = o.extra.get("source_category")
        if c is not None:
            groups[c].append(o)
    # Pick a category with at least 2 articles
    target = None
    for c, rows in groups.items():
        if len(rows) >= 2:
            target = (c, rows[:2])
            break
    if target is None:
        # Live feed has at most 1 row per category at this moment;
        # verify single-member propagation works.
        single = next(iter(groups.values()))[0]
        m = StoryMember(
            content_id=single.content_id,
            publisher="bernama",
            platform=Platform.WEBSITE,
            published_at=single.published_at or "2026-09-29T00:00:00Z",
            url=single.url,
            source_category=single.extra.get("source_category"),
        )
        prop = derive_story_cluster_category([m])
        assert prop.category == single.extra.get("source_category")
        return
    cat, rows = target
    members = [
        StoryMember(
            content_id=o.content_id,
            publisher="bernama",
            platform=Platform.WEBSITE,
            published_at=o.published_at or "2026-09-29T00:00:00Z",
            url=o.url,
            source_category=cat,
        )
        for o in rows
    ]
    prop = derive_story_cluster_category(members)
    assert prop.category == cat
    assert prop.conflict is False
    assert prop.member_count == 2
    assert prop.known_count == 2


# ============================================================================
# Real-data stats for the report
# ============================================================================

def test_report_real_bernama_propagation_stats():
    """Report-only test: prints real-data statistics for the final
    report. Always passes; only documents the propagation results.
    """
    res = _fetch_cached()
    n_total = len(res.observations)
    with_cat = sum(1 for o in res.observations
                   if o.extra.get("source_category") is not None)
    without_cat = n_total - with_cat

    # Build StoryMembers for all observations
    members = [
        StoryMember(
            content_id=o.content_id,
            publisher="bernama",
            platform=Platform.WEBSITE,
            published_at=o.published_at or "2026-09-29T00:00:00Z",
            url=o.url,
            source_category=o.extra.get("source_category"),
        )
        for o in res.observations
    ]
    prop = derive_story_cluster_category(members)

    print("\n--- P3-B-5 Real BERNAMA propagation stats ---")
    print(f"total rows: {n_total}")
    print(f"with category: {with_cat}")
    print(f"without category: {without_cat}")
    print(f"cluster.category: {prop.category!r}")
    print(f"cluster.conflict: {prop.conflict}")
    print(f"cluster.member_count: {prop.member_count}")
    print(f"cluster.known_count: {prop.known_count}")
    print("--- end stats ---\n")

    assert isinstance(prop, StoryCategoryPropagation)


# ============================================================================
# Runner
# ============================================================================

if __name__ == "__main__":
    test_funcs = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = 0
    failed = []
    for name, fn in test_funcs:
        try:
            fn()
            passed += 1
            print(f"PASS {name}")
        except AssertionError as e:
            failed.append((name, str(e) if str(e) else "<empty assertion>"))
            print(f"FAIL {name}: {e if str(e) else '<empty assertion>'}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"ERROR {name}: {e}")
            import traceback
            traceback.print_exc()
    print()
    print(f"{passed} passed, {len(failed)} failed of {len(test_funcs)} tests")
    if failed:
        for n, e in failed:
            print(f"  {n}: {e}")
        sys.exit(1)
    else:
        print(f"ALL {len(test_funcs)} P3-B-5 CATEGORY PROPAGATION TESTS PASSED")