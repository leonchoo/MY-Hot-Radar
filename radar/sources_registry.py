"""
Source registry.

Phase 1 / Batch Radar-2: real public RSS feeds, verified live before
registration. Each source must satisfy ALL of these:

  1. URL returned HTTP 200 at registration time
  2. content-type was XML (RSS or Atom) — or, for WP-JSON sources,
     the JSON response body parsed cleanly and contained posts
  3. parse succeeded and produced items
  4. feed is publicly accessible without login, paywall, or CAPTCHA
  5. tier (A..F) is documented and justified in the per-source comment block
     AND in the per-source `notes` field

If a feed URL stops working, REMOVE it from this list. We do NOT register
endpoints that returned 404 or that we cannot reach.

History:

  Radar-2 (2026-09-29): 5 RSS sources.
  A2.3 (2026-09-30): 2 WP-JSON sources added (Chinese). Total: 7.
  A2.2-A (2026-09-30): 1 HTML listing source added (Sin Chew Johor). Total: 8.
  A2.2-B (2026-09-30): 1 HTML listing source added (Sin Chew Main). Total: 9.
  A2.2-C (2026-09-30): 1 HTML listing source added (China Press). Total: 10.
  A2.2-D (2026-09-30): 1 HTML listing source added (eNanyang, Tier C). Total: 11.

Current mix:

  International anchor (English, RSS)         BBC News Asia       Tier B
  Regional Asia (English, RSS)                Channel News Asia   Tier B
  Malaysian health-policy (English, RSS)      CodeBlue            Tier B
  Malaysian news in Bahasa Malaysia (RSS)     FMT Bahasa          Tier B
  Malaysian regional news (English, RSS)      Borneo Post         Tier B
  Malaysian Chinese news (WP-JSON)            Kwong Wah Yit Poh   Tier B
  Malaysian Chinese news (WP-JSON)            Guang Ming Daily    Tier B
  Malaysian Chinese Johor news (HTML)         Sin Chew Johor desk Tier B
  Malaysian Chinese main news (HTML)          Sin Chew Main       Tier B
  Malaysian Chinese national news (HTML)      China Press / 中国报 Tier B
  Malaysian Chinese national news (HTML)      eNanyang / 南洋商报   Tier C

Tier justifications (also carried in each Source's `notes`):

  BBC News Asia, CNA Asia        - established international outlets with
    documented corrections records; not Malaysia-local but high signal for
    Malaysia-relevant Asia news. Tier B.
  CodeBlue                       - Galen Centre / APHM-affiliated health
    journalism in MY; documented outlet. Tier B (niche but established).
  Free Malaysia Today (Bahasa)   - one of the largest Bahasa-Malaysia
    newsrooms in MY, established outlet with documented corrections
    history. Tier B. Only Bahasa Malaysia source in this batch.
  Borneo Post                    - established East-Malaysia regional
    outlet, English-language. Tier B.
  Kwong Wah Yit Poh (光华日报)    - established Penang-based Chinese
    daily (since 1910); WordPress backend, public /wp-json endpoint.
    Tier B. Joined in A2.3.
  Guang Ming Daily (光明日报)    - established Malaysian Chinese daily;
    WordPress backend, public /wp-json endpoint. Tier B. Joined in A2.3.
  Sin Chew Johor desk (星洲日报柔佛版) - established Penang-based
    Chinese daily (since 1910); Johor microsite with custom-CMS
    HTML. ~16-40 dated article URLs on the homepage. Tier B.
    Joined in A2.2-A.
  Sin Chew Main (星洲日报)       - the Sin Chew Daily homepage;
    established Malaysian Chinese daily (since 1910). Custom-CMS
    HTML; ~90 article URLs on the homepage spanning 21 sections
    and 11 hostnames (metro, sarawak, sabah, johor, ...).
    Tier B. Joined in A2.2-B. Same publisher as Sin Chew Johor;
    the cross-host Johor links in Main's homepage are deduped
    against the Johor desk's homepage fetch.
  China Press / 中国报           - established Malaysian Chinese daily
    (since 1946). Custom-CMS HTML; ~10 clean /YYYYMMDD/{slug}/
    articles on the homepage, all with real news titles and 9/10
    carrying absolute timestamps (data-pdatetime, ISO 8601 +08:00
    → UTC Z). WordPress-style URL paths but WP-JSON is disabled
    (404); RSS endpoint /feed/ 301s to error404. The homepage
    also has a mixed-quality breaking-news ticker (?p=NNN URLs
    include sponsored advertorial: HONOR, GREENS, Cosmobeauté);
    these are EXPLICITLY EXCLUDED by the adapter to avoid
    advertorial contamination. Tier B. Joined in A2.2-C.

We deliberately do NOT register (per probe results):
  - The Star, NST, Malay Mail, Malaysiakini, FMT English, Astro Awani,
    The Edge: their public RSS endpoints return 404 or SSL errors at
    this time. Re-probe before considering them.
  - BERNAMA / PMO / Sarawakvoice: SSL / 403 / 404 at this time.
  - eNanyang: HTML-listing source requiring a separate
    HTML adapter (deferred to a future batch). China Press was
    joined in A2.2-C.
  - Sin Chew subdomains other than Johor (sarawak, sabah, ...):
    already covered by Sin Chew Main's homepage which links to
    them. Adding individual subdomain sources would duplicate
    stories.
  - Any source that requires auth, paywall bypass, or CAPTCHA.
"""

