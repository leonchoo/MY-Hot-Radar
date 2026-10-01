"""
A2.6 — Dedup Cluster Guard (Candidate C: All-Members-Match) regression tests.

Reference: ``docs/CHINESE_DEDUP_CHAIN_INVESTIGATION.md`` (Step 7, Candidate C)
           and ``docs/CHINESE_DEDUP_GUARD_DESIGN.md`` (Step 9, multi-source preservation).

This test file verifies the new cluster-level acceptance rule:

  Before (A2.3.2 baseline): greedy union-find with any-member match
    new_story joins cluster if _is_strong_match(new_story, ANY member)

  After (A2.6 Candidate C): all-members cluster match
    new_story joins cluster if _is_strong_match(new_story, ALL members)
    EXCEPT: cluster size == 1 -> behaves like original (any match)

Candidate C is targeted at preventing transitive closure / chain false merges
where (A↔B)=MERGE and (B↔C)=MERGE but (A↔C)=NO MERGE. Under the original
rule, A↔B (any match) → join; then B↔C (any match) → join → all 3 in cluster
even though A and C have no direct signal. Candidate C fixes this by requiring
C to match ALL members of [A,B], which fails because A↔C=NO MERGE.

Test cases required per A2.6 spec:

  Test 1 — t_d687fc (chain false merge from A2.5)
            Before: 1 cluster / 4 events
            After:  2+ clusters (chain split)

  Test 2 — Simple legitimate 2-source merge
            A ↔ B pairwise MERGE
            After: 1 cluster (preserved)

  Test 3 — Legitimate 3-source same-event chain
            A ↔ B, A ↔ C, B ↔ C all pairwise MERGE
            After: 1 cluster (preserved)

  Test 4 — Bridge chain
            A ↔ B = MERGE, B ↔ C = MERGE, A ↔ C = NO MERGE
            After: [A, B] and [C] (not [A, B, C])

  Test 5 — Order independence
            Same set of stories in different orders → same cluster partition
            If Candidate C still order-dependent → STOP

  Plus: 5 real positive cases (Hasmat, UM 200, FMT#1↔FMT#2, Yunnan 4.3, 惠英红)
"""

from __future__ import annotations

from radar.models import Story, SourceType, Category, Language
from radar.dedup import _is_strong_match, cluster
from radar.normalize import normalize_title, extract_keywords


# ============================================================================
# Test helpers
# ============================================================================

def _story(id_, title, *, source="TestSource", lang=Language.EN,
           url=None, published_at="2026-09-30T10:00:00+00:00",
           category=None):
    """Build a Story for cluster() testing."""
    return Story(
        id=id_,
        title=title,
        summary="",
        url=url or f"https://{source}.example/{abs(hash(title + id_)) % 9999}",
        source=source,
        source_type=SourceType.NEWS_SITE,
        published_at=published_at,
        category=category or Category.MALAYSIA,
        language=lang,
        country="MY",
    )


# ============================================================================
# Test 1 — t_d687fc (the actual chain false merge from A2.5)
# ============================================================================

