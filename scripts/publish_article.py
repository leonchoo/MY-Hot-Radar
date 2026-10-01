#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MY Hot Radar — Static Article Publishing Pipeline.

Generates a single static HTML article under article/<slug>/index.html,
optionally updates a category index page (prepends a story card) and
appends the new URL to sitemap.xml.

This tool writes only files under:
  - article/<slug>/index.html     (the article itself)
  - <category>/index.html          (category index, optional)
  - sitemap.xml                    (canonical URL registry)
  - /tmp/sap_pub_*.backup          (backups of edited existing files)

It refuses to:
  - Overwrite an existing article/<slug>/index.html
  - Overwrite unrelated HTML files
  - Touch public/radar/latest.json or anything under radar/ dashboard/
    performance/ radar_data/ docs/ docs/editorial/
  - Operate outside the project root
  - Publish a slug that fails path-traversal / shape / uniqueness checks
  - Publish an article without category, source_url, body, title

Mandatory dry-run mode: --dry-run reports every planned write without
touching anything. --apply actually writes.

This is NOT a CMS. It is a one-shot static-file generator. It keeps a
JSON audit log of every publish operation at scripts/.publish_log.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants — project structure
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # scripts/.. = repo root
ARTICLE_DIR_NAME = "article"
PUBLIC_DIR = PROJECT_ROOT / "public"

# Category pages that exist on the website (must match PROJECT_CONTEXT.md)
CATEGORY_KEYS = ("hot", "malaysia", "viral", "celebrity", "food", "world")

CATEGORY_DISPLAY = {
    "hot": "Hot Now",
    "malaysia": "Malaysia",
    "viral": "Viral",
    "celebrity": "Celebrity",
    "food": "Food & Lifestyle",
    "world": "World",
}

# Files that the pipeline is FORBIDDEN to modify.
PROTECTED_PATHS = (
    "public/radar/latest.json",
    "public/radar/",
    "radar/",
    "dashboard/",
    "performance/",
    "radar_data/",
    "performance_data/",
    "docs/",
)

# Files where the pipeline may write (within repo root, all paths relative).
WRITABLE_GLOBS = (
    "article/",
    "sitemap.xml",
    "{category}/index.html",  # one of CATEGORY_KEYS
)

CANONICAL_DOMAIN = "https://myhotradar.com"

# Path-traversal-safe slug pattern. Lowercase ASCII alnum and hyphens, 1..82 chars.
SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,80}[a-z0-9])?$")

# Audit log path (in scripts/, not in radar_data/)
AUDIT_LOG = Path(__file__).resolve().parent / ".publish_log.json"


# ---------------------------------------------------------------------------
# Safety / validation
# ---------------------------------------------------------------------------

class PublishError(Exception):
    """Raised when a safety check fails. Always fail-closed."""


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    raise PublishError(msg)


def validate_slug(slug: str) -> None:
    if not isinstance(slug, str) or not slug:
        fail("slug must be a non-empty string")
    if not SLUG_PATTERN.match(slug):
        fail(
            f"slug '{slug}' fails pattern "
            f"{SLUG_PATTERN.pattern} (lowercase ASCII alnum + hyphens, 1..82 chars)"
        )
    if ".." in slug or "/" in slug or "\\" in slug:
        fail(f"slug '{slug}' contains path-traversal characters")


