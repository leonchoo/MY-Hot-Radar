"""
A1 — Cross-language dedup test fixtures.

Reference: ``docs/CHINESE_DEDUP_A1_IMPLEMENTATION.md`` and
``docs/CHINESE_SOURCE_INTEGRATION_DESIGN_AUDIT.md`` §9.5.

These tests verify the deterministic Chinese place-name alias map
introduced in A1. The alias map is applied to a COPY of the input
text before entity extraction — the original title / content is
never mutated. Existing English / Malay / Chinese paths that do not
contain CJK characters are bit-identical to before A1.

Required fixture sets (per Audit §9.5):

  A. Cross-language positive ×4 — same event, different languages,
     should merge into 1 topic.

  B. Cross-language negative ×4 — different events even when sharing
     a place, must NOT merge. This is the false-merge gate.

  C. Single-language regression ×5 — existing English / Malay /
     Chinese behavior must NOT regress.

Each test is deterministic. No network. No fixture files. Each
fixture uses the in-process Radar library directly. Test sizes are
tiny; the suite runs in milliseconds.

The runner block at the bottom supports both ``python -m`` and
direct import. Per existing test conventions in this repo
(``radar/tests/test_dedup.py`` style).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from radar.dedup import cluster
from radar.models import (
    Category,
    Language,
    SourceType,
    Story,
)
from radar.normalize import (
    _apply_aliases,
    _ZH_TO_CANONICAL,
    _ZH_TO_CANONICAL_VERSION,
    entity_overlap,
    extract_entities,
    token_jaccard,
)


# ============================================================================
# Test helpers
# ============================================================================

def _story(id_, title, *, source="TestSource", lang=Language.EN,
           url=None, category=None):
    """Build a Story for cluster() testing."""
    return Story(
        id=id_,
        title=title,
        summary="",
        url=url or f"https://{source}.example/{abs(hash(title + id_)) % 9999}",
        source=source,
        source_type=SourceType.NEWS_SITE,
        published_at="2026-09-30T10:00:00+08:00",
        category=category or Category.MALAYSIA,
        language=lang,
        country="MY",
    )


# ============================================================================
# A. Cross-language positive ×4
# ============================================================================

def test_positive_zh_en_same_event_johor_charged():
    """Chinese + English: same event (Johor Bahru person charged) → 1 topic.

    Pre-A1: Chinese `新山男子被控` extracted `{}` (zero entities), so the
    cluster formed 2 topics (EN cluster + ZH singleton).
    Post-A1: Chinese `新山` → `johor_bahru` → entities {johor, bahru},
    overlapping with English `{johor, bahru}` → 1 topic.
    """
    stories = [
        _story("en", "Man charged in Johor Bahru", lang=Language.EN),
        _story("zh", "新山男子被控", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 1, (
        f"expected 1 cross-language topic for same event, got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )
    assert topics[0].mention_count == 2


def test_positive_zh_ms_same_event_johor_flood():
    """Chinese + Malay: same event (Johor flood) → 1 topic."""
    stories = [
        _story("ms", "Banjir di Johor Bahru", lang=Language.MS),
        _story("zh", "新山发生水灾", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 1, (
        f"expected 1 cross-language topic, got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )
    assert topics[0].mention_count == 2


def test_positive_zh_en_ms_three_languages_kl():
    """Chinese + English + Malay: same event (KL MRT disruption) → 1 topic."""
    stories = [
        _story("en", "KL MRT service suspended after signal fault", lang=Language.EN),
        _story("ms", "Perkhidmatan MRT KL tergendala", lang=Language.MS),
        _story("zh", "吉隆坡MRT服务中断", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 1, (
        f"expected 1 three-language topic, got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )
    assert topics[0].mention_count == 3


def test_positive_zh_en_johor_border_event():
    """Chinese + English: cross-border event (Johor Bahru checkpoint) → 1 topic.

    Audit §9.5 positive fixture #4: cross-language merge via Johor
    / Johor Bahru place aliases.

    The ZH title ``新山关卡升级`` (alias → ``johor_bahru``) produces
    entities {johor, bahru}, which overlaps with the EN title's
    {johor, bahru, checkpoint, upgrade, begins} by 2 entities —
    meeting ENTITY_MIN_OVERLAP. MERGES.
    """
    stories = [
        _story("en", "Johor Bahru checkpoint upgrade begins", lang=Language.EN),
        _story("zh", "新山关卡升级", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 1, (
        f"expected 1 Johor cross-language topic, got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )
    assert topics[0].mention_count == 2


# ============================================================================
# B. Cross-language negative ×4
# ============================================================================

def test_negative_same_place_different_event_johor():
    """Same place, different events in Johor → NO merge.

    Johor flood vs. Johor state assembly are both Johor-state stories
    but describe completely different events. The alias for ``柔佛``
    MUST NOT cause them to merge on the place-name alone — actors /
    actions / event-specific words must remain the dominant signal.
    """
    stories = [
        _story("a", "柔佛水灾疏散千人", lang=Language.ZH),
        _story("b", "柔佛州议会通过新法案", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 2, (
        f"different events in same state must NOT merge; got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )


def test_negative_same_state_different_event_johor():
    """Same state (Johor), different events → NO merge.

    Audit §9.5 negative fixture #3: ``柔佛州议会通过`` (Johor state
    assembly passes) ↔ ``柔佛水灾`` (Johor flood). Both stories are
    about Johor (alias → ``johor``). One is about state-legislative
    business, the other about a natural disaster. Different events at
    the same place must NOT merge.

    The alias for ``柔佛`` → ``johor`` means both stories share one
    entity (johor). The other tokens (议会 / 立法 / 通过 vs 水灾 / 疏散
    etc.) are CJK-only and invisible to ``extract_entities()``.
    Total entity overlap = 1. ``ENTITY_MIN_OVERLAP`` = 2 → NO merge.
    """
    stories = [
        _story("a", "柔佛州议会通过新法案", lang=Language.ZH),
        _story("b", "柔佛水灾疏散千人", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 2, (
        f"different events in same state must NOT merge; got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )


def test_negative_different_places_same_country_johor_bahru_vs_kl():
    """Different places, same country → NO merge.

    Audit §9.5 negative fixture #2: ``新山男子被控`` (Johor Bahru man
    charged) ↔ ``吉隆坡男子被控`` (KL man charged). Same country
    (Malaysia), different cities. Different places must NOT merge.

    Aliases: ``新山`` → ``johor_bahru``, ``吉隆坡`` → ``kuala_lumpur``.
    Entity overlap: 0 (no shared alias canonical forms). NO merge.
    """
    stories = [
        _story("a", "新山男子被控", lang=Language.ZH),
        _story("b", "吉隆坡男子被控", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 2, (
        f"different places must NOT merge; got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )


def test_negative_different_places_same_country_singapore():
    """Same country (Singapore), different places → NO merge.

    Audit §9.5 negative fixture #4: ``新加坡兀兰关卡`` ↔
    ``新加坡樟宜机场``. Both mention Singapore (alias → ``singapore``)
    but different places / facilities. Different places must NOT merge.

    Note: ``兀兰`` and ``樟宜`` are not aliased (per Audit §9.3 alias
    scope rule — only unambiguous place names). So entity overlap is
    just ``{singapore}`` (1 entity, below threshold 2) → NO merge.
    """
    stories = [
        _story("a", "新加坡兀兰关卡升级", lang=Language.ZH),
        _story("b", "新加坡樟宜机场启用", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 2, (
        f"different places must NOT merge; got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )


def test_negative_different_states_same_disaster_type():
    """Same disaster type, different states → NO merge.

    Audit §9.5 negative fixture #1: ``柔佛水灾`` (Johor flood) ↔
    ``马六甲水灾`` (Malacca flood). Both floods, different states.
    Same event TYPE but different events / different places.

    Note: ``马六甲`` is not in the alias map (per Audit §9.3 — the
    canonical alias list only covers high-traffic unambiguous place
    names). So ``柔佛水灾`` extracts `{johor}`, ``马六甲水灾``
    extracts `{}` (no alias). NO merge.
    """
    stories = [
        _story("a", "柔佛水灾疏散千人", lang=Language.ZH),
        _story("b", "马六甲水灾警报", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 2, (
        f"different places same-disaster must NOT merge; got {len(topics)}: "
        f"{[t.title for t in topics]}"
    )


# ============================================================================
# C. Single-language regression ×5
# ============================================================================

def test_regression_english_existing_behavior_unchanged():
    """English behavior unchanged: extract_entities short-circuit works.

    Pre-A1 extract_entities("Man charged in Johor Bahru") →
    {'man', 'charged', 'johor', 'bahru'}.
    Post-A1: _apply_aliases() short-circuits on no-CJK → text is
    unchanged → same entity set.
    """
    en = "Man charged in Johor Bahru"
    e = extract_entities(en)
    assert e == {"man", "charged", "johor", "bahru"}, (
        f"English entity extraction MUST be unchanged; got {sorted(e)}"
    )
    # The alias helper returns the SAME string object for non-CJK input.
    assert _apply_aliases(en) == en


def test_regression_malay_existing_behavior_unchanged():
    """Malay behavior unchanged."""
    ms = "Banjir di Johor Bahru"
    e = extract_entities(ms)
    assert e == {"banjir", "johor", "bahru", "di"}, (
        f"Malay entity extraction MUST be unchanged; got {sorted(e)}"
    )
    assert _apply_aliases(ms) == ms


def test_regression_chinese_only_no_alias_match_does_not_merge():
    """Two Chinese-only stories with NO aliased place shared → 2 topics.

    This proves the alias map does NOT create any new Chinese-only
    merge paths. Place-name aliasing only takes effect when an aliased
    place name appears in the text.
    """
    stories = [
        _story("a", "男子被控欺骗罪", lang=Language.ZH),
        _story("b", "女子卷入商业纠纷", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 2, (
        f"no shared place → no merge; got {len(topics)} topics"
    )


def test_regression_rts_fixture_still_merges():
    """The Audit §6.1 RTS fixture still merges across languages.

    Pre-A1 and post-A1: RTS event (with shared ASCII keyword) must
    still merge correctly. The A1 alias map MUST NOT regress this.
    """
    stories = [
        _story("en", "Malaysia announces new RTS measures", lang=Language.EN),
        _story("ms", "Malaysia umum langkah baharu RTS", lang=Language.MS),
        _story("zh", "马来西亚宣布新的RTS措施", lang=Language.ZH),
    ]
    topics, _ = cluster(stories)
    assert len(topics) == 1, (
        f"RTS fixture must still merge across all 3 languages; got {len(topics)}"
    )
    assert topics[0].mention_count == 3


def test_regression_crocodile_pandan_false_merge_preserved():
    """Known false-merge pair (Crocodile / Pandan Reservoir) preserved.

    This pair already merged in the pre-A1 code (Audit §6.1 / §9.1).
    A1 must NOT change that behavior (it could regress in either
    direction, both of which are bad). If the test fails, the alias
    map has accidentally widened or narrowed the existing false-merge
    landscape.
    """
    stories = [
        _story("a", "Crocodile spotted at Pandan Reservoir", lang=Language.EN),
        _story("b", "Pandan Reservoir water level rising", lang=Language.EN),
    ]
    topics, _ = cluster(stories)
    # Pre-A1: these merged (false-merge). Post-A1: same behavior
    # preserved. If a future A* wants to fix this, it must be a
    # SEPARATE batch with its own false-merge-protection rules.
    assert len(topics) == 1, (
        f"Crocodile/Pandan pair must keep its pre-A1 behavior "
        f"(they currently merge); got {len(topics)} topics — "
        f"this is a regression in A1 if it changed."
    )


# ============================================================================
# D. Hard-contract tests on alias normalization itself
# ============================================================================

def test_contract_original_text_not_mutated():
    """Caller string is never mutated by _apply_aliases."""
    zh = "新山男子被控"
    snapshot_bytes = id(zh)
    snapshot_text = str(zh)
    result = _apply_aliases(zh)
    # Original object unchanged
    assert str(zh) == snapshot_text, "alias substitution MUST NOT mutate input"
    assert id(zh) == snapshot_bytes, "alias substitution MUST NOT replace input object"
    # Result is a different string object
    assert result != zh, "alias result must differ from input"
    assert result == "johor_bahru 男子被控"


def test_contract_apply_aliases_idempotent():
    """Applying _apply_aliases twice is the same as applying once."""
    zh = "柔佛新山关卡升级"
    once = _apply_aliases(zh)
    twice = _apply_aliases(once)
    assert once == twice, f"alias substitution must be idempotent; once={once!r} twice={twice!r}"


def test_contract_short_circuit_no_cjk():
    """Non-CJK text passes through _apply_aliases untouched."""
    cases = [
        "Malaysia announces new RTS measures",
        "Banjir di Johor Bahru",
        "",  # empty
        "Plain ASCII title",
        "Mixed-with-numbers 1234",
    ]
    for s in cases:
        assert _apply_aliases(s) == s, f"non-CJK text must be untouched: {s!r}"


def test_contract_alias_map_is_complete():
    """All alias keys are listed in the Audit §9.5 design doc.

    This test fails if someone adds an alias without updating the
    documented list. Use it as a gate for additions.
    """
    expected = {
        "马来西亚", "新加坡", "吉隆坡",
        "柔佛", "新山",
        "马新", "新马",
    }
    actual = set(_ZH_TO_CANONICAL.keys())
    assert actual == expected, (
        f"alias map drift detected. "
        f"Expected (from docs/CHINESE_SOURCE_INTEGRATION_DESIGN_AUDIT.md "
        f"§7.6 + §13.2): {expected}; got: {actual}. "
        f"If a new alias is intentional, update this test AND the "
        f"implementation report."
    )


def test_contract_alias_version_pinned():
    """Alias version is pinned. Update this test when adding v2."""
    assert _ZH_TO_CANONICAL_VERSION == "phase-chinese-1-integration-v1"


def test_contract_alias_canonical_forms_ascii_only():
    """Every alias canonical form is ASCII-only.

    This guards against accidentally introducing a non-ASCII canonical
    form (which would break the existing entity-extraction regex).
    """
    for zh, canonical in _ZH_TO_CANONICAL.items():
        assert all(ord(c) < 128 for c in canonical), (
            f"alias canonical form must be ASCII: {zh!r} -> {canonical!r}"
        )
        assert canonical == canonical.lower(), (
            f"alias canonical form must be lowercase: {zh!r} -> {canonical!r}"
        )


# ============================================================================
# Runner
# ============================================================================

def _run_all() -> int:
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
        return 1
    print(f"ALL {len(test_funcs)} CJK DEDUP A1 TESTS PASSED")
    return 0


def _should_run_main():
    """Return True only when this file is invoked as a script.

    Pytest imports the module by its full dotted name, NOT ``__main__``,
    so the conventional ``if __name__ == "__main__":`` check correctly
    skips under pytest. When invoked as ``python -m
    radar.tests.test_dedup_cjk`` the module name is the dotted name, so
    we additionally check that ``sys.argv[0]`` matches this file.
    """
    import os, sys
    if __name__ != "__main__":
        return False
    this_file = os.path.abspath(__file__)
    argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ""
    return argv0 == this_file


if _should_run_main():
    import sys as _sys
    _sys.exit(_run_all())