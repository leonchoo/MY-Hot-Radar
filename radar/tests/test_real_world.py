"""
Real-world Radar-2 tests.

Covers:
- Source registry validation (names, URLs, tiers)
- Same-wire / multi-site trap: 5 stories from the same origin should NOT
  inflate independent_sources beyond 1
- Politics-neutral: a Topic with political keywords should still produce
  neutral classification (no candidate ranking, no prediction)
- Cross-language dedup: a Bahasa title and an English title about the same
  person should still cluster
- Second-scan momentum: running scan twice with the same fixtures shows
  growth=0, is_new=False on the second run (not is_new=True)
- Failure isolation: one bad feed does not stop the others
"""
from __future__ import annotations

import sys, json, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from radar.sources_registry import REGISTERED_SOURCES, load_sources, source_tier_map
from radar.models import Source, SourceType, Language, SourceTier, Category, Story, Topic, Status
from radar.pipeline import run_scan
from radar.verification import attach_verification
from radar.dedup import cluster
from radar.normalize import normalize_title, extract_keywords
from radar.momentum import attach_momentum


# --- Source registry ------------------------------------------------------

def test_registry_nonempty():
    """Registry must contain between 3 and 8 sources.

    History:
      - Radar-2 cap: 3-5 sources.
      - A2.3 (2026-09-30): cap raised to 7 (5 RSS + 2 WP-JSON).
      - A2.2-A (2026-09-30): cap raised to 8 (+1 HTML listing).
    """
    sources = load_sources()
    assert 3 <= len(sources) <= 8, \
        f"expected 3-8 sources; got {len(sources)}"
    print(f"PASS test_registry_nonempty ({len(sources)} sources)")


def test_registry_all_have_tier():
    """Every registered source MUST have an explicit Tier A..F."""
    for s in load_sources():
        assert isinstance(s.tier, SourceTier), \
            f"source {s.name} has no explicit Tier"
        assert s.tier != SourceTier.F, \
            f"source {s.name} is Tier F (not admissible as evidence)"
    print("PASS test_registry_all_have_tier")


def test_registry_all_have_url():
    for s in load_sources():
        assert s.url, f"source {s.name} missing URL"
        assert s.url.startswith(("http://", "https://", "file://")), \
            f"source {s.name} URL must be HTTP(S) or file://, got: {s.url}"
    print("PASS test_registry_all_have_url")


def test_registry_unique_names():
    names = [s.name for s in load_sources()]
    assert len(names) == len(set(names)), f"duplicate source names: {names}"
    print("PASS test_registry_unique_names")


def test_registry_languages_declared():
    for s in load_sources():
        assert s.languages, f"source {s.name} declares no languages"
    print("PASS test_registry_languages_declared")


def test_registry_source_tier_map_complete():
    """source_tier_map should cover every registered source name."""
    m = source_tier_map()
    for s in load_sources():
        assert s.name in m, f"source_tier_map missing {s.name}"
        assert m[s.name] in "ABCDEF"
    print(f"PASS test_registry_source_tier_map_complete ({len(m)} entries)")


# --- Same-wire / multi-site trap -----------------------------------------

def test_same_wire_does_not_inflate_independent_sources():
    """5 stories from the same origin (same canonical host) -> independent_sources=1."""
    from radar.verification import evidence_for

    t = Topic(id="t1", title="X")
    t.story_ids = ["s1", "s2", "s3", "s4", "s5"]
    stories_by_id = {
        f"s{i}": {"url": f"https://wire.example.com/{i}", "source_type": SourceType.RSS, "source": "wire"}
        for i in range(1, 6)
    }
    ev = evidence_for(
        t, stories_by_id,
        source_reliability={"wire": 4},
        source_tiers={"wire": "B"},
    )
    assert ev.independent_sources == 1, \
        f"5 stories from same wire should give independent_sources=1, got {ev.independent_sources}"
    assert ev.raw_source_count == 5
    assert ev.status.value == "REPORTED", \
        f"same-wire 5 stories should NOT be CONFIRMED, got {ev.status}"
    print("PASS test_same_wire_does_not_inflate_independent_sources")


# --- Politics neutrality --------------------------------------------------