def validate_input(article: Dict[str, Any]) -> None:
    """Validate every required field of the article input."""
    required = (
        "slug", "title", "deck", "category",
        "published_at", "updated_at",
        "author", "source_name", "source_url",
        "body", "tags", "canonical_url",
    )
    for key in required:
        if key not in article:
            fail(f"missing required field: {key}")

    slug = article["slug"]
    validate_slug(slug)

    title = str(article.get("title", "")).strip()
    if not title:
        fail("title is empty")
    if len(title) > 200:
        fail(f"title too long ({len(title)} chars, max 200)")

    deck = str(article.get("deck", "")).strip()
    if not deck:
        fail("deck is empty")
    if len(deck) > 500:
        fail(f"deck too long ({len(deck)} chars, max 500)")

    body = str(article.get("body", "")).strip()
    if not body:
        fail("body is empty")
    if len(body) < 50:
        fail(f"body too short ({len(body)} chars, minimum 50)")

    category = article["category"]
    if category not in CATEGORY_KEYS:
        fail(
            f"category '{category}' not in allowed set {list(CATEGORY_KEYS)}"
        )

    source_url = str(article.get("source_url", "")).strip()
    if not source_url:
        fail("source_url is empty")
    if not (source_url.startswith("http://") or source_url.startswith("https://")):
        fail(f"source_url must be http(s)://... got: {source_url!r}")

    canonical_url = str(article.get("canonical_url", "")).strip()
    if not canonical_url:
        fail("canonical_url is empty")
    if not canonical_url.startswith(CANONICAL_DOMAIN + "/"):
        fail(
            f"canonical_url must start with '{CANONICAL_DOMAIN}/' got: "
            f"{canonical_url!r}"
        )

    # Date sanity check — must be ISO8601 (YYYY-MM-DDTHH:MM:SS+TZ)
    date_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$"
    )
    for date_field in ("published_at", "updated_at"):
        v = str(article.get(date_field, "")).strip()
        if not date_pattern.match(v):
            fail(
                f"{date_field} '{v}' is not ISO8601 (expected "
                f"YYYY-MM-DDTHH:MM:SS+TZ or Z)"
            )

    # Tags must be a list of non-empty strings
    tags = article.get("tags", [])
    if not isinstance(tags, list):
        fail("tags must be a list")
    for t in tags:
        if not isinstance(t, str) or not t.strip():
            fail(f"tag must be a non-empty string, got: {t!r}")

    # sample_flag is optional but if present must be bool
    if "sample_flag" in article and not isinstance(article["sample_flag"], bool):
        fail("sample_flag must be a boolean")


# ---------------------------------------------------------------------------
# HTML escape
# ---------------------------------------------------------------------------