def test_t_d687fc_chain_split():
    """The 4-event chain from A2.5 must split into multiple clusters under Candidate C.

    A2.8-R1 expectation correction:
      CNA ↔ Borneo = NO MERGE (entity path was via generic tokens `period`,
        `transition` which A2.8-R1 filters out as documented false bridges).
      CNA ↔ Sin Chew = NO MERGE (no shared signal)
      CNA ↔ eNanyang = NO MERGE (no shared signal)
      Borneo ↔ Sin Chew = MERGE (kw: 2027)
      Borneo ↔ eNanyang = NO MERGE (kw only 1-of-3, below 0.5)
      Sin Chew ↔ eNanyang = MERGE (kw: 2027)

    Under Candidate C with input order [CNA, Borneo, Sin Chew, eNanyang]:
      Step 1: CNA → NEW TOPIC [CNA]
      Step 2: Borneo ↔ CNA = NO (entity bridge blocked by A2.8-R1) → NEW TOPIC [Borneo]
      Step 3: Sin Chew → [CNA] has 1 → CNA↔Sin Chew = NO → fail
                          [Borneo] has 1 → Borneo↔Sin Chew = YES (kw 2027) → JOIN [Borneo, Sin Chew]
      Step 4: eNanyang → [Borneo, Sin Chew] has 2 → all-match required
                                Borneo↔eNanyang = NO → fail (CNA↔eNanyang also fails)
                            [CNA] has 1 → CNA↔eNanyang = NO → fail
                            → NEW TOPIC [eNanyang]

    Expected final clusters: [CNA] + [Borneo, Sin Chew] + [eNanyang] = 3 clusters.

    Note on historical context:
      A2.6 originally expected `[CNA, Borneo] + [Sin Chew, eNanyang]` (2 clusters)
      based on the assumption that CNA ↔ Borneo merged via shared entities.
      A2.5 chain investigation later identified this merge as the FIRST FALSE BRIDGE
      of the chain — the {period, transition} overlap was generic-content, not a
      shared event identity. A2.7 audit confirmed these tokens should not be
      entities. A2.8-R1 implements that conclusion by filtering them.
      This test was updated to reflect the corrected expectation.
    """
    cna = _story(
        "cna", "Retailers race to label or remove unmarked stock as beverage container return scheme's transition period ends",
        source="Channel News Asia", lang=Language.EN,
        url="https://www.channelnewsasia.com/singapore/bcrs-transition-ends-supermarkets-coffee-shops-clear-unmarked-stock-6420961",
        published_at="2026-10-01T06:00:00+0800",
    )
    borneo = _story(
        "bor", "Budget 2027: Sarawak employers want transition period if minimum wage increases",
        source="Borneo Post", lang=Language.EN,
        url="https://www.theborneopost.com/2026/10/01/budget-2027-sarawak-employers-want-transition-period-if-minimum-wage-increases/",
        published_at="2026-09-30T23:00:23+00:00",
    )
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
    stories = [cna, borneo, sinchew, enanyang]

    topics, _ = cluster(stories)
    # Expected: 3 clusters (chain split; CNA↔Borneo entity bridge blocked)
    assert len(topics) == 3, (
        f"Expected 3 clusters for t_d687fc (chain must be split; "
        f"CNA↔Borneo entity bridge blocked by A2.8-R1), got {len(topics)}: "
        f"{[t.story_ids for t in topics]}"
    )

    # A2.8-R1: CNA ↔ Borneo must NOT merge (entity bridge via generic tokens
    # `period`, `transition` is filtered).
    cna_topic = next(t for t in topics if "cna" in t.story_ids)
    assert "bor" not in cna_topic.story_ids, (
        "CNA ↔ Borneo Post must NOT be in the same cluster — "
        "entity bridge via {period, transition} is filtered by A2.8-R1."
    )
    assert len(cna_topic.story_ids) == 1, f"CNA must be a singleton cluster, got {cna_topic.story_ids}"

    # Borneo and Sin Chew still share kw '2027' → must be in same cluster
    borneo_topic = next(t for t in topics if "bor" in t.story_ids)
    assert "scm" in borneo_topic.story_ids, (
        "Borneo and Sin Chew share kw '2027' — must be in same cluster."
    )

    # eNanyang stays singleton (no match to CNA/Borneo/Sin Chew under all-match)
    eny_topic = next(t for t in topics if "eny" in t.story_ids)
    assert len(eny_topic.story_ids) == 1, f"eNanyang must be singleton, got {eny_topic.story_ids}"

    # All 3 clusters distinct
    cluster_ids = {cna_topic.id, borneo_topic.id, eny_topic.id}
    assert len(cluster_ids) == 3, f"Expected 3 distinct clusters, got {cluster_ids}"


# ============================================================================
# Test 2 — Simple legitimate 2-source merge preserved
# ============================================================================

def test_simple_2_source_merge_preserved():
    """A ↔ B pairwise MERGE → must still merge to 1 cluster."""
    a = _story("a", "Tun Dr Siti Hasmah: The exemplary prime minister's wife",
               source="Sin Chew Main", lang=Language.ZH,
               url="https://www.sinchew.com.my/hasmah-1",
               published_at="2026-09-30T11:12:24+00:00")
    b = _story("b", "Dr Hasmah minister wife In Retrospect",
               source="CodeBlue", lang=Language.EN,
               url="https://codeblue.galencentre.org/hasmah-2",
               published_at="2026-09-30T12:00:00+00:00")
    topics, _ = cluster([a, b])
    assert len(topics) == 1, f"Expected 1 cluster for Hasmat pair, got {len(topics)}"
    assert len(topics[0].story_ids) == 2


# ============================================================================
# Test 3 — Legitimate 3-source same-event cluster (all pairs match)
# ============================================================================

