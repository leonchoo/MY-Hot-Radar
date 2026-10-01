"""
A2.8-R1 — Minimal Entity Guard regression tests.

Reference: ``docs/CHINESE_DEDUP_CHAIN_INVESTIGATION.md`` (t_d687fc entity bridge),
           ``docs/CHINESE_NORMALIZATION_ENTITY_AUDIT_A27.md`` (A2.7 audit),
           ``docs/CHINESE_DEDUP_ENTITY_GUARD_A28R1.md`` (this implementation).

This module pins the evidence-first minimal change:

  1. ``period`` and ``transition`` are added to ``_ENTITY_STOPWORDS`` because
     A2.5 chain investigation replay proved they were the first false bridge of
     t_d687fc (CNA ↔ Borneo Post via ``entity_overlap``).

  2. ``ENTITY_MIN_SHARE`` stays at 0.20 (A2.3.2 value). The A2.8 proposal to
     raise it to 0.25 was rejected because PH-Bersatu is already blocked at
     2/11 = 0.1818 < 0.20.

  3. A2.6 Candidate C (all-members match) cluster construction is preserved
     unchanged.

  4. ``man``, ``kata``, ``dr`` remain in the entity set (they are needed for
     legitimate same-source analyst merges and the Hasmat cross-language merge).

  5. A1 Chinese alias map (7 entries) is untouched.

Order-independence is documented as a known greedy union-find limitation, NOT
asserted as strict set-equality.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from radar.models import Story, Category, Language, SourceType
from radar.dedup import cluster, _is_strong_match
from radar.normalize import extract_entities, _ENTITY_STOPWORDS
import radar.thresholds as th


# ============================================================================
# Helper
# ============================================================================

def _story(id_, title, *, source='TestSource', lang=Language.EN, url=None,
           published_at='2026-09-30T10:00:00+00:00'):
    return Story(
        id=id_, title=title, summary='',
        url=url or f'https://{source}.example/{abs(hash(title+id_))%99999}',
        source=source, source_type=SourceType.NEWS_SITE,
        published_at=published_at,
        category=Category.MALAYSIA, language=lang, country='MY',
    )


# ============================================================================
# Test A — period filtered
# ============================================================================

def test_period_filtered():
    """period must not appear in entity set."""
    title = "Minimum wage increases during transition period"
    ents = extract_entities(title)
    assert 'period' not in ents, (
        f"Filter must remove 'period' from entities. Got: {sorted(ents)}"
    )
    print(f'  "period" filtered from {sorted(ents)}')


# ============================================================================
# Test B — transition filtered
# ============================================================================

def test_transition_filtered():
    """transition must not appear in entity set."""
    title = "The transition period of the policy ends today"
    ents = extract_entities(title)
    assert 'transition' not in ents, (
        f"Filter must remove 'transition' from entities. Got: {sorted(ents)}"
    )
    print(f'  "transition" filtered from {sorted(ents)}')


# ============================================================================
# Test C — man preserved
# ============================================================================

def test_man_preserved():
    """man must still appear in entity set (A1 regression test requires it)."""
    title = "Man charged in Johor Bahru court case"
    ents = extract_entities(title)
    assert 'man' in ents, (
        f"'man' must be preserved (A1 regression). Got: {sorted(ents)}"
    )
    print(f'  "man" preserved in {sorted(ents)}')


# ============================================================================
# Test D — kata preserved
# ============================================================================

def test_kata_preserved():
    """kata (MS analyst-says connector) must still appear in entity set."""
    title = "Hasrat Umno kekal kuasa utama, kata penganalisis"
    ents = extract_entities(title)
    assert 'kata' in ents, (
        f"'kata' must be preserved (FMT analyst merge). Got: {sorted(ents)}"
    )
    print(f'  "kata" preserved in {sorted(ents)}')


# ============================================================================
# Test E — dr preserved
# ============================================================================

def test_dr_preserved():
    """dr must still appear in entity set (Hasmat cross-language merge requires it)."""
    title = "Tun Dr Siti Hasmah receives award"
    ents = extract_entities(title)
    assert 'dr' in ents, (
        f"'dr' must be preserved (Hasmat ZH↔EN merge). Got: {sorted(ents)}"
    )
    print(f'  "dr" preserved in {sorted(ents)}')


# ============================================================================
# Test F — t_d687fc entity bridge removed
# ============================================================================

def test_t_d687fc_cna_borneo_no_merge():
    """t_d687fc CNA ↔ Borneo Post must NOT match (entity bridge blocked)."""
    cna = _story(
        "cna", "Retailers race to label or remove unmarked stock as beverage container return scheme's transition period ends",
        source="Channel News Asia (Asia section)", lang=Language.EN,
        url="https://www.channelnewsasia.com/singapore/bcrs-transition-ends-supermarkets-coffee-shops-clear-unmarked-stock-6420961",
        published_at="2026-10-01T06:00:00+0800",
    )
    borneo = _story(
        "bor", "Budget 2027: Sarawak employers want transition period if minimum wage increases",
        source="Borneo Post", lang=Language.EN,
        url="https://www.theborneopost.com/2026/10/01/budget-2027-sarawak-employers-want-transition-period-if-minimum-wage-increases/",
        published_at="2026-09-30T23:00:23+00:00",
    )

    # CNA ents must NOT contain period or transition
    cna_ents = extract_entities(cna.title)
    assert 'period' not in cna_ents, "Filter must remove 'period' from CNA ents"
    assert 'transition' not in cna_ents, "Filter must remove 'transition' from CNA ents"

    # Borneo ents must NOT contain period or transition
    bor_ents = extract_entities(borneo.title)
    assert 'period' not in bor_ents, "Filter must remove 'period' from Borneo ents"
    assert 'transition' not in bor_ents, "Filter must remove 'transition' from Borneo ents"

    # CNA ↔ Borneo must NOT match
    assert not _is_strong_match(cna, borneo), (
        "CNA ↔ Borneo Post must NOT match — period/transition must no longer be entity bridge."
    )

    # Cluster: chain must be split (4 stories produce 2+ topics)
    sinchew = _story(
        "scm", "张庆禄.2027财案：人人要糖果，谁来买单？",
        source="Sin Chew Main", lang=Language.ZH,
        url="https://budget2027.sinchew.com.my/news/20261001/budget2027/7895736",
        published_at=None,
    )
    enanyang = _story(
        "eny", "2027年STR开放申请 明起可交表格 15日开放线上申请",
        source="eNanyang", lang=Language.ZH,
        url="https://www.enanyang.my/news/20260930/Finance/1398789",
        published_at=None,
    )
    topics, _ = cluster([cna, borneo, sinchew, enanyang])
    assert len(topics) >= 2, (
        f"t_d687fc must produce 2+ clusters, got {len(topics)}: "
        f"{[t.story_ids for t in topics]}"
    )

    # Verify NO topic contains all 4 stories
    for t in topics:
        assert not (set(['cna', 'bor', 'scm', 'eny']).issubset(set(t.story_ids))), (
            f"Topic contains all 4 t_d687fc stories: {t.story_ids}"
        )

    print(f'  t_d687fc: {len(topics)} clusters, none containing all 4 stories')


# ============================================================================
# Test G — PH-Bersatu blocked at share < 0.20
# ============================================================================

def test_ph_bersatu_blocked():
    """PH-Bersatu must NOT merge. PH share (2/11=0.182) must be < 0.20."""
    fmt = _story(
        "fmt", "Elak PH-Bersatu bertembung lebih realistik berbanding persefahaman rasmi, kata penganalisis",
        source="Free Malaysia Today (Bahasa)", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/elak-ph-bersatu-bertembung-lebih-realistik-berbanding-persefahaman-rasmi-kata-penganalisis",
        published_at="Wed, 30 Sep 2026 00:00:00 +0000",
    )
    scm = _story(
        "scm", "In Melaka and GE16, PH + Bersatu + Bersama+MUDA must team up to beat BN + PN",
        source="Sin Chew Main", lang=Language.ZH,
        url="https://mysinchew.sinchew.com.my/news/20260928/mysinchew/7885171",
        published_at=None,
    )

    assert not _is_strong_match(fmt, scm), "PH-Bersatu must NOT merge"

    # Verify entity_path math: smaller should be 11 (kata is preserved in R1)
    from radar.normalize import entity_overlap
    eo, smaller, jacc = entity_overlap(fmt.title, scm.title)
    share = eo / smaller if smaller > 0 else 0
    print(f'  PH-Bersatu entity_overlap: eo={eo}, smaller={smaller}, share={share:.3f}')
    print(f'  ENTITY_MIN_SHARE threshold: {th.ENTITY_MIN_SHARE}')

    # Verify share is below threshold
    assert share < th.ENTITY_MIN_SHARE, (
        f"PH-Bersatu share {share:.3f} must be < ENTITY_MIN_SHARE {th.ENTITY_MIN_SHARE}"
    )

    # Cluster: must produce 2 separate topics
    topics, _ = cluster([fmt, scm])
    assert len(topics) == 2, (
        f"PH-Bersatu must produce 2 separate topics, got {len(topics)}"
    )
    print(f'  PH-Bersatu: NO MERGE, share={share:.3f} < {th.ENTITY_MIN_SHARE}')


# ============================================================================
# Test H — FMT#1 ↔ FMT#2 preserved (kata NOT filtered)
# ============================================================================

def test_fmt_intra_pair_preserved():
    """FMT#1 ↔ FMT#2 must still merge (kata preserved)."""
    a = _story(
        "a", "Hasrat Umno kekal kuasa utama boleh jejas kestabilan, kata penganalisis",
        source="Free Malaysia Today (Bahasa)", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/hasrat-umno-kekal-kuasa-utama-boleh-jejas-kestabilan-kata-penganalisis",
        published_at="Wed, 30 Sep 2026 00:30:00 +0000",
    )
    b = _story(
        "b", "Elak PH-Bersatu bertembung lebih realistik berbanding persefahaman rasmi, kata penganalisis",
        source="Free Malaysia Today (Bahasa)", lang=Language.MS,
        url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/elak-ph-bersatu-bertembung-lebih-realistik-berbanding-persefahaman-rasmi-kata-penganalisis",
        published_at="Wed, 30 Sep 2026 00:00:00 +0000",
    )

    # Verify kata is preserved in both
    a_ents = extract_entities(a.title)
    b_ents = extract_entities(b.title)
    assert 'kata' in a_ents, "'kata' must be in FMT#1 ents"
    assert 'kata' in b_ents, "'kata' must be in FMT#2 ents"

    # Verify entity_path: shared = {kata, penganalisis} = 2
    from radar.normalize import entity_overlap
    eo, smaller, jacc = entity_overlap(a.title, b.title)
    print(f'  FMT intra-pair entity_overlap: eo={eo}, smaller={smaller}, share={eo/smaller:.3f}')

    # Cluster: must produce 1 topic
    topics, _ = cluster([a, b])
    assert len(topics) == 1, (
        f"FMT#1 ↔ FMT#2 must produce 1 topic, got {len(topics)}"
    )
    assert len(topics[0].story_ids) == 2
    print(f'  FMT#1 ↔ FMT#2: MERGE preserved')


