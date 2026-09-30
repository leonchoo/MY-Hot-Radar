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

Current mix:

  International anchor (English, RSS)         BBC News Asia       Tier B
  Regional Asia (English, RSS)                Channel News Asia   Tier B
  Malaysian health-policy (English, RSS)      CodeBlue            Tier B
  Malaysian news in Bahasa Malaysia (RSS)     FMT Bahasa          Tier B
  Malaysian regional news (English, RSS)      Borneo Post         Tier B
  Malaysian Chinese news (WP-JSON)            Kwong Wah Yit Poh   Tier B
  Malaysian Chinese news (WP-JSON)            Guang Ming Daily    Tier B
  Malaysian Chinese Johor news (HTML)         Sin Chew Johor desk Tier B

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

We deliberately do NOT register (per probe results):
  - The Star, NST, Malay Mail, Malaysiakini, FMT English, Astro Awani,
    The Edge: their public RSS endpoints return 404 or SSL errors at
    this time. Re-probe before considering them.
  - BERNAMA / PMO / Sarawakvoice: SSL / 403 / 404 at this time.
  - Sin Chew / China Press / eNanyang: HTML-listing sources requiring
    a separate HTML adapter (deferred to A2.2 / future batches).
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
               "~16-38 dated article URLs on the homepage. "
               "Joined registry in A2.2-A (2026-09-30). "
               "Listing page only carries relative time strings, "
               "so published_at=None by default. "
               "Cross-language dedup works via the A1 Chinese "
               "place-name aliases (马来西亚 / 新加坡 / 吉隆坡 / "
               "柔佛 / 新山 / 马新 / 新马). "
               "Sin Chew Main (https://www.sinchew.com.my/) is a "
               "separate source requiring its own HTML adapter; "
               "deferred to a future batch."),
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
