#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the Static Article Publishing Pipeline (scripts/publish_article.py).

Coverage:
  - generator unit tests
  - invalid input tests
  - duplicate slug test
  - duplicate canonical test
  - overwrite protection test
  - dry-run test
  - sitemap update test
  - category update test
  - HTML metadata test
  - JSON-LD test
  - Chinese content test
  - path traversal test

All tests are run against a TEMPORARY copy of the project tree (via
PYTHON_TMP_ROOT env var or a per-test temporary directory). No test
mutates the real MY-Hot-Radar repo on disk.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "publish_article.py"


VALID_SAMPLE = {
    "slug": "sample-static-pipeline-test",
    "title": "Sample Static Pipeline Test Article",
    "deck": "SAMPLE / TEST — pipeline verification only.",
    "category": "hot",
    "published_at": "2026-10-01T10:00:00+08:00",
    "updated_at": "2026-10-01T10:00:00+08:00",
    "author": "MY Hot Radar (pipeline test)",
    "source_name": "MY Hot Radar Pipeline Test",
    "source_url": "https://myhotradar.com/about/",
    "excerpt": "Pipeline verification only — SAMPLE / TEST.",
    "tags": ["sample", "test", "pipeline"],
    "status": "WATCH",
    "sample_flag": True,
    "canonical_url": "https://myhotradar.com/article/sample-static-pipeline-test/",
    "body": (
        "## 这是 sample / test 文章\n\n"
        "本篇文章只是 MY Hot Radar 静态发布管线的技术验证。\n\n"
        "本文**不包含任何真实新闻**。所有出现的人名、机构名、数字、链接、"
        "时间都是测试桩，仅用于验证 HTML 生成、metadata、JSON-LD、sitemap、"
        "category 索引、mobile layout、Chinese rendering、HTTP 200 路径。"
    ),
}


def make_tmp_repo() -> Path:
    """Create a temp copy of the repo (no radar_data, no public, no docs).

    Only the parts the script writes to / reads from are copied:
      - article/example/index.html
      - {category}/index.html for each category
      - sitemap.xml
      - assets/css/style.css
      - _redirects
    """
    tmp = Path(tempfile.mkdtemp(prefix="sap_test_"))
    # Copy minimum viable site
    for sub in ("article", "hot", "malaysia", "viral", "celebrity", "food",
                "world", "assets"):
        src = REPO_ROOT / sub
        if src.is_dir():
            shutil.copytree(src, tmp / sub)
    for fname in ("sitemap.xml", "_redirects"):
        src = REPO_ROOT / fname
        if src.exists():
            shutil.copy2(src, tmp / fname)
    # Make scripts/ containing the publish tool
    scripts_dst = tmp / "scripts"
    scripts_dst.mkdir()
    shutil.copy2(SCRIPT_PATH, scripts_dst / "publish_article.py")
    return tmp


def write_input(tmp: Path, article: dict, name: str = "input.json") -> Path:
    p = tmp / name
    p.write_text(json.dumps(article, ensure_ascii=False), encoding="utf-8")
    return p


def run_publish(tmp: Path, input_path: Path, *args: str) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable, "scripts/publish_article.py",
        "--input", str(input_path.relative_to(tmp)),
        "--root", str(tmp),
        *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(tmp))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSlugAndValidation(unittest.TestCase):
    def test_valid_slug_accepted(self):
        a = dict(VALID_SAMPLE)
        a["slug"] = "hasmah-passing-2026"
        from scripts.publish_article import validate_input
        validate_input(a)  # no raise

    def test_empty_slug_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["slug"] = ""
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_uppercase_slug_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["slug"] = "Hasmah-Passing"
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_underscore_slug_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["slug"] = "hasmah_passing"
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_path_traversal_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["slug"] = "../etc/passwd"
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_path_traversal_subdir_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["slug"] = "foo/bar"
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_long_slug_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["slug"] = "a" * 100
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_empty_body_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["body"] = ""
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_short_body_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["body"] = "too short"
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_invalid_canonical_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["canonical_url"] = "https://example.com/article/x/"
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_invalid_source_url_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["source_url"] = "ftp://example.com/"
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_bad_date_format_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["published_at"] = "2026-10-01"
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_unknown_category_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        a["category"] = "breaking"  # not in CATEGORY_KEYS
        with self.assertRaises(PublishError):
            validate_input(a)

    def test_missing_field_rejected(self):
        from scripts.publish_article import validate_input, PublishError
        a = dict(VALID_SAMPLE)
        del a["body"]
        with self.assertRaises(PublishError):
            validate_input(a)


