"""
Tier-C source review fixtures (A2.2-D).

This module holds the frozen fixture data for Tier-C sources (sources
that pass basic quality checks but do NOT meet the higher Tier-B bar
on volume, freshness, or timestamp coverage). Tier-C sources still
participate in the registry and the verification engine but contribute
less confidence than Tier-B.

Currently registered Tier-C sources:
  - eNanyang / 南洋商报 (A2.2-D, joined 2026-09-30)

Tier-C sources have the SAME frozen-fixture shape as Tier-B fixtures
in fixtures_tier_b_review.py so the review framework can build a
``SourceReview`` from them via the same mechanism. The decision logic
in ``tier_b_review.py::decide_registry_decision`` does NOT check the
source tier — it only checks quality. For a Tier-C source that passes
quality checks (all 3 fetches OK, parse succeeds, freshness ACTIVE,
not placeholder-heavy), the decision name is ``KEEP_TIER_B`` even
though the source is actually Tier C. This is intentional: the
decision is "keep in registry", not "promote to Tier B".

A2.2-D added eNanyang. Live-verified 2026-09-30
(https://www.enanyang.my/, sha12 29c349994c0b, byte-identical across
3 fetches, 6 articles per fetch).
"""

ENANYANG = "eNanyang"

ALL_TIER_C_SOURCES = [ENANYANG]


FIXTURES = {
    'eNanyang': {
        'url': 'https://www.enanyang.my/',
        'fetches': [
            {'ok': True, 'status': 200, 'sha12': '29c349994c0b', 'item_count': 6, 'parse_status': 'ok_html_listing'},
            {'ok': True, 'status': 200, 'sha12': '29c349994c0b', 'item_count': 6, 'parse_status': 'ok_html_listing'},
            {'ok': True, 'status': 200, 'sha12': '29c349994c0b', 'item_count': 6, 'parse_status': 'ok_html_listing'},
        ],
        'samples': [
            {'title': '美景控股全购达90%门槛 峇都加湾启动强制收购',
             'url': 'https://www.enanyang.my/news/20260930/Finance/1398686',
             'pub_date': None, 'nature': 'NEWS'},
            {'title': '哥宾星:迈向企业人才与创新发展 数字投资须转化为经济机会',
             'url': 'https://www.enanyang.my/news/20260930/Finance/1397184',
             'pub_date': None, 'nature': 'NEWS'},
            {'title': '俄罗斯再延长柴油出口禁令 全球燃料市场恐趋紧',
             'url': 'https://www.enanyang.my/news/20260930/Finance/1398649',
             'pub_date': None, 'nature': 'NEWS'},
            {'title': '权重股领涨 带动马股回升至1650点关口',
             'url': 'https://www.enanyang.my/news/20260930/Finance/1398540',
             'pub_date': None, 'nature': 'NEWS'},
            {'title': '英国首相:脱欧弊大于利 重返欧盟列考虑选项',
             'url': 'https://www.enanyang.my/news/20260930/International/1398544',
             'pub_date': None, 'nature': 'NEWS'},
            {'title': '暴雨袭新山 多区水灾',
             'url': 'https://www.enanyang.my/news/20260930/State/1398635',
             'pub_date': None, 'nature': 'NEWS'},
        ],
        'content_distribution': {'NEWS': 100.0},
        'freshness_verdict': 'ACTIVE',
        'newest_age_days': 0,
        'median_age_days': 0,
        'items_with_valid_date': 0,
        'items_total': 6,
        'unique_title_count': 6,
        'unique_pubdate_count': 0,
        'distinct_url_hosts': 1,
        'self_host_count': 6,
    },
}