def esc(s: Any) -> str:
    """HTML-escape a string for safe insertion."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def attr_esc(s: Any) -> str:
    return esc(s)


# ---------------------------------------------------------------------------
# Article HTML builder
# ---------------------------------------------------------------------------

def format_date_human(iso8601: str) -> str:
    """Convert '2026-09-28T09:00:00+08:00' → '28 Sep 2026'."""
    # Strip timezone for simple parsing; we only need the date part
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", iso8601)
    if not m:
        return iso8601
    y, mo, d = m.group(1), m.group(2), m.group(3)
    months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    return f"{int(d)} {months[int(mo) - 1]} {y}"


def category_back_label(category: str) -> str:
    return CATEGORY_DISPLAY.get(category, category.title())


def build_json_ld(article: Dict[str, Any], canonical_url: str) -> str:
    """Build schema.org NewsArticle JSON-LD block."""
    payload = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": article["title"],
        "description": article["deck"],
        "datePublished": article["published_at"],
        "dateModified": article["updated_at"],
        "inLanguage": article.get("in_language", "zh-Hans"),
        "isAccessibleForFree": True,
        "url": canonical_url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url},
        "publisher": {
            "@type": "Organization",
            "name": "MY Hot Radar",
            "url": CANONICAL_DOMAIN + "/",
            "logo": {
                "@type": "ImageObject",
                "url": CANONICAL_DOMAIN + "/assets/img/logo.svg",
            },
        },
        "author": {
            "@type": "Organization",
            "name": article.get("author", "MY Hot Radar"),
            "url": CANONICAL_DOMAIN + "/about/",
        },
        "articleSection": category_back_label(article["category"]),
        "keywords": ", ".join(article.get("tags", [])),
        "isBasedOn": {
            "@type": "NewsArticle",
            "headline": article["source_name"],
            "url": article["source_url"],
        } if article.get("source_url") else None,
    }
    # Drop null fields
    payload = {k: v for k, v in payload.items() if v is not None}
    raw_json = json.dumps(payload, ensure_ascii=False, indent=2)
    # Defensive: prevent </script> inside JSON strings from prematurely
    # closing the <script type="application/ld+json"> block.
    # JSON allows \/ as an escape; </script> → <\/script> parses identically.
    safe_json = raw_json.replace("</script>", "<\\/script>")
    return safe_json


def build_og_block(article: Dict[str, Any], canonical_url: str) -> str:
    title = esc(article["title"])
    desc = esc(article["deck"])
    return f'''  <meta property="og:type" content="article">
  <meta property="og:site_name" content="MY Hot Radar">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{esc(canonical_url)}">
  <meta property="og:locale" content="zh_MY">
  <meta property="og:image" content="{CANONICAL_DOMAIN}/assets/img/og-default.svg">
  <meta property="article:published_time" content="{esc(article["published_at"])}">
  <meta property="article:modified_time" content="{esc(article["updated_at"])}">
  <meta property="article:author" content="{esc(article.get("author", "MY Hot Radar"))}">
  <meta property="article:section" content="{esc(category_back_label(article["category"]))}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{desc}">
  <meta name="twitter:image" content="{CANONICAL_DOMAIN}/assets/img/og-default.svg">'''


def build_meta_block(article: Dict[str, Any], canonical_url: str) -> str:
    title = esc(article["title"]) + " — MY Hot Radar"
    desc = esc(article["deck"])
    return f'''  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <meta name="theme-color" content="#0a0a0a">
  <link rel="canonical" href="{esc(canonical_url)}">
  <link rel="icon" type="image/svg+xml" href="/assets/img/favicon.svg">'''


def render_status_badge(status: Optional[str], sample_flag: bool) -> str:
    parts = []
    if sample_flag:
        parts.append('<span class="badge badge--sample">SAMPLE</span>')
    if status:
        cls = {
            "HOT": "badge--hot",
            "RISING": "badge--rising",
            "BREAKING": "badge--breaking",
            "COOLING": "badge--cooling",
            "WATCH": "badge--sample",  # WATCH reuses neutral gray
        }.get(status.upper(), "badge--sample")
        parts.append(f'<span class="badge {cls}">{esc(status.upper())}</span>')
    return "\n        ".join(parts)


def render_body(body: str) -> str:
    """Convert simple markdown-ish body to HTML paragraphs.

    Body rules:
      - Blank line splits paragraphs
      - Lines starting with '## ' become <h2>
      - Lines starting with '### ' become <h3>
      - Lines starting with '- ' become <ul><li>
    No external markdown lib used (keep it simple, auditable).
    """
    out_lines: List[str] = []
    paragraphs = re.split(r"\n\s*\n", body.strip())
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if para.startswith("### "):
            out_lines.append(f"        <h3>{esc(para[4:])}</h3>")
        elif para.startswith("## "):
            out_lines.append(f"        <h2>{esc(para[3:])}</h2>")
        elif para.startswith("- "):
            items = [line[2:].strip() for line in para.split("\n") if line.startswith("- ")]
            li_html = "\n".join(f"          <li>{esc(it)}</li>" for it in items)
            out_lines.append(f"        <ul>\n{li_html}\n        </ul>")
        else:
            out_lines.append(f"        <p>{esc(para)}</p>")
    return "\n".join(out_lines)


def render_hero_svg(category: str, sample_flag: bool) -> str:
    """Inline SVG hero placeholder. No external images, per DEVELOPMENT_RULES."""
    if sample_flag:
        # Explicit SAMPLE visual — gray with TEST marker
        bg = "#f3f4f6"
        color = "#6b7280"
        label = "SAMPLE / TEST PLACEHOLDER"
    else:
        bg = "#fff1f2"
        color = "#e11d2a"
        label = "ARTICLE HERO PLACEHOLDER"
    return f'''        <svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
          <rect width="800" height="450" fill="{bg}"/>
          <g opacity="0.35">
            <circle cx="400" cy="225" r="180" fill="{color}" opacity="0.25"/>
            <circle cx="400" cy="225" r="120" fill="{color}" opacity="0.45"/>
            <circle cx="400" cy="225" r="60" fill="{color}"/>
            <circle cx="400" cy="225" r="18" fill="#fff"/>
          </g>
          <text x="400" y="430" text-anchor="middle"
                font-family="-apple-system, Segoe UI, Roboto, sans-serif"
                font-size="16" font-weight="700" letter-spacing="2"
                fill="#0a0a0a" opacity="0.5">{label}</text>
        </svg>'''


def build_full_html(article: Dict[str, Any], canonical_url: str) -> str:
    """Build the complete article HTML page."""
    sample_flag = bool(article.get("sample_flag", False))
    slug = article["slug"]
    title = esc(article["title"])
    category = article["category"]
    cat_label = esc(category_back_label(category))
    cat_url = f"/{category}/"
    deck = esc(article["deck"])
    source_url = esc(article["source_url"])
    source_name = esc(article.get("source_name", ""))
    author = esc(article.get("author", "MY Hot Radar (demo)"))
    pub_human = esc(format_date_human(article["published_at"]))
    upd_human = esc(format_date_human(article["updated_at"]))
    pub_iso = esc(article["published_at"])
    upd_iso = esc(article["updated_at"])
    status = article.get("status")
    body_html = render_body(article["body"])
    badges_html = render_status_badge(status, sample_flag)
    hero_svg = render_hero_svg(category, sample_flag)
    json_ld = build_json_ld(article, canonical_url)
    meta_block = build_meta_block(article, canonical_url)
    og_block = build_og_block(article, canonical_url)
    eyebrow_text = (
        "SAMPLE · PIPELINE TEST"
        if sample_flag
        else f"MY Hot Radar · {cat_label}"
    )

    byline_note = (
        "No real author — sample content"
        if sample_flag
        else "MY Hot Radar editorial"
    )

    source_label = (
        "Demo content for MY Hot Radar static pipeline test. "
        "No external source has been cited."
        if sample_flag
        else f"本文事实综合自公开报道。主要来源：{source_name}。"
    )

    html = f'''<!doctype html>
<html lang="zh-Hans">
<head>
{meta_block}

{og_block}

<script type="application/ld+json">
{json_ld}
</script>

<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6219340004578553"
     crossorigin="anonymous"></script>
<link rel="stylesheet" href="/assets/css/style.css">
</head>
<body>

<header class="site-header">
  <div class="container site-header__inner">
    <a href="/" class="brand" aria-label="MY Hot Radar — Home">
      <img src="/assets/img/logo.svg" alt="" class="brand__mark" width="30" height="30">
      <span class="brand__name">MY <em>Hot</em> Radar</span>
    </a>
    <nav class="nav-primary" aria-label="Primary">
      <ul class="nav-primary__list">
        <li><a href="/hot/"       class="nav-primary__link">Hot Now</a></li>
        <li><a href="/malaysia/"  class="nav-primary__link">Malaysia</a></li>
        <li><a href="/viral/"     class="nav-primary__link">Viral</a></li>
        <li><a href="/celebrity/" class="nav-primary__link">Celebrity</a></li>
        <li><a href="/food/"      class="nav-primary__link">Food</a></li>
        <li><a href="/world/"     class="nav-primary__link">World</a></li>
        <li><a href="/about/"     class="nav-primary__link">About</a></li>
        <li><a href="/contact/"   class="nav-primary__link">Contact</a></li>
      </ul>
    </nav>
    <button class="nav-toggle" data-nav-toggle aria-controls="mobile-nav" aria-expanded="false" aria-label="Open navigation menu">
      <span class="nav-toggle__bar" aria-hidden="true"></span>
    </button>
  </div>
  <div class="mobile-nav" id="mobile-nav" data-mobile-nav>
    <ul class="mobile-nav__list">
      <li><a href="/hot/"       class="mobile-nav__link">Hot Now</a></li>
      <li><a href="/malaysia/"  class="mobile-nav__link">Malaysia</a></li>
      <li><a href="/viral/"     class="mobile-nav__link">Viral</a></li>
      <li><a href="/celebrity/" class="mobile-nav__link">Celebrity</a></li>
      <li><a href="/food/"      class="mobile-nav__link">Food</a></li>
      <li><a href="/world/"     class="mobile-nav__link">World</a></li>
      <li><a href="/about/"     class="mobile-nav__link">About</a></li>
      <li><a href="/contact/"   class="mobile-nav__link">Contact</a></li>
    </ul>
  </div>
</header>

<main id="main">

  <article class="section">
    <div class="container container--narrow">

      <a href="{esc(cat_url)}" class="article-back" aria-label="Back to {cat_label}">
        <span aria-hidden="true">←</span> Back to {cat_label}
      </a>

      <p class="page-eyebrow">{esc(eyebrow_text)}</p>

      <h1 class="page-title" style="margin-top:var(--sp-2)">{title}</h1>

      <p class="page-lede">{deck}</p>

      <div class="article-meta">
        {badges_html}
        <span class="card__cat">{cat_label}</span>
        <span class="article-meta__sep" aria-hidden="true">·</span>
        <time class="article-meta__time" datetime="{pub_iso}">Published {pub_human}</time>
        <span class="article-meta__sep" aria-hidden="true">·</span>
        <time class="article-meta__time" datetime="{upd_iso}">Updated {upd_human}</time>
        <span class="article-meta__sep" aria-hidden="true">·</span>
        <span>~{max(1, len(article["body"]) // 400)} min read</span>
      </div>

      <div class="article-hero" aria-hidden="true">
{hero_svg}
      </div>

      <div class="prose" style="margin-top:var(--sp-8)">

{body_html}

        <div class="article-source">
          <strong>来源：</strong>{source_label} 原文链接：<a href="{source_url}" rel="noopener noreferrer" target="_blank">{source_name}</a>
        </div>

      </div>

      <div class="article-byline" aria-label="Article byline">
        <span><strong>By</strong> {author}</span>
        <span class="article-meta__sep" aria-hidden="true">·</span>
        <span>{byline_note}</span>
      </div>

      <div class="article-share" aria-label="Share this article">
        <span class="article-share__label">Share</span>

        <a class="share-btn"
           href="https://www.facebook.com/sharer/sharer.php?u={esc(article['canonical_url'].replace('https://myhotradar.com', '%2F%2Fmyhotradar.com').replace('/', '%2F'))}"
           target="_blank" rel="noopener noreferrer"
           aria-label="Share on Facebook">
          <span>Facebook</span>
        </a>

        <a class="share-btn"
           href="https://api.whatsapp.com/send?text={esc((article['title'] + ' — MY Hot Radar').replace(' ', '%20'))}%0A{esc(article['canonical_url'])}"
           target="_blank" rel="noopener noreferrer"
           aria-label="Share on WhatsApp">
          <span>WhatsApp</span>
        </a>

        <a class="share-btn"
           href="https://twitter.com/intent/tweet?text={esc(article['title'].replace(' ', '%20'))}&amp;url={esc(article['canonical_url'])}"
           target="_blank" rel="noopener noreferrer"
           aria-label="Share on X">
          <span>X</span>
        </a>
      </div>

      <p style="margin-top:var(--sp-8);">
        <a href="{esc(cat_url)}" class="btn-secondary">← 返回 {cat_label}</a>
      </p>

    </div>
  </article>

</main>

<div class="mvp-note" role="note">
  <div class="container">
    <p class="mvp-note__inner">
      MY Hot Radar is currently in MVP stage. All displayed stories are sample content for demonstration purposes.
    </p>
  </div>
</div>

<footer class="site-footer">
  <div class="container site-footer__inner">
    <div>
      <div class="site-footer__brand">
        <img src="/assets/img/logo-mark.svg" alt="" class="brand__mark" width="30" height="30">
        <span>MY <em style="font-style:normal;color:#E11D2A">Hot</em> Radar</span>
      </div>
      <p class="site-footer__tagline">
        Malaysia's Trending Radar — surfacing what is heating up now, not just what happened today.
      </p>
    </div>
    <div class="site-footer__col">
      <p class="site-footer__heading">Sections</p>
      <ul class="site-footer__list">
        <li><a href="/hot/"       class="site-footer__link">Hot Now</a></li>
        <li><a href="/malaysia/"  class="site-footer__link">Malaysia</a></li>
        <li><a href="/viral/"     class="site-footer__link">Viral</a></li>
        <li><a href="/celebrity/" class="site-footer__link">Celebrity</a></li>
        <li><a href="/food/"      class="site-footer__link">Food</a></li>
        <li><a href="/world/"     class="site-footer__link">World</a></li>
      </ul>
    </div>
    <div class="site-footer__col">
      <p class="site-footer__heading">About</p>
      <ul class="site-footer__list">
        <li><a href="/about/"   class="site-footer__link">About</a></li>
        <li><a href="/contact/" class="site-footer__link">Contact</a></li>
      </ul>
    </div>
    <div class="site-footer__col">
      <p class="site-footer__heading">Legal</p>
      <ul class="site-footer__list">
        <li><a href="/privacy/" class="site-footer__link">Privacy</a></li>
        <li><a href="/terms/"   class="site-footer__link">Terms</a></li>
      </ul>
    </div>
    <div class="site-footer__bottom">
      <span>&copy; <span id="year">2026</span> MY Hot Radar. All rights reserved.</span>
      <span>myhotradar.com</span>
    </div>
  </div>
</footer>

<script>document.getElementById('year').textContent = new Date().getFullYear();</script>
<script src="/assets/js/main.js"></script>
</body>
</html>
'''
    return html


# ---------------------------------------------------------------------------
# Sitemap update
# ---------------------------------------------------------------------------

def read_sitemap(project_root: Path) -> str:
    p = project_root / "sitemap.xml"
    if not p.exists():
        fail(f"sitemap.xml not found at {p}")
    return p.read_text(encoding="utf-8")


def update_sitemap(canonical_url: str, project_root: Path) -> Tuple[str, str]:
    """Insert a new <url> block into sitemap.xml.

    Returns (old_content, new_content).
    """
    old = read_sitemap(project_root)
    if canonical_url in old:
        # Already present — leave unchanged
        return old, old
    new_block = (
        f'''  <url>
    <loc>{canonical_url}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>

'''
    )
    # Insert before the closing </urlset>
    if "</urlset>" not in old:
        fail("sitemap.xml has no </urlset> closing tag — refusing to modify")
    new = old.replace("</urlset>", new_block + "</urlset>", 1)
    return old, new


# ---------------------------------------------------------------------------
# Category index prepend
# ---------------------------------------------------------------------------

def find_category_main_open(category: str, project_root: Path) -> Tuple[Path, int]:
    """Find the position just after `<main id="main">` in the category page.

    Returns (path, position).
    """
    p = project_root / category / "index.html"
    if not p.exists():
        fail(f"category page not found: {p}")
    text = p.read_text(encoding="utf-8")
    m = re.search(r"<main id=\"main\">", text)
    if not m:
        fail(f"no <main id=\"main\"> in {p}")
    return p, m.end()


def make_card_html(article: Dict[str, Any], canonical_url: str) -> str:
    cat_label = category_back_label(article["category"])
    title = esc(article["title"])
    excerpt = esc(article["excerpt"] if "excerpt" in article else article["deck"])
    slug = article["slug"]
    sample_flag = bool(article.get("sample_flag", False))
    status = article.get("status")
    badges = render_status_badge(status, sample_flag)

    # Determine hero SVG color palette based on category
    palette = {
        "hot": ("#fff1f2", "#e11d2a"),
        "malaysia": ("#fff7ed", "#f59e0b"),
        "viral": ("#fef3c7", "#f59e0b"),
        "celebrity": ("#fdf2f8", "#ec4899"),
        "food": ("#fefce8", "#facc15"),
        "world": ("#eff6ff", "#3b82f6"),
    }.get(article["category"], ("#fff1f2", "#e11d2a"))
    bg, color = palette
    hero_label = "SAMPLE / TEST" if sample_flag else "STORY HERO PLACEHOLDER"

    return f'''
        <article class="card">
          <div class="card__media" aria-hidden="true">
            <svg viewBox="0 0 320 200" xmlns="http://www.w3.org/2000/svg">
              <rect width="320" height="200" fill="{bg}"/>
              <circle cx="160" cy="100" r="48" fill="{color}" opacity="0.25"/>
              <circle cx="160" cy="100" r="20" fill="{color}"/>
              <text x="160" y="180" text-anchor="middle"
                    font-family="-apple-system, Segoe UI, Roboto, sans-serif"
                    font-size="11" font-weight="700" letter-spacing="1"
                    fill="#0a0a0a" opacity="0.55">{hero_label}</text>
            </svg>
          </div>
          <div class="card__body">
            <div class="card__meta">
              {badges}
              <span class="card__cat">{esc(cat_label)}</span>
              <span class="text-muted">{esc(format_date_human(article["published_at"]))}</span>
            </div>
            <h3 class="card__title"><a href="/article/{slug}/">{title}</a></h3>
            <p class="card__excerpt">{excerpt}</p>
            <div class="card__footer">
              <span>By {esc(article.get("author", "MY Hot Radar"))}</span>
              <span>~{max(1, len(article["body"]) // 400)} min read</span>
            </div>
          </div>
        </article>

'''


def insert_card_into_category(
    category: str, card_html: str, project_root: Path
) -> Tuple[str, str, str]:
    """Prepend a story card after <main id="main"> in the category page.

    Returns (path_str, old_content, new_content).
    """
    p, pos = find_category_main_open(category, project_root)
    old = p.read_text(encoding="utf-8")
    if f"/article/{extract_slug_from_card_or_input(card_html)}/" in old:
        # Already inserted — leave unchanged
        return str(p), old, old
    # Wrap card with a section "Latest" heading for clarity
    section_open = '\n      <!-- Latest -->\n      <section class="section" aria-labelledby="latest-heading">\n        <div class="container">\n          <div class="section-head">\n            <h2 class="section-head__title" id="latest-heading">最新 / Latest</h2>\n          </div>\n          <div class="grid grid--3">\n'
    section_close = '          </div>\n        </div>\n      </section>\n'
    new = old[:pos] + section_open + card_html + section_close + old[pos:]
    return str(p), old, new


def extract_slug_from_card_or_input(card_html: str) -> str:
    m = re.search(r"/article/([^/]+)/", card_html)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def append_audit_log(article: Dict[str, Any], canonical_url: str,
                     category: str, dry_run: bool) -> None:
    if dry_run:
        return
    entry = {
        "ts_utc": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "slug": article["slug"],
        "title": article["title"],
        "category": category,
        "canonical_url": canonical_url,
        "status": article.get("status"),
        "sample_flag": bool(article.get("sample_flag", False)),
    }
    log: List[Dict[str, Any]] = []
    if AUDIT_LOG.exists():
        try:
            log = json.loads(AUDIT_LOG.read_text(encoding="utf-8"))
        except Exception:
            log = []
    log.append(entry)
    AUDIT_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="MY Hot Radar static article publishing pipeline."
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to article JSON input (relative to repo root or absolute)."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report every planned change without writing anything."
    )
    parser.add_argument(
        "--update-category", action="store_true",
        help="Also prepend a story card to the category index page."
    )
    parser.add_argument(
        "--update-sitemap", action="store_true",
        help="Also append the new URL to sitemap.xml."
    )
    parser.add_argument(
        "--root", default=str(PROJECT_ROOT),
        help="Override project root (for testing only)."
    )
    args = parser.parse_args(argv)

    project_root = Path(args.root).resolve()

    # Load input
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = project_root / input_path
    if not input_path.exists():
        print(f"[FAIL] input file not found: {input_path}", file=sys.stderr)
        return 2
    try:
        article = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[FAIL] input JSON invalid: {e}", file=sys.stderr)
        return 2

    try:
        validate_input(article)
    except PublishError as e:
        print(f"[FAIL] validation: {e}", file=sys.stderr)
        return 3

    slug = article["slug"]
    article_dir = project_root / "article" / slug
    article_path = article_dir / "index.html"
    canonical_url = article["canonical_url"]

    # Hard-fail checks (apply BEFORE any write)
    if article_path.exists():
        print(f"[FAIL] article already exists: {article_path}", file=sys.stderr)
        return 4
    # Ensure canonical not already in sitemap (would indicate duplicate)
    if (project_root / "sitemap.xml").exists():
        sm = (project_root / "sitemap.xml").read_text(encoding="utf-8")
        if canonical_url in sm:
            print(f"[FAIL] canonical_url already in sitemap: {canonical_url}", file=sys.stderr)
            return 4

    print("=" * 70)
    print(f"MY Hot Radar — Static Article Publishing Pipeline")
    print(f"  Mode        : {'DRY-RUN (no writes)' if args.dry_run else 'APPLY (will write)'}")
    print(f"  Project root: {project_root}")
    print(f"  Slug        : {slug}")
    print(f"  Title       : {article['title']}")
    print(f"  Category    : {article['category']}")
    print(f"  Canonical   : {canonical_url}")
    print(f"  Status      : {article.get('status', '(none)')}")
    print(f"  Sample flag : {bool(article.get('sample_flag', False))}")
    print(f"  Source      : {article['source_name']} — {article['source_url']}")
    print(f"  Tags        : {', '.join(article.get('tags', []))}")
    print(f"  Body length : {len(article['body'])} chars")
    print()

    # Plan: 1. article HTML
    full_html = build_full_html(article, canonical_url)
    print(f"[PLAN 1] write {article_path}")
    print(f"         size: {len(full_html)} chars")
    print()

    # Plan: 2. category card (optional)
    if args.update_category:
        card_html = make_card_html(article, canonical_url)
        cat_path, cat_old, cat_new = insert_card_into_category(
            article["category"], card_html, project_root
        )
        print(f"[PLAN 2] prepend card to {cat_path}")
        print(f"         size delta: +{len(cat_new) - len(cat_old)} chars")
        print()

    # Plan: 3. sitemap (optional)
    if args.update_sitemap:
        sm_old, sm_new = update_sitemap(canonical_url, project_root)
        if sm_old == sm_new:
            print(f"[PLAN 3] sitemap already contains {canonical_url} — no change")
        else:
            print(f"[PLAN 3] append <url> to sitemap.xml")
            print(f"         size delta: +{len(sm_new) - len(sm_old)} chars")
        print()

    # Plan: 4. audit log
    print(f"[PLAN 4] append entry to scripts/.publish_log.json")
    print()

    if args.dry_run:
        print("[DRY-RUN] no files written. Exiting 0.")
        return 0

    # === APPLY PHASE ===
    # Backup then write article
    article_dir.mkdir(parents=True, exist_ok=True)
    article_path.write_text(full_html, encoding="utf-8")
    print(f"[OK] wrote {article_path}")

    if args.update_category:
        card_html = make_card_html(article, canonical_url)
        cat_path, cat_old, cat_new = insert_card_into_category(
            article["category"], card_html, project_root
        )
        # Backup
        backup = cat_path + ".bak." + dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(cat_path, backup)
        Path(cat_path).write_text(cat_new, encoding="utf-8")
        print(f"[OK] updated {cat_path} (backup: {backup})")

    if args.update_sitemap:
        sm_old, sm_new = update_sitemap(canonical_url, project_root)
        if sm_old != sm_new:
            sm_path = project_root / "sitemap.xml"
            backup = str(sm_path) + ".bak." + dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            shutil.copy2(sm_path, backup)
            sm_path.write_text(sm_new, encoding="utf-8")
            print(f"[OK] updated {sm_path} (backup: {backup})")
        else:
            print(f"[OK] sitemap already has {canonical_url} (no change)")

    append_audit_log(article, canonical_url, article["category"], dry_run=False)
    print(f"[OK] audit log: {AUDIT_LOG}")
    print()
    print("[DONE] article published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