# ============================================================================
# Test I — Hasmat preserved
# ============================================================================

def test_hasmat_preserved():
    """Hasmat ZH↔EN must still MERGE (dr preserved)."""
    a = _story(
        "a", "Tun Dr Siti Hasmah: The exemplary prime minister's wife",
        source="Sin Chew Main", lang=Language.ZH,
        url="https://www.sinchew.com.my/hasmah-1",
        published_at="2026-09-30T11:12:24+00:00",
    )
    b = _story(
        "b", "Dr Hasmah minister wife In Retrospect",
        source="CodeBlue", lang=Language.EN,
        url="https://codeblue.galencentre.org/hasmah-2",
        published_at="2026-09-30T12:00:00+00:00",
    )

    # Populate keywords
    _, _ = cluster([a, b])
    assert _is_strong_match(a, b), "Hasmat must MERGE"

    topics, _ = cluster([a, b])
    assert len(topics) == 1
    print(f'  Hasmat: MERGE preserved')


# ============================================================================
# Test J — A1 alias map untouched
# ============================================================================

def test_a1_alias_map_untouched():
    """A1 alias map must be unchanged (7 entries, phase-chinese-1-integration-v1)."""
    from radar.normalize import _ZH_TO_CANONICAL, _ZH_TO_CANONICAL_VERSION
    assert len(_ZH_TO_CANONICAL) == 7, f"Expected 7 alias entries, got {len(_ZH_TO_CANONICAL)}"
    assert _ZH_TO_CANONICAL_VERSION == 'phase-chinese-1-integration-v1'
    expected = {
        '马来西亚': 'malaysia',
        '新加坡': 'singapore',
        '吉隆坡': 'kuala_lumpur',
        '柔佛': 'johor',
        '新山': 'johor_bahru',
        '马新': 'malaysia_singapore',
        '新马': 'malaysia_singapore',
    }
    assert _ZH_TO_CANONICAL == expected, f"Alias map changed: {_ZH_TO_CANONICAL}"
    print(f'  A1 alias map: UNCHANGED (7 entries)')


