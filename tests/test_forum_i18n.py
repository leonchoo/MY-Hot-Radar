#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Forum v2 中文 i18n (Phase 4 — 中文新闻室).

Coverage (per 彪哥's spec):
  1. Topic 中文标题
  2. Event 中文 description
  3. Collector 中文 observation
  4. Radar 中文 update
  5. Performance 中文 report
  6. Default 中文 editorial note
  7. English / Malay source produces Chinese Forum content
  8. Machine fields stay English
  9. JSON schema compatibility

Rules:
  - Human-readable content (note, summary, decision) becomes bilingual.
  - Schema keys / agent IDs / status / event_type stay English.
  - Existing English content preserved under "en" key.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import forum_v2  # noqa: E402
import forum_i18n  # noqa: E402
import forum_integration  # noqa: E402


class TempI18nEnv:
    """Isolated forum root for i18n tests."""

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="i18n_test_"))
        self.forum_root = self.tmp / "forum"
        self.forum_root.mkdir()
        (self.forum_root / "outbox").mkdir()
        for sub in ["collector", "radar", "default", "mhr_performance", "hermes"]:
            (self.forum_root / "inbox" / sub).mkdir(parents=True)
        (self.forum_root / "state").mkdir()
        self._saved = (forum_v2.DEFAULT_FORUM_ROOT, forum_integration.DEFAULT_FORUM_ROOT)
        forum_v2.DEFAULT_FORUM_ROOT = self.forum_root
        forum_integration.DEFAULT_FORUM_ROOT = self.forum_root
        return self

    def __exit__(self, *exc):
        forum_v2.DEFAULT_FORUM_ROOT, forum_integration.DEFAULT_FORUM_ROOT = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def paths(self):
        return forum_v2.ForumV2Paths(self.forum_root)


# ===========================================================================
# 1. Topic 中文标题
# ===========================================================================