class TestHtmlGeneration(unittest.TestCase):
    def setUp(self):
        from scripts.publish_article import build_full_html
        self.html = build_full_html(VALID_SAMPLE, VALID_SAMPLE["canonical_url"])

    def test_has_doctype(self):
        self.assertTrue(self.html.startswith("<!doctype html>"))

    def test_has_title(self):
        self.assertIn("<title>", self.html)
        self.assertIn(VALID_SAMPLE["title"], self.html)

    def test_has_meta_description(self):
        self.assertIn('name="description"', self.html)
        self.assertIn(VALID_SAMPLE["deck"], self.html)

    def test_has_canonical(self):
        self.assertIn('rel="canonical"', self.html)
        self.assertIn(VALID_SAMPLE["canonical_url"], self.html)

    def test_has_og_title(self):
        self.assertIn('property="og:title"', self.html)
        self.assertIn(VALID_SAMPLE["title"], self.html)

    def test_has_og_description(self):
        self.assertIn('property="og:description"', self.html)

    def test_has_og_url(self):
        self.assertIn('property="og:url"', self.html)
        self.assertIn(VALID_SAMPLE["canonical_url"], self.html)

    def test_has_article_published_time(self):
        self.assertIn('property="article:published_time"', self.html)
        self.assertIn(VALID_SAMPLE["published_at"], self.html)

    def test_has_article_modified_time(self):
        self.assertIn('property="article:modified_time"', self.html)
        self.assertIn(VALID_SAMPLE["updated_at"], self.html)

    def test_has_newsarticle_jsonld(self):
        m = re.search(
            r'<script type="application/ld\+json">(.+?)</script>',
            self.html, re.DOTALL,
        )
        self.assertIsNotNone(m, "NewsArticle JSON-LD not found")
        ld = json.loads(m.group(1))
        self.assertEqual(ld["@type"], "NewsArticle")
        self.assertEqual(ld["headline"], VALID_SAMPLE["title"])
        self.assertEqual(ld["datePublished"], VALID_SAMPLE["published_at"])
        self.assertEqual(ld["dateModified"], VALID_SAMPLE["updated_at"])
        self.assertEqual(ld["url"], VALID_SAMPLE["canonical_url"])
        self.assertIn("publisher", ld)
        self.assertEqual(ld["publisher"]["name"], "MY Hot Radar")

    def test_has_main_entity_of_page(self):
        m = re.search(
            r'<script type="application/ld\+json">(.+?)</script>',
            self.html, re.DOTALL,
        )
        ld = json.loads(m.group(1))
        self.assertIn("mainEntityOfPage", ld)
        self.assertEqual(
            ld["mainEntityOfPage"]["@id"], VALID_SAMPLE["canonical_url"]
        )

    def test_has_isbasedon_source(self):
        m = re.search(
            r'<script type="application/ld\+json">(.+?)</script>',
            self.html, re.DOTALL,
        )
        ld = json.loads(m.group(1))
        self.assertIn("isBasedOn", ld)
        self.assertEqual(ld["isBasedOn"]["url"], VALID_SAMPLE["source_url"])

    def test_chinese_body_preserved(self):
        self.assertIn("这是 sample / test 文章", self.html)
        self.assertIn("技术验证", self.html)

    def test_h2_and_p_rendered(self):
        self.assertIn("<h2>", self.html)
        self.assertIn("<p>", self.html)

    def test_html_escapes_special_chars_in_title(self):
        from scripts.publish_article import build_full_html
        a = dict(VALID_SAMPLE)
        a["title"] = "Hasmah <script>alert(1)</script>"
        html = build_full_html(a, a["canonical_url"])
        # Visible HTML tags must escape: <title>, <h1>, <meta og:title>,
        # <meta twitter:title>. The JSON-LD <script> is application/ld+json
        # so its content is data, not HTML — there it MUST remain a raw JSON
        # string (no entity escaping) so the JSON parser can read it.
        self.assertIn("<title>Hasmah &lt;script&gt;", html)
        self.assertIn('og:title" content="Hasmah &lt;script&gt;', html)
        # JSON-LD must contain the raw string (escaped only as JSON)
        ld_match = re.search(
            r'<script type="application/ld\+json">(.+?)</script>',
            html, re.DOTALL,
        )
        ld = json.loads(ld_match.group(1))
        self.assertEqual(ld["headline"], "Hasmah <script>alert(1)</script>")

    def test_sample_flag_marks_eyebrow(self):
        self.assertIn("SAMPLE · PIPELINE TEST", self.html)

    def test_status_badge_rendered(self):
        self.assertIn('class="badge', self.html)

    def test_mvp_disclaimer_present(self):
        self.assertIn("mvp-note", self.html)
        self.assertIn("MVP stage", self.html)