# ============================================================================
# Test K — Other 4 positive merges preserved
# ============================================================================

def test_4_other_positive_merges_preserved():
    """UM 200, Yunnan 4.3, 惠英红 must still merge."""
    # UM 200
    a2 = _story("a2", "200名大专生齐聚UM校园活动",
                source="Sin Chew Main", lang=Language.ZH,
                url="https://www.sinchew.com.my/um200-a",
                published_at="2026-09-30T13:00:00+00:00")
    b2 = _story("b2", "UM 200 students gather for campus event",
                source="Borneo Post", lang=Language.EN,
                url="https://www.theborneopost.com/um200-b",
                published_at="2026-09-30T13:30:00+00:00")
    _, _ = cluster([a2, b2])
    assert _is_strong_match(a2, b2), "UM 200 must merge"
    print(f'  UM 200: MERGE ✓')

    # Yunnan 4.3
    a4 = _story("a4", "Earthquake strikes Yunnan, magnitude 4.3",
                source="Channel News Asia (Asia section)", lang=Language.EN,
                url="https://www.channelnewsasia.com/yunnan-eq-a",
                published_at="2026-09-30T14:00:00+00:00")
    b4 = _story("b4", "Yunnan earthquake 4.3 magnitude confirmed",
                source="Borneo Post", lang=Language.EN,
                url="https://www.theborneopost.com/yunnan-eq-b",
                published_at="2026-09-30T14:30:00+00:00")
    _, _ = cluster([a4, b4])
    assert _is_strong_match(a4, b4), "Yunnan 4.3 must merge"
    print(f'  Yunnan 4.3: MERGE ✓')

    # 惠英红
    a5 = _story("a5", "惠英红巴黎遭打劫 匪徒砸车窗强抢财物",
                source="Kwong Wah Yit Poh", lang=Language.ZH,
                url="https://www.kwongwah.com.my/news/20260930/a",
                published_at="2026-09-30T15:00:00+00:00")
    b5 = _story("b5", "惠英红巴黎遭打劫 匪徒砸爆车窗强抢财物",
                source="Sin Chew Main", lang=Language.ZH,
                url="https://www.sinchew.com.my/news/20260930/b",
                published_at="2026-09-30T15:30:00+00:00")
    _, _ = cluster([a5, b5])
    assert _is_strong_match(a5, b5), "惠英红 must merge"
    print(f'  惠英红: MERGE ✓')


# ============================================================================
# Test runner
# ============================================================================

if __name__ == '__main__':
    tests = [
        test_period_filtered,
        test_transition_filtered,
        test_man_preserved,
        test_kata_preserved,
        test_dr_preserved,
        test_t_d687fc_cna_borneo_no_merge,
        test_ph_bersatu_blocked,
        test_fmt_intra_pair_preserved,
        test_hasmat_preserved,
        test_a1_alias_map_untouched,
        test_4_other_positive_merges_preserved,
    ]

    passed, failed = 0, 0
    for t in tests:
        name = t.__name__
        try:
            t()
            print(f'PASS {name}')
            passed += 1
        except Exception as e:
            print(f'FAIL {name}: {e}')
            import traceback
            traceback.print_exc()
            failed += 1
        print()

    print(f'\n{passed} passed, {failed} failed of {len(tests)} tests')
    if failed == 0:
        print('ALL A2.8-R1 MINIMAL ENTITY GUARD TESTS PASSED')
    else:
        print('SOME TESTS FAILED')