from __future__ import annotations

from typing import Dict, List

from .models import Source, SourceType, Category, Language, SourceTier


REGISTERED_SOURCES: List[Source] = [
    # ---- 1. International anchor ------------------------------------------
    Source(
        name="BBC News Asia",
        type=SourceType.RSS,
        url="https://feeds.bbci.co.uk/news/world/asia/rss.xml",
        reliability=4,
        country="GB",
        languages=[Language.EN],
        tier=SourceTier.B,
        notes=("Public BBC RSS feed. English. ~17 items per fetch."),
    ),

    # ---- 2. Regional Asia -------------------------------------------------
    Source(
        name="Channel News Asia (Asia section)",
        type=SourceType.RSS,
        url=("https://www.channelnewsasia.com/api/v1/rss-outbound-feed"
             "?_charset_=UTF-8&cnaCategId=100348&type=feed"),
        reliability=4,
        country="SG",
        languages=[Language.EN],
        tier=SourceTier.B,
        notes=("Open RSS feed. English. ~20 items per fetch."),
    ),

    # ---- 3. Malaysia (English, niche) -------------------------------------
    Source(
        name="CodeBlue",
        type=SourceType.RSS,
        url="https://codeblue.galencentre.org/feed/",
        reliability=4,
        country="MY",
        languages=[Language.EN],
        tier=SourceTier.B,
        notes=("Public RSS feed. English. ~10 items per fetch."),
    ),

    # ---- 4. Malaysia (Bahasa Malaysia) ------------------------------------
    Source(
        name="Free Malaysia Today (Bahasa)",
        type=SourceType.RSS,
        url="https://www.freemalaysiatoday.com/category/bahasa/feed",
        reliability=4,
        country="MY",
        languages=[Language.MS],
        tier=SourceTier.B,
        notes=("Public RSS feed. Bahasa Malaysia. ~50 items per fetch. "
               "When deduplicating cross-language, the entity-overlap rule "
               "catches name mentions even when the words differ."),
    ),

    # ---- 5. Malaysia regional (English) ------------------------------------
    Source(
        name="Borneo Post",
        type=SourceType.RSS,
        url="https://www.theborneopost.com/feed/",
        reliability=4,
        country="MY",
        languages=[Language.EN],
        tier=SourceTier.B,
        notes=("Public RSS feed. English. ~20 items per fetch."),
    ),

    # ---- 6. Malaysia (Chinese, WP-JSON) — A2.3 -----------------------------
    # Kwong Wah Yit Poh / 光华日报 — established Penang-based Chinese-
    # language daily; published continuously since 1910. WordPress
    # backend exposes a public /wp-json/wp/v2/posts endpoint returning
    # a JSON array of recent posts with date_gmt, title.rendered,
    # excerpt.rendered, content.rendered, link. Verified live
    # 2026-09-30: 10 posts, sha12 d9b3b8cfbebb, all today's dates.
    # Tier B — established regional outlet, not Tier A.
    Source(
        name="Kwong Wah Yit Poh",
        type=SourceType.WP_JSON,
        url="https://www.kwongwah.com.my/wp-json/wp/v2/posts",
        reliability=4,
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.B,
        notes=("Public WordPress JSON API endpoint. Chinese (Simplified/Traditional). "
               "~10 items per fetch. Joined registry in A2.3 (2026-09-30). "
               "Publisher identity preserved as a single source (Penang-based). "
               "Distinct from Sin Chew Main (which uses HTML listing, deferred to A2.2)."),
    ),

    # ---- 7. Malaysia (Chinese, WP-JSON) — A2.3 -----------------------------
    # Guang Ming Daily / 光明日报 — established Malaysian Chinese-language
    # daily. WordPress backend exposes /wp-json/wp/v2/posts. Verified
    # live 2026-09-30: 10 posts, sha12 8222bdc0982c, all today's dates.
    # Tier B — established regional outlet, not Tier A.
    Source(
        name="Guang Ming Daily",
        type=SourceType.WP_JSON,
        url="https://guangming.com.my/wp-json/wp/v2/posts",
        reliability=4,
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.B,
        notes=("Public WordPress JSON API endpoint. Chinese. ~10 items per fetch. "
               "Joined registry in A2.3 (2026-09-30). "
               "Cross-language dedup works via the A1 Chinese place-name aliases "
               "(马来西亚 / 新加坡 / 吉隆坡 / 柔佛 / 新山 / 马新 / 新马)."),
    ),

    # ---- 8. Malaysia (Chinese, HTML listing) — A2.2-A ----------------------
    # Sin Chew Johor desk / 星洲日报柔佛版 — Johor-focused microsite
    # under the Sin Chew Daily publisher. WP-JSON, RSS, and sitemap
    # all return 404; the homepage is a custom-CMS HTML page with
    # ~38 dated article URLs in /news/YYYYMMDD/johor/{id} form.
    # HtmlListingAdapter walks <h2 class="title"> and <a class=
    # "internalLink" data-title="..."> blocks. The listing page
    # only carries relative time strings ("16分钟前") so
    # published_at is None by default — see adapter docstring.
    # Tier B — established regional outlet, not Tier A.
    # This is NOT a separate publisher; it is Sin Chew Daily's
    # Johor desk.
    Source(
        name="Sin Chew Johor desk",
        type=SourceType.HTML_LISTING,
        url="https://johor.sinchew.com.my/",
        reliability=4,
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.B,
        notes=("Custom-CMS HTML listing page. Chinese. Johor-focused "
               "microsite under Sin Chew Daily (星洲日报). "
               "~16-40 dated article URLs on the homepage. "
               "Joined registry in A2.2-A (2026-09-30). "
               "Listing page only carries relative time strings, "
               "so published_at=None by default. "
               "Cross-language dedup works via the A1 Chinese "
               "place-name aliases (马来西亚 / 新加坡 / 吉隆坡 / "
               "柔佛 / 新山 / 马新 / 新马). "
               "Sin Chew Main (https://www.sinchew.com.my/) was "
               "joined as a separate Tier-B source in A2.2-B "
               "(2026-09-30); cross-host Johor links in the Main "
               "homepage dedupe against this desk's fetch."),
    ),

    # ---- 9. Malaysia (Chinese, HTML listing) — A2.2-B ----------------------
    # Sin Chew Main / 星洲日报 — the Sin Chew Daily homepage. Established
    # Malaysian Chinese daily (since 1910). WP-JSON, RSS, and sitemap
    # all return 404; the homepage is a custom-CMS HTML page with
    # ~90 dated article URLs spanning 21 sections (metro, sarawak,
    # sabah, johor, sports, international, ...) and 11 hostnames
    # (metro.sinchew.com.my, eastcoast.sinchew.com.my, ...).
    # HtmlListingAdapter's generalized Phase-2 walk (<a class=
    # "internalLink" data-title="..." href="...">) is the workhorse;
    # Sin Chew Main does NOT expose <h2 class="title"> cards (unlike
    # the Johor desk). The listing page only carries relative time
    # strings ("2小时前", "3天前") so published_at is None by default.
    # Cross-host Johor links in the Main homepage dedupe against the
    # Sin Chew Johor desk fetch via the dedup pipeline's URL-based
    # canonicalization. Tier B — established national outlet, not Tier A.
    Source(
        name="Sin Chew Main",
        type=SourceType.HTML_LISTING,
        url="https://www.sinchew.com.my/",
        reliability=4,
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.B,
        notes=("Custom-CMS HTML listing page. Chinese. Sin Chew "
               "Daily's national homepage (星洲日报). ~90 dated "
               "article URLs on the homepage spanning 21 sections "
               "and 11 hostnames (metro, sarawak, sabah, johor, "
               "sports, ...). Joined registry in A2.2-B (2026-09-30). "
               "Listing page only carries relative time strings, "
               "so published_at=None by default. Same publisher as "
               "the Johor desk (joined A2.2-A); cross-host Johor "
               "links in the Main homepage dedupe against the Johor "
               "desk's fetch. Cross-language dedup works via the A1 "
               "Chinese place-name aliases (马来西亚 / 新加坡 / "
               "吉隆坡 / 柔佛 / 新山 / 马新 / 新马). "
               "Sin Chew regional subdomains (sarawak, sabah, "
               "metro, etc.) are NOT separately registered — they "
               "are reachable through this source's homepage."),
    ),

    # ---- 10. Malaysia (Chinese, HTML listing) — A2.2-C ----------------------
    # China Press / 中国报 — established Malaysian Chinese daily
    # (since 1946). WordPress-style URL paths (/YYYYMMDD/{slug}/)
    # but WP-JSON is disabled (404) and RSS endpoint /feed/ 301s
    # to error404. Custom-CMS HTML homepage.
    #
    # Live-verified 2026-09-30 (https://www.chinapress.com.my/,
    # sha12=184362a22be3): 10 clean /YYYYMMDD/{slug}/ articles
    # per fetch with real Chinese titles; 9 of 10 carry absolute
    # timestamps via <div data-pdatetime="ISO_8601+08:00"> which
    # the adapter converts to UTC ISO Z. The 7 ?p=NNN ticker URLs
    # on the homepage mix real news with sponsored advertorial
    # (HONOR X9e Pro, GREENS GREENSTOPIA, Cosmobeauté Malaysia) and
    # are EXPLICITLY EXCLUDED by the adapter's URL filter to avoid
    # advertorial contamination.
    #
    # Tier B — established national outlet, not Tier A. Discovery
    # audit flagged China Press as NEEDS_FURTHER_VALIDATION; the
    # A2.2-C validation pass (live fetch + 3-fetch stability +
    # adapter extraction + fixture roundtrip) clears the flag.
    Source(
        name="China Press",
        type=SourceType.HTML_LISTING,
        url="https://www.chinapress.com.my/",
        reliability=4,
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.B,
        notes=("Custom-CMS HTML listing page. Chinese. National "
               "Malaysian Chinese daily (中国报, since 1946). "
               "~10 clean /YYYYMMDD/{percent-encoded-slug}/ "
               "articles on the homepage with real news titles; "
               "9 of 10 carry absolute timestamps "
               "(data-pdatetime ISO 8601 +08:00 → UTC Z). "
               "Joined registry in A2.2-C (2026-09-30). "
               "WordPress-style URL paths but WP-JSON is disabled; "
               "RSS endpoint /feed/ 301s to error404. Homepage "
               "ticker ?p=NNN URLs are EXCLUDED by the adapter "
               "because the homepage ticker mixes real news with "
               "sponsored advertorial (HONOR, GREENS, Cosmobeauté) "
               "at the HTML level. Cross-language dedup works via "
               "the A1 Chinese place-name aliases (马来西亚 / "
               "新加坡 / 吉隆坡 / 柔佛 / 新山 / 马新 / 新马). "
               "Sin Chew subdomains are NOT separately registered."),
    ),

    # ---- 11. Malaysia (Chinese, HTML listing) — A2.2-D -------------------
    # eNanyang / 南洋商报 — sister paper of Sin Chew Daily, also part
    # of the same publisher family but with its own canonical domain
    # (enanyang.my, NOT a sinchew.com.my subdomain).
    #
    # Live-verified 2026-09-30 (https://www.enanyang.my/, sha12
    # 29c349994c0b, byte-identical across 3 consecutive fetches):
    # 6 unique /news/20260930/{Section}/{numeric_id} articles per
    # fetch (4 Finance, 1 International, 1 State). All titles
    # extracted from <img alt="TITLE"> inside a Swiper carousel.
    # No <h1>/<h2>/<h3> article cards on the homepage. 0 <time>
    # tags, 0 datetime= attributes, 0 relative time strings — the
    # listing page emits published_at=None for all 6 stories (per
    # spec rule).
    #
    # Tier: **C** (NOT B). Per Chinese Source Discovery Audit,
    # eNanyang was flagged as Tier-C candidate / NEEDS
    # VALIDATION. A2.2-D validation-first probe confirms the
    # borderline classification:
    #
    #   - Volume 6 is below typical Tier-B threshold (10+ items).
    #   - published_at is None for every story (no timestamp data).
    #   - 90.5% of homepage URLs are navigation (57/63 are
    #     /category/{section}/{subsection} nav links; only 6 are
    #     article URLs).
    #   - Despite being a 100-year-old established national outlet
    #     (南洋商报, since 1923), the website implementation is
    #     sparse.
    #
    # WP-JSON / RSS / sitemap all 404; vega.enanyang.my is the
    # WordPress CDN host but the JSON API is disabled. Joined
    # registry in A2.2-D (2026-09-30).
    Source(
        name="eNanyang",
        type=SourceType.HTML_LISTING,
        url="https://www.enanyang.my/",
        reliability=3,  # Tier C: lower than Tier B's reliability=4
        country="MY",
        languages=[Language.ZH],
        tier=SourceTier.C,
        notes=("Custom-CMS HTML listing page. Chinese. National "
               "Malaysian Chinese daily (南洋商报, since 1923). "
               "Only ~6 articles on the homepage (Swiper carousel "
               "with <img alt='TITLE'> as title source; no "
               "<h1>/<h2>/<h3> cards). published_at=None for every "
               "story (listing has no timestamp). 90.5% of homepage "
               "URLs are navigation, only 6 are articles. Tier C "
               "(NEEDS VALIDATION cleared in A2.2-D but volume + "
               "no-timestamp = borderline). Joined registry in "
               "A2.2-D (2026-09-30). Sin Chew family but separate "
               "canonical domain. Verification engine treats Tier C "
               "as fallback 'Tier C or single lower-tier coverage -> "
               "REPORTED' with confidence 0.30 (vs Tier-B 0.60)."),
    ),
]


def load_sources() -> List[Source]:
    """Return the current registered source list."""
    return list(REGISTERED_SOURCES)


def get_registered_source(name: str) -> Source | None:
    for s in REGISTERED_SOURCES:
        if s.name == name:
            return s
    return None


def source_tier_map() -> Dict[str, str]:
    """Convenience: name -> tier letter, used by the verification engine."""
    return {s.name: s.tier.value for s in REGISTERED_SOURCES}