class TestEndToEndDryRun(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        tmp = make_tmp_repo()
        try:
            inp = write_input(tmp, VALID_SAMPLE)
            r = run_publish(tmp, inp, "--dry-run", "--update-category",
                            "--update-sitemap")
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            self.assertIn("DRY-RUN", r.stdout)
            # No new article created
            self.assertFalse(
                (tmp / "article" / VALID_SAMPLE["slug"] / "index.html").exists()
            )
            # Sitemap unchanged
            sitemap_after = (tmp / "sitemap.xml").read_text(encoding="utf-8")
            sitemap_before = (REPO_ROOT / "sitemap.xml").read_text(encoding="utf-8")
            self.assertEqual(sitemap_after, sitemap_before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestEndToEndApply(unittest.TestCase):
    def setUp(self):
        self.tmp = make_tmp_repo()
        self.inp = write_input(self.tmp, VALID_SAMPLE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_apply_creates_article(self):
        r = run_publish(self.tmp, self.inp, "--update-category",
                        "--update-sitemap")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        article = self.tmp / "article" / VALID_SAMPLE["slug"] / "index.html"
        self.assertTrue(article.exists())

    def test_apply_updates_sitemap(self):
        r = run_publish(self.tmp, self.inp, "--update-category",
                        "--update-sitemap")
        self.assertEqual(r.returncode, 0)
        sm = (self.tmp / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn(VALID_SAMPLE["canonical_url"], sm)

    def test_apply_updates_category(self):
        r = run_publish(self.tmp, self.inp, "--update-category",
                        "--update-sitemap")
        self.assertEqual(r.returncode, 0)
        hot = (self.tmp / "hot" / "index.html").read_text(encoding="utf-8")
        self.assertIn(f"/article/{VALID_SAMPLE['slug']}/", hot)

    def test_apply_creates_backup_of_category(self):
        r = run_publish(self.tmp, self.inp, "--update-category",
                        "--update-sitemap")
        self.assertEqual(r.returncode, 0)
        backups = list((self.tmp / "hot").glob("*.bak.*"))
        self.assertGreaterEqual(len(backups), 1)

    def test_apply_creates_backup_of_sitemap(self):
        r = run_publish(self.tmp, self.inp, "--update-sitemap")
        self.assertEqual(r.returncode, 0)
        backups = list(self.tmp.glob("sitemap.xml.bak.*"))
        self.assertGreaterEqual(len(backups), 1)

    def test_apply_appends_audit_log(self):
        log = self.tmp / "scripts" / ".publish_log.json"
        if log.exists():
            log.unlink()
        r = run_publish(self.tmp, self.inp, "--update-category",
                        "--update-sitemap")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(log.exists())
        entries = json.loads(log.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(entries), 1)
        self.assertEqual(entries[-1]["slug"], VALID_SAMPLE["slug"])


class TestOverwriteProtection(unittest.TestCase):
    def test_double_publish_blocked(self):
        tmp = make_tmp_repo()
        try:
            inp = write_input(tmp, VALID_SAMPLE)
            r1 = run_publish(tmp, inp, "--update-category", "--update-sitemap")
            self.assertEqual(r1.returncode, 0, msg=r1.stderr)

            # Second run with same input must fail
            r2 = run_publish(tmp, inp, "--update-category", "--update-sitemap")
            self.assertNotEqual(r2.returncode, 0)
            self.assertIn("already exists", r2.stdout + r2.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_writing_into_existing_dir_blocked(self):
        tmp = make_tmp_repo()
        try:
            # Pre-create the article dir
            (tmp / "article" / VALID_SAMPLE["slug"]).mkdir(parents=True)
            (tmp / "article" / VALID_SAMPLE["slug"] / "index.html").write_text(
                "preexisting", encoding="utf-8"
            )
            inp = write_input(tmp, VALID_SAMPLE)
            r = run_publish(tmp, inp, "--update-category", "--update-sitemap")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("already exists", r.stdout + r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSitemapUpdate(unittest.TestCase):
    def test_sitemap_idempotent_on_duplicate_url(self):
        tmp = make_tmp_repo()
        try:
            sm_path = tmp / "sitemap.xml"
            original = sm_path.read_text(encoding="utf-8")
            # Manually inject the URL
            injected = original.replace(
                "</urlset>",
                f'  <url>\n    <loc>{VALID_SAMPLE["canonical_url"]}</loc>\n'
                f'    <changefreq>monthly</changefreq>\n    <priority>0.5</priority>\n'
                f'  </url>\n</urlset>',
                1,
            )
            sm_path.write_text(injected, encoding="utf-8")
            inp = write_input(tmp, VALID_SAMPLE)
            r = run_publish(tmp, inp, "--update-category", "--update-sitemap")
            # Should fail with duplicate canonical
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("already in sitemap", r.stdout + r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestProtectedPaths(unittest.TestCase):
    def test_apply_does_not_touch_radar(self):
        """--apply (no --dry-run) must not write to public/radar/latest.json
        (or anything outside the article + category + sitemap surface)."""
        tmp = make_tmp_repo()
        try:
            # Create a fake public/radar/latest.json — script must not write it
            public = tmp / "public"
            radar = public / "radar"
            radar.mkdir(parents=True)
            radar_json = radar / "latest.json"
            original = '{"sha":"b03d848cb3b7ff26320bedcd6d44b6070f99b93f53efcf3bd9a2909dab497edf","protected":true}'
            radar_json.write_text(original, encoding="utf-8")

            inp = write_input(tmp, VALID_SAMPLE)
            r = run_publish(tmp, inp, "--update-category", "--update-sitemap")
            self.assertEqual(r.returncode, 0, msg=r.stderr + r.stdout)
            after = radar_json.read_text(encoding="utf-8")
            self.assertEqual(after, original)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestChineseContent(unittest.TestCase):
    def test_chinese_body_unchanged_in_output(self):
        tmp = make_tmp_repo()
        try:
            inp = write_input(tmp, VALID_SAMPLE)
            r = run_publish(tmp, inp, "--update-category", "--update-sitemap")
            self.assertEqual(r.returncode, 0)
            html = (
                tmp / "article" / VALID_SAMPLE["slug"] / "index.html"
            ).read_text(encoding="utf-8")
            # Chinese characters must round-trip cleanly
            self.assertIn("这是 sample / test 文章", html)
            self.assertIn("技术验证", html)
            self.assertIn("MY Hot Radar", html)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCategoryBackLink(unittest.TestCase):
    def test_back_link_in_article_body(self):
        from scripts.publish_article import build_full_html
        html = build_full_html(VALID_SAMPLE, VALID_SAMPLE["canonical_url"])
        self.assertIn('href="/hot/"', html)
        self.assertIn("Back to", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
