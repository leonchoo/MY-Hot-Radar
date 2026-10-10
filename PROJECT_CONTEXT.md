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
| Sitemap | `/sitemap.xml` (25 URLs, apex only) |
| robots.txt | Cloudflare-managed (Content-Signal enabled) |
| Privacy/Terms | present, real Simplified Chinese (rewritten 2026-10-10) |

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

**MVP 演示阶段已结束**（2026-10-10 全站整改后，站点已发布正式真实文章并移除占位/Demo 页面）。

Important constraints:

- **正式发布的真实文章已上线**（2026-10 起 16 篇）；`DEMO / SAMPLE` 标记仅适用于显式标记的演示内容。
- Site does **not** yet run a live radar / crawler (still true).
- Site does **not** yet have real-time signals; the editorial workflow is rule-driven
  (see the Document Map / Agent entry rules above).
- Site serves the demo layout, design system, and information architecture.
- The News Radar system is **planned**, **not implemented**.

---

## Main Categories (current)

| Key | Display | Chinese |
|---|---|---|
| `malaysia` | Malaysia | 马来西亚 |
| `world` | World | 国际新闻 |
| `hot` | Hot Now | 热门头条 |
| `all` | All | 全部新闻 |

`viral` / `celebrity` / `food` 占位分类与 `article/example/` 演示页已于 2026-10-10
随全站整改移除，不再是公开栏目。

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

> **Agent 入口指引（binding）**：所有处理新闻选题、采编、写作、内容、分类、网站发布或
> 线上验证的 Agent，在执行任务前必须先阅读本文件（含下方 Document Map），
> 并按任务类型读取对应规则文件：
>
> - **本地（马来西亚）新闻**的选题、采编与写作任务：先阅读 `docs/LOCAL_NEWS_EDITORIAL_RULES.md`（本地新闻编辑规则）。
> - **国际新闻**选题与采编任务：读取 `NEWS_RADAR.md`（国际新闻选题与核实）。
> - **国际新闻**写作任务：读取 `CONTENT_RULES.md`（含国际新闻编辑规则）。
> - 发布与线上验收任务：读取 `VERIFICATION_RULES.md`（发布后线上验收）。
> - **发现规则冲突时，先报告冲突并等待裁决，不得自行选择性忽略。**
> - **上述规则不因更换 Agent、模型或会话而失效。**
> - 所有 Agent 遵循本项目的 `DEVELOPMENT_RULES.md` 与 `EXPERIENCE.md` 治理规则。

This file lives in a memory pack. Read order before a task:

| Task kind | Files to read |
|---|---|
| Website / UI / HTML edit | this file + `DEVELOPMENT_RULES.md` |
| News Radar / crawler / scoring | this file + `DEVELOPMENT_RULES.md` + `NEWS_RADAR.md` + `CONTENT_RULES.md` + `VERIFICATION_RULES.md` |
| 本地新闻选题 / 采编 | this file + `docs/LOCAL_NEWS_EDITORIAL_RULES.md`（本地新闻编辑规则） |
| 本地新闻写稿 | this file + `docs/LOCAL_NEWS_EDITORIAL_RULES.md` + `CONTENT_RULES.md` |
| 新闻选题 / 采编（国际新闻） | this file + `NEWS_RADAR.md`（国际新闻选题与核实）+ `VERIFICATION_RULES.md` |
| 文章写作（国际新闻） | this file + `CONTENT_RULES.md`（国际新闻编辑规则） |
| 发布与线上验收 | this file + `VERIFICATION_RULES.md`（发布后线上验收） |
| Content production / Facebook posts | this file + `CONTENT_RULES.md` |
| Verifying past decisions / evolution | this file + `EXPERIENCE.md` |

The remaining documents:

- `DEVELOPMENT_RULES.md` — strict development rules (git, code style, content).
- `NEWS_RADAR.md` — design-only specification of the future Radar pipeline.
- `CONTENT_RULES.md` — voice, label, and status rules for any published content.
- `VERIFICATION_RULES.md` — how the Radar will verify and score topics.
- `EXPERIENCE.md` — verified, reusable lessons from past batches.