class TestChineseTopicTitle(unittest.TestCase):
    """Topic 中文标题测试."""

    def test_english_title_translates(self):
        zh = forum_i18n.translate_title("Najib house arrest starts")
        self.assertEqual(zh, "纳吉居家监禁开始")

    def test_malay_title_translates(self):
        zh = forum_i18n.translate_title("Jerebu meningkat di Johor")
        self.assertEqual(zh, "柔佛烟霾情况恶化")

    def test_chinese_title_passes_through(self):
        zh = forum_i18n.translate_title("纳吉居家监禁开始")
        # Chinese input preserved (we never re-translate)
        self.assertEqual(zh, "纳吉居家监禁开始")

    def test_unknown_title_preserved_as_is(self):
        # No fabrication: unknown English titles kept as-is
        zh = forum_i18n.translate_title("Some unknown event description")
        self.assertEqual(zh, "Some unknown event description")

    def test_partial_translation_via_keywords(self):
        # Even without exact dict match, keyword-level translation applies
        zh = forum_i18n.translate_title("MCMC WhatsApp complaints about Meta")
        self.assertIn("MCMC", zh)
        self.assertIn("WhatsApp", zh)
        self.assertIn("Meta", zh)

    def test_topic_payload_carries_title_i18n(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="Najib house arrest starts",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            # Topic title is stored raw (English) for backward compat
            self.assertEqual(topic.title, "Najib house arrest starts")
            # payload gets bilingual title_i18n
            self.assertIn("title_i18n", evt.payload)
            ti = evt.payload["title_i18n"]
            self.assertEqual(ti["en"], "Najib house arrest starts")
            self.assertEqual(ti["zh"], "纳吉居家监禁开始")


# ===========================================================================
# 2. Event 中文 description
# ===========================================================================

class TestChineseEventDescription(unittest.TestCase):
    """Event 中文 description 测试."""

    def test_collector_observation_note_bilingual(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="Test title",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            self.assertIsInstance(note, dict)
            self.assertIn("en", note)
            self.assertIn("zh", note)
            # Chinese version is not empty
            self.assertTrue(note["zh"])
            # English version is the original message
            self.assertIn("Collector", note["en"])

    def test_social_heat_signal_note_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Heat test topic",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            forum_integration.default_emit_close(
                topic_id=topic.topic_id, reason="test", paths=env.paths()
            )
            _, evt = forum_integration.collector_emit_social_heat_signal(
                title="Heat test topic",
                evidence={"heat_score": 0.95},
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            self.assertIn("zh", note)
            # Heat-score-based Chinese text
            self.assertIn("热度", note["zh"])


# ===========================================================================
# 3. Collector 中文 observation
# ===========================================================================

class TestChineseCollectorObservation(unittest.TestCase):
    """Collector 中文 observation 测试."""

    def test_collector_emit_note_chinese(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="Collector test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            # Chinese text contains 中文 keywords
            self.assertIn("发现", note["zh"])


# ===========================================================================
# 4. Radar 中文 update
# ===========================================================================

class TestChineseRadarUpdate(unittest.TestCase):
    """Radar 中文 update 测试."""

    def test_radar_source_note_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Radar test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            _, evt, _ = forum_integration.radar_emit_source_update(
                radar_topic_id="t1",
                title="Radar test",
                source_url="https://bernama.com/x",
                source_name="Bernama",
                language="en",
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            self.assertIn("Bernama", note["zh"])

    def test_radar_classification_note_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Classify test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            _, evt = forum_integration.radar_emit_classification_update(
                topic_id=topic.topic_id,
                classification="BREAKING",
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            self.assertIn("BREAKING", note["zh"])

    def test_radar_momentum_note_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Momentum test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            # rising: delta 0.6
            _, evt = forum_integration.radar_emit_momentum_update(
                topic_id=topic.topic_id,
                delta_score=0.6,
                window="4h",
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            self.assertIn("上升", note["zh"])

    def test_radar_cross_source_note_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Cross-source test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            _, evt = forum_integration.radar_emit_cross_source_confirmation(
                topic_id=topic.topic_id,
                source_url="https://cna.com/x",
                source_name="CNA",
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            self.assertIn("CNA", note["zh"])


# ===========================================================================
# 5. Performance 中文 report
# ===========================================================================

class TestChinesePerformanceReport(unittest.TestCase):
    """Performance 中文 report 测试."""

    def test_performance_emit_report_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Perf test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            _, evt = forum_integration.performance_emit_report(
                topic_id=topic.topic_id,
                velocity="rising",
                engagement="medium",
                window="24h",
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            self.assertIn("上升", note["zh"])
            # velocity field is still English
            self.assertEqual(evt.payload.get("velocity"), "rising")
            # window field is still English
            self.assertEqual(evt.payload.get("window"), "24h")

    def test_performance_sustained_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Sustained test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            _, evt = forum_integration.performance_emit_sustained(
                topic_id=topic.topic_id,
                duration_hours=24.0,
                sources_increasing=True,
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            self.assertIn("持续", note["zh"])

    def test_performance_cooling_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Cooling test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            _, evt = forum_integration.performance_emit_cooling(
                topic_id=topic.topic_id, window="24h", paths=env.paths()
            )
            note = evt.payload.get("note")
            self.assertIn("下降", note["zh"])


# ===========================================================================
# 6. Default 中文 editorial note
# ===========================================================================

class TestChineseDefaultEditorialNote(unittest.TestCase):
    """Default 中文 editorial note 测试."""

    def test_default_review_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Editorial test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            _, evt = forum_integration.default_emit_editorial_review(
                topic_id=topic.topic_id, note="", paths=env.paths()
            )
            note = evt.payload.get("note")
            self.assertIn("zh", note)
            self.assertTrue(note["zh"])

    def test_default_publish_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Publish test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            forum_integration.default_emit_editorial_review(
                topic_id=topic.topic_id, note="", paths=env.paths()
            )
            _, evt = forum_integration.default_emit_publish(
                topic_id=topic.topic_id,
                canonical_url="https://myhotradar.com/article/test/",
                slug="test",
                paths=env.paths(),
            )
            note = evt.payload.get("note")
            self.assertIn("发布", note["zh"])

    def test_default_close_chinese(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Close test",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            forum_integration.default_emit_editorial_review(
                topic_id=topic.topic_id, note="", paths=env.paths()
            )
            _, evt = forum_integration.default_emit_close(
                topic_id=topic.topic_id, reason="coverage cooled", paths=env.paths()
            )
            note = evt.payload.get("note")
            self.assertIn("关闭", note["zh"])


# ===========================================================================
# 7. English / Malay source produces Chinese Forum content
# ===========================================================================

class TestMultilingualSource(unittest.TestCase):
    """English / Malay source 仍可正确产生中文 Forum 内容."""

    def test_english_source(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="Jerebu makin pulih, 8 kawasan catat IPU tak sihat",
                evidence={"source": "test"},
                paths=env.paths(),
            )
            ti = evt.payload.get("title_i18n", {})
            self.assertIn("zh", ti)
            # Malay title gets translated to Chinese
            self.assertIn("烟霾", ti["zh"])

    def test_malay_source(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="Najib house arrest starts",
                evidence={"source": "Bernama"},
                paths=env.paths(),
            )
            ti = evt.payload.get("title_i18n", {})
            self.assertEqual(ti["zh"], "纳吉居家监禁开始")

    def test_chinese_source_passes_through(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="敦斯里哈斯玛逝世",
                evidence={"source": "Bernama"},
                paths=env.paths(),
            )
            ti = evt.payload.get("title_i18n", {})
            self.assertEqual(ti["zh"], "敦斯里哈斯玛逝世")
            self.assertEqual(ti["en"], "敦斯里哈斯玛逝世")


# ===========================================================================
# 8. Machine fields stay English
# ===========================================================================

class TestMachineFieldsEnglish(unittest.TestCase):
    """Machine fields 保持英文."""

    def test_agent_id_english(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="Test", evidence={"source": "test"}, paths=env.paths()
            )
            self.assertEqual(evt.agent, "collector")

    def test_event_type_english(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="Test", evidence={"source": "test"}, paths=env.paths()
            )
            self.assertEqual(evt.event_type, "CREATE_TOPIC")

    def test_schema_keys_english(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="Test", evidence={"source": "test"}, paths=env.paths()
            )
            # Topic fields
            topic_dict = topic.to_dict()
            for key in ("topic_id", "status", "classification", "first_seen",
                        "last_seen", "source_count", "languages",
                        "participants", "linkage_key", "events_count", "tags"):
                self.assertIn(key, topic_dict, f"missing key {key}")
            # Event fields
            for key in ("event_id", "topic_id", "agent", "event_type",
                        "timestamp", "payload", "evidence", "confidence"):
                self.assertIn(key, evt.to_dict(), f"missing key {key}")

    def test_machine_payload_fields_english(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Test", evidence={"source": "test"}, paths=env.paths()
            )
            _, evt, _ = forum_integration.radar_emit_source_update(
                radar_topic_id="t1", title="Test",
                source_url="https://b.com/x", source_name="Bernama",
                language="en", paths=env.paths()
            )
            p = evt.payload
            # Machine fields stay English
            self.assertEqual(p["radar_topic_id"], "t1")
            self.assertEqual(p["url"], "https://b.com/x")
            self.assertEqual(p["source_name"], "Bernama")
            self.assertEqual(p["language"], "en")
            # Human-readable field is bilingual dict
            self.assertIsInstance(p["note"], dict)
            self.assertIn("zh", p["note"])

    def test_status_enum_english(self):
        with TempI18nEnv() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Test", evidence={"source": "test"}, paths=env.paths()
            )
            self.assertEqual(topic.status, "NEW")
            self.assertEqual(topic.classification, "WATCH")


# ===========================================================================
# 9. JSON schema compatibility
# ===========================================================================

class TestJSONSchemaCompatibility(unittest.TestCase):
    """JSON schema 保持兼容."""

    def test_topic_json_serializable(self):
        with TempI18nEnv() as env:
            topic, evt, _, _ = forum_integration.collector_emit_observation(
                title="Schema test", evidence={"source": "test"}, paths=env.paths()
            )
            # Read back from disk
            topic_path = env.forum_root / "topics" / topic.topic_id / "topic.json"
            data = json.loads(topic_path.read_text(encoding="utf-8"))
            # All keys are strings (JSON-serializable)
            for key, value in data.items():
                self.assertIsInstance(key, str)
                if key == "title":
                    self.assertIsInstance(value, str)
            # Event also JSON-serializable
            events_path = env.forum_root / "topics" / topic.topic_id / "events.jsonl"
            for line in events_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    ed = json.loads(line)
                    for key in ("event_id", "topic_id", "agent", "event_type"):
                        self.assertIn(key, ed)
                        self.assertIsInstance(ed[key], str)

    def test_bilingual_dict_is_json_serializable(self):
        # {"en": ..., "zh": ...} dicts are JSON-friendly
        b = forum_i18n.bilingual("Hello", "你好")
        s = json.dumps(b, ensure_ascii=False)
        loaded = json.loads(s)
        self.assertEqual(loaded["en"], "Hello")
        self.assertEqual(loaded["zh"], "你好")

    def test_is_bilingual(self):
        self.assertTrue(forum_i18n.is_bilingual({"en": "x", "zh": "y"}))
        self.assertFalse(forum_i18n.is_bilingual({"x": 1, "y": 2}))
        self.assertFalse(forum_i18n.is_bilingual("plain string"))
        self.assertFalse(forum_i18n.is_bilingual(None))


# ===========================================================================
# 10. i18n module unit tests
# ===========================================================================

class TestI18nModule(unittest.TestCase):
    """i18n module 直接 unit 测试."""

    def test_bilingual_helper(self):
        b = forum_i18n.bilingual("Hello", "你好")
        self.assertEqual(b["en"], "Hello")
        self.assertEqual(b["zh"], "你好")

    def test_render_bilingual(self):
        b = forum_i18n.bilingual("Hello", "你好")
        self.assertEqual(forum_i18n.render_bilingual(b, "en"), "Hello")
        self.assertEqual(forum_i18n.render_bilingual(b, "zh"), "你好")
        # Fallback to en if zh missing
        b2 = {"en": "only"}
        self.assertEqual(forum_i18n.render_bilingual(b2, "zh"), "only")

    def test_zh_text_extractor(self):
        b = forum_i18n.bilingual("Hello", "你好")
        self.assertEqual(forum_i18n.zh_text(b), "你好")
        self.assertEqual(forum_i18n.zh_text("plain"), "plain")

    def test_contains_chinese(self):
        self.assertTrue(forum_i18n._contains_chinese("你好"))
        self.assertTrue(forum_i18n._contains_chinese("Hello 你好"))
        self.assertFalse(forum_i18n._contains_chinese("Hello"))
        self.assertFalse(forum_i18n._contains_chinese("1234"))

    def test_i18n_payload_preserves_existing_bilingual(self):
        existing = forum_i18n.bilingual("Original", "原")
        payload = {"note": existing, "other": "stuff"}
        wrapped = forum_i18n.i18n_payload(payload)
        # Existing bilingual preserved
        self.assertEqual(wrapped["note"], existing)
        self.assertEqual(wrapped["other"], "stuff")

    def test_i18n_payload_converts_plain_string(self):
        payload = {"note": "hello"}
        wrapped = forum_i18n.i18n_payload(payload)
        self.assertIsInstance(wrapped["note"], dict)
        self.assertEqual(wrapped["note"]["en"], "hello")
        self.assertEqual(wrapped["note"]["zh"], "暂无中文说明。")


# ===========================================================================
# 11. 政治 guardrail 测试
# ===========================================================================

class TestPoliticalGuardrails(unittest.TestCase):
    """政治新闻遵守现有 guardrails: 不做政治排名,不写未证实事件。"""

    def test_political_title_no_fabrication(self):
        # 政治事件标题不会生成虚假信息
        zh = forum_i18n.translate_title("Najib house arrest starts")
        # Says "纳吉居家监禁开始" — translates the action factually
        self.assertEqual(zh, "纳吉居家监禁开始")
        # Does NOT contain evaluative language
        for word in ("好人", "坏人", "优秀", "腐败"):
            self.assertNotIn(word, zh)

    def test_malaysian_political_title_translated(self):
        zh = forum_i18n.translate_title("Najib house arrest starts 2026-09-19")
        # "纳吉" appears (name), no political evaluation
        self.assertIn("纳吉", zh)
        # No political ranking words
        for word in ("排名", "领先", "落后"):
            self.assertNotIn(word, zh)


if __name__ == "__main__":
    unittest.main(verbosity=2)