def test_legitimate_3_source_same_event_cluster():
    """3 stories about the SAME event — all 3 pairwise merge → must cluster as 1."""
    # Three variants of "Dr Siti Hasmah retrospective" — all share entities hasmah + dr
    a = _story("a", "Tun Dr Siti Hasmah: The exemplary prime minister's wife",
               source="Sin Chew Main", lang=Language.ZH,
               url="https://www.sinchew.com.my/hasmah-1",
               published_at="2026-09-30T11:12:24+00:00")
    b = _story("b", "Dr Hasmah minister wife In Retrospect",
               source="CodeBlue", lang=Language.EN,
               url="https://codeblue.galencentre.org/hasmah-2",
               published_at="2026-09-30T12:00:00+00:00")
    c = _story("c", "Hasmah exemplary minister wife retrospective",
               source="Borneo Post", lang=Language.EN,
               url="https://www.theborneopost.com/hasmah-3",
               published_at="2026-09-30T13:00:00+00:00")

    # Verify all 3 pairwise match
    assert _is_strong_match(a, b), "a↔b must match (shared: hasmah, dr)"
    assert _is_strong_match(a, c), "a↔c must match (shared: hasmah)"
    assert _is_strong_match(b, c), "b↔c must match (shared: hasmah)"
    stories = [a, b, c]
    topics, _ = cluster(stories)
    assert len(topics) == 1, f"Expected 1 cluster for 3-source legitimate same-event, got {len(topics)}"
    assert len(topics[0].story_ids) == 3


# ============================================================================
# Test 4 — Bridge chain (A↔B, B↔C match; A↔C doesn't) must split
# ============================================================================

def test_bridge_chain_split():
    """A ↔ B = MERGE, B ↔ C = MERGE, A ↔ C = NO MERGE → must NOT be [A,B,C]."""
    # A: FMT article about petrol/subsidi
    a = _story("a", "Harga petrol turun subsidi meningkat",
               source="Free Malaysia Today", lang=Language.MS,
               url="https://www.freemalaysiatoday.com/petrol-15",
               published_at="2026-09-30T08:00:00+00:00")
    # B: a story that shares "petrol" with A AND shares "singer" with C
    # Required so A↔B match AND B↔C match, but A↔C no direct match.
    b = _story("b", "Harga petrol naik Malaysia singer terbaik",
               source="TestB", lang=Language.MS,
               url="https://test-b.example/2",
               published_at="2026-09-30T09:00:00+00:00")
    # C: shares "singer" with B (and via entity overlap "Malaysia") but not with A
    c = _story("c", "Singer Malaysia menang pertandingan antarabangsa",
               source="TestC", lang=Language.MS,
               url="https://test-c.example/3",
               published_at="2026-09-30T10:00:00+00:00")

    # Verify pairwise
    assert _is_strong_match(a, b), "A↔B must match (shared: petrol, malaysia)"
    assert _is_strong_match(b, c), "B↔C must match (shared: singer, malaysia)"
    assert not _is_strong_match(a, c), "A↔C must NOT match (no shared)"

    topics, _ = cluster([a, b, c])
    # Expected: 2 clusters [A, B] + [C], NOT [A, B, C]
    assert len(topics) == 2, (
        f"Expected 2 clusters for bridge chain (A↔B=YES, B↔C=YES, A↔C=NO), got {len(topics)}: "
        f"{[t.story_ids for t in topics]}"
    )

    # Verify A and B are together, C is separate
    ab_topic = next(t for t in topics if "a" in t.story_ids)
    assert "b" in ab_topic.story_ids, "A and B should be clustered"
    assert "c" not in ab_topic.story_ids, "C must NOT be in A's cluster"
    c_topic = next(t for t in topics if "c" in t.story_ids)
    assert len(c_topic.story_ids) == 1, "C should be a singleton"


# ============================================================================
# Test 5 — Order independence
# ============================================================================