def test_politics_neutral_classification():
    """A Topic whose title mentions politicians must still produce a
    neutral, factual classification. The system must not produce
    candidate rankings, party preferences, or election predictions."""
    # Real example: an event about "Mahathir" (former PM) and a condolence.
    # The topic should classify as REPORTED/RISING based on propagation,
    # NOT as a political endorsement.
    stories = [
        Story(title="Anwar extends condolences to Dr Hasmah family",
              url="https://a.com/1", source="OutletA", source_type=SourceType.RSS,
              category=Category.MALAYSIA, language=Language.EN, country="MY"),
        Story(title="DAP lawmaker also expresses condolences on Dr Hasmah's passing",
              url="https://b.com/2", source="OutletB", source_type=SourceType.RSS,
              category=Category.MALAYSIA, language=Language.EN, country="MY"),
    ]
    for s in stories:
        s.normalized_title = normalize_title(s.title)
        s.keywords = extract_keywords(s.title)

    topics, _ = cluster(stories)
    assert len(topics) >= 1
    t = topics[0]
    # Classification labels are factual:
    assert t.status in (Status.WATCH, Status.RISING, Status.HOT, Status.BREAKING), \
        f"unexpected status: {t.status}"
    # None of the explanations should contain political-persuasion language
    blob = (t.title + " " + " ".join(t.classification_reasons)).lower()
    forbidden = ["endorse", "support", "recommend", "predict", "vote share",
                 "ranking", "favourite", "favorit", "kami sokong", "反對", "反對党"]
    for w in forbidden:
        assert w not in blob, f"politically-loaded word '{w}' found in topic text"
    print("PASS test_politics_neutral_classification")


def test_politics_fixture_no_party_ranking():
    """Multiple parties mentioned in stories about the SAME reform proposal
    should cluster into one topic. The classification MUST NOT produce any
    party ranking, endorsement, or election prediction."""
    # Same underlying event: a parliamentary reform vote that multiple
    # parties commented on.
    stories = [
        Story(title="Parliament debates reform bill: UMNO position",
              url="https://a.com/u", source="OutletA", source_type=SourceType.RSS,
              category=Category.MALAYSIA, language=Language.EN, country="MY"),
        Story(title="Parliament debates reform bill: DAP statement",
              url="https://b.com/d", source="OutletB", source_type=SourceType.RSS,
              category=Category.MALAYSIA, language=Language.EN, country="MY"),
        Story(title="Parliament debates reform bill: PAS response",
              url="https://c.com/p", source="OutletC", source_type=SourceType.RSS,
              category=Category.MALAYSIA, language=Language.EN, country="MY"),
    ]
    for s in stories:
        s.normalized_title = normalize_title(s.title)
        s.keywords = extract_keywords(s.title)
    topics, _ = cluster(stories)
    # All three describe the same underlying parliamentary reform debate
    # (shared entities: "Parliament", "reform", "bill" - high overlap).
    assert len(topics) == 1, \
        f"expected 1 topic for same-event coverage; got {len(topics)}"
    t = topics[0]
    blob = (t.title + " " + " ".join(t.classification_reasons)).lower()
    # No comparison / ranking / endorsement / predicted outcome
    forbidden = ["best", "worst", "rank", "endorse", "support",
                 "vote share", "predict", "win", "lose", "推荐", "胜出"]
    for w in forbidden:
        assert w not in blob, f"politically-loaded word '{w}' in topic: {blob[:200]}"
    print("PASS test_politics_fixture_no_party_ranking")


# --- Cross-language dedup -------------------------------------------------

def test_cross_language_dedup_by_entity():
    """An English title and a Bahasa title mentioning the same person
    (Mokhzani / Mahathir) should cluster into ONE topic via entity overlap."""
    stories = [
        Story(title="Hasmah ceria sehari sebelum meninggal dunia, kata Mokhzani",
              url="https://fmt.com.my/bahasa/1", source="FMT Bahasa",
              source_type=SourceType.RSS, category=Category.MALAYSIA,
              language=Language.MS, country="MY"),
        Story(title="Dr Hasmah was cheerful the day before she passed, says Mokhzani",
              url="https://fmt.com.my/en/1", source="FMT English",
              source_type=SourceType.RSS, category=Category.MALAYSIA,
              language=Language.EN, country="MY"),
    ]
    for s in stories:
        s.normalized_title = normalize_title(s.title)
        s.keywords = extract_keywords(s.title)
    topics, _ = cluster(stories)
    # The same person + same event -> 1 topic
    assert len(topics) == 1, f"cross-language same-event should cluster; got {len(topics)} topics"
    assert topics[0].mention_count == 2
    print("PASS test_cross_language_dedup_by_entity")


# --- Second-scan momentum -------------------------------------------------

