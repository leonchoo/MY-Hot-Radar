# MY Hot Radar — Project Context

> Long-lived project context for the MY Hot Radar website + future News Radar work.
> Read this first when starting any task on this project.

---

## Project

**MY Hot Radar** — a Malaysia-focused trending / viral topic radar (MVP stage).

Goal:
- Surface **what is heating up now**, not just what already happened.
- Built as a static-first site; the eventual News Radar will feed it.

---

## Brand

| Property | Value |
|---|---|
| English brand | **MY Hot Radar** |
| Chinese brand | **MY 热点雷达** |
| Tagline (EN) | Malaysia's Trending Radar — what is heating up now. |
| Tagline (ZH) | 发现正在升温的话题。 |
| Wordmark colors | `#0a0a0a` + `#ffffff` + `#e11d2a` (accent) |
| Logo files | `assets/img/logo.svg`, `assets/img/logo-mark.svg` |
| Favicon | `assets/img/favicon.svg` |
| OG default image | `assets/img/og-default.svg` (1200×630) |

---

## Website

| Property | Value |
|---|---|
| Canonical apex | `https://myhotradar.com` |
| Also active | `https://www.myhotradar.com` (no apex→www redirect enforced yet) |
| Hosting | Cloudflare Pages project `my-hot-radar` |
| Source-of-truth branch | `master` |
| Auto-deploy | via Cloudflare Pages GitHub integration (must be ON) |
| Sitemap | `/sitemap.xml` (12 URLs, apex only) |
| robots.txt | Cloudflare-managed (Content-Signal enabled) |
| Privacy/Terms | present, MVP-honest |

---

## Facebook

| Property | Value |
|---|---|
| Page id | `61594550116065` |
| URL | `https://www.facebook.com/profile.php?id=61594550116065` |
| Target username | `@myhotradar` (if available) |
| Content language | Chinese first; mixed EN + Bahasa Malaysia acceptable |
| Brand line on FB | MY 热点雷达 · Hot Radar |

> Facebook posting is **manual only**. No API integration yet.

---

## Positioning

Malaysia-focused trending / viral topic radar concept.

Core idea:
> 「发现正在升温的话题，而不只是复制已经发生的新闻。」

The site positions itself against "traditional news sites" by promising
detection of momentum, not just delivery of headlines.

---

## Current Stage

**MVP** — the static site is live and deployed.

Important constraints:

- **All currently displayed stories are SAMPLE / DEMO** — explicit and labelled.
- Site does **not** yet run a live radar / crawler.
- Site does **not** yet have a newsroom, editor team, or real-time signals.
- Site serves the demo layout, design system, and information architecture.
- The News Radar system is **planned**, **not implemented**.

---

## Main Categories (5)

| Key | Display | Chinese |
|---|---|---|
| `malaysia` | Malaysia | 马来西亚 |
| `viral` | Viral | 网络爆红 |
| `celebrity` | Celebrity | 娱乐圈 |
| `food` | Food & Lifestyle | 美食 · 生活 |
| `world` | World | 国际 |

Plus the **Hot Now** aggregator (`hot/`) and the **Article** demo (`article/example/`).

---

## Brand Colors

| Name | Hex | Use |
|---|---|---|
| Brand black | `#0a0a0a` | Background, body text |
| Brand white | `#ffffff` | Surfaces, inversion |
| HOT red | `#e11d2a` | Primary accent, "HOT" / breaking signals |
| RISING orange | `#f59e0b` | Secondary accent, "RISING" / warming signals |

Muted gray `#6B7280` is used as supporting metadata tone (defined in `style.css`).

---

## Website Architecture (actual current state)

```
C:\MY-Hot-Radar
├── index.html                  Homepage
├── partials.html               Internal component reference
├── README.md                   Public-facing project README
├── sitemap.xml                 12-URL sitemap (apex only)
├── .gitignore
├── hot/index.html              Hot Now category
├── malaysia/index.html         Malaysia category
├── viral/index.html            Viral category
├── celebrity/index.html        Celebrity category
├── food/index.html             Food & Lifestyle category
├── world/index.html            World category
├── article/example/index.html  Demo article detail
├── about/index.html            About (MVP-honest)
├── contact/index.html          Contact (no fake info)
├── privacy/index.html          Privacy Policy (MVP-honest)
├── terms/index.html            Terms of Use (MVP-honest)
└── assets/
    ├── css/style.css           Single shared stylesheet
    ├── js/main.js              Tiny vanilla JS (mobile nav, year fill)
    └── img/
        ├── logo.svg            Full wordmark + mark
        ├── logo-mark.svg       Symbol-only
        ├── favicon.svg         Tab icon
        └── og-default.svg      1200×630 social card
```

**Total public pages**: 12 HTML page + 1 OG image + 1 sitemap + 3 logo SVGs + 1 shared CSS + 1 shared JS.

---

## Future Direction (planned, NOT built)

The following items belong to the **Roadmap**, not to the current state.
They MUST NOT be described as live features anywhere on the site or social.

- Live data ingestion (News Radar engine)
- Topic clustering and momentum scoring
- Cross-source verification pipeline
- Article CMS or post-publishing workflow
- Newsletter signup
- Comments / community features
- Facebook auto-publishing
- Multi-language localization (Bahasa Melayu / English / 中文)
- Real analytics beyond Cloudflare Web Analytics
- AI-assisted draft generation (not until Radar stage I)

When these exist, they graduate out of this section into the
relevant state documents.

---

## Document Map

This file lives in a memory pack. Read order before a task:

| Task kind | Files to read |
|---|---|
| Website / UI / HTML edit | this file + `DEVELOPMENT_RULES.md` |
| News Radar / crawler / scoring | this file + `DEVELOPMENT_RULES.md` + `NEWS_RADAR.md` + `CONTENT_RULES.md` + `VERIFICATION_RULES.md` |
| Content production / Facebook posts | this file + `CONTENT_RULES.md` |
| Verifying past decisions / evolution | this file + `EXPERIENCE.md` |

The remaining documents:

- `DEVELOPMENT_RULES.md` — strict development rules (git, code style, content).
- `NEWS_RADAR.md` — design-only specification of the future Radar pipeline.
- `CONTENT_RULES.md` — voice, label, and status rules for any published content.
- `VERIFICATION_RULES.md` — how the Radar will verify and score topics.
- `EXPERIENCE.md` — verified, reusable lessons from past batches.