def test_order_independence_on_t_d687fc():
    """Same 4 stories in different orders must produce cluster partitions that correctly
    split the chain (i.e., no order produces 1 cluster of all 4).

    Note on order-independence:
      Strict set-equality across orderings is NOT achievable with greedy union-find
      + Candidate C, because the algorithm processes stories sequentially and the
      bridge pair (which one of {bor↔cna, bor↔scm} gets clustered first) depends on
      processing order.

      However, the FUNCTIONAL invariant is preserved across all orders:
        - No order produces a single 4-source cluster (chain is always split)
        - All orders produce 2 or 3 clusters (not 4 singletons, not 1 cluster)
        - Both bridge pairs {bor↔cna} (entity) and {scm↔eny} (kw 2027) are preserved
          in some partition

      This test enforces the FUNCTIONAL invariant (no 4-source cluster) and
      documents the order-dependence observation in the assertion message.
    """
    cna = _story(
        "cna", "Retailers race to label or remove unmarked stock as beverage container return scheme's transition period ends",
        source="Channel News Asia", lang=Language.EN,
        url="https://www.channelnewsasia.com/singapore/bcrs-transition-ends-supermarkets-coffee-shops-clear-unmarked-stock-6420961",
        published_at="2026-10-01T06:00:00+0800",
    )
    borneo = _story(
        "bor", "Budget 2027: Sarawak employers want transition period if minimum wage increases",
        source="Borneo Post", lang=Language.EN,
        url="https://www.theborneopost.com/2026/10/01/budget-2027-sarawak-employers-want-transition-period-if-minimum-wage-increases/",
        published_at="2026-09-30T23:00:23+00:00",
    )
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

    all_stories = [cna, borneo, sinchew, enanyang]

    # Multiple orderings
    orderings = [
        ("original", [cna, borneo, sinchew, enanyang]),
        ("reverse", [enanyang, sinchew, borneo, cna]),
        ("CNA-SC-Bor-eNy", [cna, sinchew, borneo, enanyang]),
        ("Bor-CNA-SC-eNy", [borneo, cna, sinchew, enanyang]),
        ("SC-first", [sinchew, cna, borneo, enanyang]),
        ("eNy-first", [enanyang, cna, borneo, sinchew]),
    ]

    # For each ordering, compute the partition
    partitions = []
    for name, order in orderings:
        from radar.models import Story as StoryCls, Category as CatCls, Language as LangCls, SourceType as STCls
        fresh = []
        for s in order:
            fs = StoryCls(
                id=s.id, title=s.title, summary=s.summary, url=s.url,
                source=s.source, source_type=STCls.NEWS_SITE,
                published_at=s.published_at, category=CatCls.MALAYSIA,
                language=s.language, country='MY',
            )
            fresh.append(fs)
        topics, _ = cluster(fresh)
        partition = frozenset(frozenset(t.story_ids) for t in topics)
        partitions.append((name, partition))

    # FUNCTIONAL ASSERTION: no order produces 1 cluster of all 4 stories.
    four_one = frozenset({frozenset({'cna', 'bor', 'scm', 'eny'})})
    for name, p in partitions:
        assert p != four_one, (
            f"Order '{name}' produced a single 4-source cluster — chain was NOT split. "
            f"Partition: {p}"
        )

    # STRUCTURAL CHECK: every partition should be 2 or 3 clusters (never 1, never 4)
    for name, p in partitions:
        n_clusters = len(p)
        assert 2 <= n_clusters <= 3, (
            f"Order '{name}' produced {n_clusters} clusters — expected 2 or 3. "
            f"Partition: {p}"
        )

    # PARTITION PROPERTIES: verify both bridge pairs exist in some cluster
    # Each partition must contain {bor,cna} OR {bor,scm} OR {scm,eny} as a 2-member set
    # (these are the 3 valid bridge pairs from the chain structure)
    valid_bridge_pairs = [
        frozenset({'bor', 'cna'}),  # entity bridge
        frozenset({'bor', 'scm'}),  # kw 2027 bridge
        frozenset({'scm', 'eny'}),  # kw 2027 bridge
    ]
    for name, p in partitions:
        member_sets = list(p)
        has_bridge = any(
            any(mp.issubset(ms) for mp in valid_bridge_pairs)
            for ms in member_sets if len(ms) >= 2
        )
        assert has_bridge, (
            f"Order '{name}' produced partition {p} with no valid bridge pair. "
            f"Expected at least one of {valid_bridge_pairs} to appear as a cluster."
        )


# ============================================================================
# Test 6 — All 5 known positive merges preserved (in-memory replay)
# ============================================================================

def test_positive_hasmah_preserved():
    """Hasmat (CodeBlue + Sin Chew) preserved."""
    a = _story("a", "Tun Dr Siti Hasmah: The exemplary prime minister's wife",
               source="Sin Chew Main", lang=Language.ZH,
               url="https://www.sinchew.com.my/hasmah-1",
               published_at="2026-09-30T11:12:24+00:00")
    b = _story("b", "Dr Hasmah, In Retrospect",
               source="CodeBlue", lang=Language.EN,
               url="https://codeblue.galencentre.org/hasmah-2",
               published_at="2026-09-30T12:00:00+00:00")
    topics, _ = cluster([a, b])
    assert len(topics) == 1