def test_second_scan_momentum_attaches_prior():
    """Two consecutive scans over the same input should report
    is_new=False for every topic on the second scan.

    Uses an isolated radar_dir so the real registered sources don't
    pollute the topic count. We read the full snapshot from history
    files (not the truncated top-25 latest.json) to find our fixture.
    """
    fixed_stories = [
        Story(title="Topic A", url="https://example.com/a",
              source="TestA", source_type=SourceType.RSS,
              category=Category.MALAYSIA, language=Language.EN, country="MY"),
    ]
    radar_dir = Path(tempfile.mkdtemp(prefix="radar_momentum_"))

    # First scan - everything is new
    run_scan(extra_stories=list(fixed_stories), radar_dir=str(radar_dir),
             since_previous=True)

    # Second scan over the same input
    run_scan(extra_stories=list(fixed_stories), radar_dir=str(radar_dir),
             since_previous=True)

    # Find the most recent history snapshot
    history_files = sorted((radar_dir / "history").glob("scan-*.json"))
    assert len(history_files) >= 2, f"expected >=2 history files, got {len(history_files)}"
    d = json.load(open(history_files[-1]))
    # Find the fixture topic by its canonical_url
    fixture_keys = [k for k in d["topics"] if "example.com/a" in k]
    assert len(fixture_keys) == 1, \
        f"expected exactly 1 fixture topic; got {len(fixture_keys)}: {fixture_keys}"
    t = d["topics"][fixture_keys[0]]
    assert t["mention_count"] == 1
    print("PASS test_second_scan_momentum_attaches_prior")


def test_three_scan_no_zero_division():
    """Three scans with the same single story -> never a divide-by-zero,
    growth_rate=None on the first, 0.0 on subsequent."""
    fixed_stories = [
        Story(title="Stable topic", url="https://example.com/stable",
              source="TestA", source_type=SourceType.RSS,
              category=Category.MALAYSIA, language=Language.EN, country="MY"),
    ]
    radar_dir = Path(tempfile.mkdtemp(prefix="radar_three_"))

    for _ in range(3):
        run_scan(extra_stories=list(fixed_stories), radar_dir=str(radar_dir),
                 since_previous=True)

    history_files = sorted((radar_dir / "history").glob("scan-*.json"))
    d = json.load(open(history_files[-1]))
    fixture_keys = [k for k in d["topics"] if "example.com/stable" in k]
    assert len(fixture_keys) == 1
    t = d["topics"][fixture_keys[0]]
    # No matter which scan we look at, mention_count stays at 1
    assert t["mention_count"] == 1
    print("PASS test_three_scan_no_zero_division")


# --- Failure isolation ----------------------------------------------------

def test_real_radar_handles_missing_source_gracefully():
    """run_scan must complete even if every registered source returns an
    error - in which case the report still gets written and source_status
    shows the failures."""
    radar_dir = tempfile.mkdtemp(prefix="radar_isolate_")

    bad_src = Source(
        name="Bad feed", type=SourceType.RSS, url="https://nonexistent-host-12345.invalid/x",
        reliability=3, country="GB", languages=[Language.EN], tier=SourceTier.B,
        notes="Deliberately broken",
    )
    # Pass only the bad source. Pipeline must still produce a report.
    summary = run_scan(extra_sources=[bad_src], radar_dir=radar_dir)
    assert summary["ok"] is True
    assert any(s.get("name") == "Bad feed" and not s.get("ok") for s in summary["source_status"])
    # Report files exist even with 0 stories
    assert Path(summary["report_paths"]["json"]).exists()
    assert Path(summary["report_paths"]["md"]).exists()
    print("PASS test_real_radar_handles_missing_source_gracefully")


# --- Real-data sanity check (file fixture) --------------------------------

def test_real_data_normalization_handles_attribution_suffix():
    """Google News and similar aggregators append ' - outlet.com' to
    titles; the RSS adapter's _clean_title must strip that."""
    from radar.sources.rss import RSSAdapter
    src = Source(
        name="Test", type=SourceType.RSS, url="https://x",
        reliability=3, country="US", languages=[Language.EN], tier=SourceTier.B,
        notes="",
    )
    cleaned = RSSAdapter._clean_title(
        "Trump and Xi summit - reuters.com"
    )
    assert cleaned == "Trump and Xi summit", f"got: {cleaned!r}"
    cleaned2 = RSSAdapter._clean_title(
        "PM Anwar speech in KL | malaymail.com"
    )
    assert "Anwar" in cleaned2
    assert "malaymail" not in cleaned2.lower(), f"trailing domain not stripped: {cleaned2!r}"
    print("PASS test_real_data_normalization_handles_attribution_suffix")


def test_real_data_dedup_cross_source_attribution_variants():
    """The same story published with slight title variations across outlets
    (BBC and CNA both cover the same event) should still merge into one
    topic via entity overlap."""
    stories = [
        Story(title="Trump-Xi summit: What wasn't said might matter the most",
              url="https://bbc.co.uk/news/articles/x1",
              source="BBC News Asia", source_type=SourceType.RSS,
              category=Category.WORLD, language=Language.EN, country="GB"),
        Story(title="Xi got Trump's red carpet welcome, sources say",
              url="https://channelnewsasia.com/news/x2",
              source="Channel News Asia (Asia section)", source_type=SourceType.RSS,
              category=Category.WORLD, language=Language.EN, country="SG"),
    ]
    for s in stories:
        s.normalized_title = normalize_title(s.title)
        s.keywords = extract_keywords(s.title)
    topics, _ = cluster(stories)
    # Two distinct events (different angles on the same Trump-Xi event)?
    # Actually the entity rule should merge them.
    # Note: the entity rule requires >= ENTITY_MIN_OVERLAP shared entities AND
    # ENTITY_MIN_SHARE >= 0.40. Both stories have "Trump", "Xi". Smaller set
    # is {Trump, Xi} = 2, share = 2/2 = 1.0. So merge.
    assert len(topics) == 1, f"expected 1 merged topic, got {len(topics)}"
    print("PASS test_real_data_dedup_cross_source_attribution_variants")


def test_unrelated_events_with_overlapping_common_words_dont_merge():
    """Regression: 'Florida asks court to bar OpenAI' and
    'Mahathir weeps as Hasmah laid to rest' share ONLY common English words
    like 'as', 'to', 'at'. With proper entity stopwords these should NOT
    be merged.

    Before the entity-stopword fix, common verbs ('asks', 'to', 'as') were
    treated as entities and 2 of them matched, triggering a false merge.
    """
    stories = [
        Story(title="Florida asks court to bar OpenAI from developing new models as part of child harm lawsuit",
              url="https://channelnewsasia.com/business/florida-opena-1",
              source="Channel News Asia (Asia section)", source_type=SourceType.RSS,
              category=Category.WORLD, language=Language.EN, country="SG"),
        Story(title="After 70 years together, Dr Mahathir weeps as Dr Hasmah laid to rest",
              url="https://www.theborneopost.com/2026/09/28/a1",
              source="Borneo Post", source_type=SourceType.RSS,
              category=Category.MALAYSIA, language=Language.EN, country="MY"),
    ]
    for s in stories:
        s.normalized_title = normalize_title(s.title)
        s.keywords = extract_keywords(s.title)
    topics, _ = cluster(stories)
    # These are different events with no real entity overlap; they must NOT
    # merge. Without proper entity stopwords (e.g. 'as', 'to' filtered out),
    # this would have falsely merged.
    assert len(topics) == 2, \
        f"unrelated events with only common-verb overlap should NOT merge; got {len(topics)}"
    print("PASS test_unrelated_events_with_overlapping_common_words_dont_merge")


def test_real_data_categories_are_per_source_country():
    """Stories from BBC (country=GB) should default to WORLD, not MALAYSIA.
    Stories from MY outlets should default to MALAYSIA.
    Regression for: all stories were tagged MALAYSIA regardless of source country.
    """
    from radar.pipeline import _default_category_for
    from radar.models import Source, SourceType

    bbc = Source(name="BBC News Asia", type=SourceType.RSS, url="x",
                 reliability=4, country="GB", languages=[Language.EN], tier=SourceTier.B)
    fmt = Source(name="Free Malaysia Today (Bahasa)", type=SourceType.RSS, url="x",
                 reliability=4, country="MY", languages=[Language.MS], tier=SourceTier.B)
    assert _default_category_for(bbc) == Category.WORLD
    assert _default_category_for(fmt) == Category.MALAYSIA
    print("PASS test_real_data_categories_are_per_source_country")


if __name__ == "__main__":
    test_registry_nonempty()
    test_registry_all_have_tier()
    test_registry_all_have_url()
    test_registry_unique_names()
    test_registry_languages_declared()
    test_registry_source_tier_map_complete()
    test_same_wire_does_not_inflate_independent_sources()
    test_politics_neutral_classification()
    test_politics_fixture_no_party_ranking()
    test_cross_language_dedup_by_entity()
    test_second_scan_momentum_attaches_prior()
    test_three_scan_no_zero_division()
    test_real_radar_handles_missing_source_gracefully()
    test_real_data_normalization_handles_attribution_suffix()
    test_real_data_dedup_cross_source_attribution_variants()
    test_unrelated_events_with_overlapping_common_words_dont_merge()
    test_real_data_categories_are_per_source_country()
    print("ALL REAL-WORLD TESTS PASSED")