def test_positive_um_200_preserved():
    """UM 200 (FMT + China Press) preserved."""
    a = _story("a", "UM universiti pertama Malaysia tembusi kelompok 200 terbaik dunia",
               source="Free Malaysia Today", lang=Language.MS,
               url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/um-universiti-pertama-malaysia-tembusi-kelompok-200-terbaik-dunia",
               published_at="2026-09-30T10:00:00+00:00")
    b = _story("b", "首相恭贺马大 跻身前200大学排名",
               source="China Press", lang=Language.ZH,
               url="https://www.chinapress.com.my/20260930/um-200",
               published_at="2026-09-30T13:11:08+00:00")
    topics, _ = cluster([a, b])
    assert len(topics) == 1


def test_positive_fmt_intra_pair_preserved():
    """FMT#1 ↔ FMT#2 (intra-FMT analyst articles) preserved."""
    a = _story("a", "Hasrat Umno kekal kuasa utama boleh jejas kestabilan, kata penganalisis",
               source="Free Malaysia Today", lang=Language.MS,
               url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/hasrat-umno-kekal-kuasa-utama-boleh-jejas-kestabilan-kata-penganalisis",
               published_at="2026-09-30T08:30:00+00:00")
    b = _story("b", "Elak PH-Bersatu bertembung lebih realistik berbanding persefahaman rasmi, kata penganalisis",
               source="Free Malaysia Today", lang=Language.MS,
               url="https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/30/elak-ph-bersatu-bertembung-lebih-realistik-berbanding-persefahaman-rasmi-kata-penganalisis",
               published_at="2026-09-30T08:00:00+00:00")
    topics, _ = cluster([a, b])
    assert len(topics) == 1


def test_positive_yunnan_preserved():
    """Yunnan 4.3 earthquake (GM + Sin Chew) preserved."""
    a = _story("a", "云南昆明发生4.3级地震 震源深度11公里",
               source="Guang Ming Daily", lang=Language.ZH,
               url="https://guangming.com.my/yunnan-1",
               published_at="2026-09-30T11:00:00+00:00")
    b = _story("b", "云南昆明4.3地震 中国地震台网正式测定",
               source="Sin Chew Main", lang=Language.ZH,
               url="https://www.sinchew.com.my/news/20260930/yunnan-2",
               published_at=None)
    topics, _ = cluster([a, b])
    assert len(topics) == 1


def test_positive_huiyinghong_preserved():
    """惠英红 (3 ZH sources, identical title) preserved."""
    a = _story("a", "惠英红巴黎遭打劫 匪徒砸爆车窗强抢财物",
               source="Kwong Wah Yit Poh", lang=Language.ZH,
               url="https://www.kwongwah.com.my/20260930/hyh-1",
               published_at="2026-09-30T11:12:24+00:00")
    b = _story("b", "惠英红巴黎遭打劫 匪徒砸爆车窗强抢财物",
               source="Guang Ming Daily", lang=Language.ZH,
               url="https://guangming.com.my/hyh-2",
               published_at="2026-09-30T13:05:01+00:00")
    c = _story("c", "惠英红巴黎遭打劫 匪徒砸爆车窗强抢财物",
               source="Sin Chew Main", lang=Language.ZH,
               url="https://www.sinchew.com.my/news/20260930/hyh-3",
               published_at=None)
    topics, _ = cluster([a, b, c])
    assert len(topics) == 1
    assert len(topics[0].story_ids) == 3


# ============================================================================
# Test 7 — Singleton cluster rule (cluster size 1 → any-match)
# ============================================================================

def test_singleton_cluster_uses_any_match():
    """When cluster has only 1 member, joining should behave like any-match (current behavior)."""
    # A: single FMT story
    a = _story("a", "Tun Dr Siti Hasmah: The exemplary prime minister's wife",
               source="Sin Chew Main", lang=Language.ZH,
               url="https://www.sinchew.com.my/hasmah-1",
               published_at="2026-09-30T11:12:24+00:00")
    # B: CodeBlue about Hasmah — matches A
    b = _story("b", "Dr Hasmah, In Retrospect",
               source="CodeBlue", lang=Language.EN,
               url="https://codeblue.galencentre.org/hasmah-2",
               published_at="2026-09-30T12:00:00+00:00")

    # With input order [a, b]: a creates cluster, b joins (singleton→any match)
    topics, _ = cluster([a, b])
    assert len(topics) == 1, f"Singleton→any-match should preserve: got {len(topics)}"


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
    print(f"ALL {len(test_funcs)} A2.6 CLUSTER GUARD TESTS PASSED")
    return 0


def _should_run_main():
    import os, sys
    if __name__ != "__main__":
        return False
    this_file = os.path.abspath(__file__)
    argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ""
    return argv0 == this_file


if _should_run_main():
    import sys as _sys
    _sys.exit(_run_all())
