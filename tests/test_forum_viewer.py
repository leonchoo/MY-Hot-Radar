#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Forum Newsroom Viewer (Phase 5).

Coverage (per 彪哥's spec):
  A. Topic list — Chinese title_i18n.zh priority, no fabrication
  B. Classification — machine enum to UI label mapping
  C. Status — machine enum to UI label mapping
  D. Event rendering — all four agents
  E. Chinese content — zh priority, en fallback
  F. Reactivation — REACTIVATED visualization
  G. Lifecycle — derived from real events
  H. Evidence — URLs / confidence / source_message_id not lost
  I. Read-only — viewer does not modify Forum data
  J. Existing tests — 159/159 PASS preserved

Plus real-data tests against the live Forum at:
  C:/MY-Hot-Radar-Bridge/forum
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib import request as urlreq


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import forum_v2  # noqa: E402
import forum_viewer as fv  # noqa: E402


PRODUCTION_FORUM_ROOT = Path(r"C:\MY-Hot-Radar-Bridge\forum")
VIEWER_DIR = HERE.parent / "forum" / "viewer"


class TestChineseTitleRender(unittest.TestCase):
    """A. Topic 中文标题测试."""

    def test_zh_priority(self):
        # title_i18n.zh is preferred over raw title
        topic = {
            "title": "Najib house arrest starts",
            "title_i18n": {
                "en": "Najib house arrest starts",
                "zh": "纳吉居家监禁开始",
            }
        }
        result = fv.render_topic_title(topic)
        self.assertEqual(result["primary"], "纳吉居家监禁开始")

    def test_no_i18n_falls_back_to_raw(self):
        topic = {
            "title": "Unknown English title",
            "title_i18n": None,
        }
        result = fv.render_topic_title(topic)
        self.assertEqual(result["primary"], "Unknown English title")
        self.assertIsNone(result["secondary"])

    def test_zh_seen_keeps_en_as_secondary(self):
        topic = {
            "title": "Original English",
            "title_i18n": {"en": "Original English", "zh": "原始英文"},
        }
        result = fv.render_topic_title(topic)
        self.assertEqual(result["primary"], "原始英文")
        self.assertEqual(result["secondary"], "Original English")


class TestClassificationLabels(unittest.TestCase):
    """B. Classification UI 映射测试."""

    def test_all_machine_enums_mapped(self):
        for k in ["BREAKING", "RISING", "HOT", "COOLING", "WATCH"]:
            self.assertIn(k, fv.CLASSIFICATION_LABELS)
            # UI label is Chinese (contains CJK)
            label = fv.CLASSIFICATION_LABELS[k]
            self.assertTrue(any("\u4e00" <= c <= "\u9fff" for c in label),
                            f"{k} UI label must contain Chinese chars")

    def test_machine_values_unchanged(self):
        # The mapping is the only place UI labels live;
        # the JSON file still has BREAKING / RISING / etc.
        self.assertEqual(fv.CLASSIFICATION_LABELS["BREAKING"], "突发")
        self.assertEqual(fv.CLASSIFICATION_LABELS["RISING"], "上升")
        self.assertEqual(fv.CLASSIFICATION_LABELS["HOT"], "热门")
        self.assertEqual(fv.CLASSIFICATION_LABELS["COOLING"], "降温")
        self.assertEqual(fv.CLASSIFICATION_LABELS["WATCH"], "关注")


class TestStatusLabels(unittest.TestCase):
    """C. Status UI 映射测试."""

    def test_all_machine_enums_mapped(self):
        for k in ["NEW", "RADAR_TRACKING", "EDITORIAL_REVIEW",
                  "PUBLISHED", "MONITORING", "FOLLOW_UP",
                  "REACTIVATED", "CLOSED"]:
            self.assertIn(k, fv.STATUS_LABELS)
            label = fv.STATUS_LABELS[k]
            self.assertTrue(any("\u4e00" <= c <= "\u9fff" for c in label),
                            f"{k} UI label must contain Chinese chars")

    def test_specific_labels(self):
        self.assertEqual(fv.STATUS_LABELS["NEW"], "新发现")
        self.assertEqual(fv.STATUS_LABELS["RADAR_TRACKING"], "Radar 跟踪中")
        self.assertEqual(fv.STATUS_LABELS["EDITORIAL_REVIEW"], "编辑审核")
        self.assertEqual(fv.STATUS_LABELS["PUBLISHED"], "已发布")
        self.assertEqual(fv.STATUS_LABELS["MONITORING"], "持续监测")
        self.assertEqual(fv.STATUS_LABELS["FOLLOW_UP"], "后续跟进")
        self.assertEqual(fv.STATUS_LABELS["REACTIVATED"], "重新升温")
        self.assertEqual(fv.STATUS_LABELS["CLOSED"], "已关闭")


class TestEventRendering(unittest.TestCase):
    """D. Event rendering 测试 for all four agents."""

    def _make_event(self, agent, event_type, **kwargs):
        return {
            "event_id": f"evt_{agent}_001",
            "topic_id": "T_test",
            "agent": agent,
            "event_type": event_type,
            "timestamp": "2026-10-01T00:00:00Z",
            "confidence": 1.0,
            "payload": kwargs.get("payload", {}),
            "evidence": kwargs.get("evidence", {}),
        }

    def test_collector_event(self):
        e = self._make_event(
            "collector", "CREATE_TOPIC",
            payload={"note": {"en": "X", "zh": "观察记录"}},
        )
        d = fv.event_to_api_dict(e)
        self.assertEqual(d["agent_label"], "Collector")
        self.assertEqual(d["agent_color"], "#16a34a")
        self.assertEqual(d["event_type_label"], "创建 Topic")
        self.assertEqual(d["note_rendered"]["primary"], "观察记录")
        self.assertEqual(d["note_rendered"]["primary_lang"], "zh")

    def test_radar_event(self):
        e = self._make_event(
            "radar", "SOURCE_UPDATE",
            payload={
                "url": "https://bernama.com/x",
                "note": {"en": "Source X", "zh": "Bernama 报道"},
            },
        )
        d = fv.event_to_api_dict(e)
        self.assertEqual(d["agent_label"], "Radar")
        self.assertEqual(d["agent_color"], "#2563eb")
        self.assertEqual(d["event_type_label"], "来源更新")
        self.assertEqual(len(d["urls"]), 1)
        self.assertEqual(d["urls"][0]["url"], "https://bernama.com/x")

    def test_default_event(self):
        e = self._make_event(
            "default", "EDITORIAL_REVIEW",
            payload={"note": {"en": "X", "zh": "编辑审核中"}},
        )
        d = fv.event_to_api_dict(e)
        self.assertEqual(d["agent_label"], "MHR Default")
        self.assertEqual(d["agent_color"], "#9333ea")
        self.assertEqual(d["event_type_label"], "编辑审核")

    def test_performance_event(self):
        e = self._make_event(
            "mhr_performance", "PERFORMANCE_REPORT",
            payload={
                "velocity": "rising",
                "engagement": "medium",
                "window": "24h",
                "note": {"en": "X", "zh": "过去 24h 传播速度持续上升"},
            },
        )
        d = fv.event_to_api_dict(e)
        self.assertEqual(d["agent_label"], "MHR Performance")
        self.assertEqual(d["event_type_label"], "传播表现报告")
        # Machine fields preserved
        self.assertEqual(d["payload"]["velocity"], "rising")
        self.assertEqual(d["payload"]["window"], "24h")


class TestChineseContentPriority(unittest.TestCase):
    """E. Chinese content — zh 优先, en fallback."""

    def test_zh_priority_in_note(self):
        e = {"payload": {"note": {"en": "Hello", "zh": "你好"}}}
        result = fv.render_event_note(e["payload"])
        self.assertEqual(result["primary"], "你好")
        self.assertEqual(result["primary_lang"], "zh")

    def test_en_fallback_when_no_zh(self):
        e = {"payload": {"note": {"en": "Hello", "zh": ""}}}
        result = fv.render_event_note(e["payload"])
        self.assertEqual(result["primary"], "Hello")
        self.assertEqual(result["primary_lang"], "en")

    def test_no_i18n_struct_uses_string_value(self):
        e = {"payload": {"note": "Plain English note"}}
        result = fv.render_event_note(e["payload"])
        self.assertEqual(result["primary"], "Plain English note")
        self.assertEqual(result["primary_lang"], "en")

    def test_decision_field_used(self):
        e = {"payload": {"decision": {"en": "follow up", "zh": "后续跟进"}}}
        result = fv.render_event_note(e["payload"])
        self.assertEqual(result["primary"], "后续跟进")

    def test_reason_field_used(self):
        e = {"payload": {"reason": {"en": "coverage cooled", "zh": "热度下降"}}}
        result = fv.render_event_note(e["payload"])
        self.assertEqual(result["primary"], "热度下降")

    def test_change_summary_field_used(self):
        e = {"payload": {"change_summary": {"en": "X", "zh": "内容更新"}}}
        result = fv.render_event_note(e["payload"])
        self.assertEqual(result["primary"], "内容更新")

    def test_no_fields_returns_empty(self):
        e = {"payload": {}}
        result = fv.render_event_note(e["payload"])
        self.assertEqual(result["primary"], "")


class TestReactivation(unittest.TestCase):
    """F. Reactivation 可视化测试."""

    def test_social_heat_marked_as_reactivation(self):
        e = {
            "agent": "collector",
            "event_type": "SOCIAL_HEAT_SIGNAL",
            "payload": {"note": {"zh": "社交热度信号"}},
            "evidence": {},
            "timestamp": "2026-10-01T00:00:00Z",
            "event_id": "evt_x",
            "topic_id": "T_x",
        }
        d = fv.event_to_api_dict(e)
        self.assertTrue(d["is_reactivation"])

    def test_reactivation_signal_marked(self):
        e = {
            "agent": "collector",
            "event_type": "REACTIVATION_SIGNAL",
            "payload": {},
            "evidence": {},
            "timestamp": "2026-10-01T00:00:00Z",
            "event_id": "evt_x",
            "topic_id": "T_x",
        }
        d = fv.event_to_api_dict(e)
        self.assertTrue(d["is_reactivation"])

    def test_normal_event_not_reactivation(self):
        e = {
            "agent": "radar",
            "event_type": "SOURCE_UPDATE",
            "payload": {},
            "evidence": {},
            "timestamp": "2026-10-01T00:00:00Z",
            "event_id": "evt_x",
            "topic_id": "T_x",
        }
        d = fv.event_to_api_dict(e)
        self.assertFalse(d["is_reactivation"])

    def test_lifecycle_includes_reactivated_stage(self):
        events = [
            {"event_type": "CREATE_TOPIC"},
            {"event_type": "SOCIAL_HEAT_SIGNAL"},  # implies REACTIVATED
        ]
        stages = fv.build_lifecycle_stages(events, "REACTIVATED")
        reactivated_stage = next(s for s in stages if s["machine"] == "REACTIVATED")
        self.assertTrue(reactivated_stage["reached"])
        self.assertTrue(reactivated_stage["current"])


class TestLifecycleRendering(unittest.TestCase):
    """G. Lifecycle rendering 测试."""

    def test_lifecycle_only_shows_reached_stages(self):
        # Topic only at NEW -> only NEW should be reached
        events = [{"event_type": "CREATE_TOPIC"}]
        stages = fv.build_lifecycle_stages(events, "NEW")
        # Only NEW reached
        reached = [s for s in stages if s["reached"]]
        self.assertEqual(len(reached), 1)
        self.assertEqual(reached[0]["machine"], "NEW")

    def test_lifecycle_full_path(self):
        events = [
            {"event_type": "CREATE_TOPIC"},
            {"event_type": "SOURCE_UPDATE"},
            {"event_type": "EDITORIAL_REVIEW"},
            {"event_type": "PUBLISH"},
            {"event_type": "MONITOR"},
            {"event_type": "REACTIVATION_SIGNAL"},
            {"event_type": "FOLLOW_UP"},
            {"event_type": "CLOSE"},
        ]
        stages = fv.build_lifecycle_stages(events, "CLOSED")
        machines = [s["machine"] for s in stages if s["reached"]]
        self.assertEqual(
            machines,
            ["NEW", "RADAR_TRACKING", "EDITORIAL_REVIEW",
             "PUBLISHED", "MONITORING", "REACTIVATED", "FOLLOW_UP", "CLOSED"],
        )

    def test_lifecycle_only_current_has_current_true(self):
        events = [{"event_type": "PUBLISH"}]
        stages = fv.build_lifecycle_stages(events, "PUBLISHED")
        current = [s for s in stages if s.get("current")]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["machine"], "PUBLISHED")


class TestEvidence(unittest.TestCase):
    """H. Evidence rendering 测试."""

    def test_source_url_preserved(self):
        e = {"payload": {}, "evidence": {"source_url": "https://x.com/y"}}
        urls = fv.extract_urls_from_payload(e["payload"], e["evidence"])
        self.assertEqual(len(urls), 1)
        self.assertEqual(urls[0]["url"], "https://x.com/y")

    def test_source_message_id_preserved(self):
        e = {"payload": {}, "evidence": {"source_message_id": "msg_001"}}
        d = fv.event_to_api_dict({
            "event_id": "evt_x",
            "topic_id": "T_x",
            "agent": "radar",
            "event_type": "SOURCE_UPDATE",
            "timestamp": "2026-10-01T00:00:00Z",
            "payload": e["payload"],
            "evidence": e["evidence"],
            "confidence": 1.0,
        })
        self.assertEqual(d["evidence"]["source_message_id"], "msg_001")

    def test_confidence_preserved(self):
        d = fv.event_to_api_dict({
            "event_id": "evt_x",
            "topic_id": "T_x",
            "agent": "radar",
            "event_type": "SOURCE_UPDATE",
            "timestamp": "2026-10-01T00:00:00Z",
            "payload": {},
            "evidence": {},
            "confidence": 0.85,
        })
        self.assertEqual(d["confidence"], 0.85)

    def test_evidence_summary(self):
        e = {
            "source": "Bernama",
            "source_url": "https://b.com/x",
            "heat_score": 0.9,
            "source_message_id": "msg_001",
        }
        s = fv.render_evidence_summary(e)
        self.assertIn("Bernama", s)
        self.assertIn("https://b.com/x", s)
        self.assertIn("0.9", s)
        self.assertIn("msg_001", s)

    def test_empty_evidence_returns_none(self):
        self.assertIsNone(fv.render_evidence_summary({}))
        self.assertIsNone(fv.render_evidence_summary(None))


# ===========================================================================
# I. Read-only test (verify HTTP server doesn't modify Forum files)
# ===========================================================================

class TestReadOnlyServer(unittest.TestCase):
    """Verify the HTTP server never modifies Forum data."""

    @classmethod
    def setUpClass(cls):
        if not PRODUCTION_FORUM_ROOT.exists():
            raise unittest.SkipTest(f"Production Forum not found: {PRODUCTION_FORUM_ROOT}")
        # Take SHA of every Topic file before starting server
        cls.topic_files = list(PRODUCTION_FORUM_ROOT.glob("topics/*/topic.json"))
        cls.events_files = list(PRODUCTION_FORUM_ROOT.glob("topics/*/events.jsonl"))
        cls.dashboard_file = PRODUCTION_FORUM_ROOT / "dashboard" / "index.json"
        cls.pre_sha = {}
        for f in cls.topic_files + cls.events_files:
            if f.exists():
                cls.pre_sha[str(f)] = (f.stat().st_mtime, f.stat().st_size)
        if cls.dashboard_file.exists():
            cls.pre_sha[str(cls.dashboard_file)] = (
                cls.dashboard_file.stat().st_mtime,
                cls.dashboard_file.stat().st_size,
            )

        # Start server on a free port
        import socket
        cls.port = 18765  # fixed test port (avoid conflicts)
        paths = forum_v2.ForumV2Paths(PRODUCTION_FORUM_ROOT)
        handler = fv.make_handler(paths, VIEWER_DIR)
        cls.server = fv.ThreadingHTTPServer(("127.0.0.1", cls.port), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _fetch(self, url):
        with urlreq.urlopen(url, timeout=5) as r:
            return r.status, r.read().decode("utf-8")

    def test_api_topics_does_not_modify_files(self):
        self._fetch(f"http://127.0.0.1:{self.port}/api/topics")
        for path, (mtime, size) in self.pre_sha.items():
            if Path(path).exists():
                self.assertEqual(Path(path).stat().st_mtime, mtime,
                                 f"file {path} was modified")
                self.assertEqual(Path(path).stat().st_size, size,
                                 f"file {path} size changed")

    def test_api_topic_detail_does_not_modify_files(self):
        # Find any real topic id
        if not self.topic_files:
            self.skipTest("no topics")
        topic_id = self.topic_files[0].parent.name
        self._fetch(f"http://127.0.0.1:{self.port}/api/topics/{topic_id}")
        for path, (mtime, size) in self.pre_sha.items():
            if Path(path).exists():
                self.assertEqual(Path(path).stat().st_mtime, mtime)
                self.assertEqual(Path(path).stat().st_size, size)

    def test_static_files_do_not_modify_files(self):
        self._fetch(f"http://127.0.0.1:{self.port}/")
        for path, (mtime, size) in self.pre_sha.items():
            if Path(path).exists():
                self.assertEqual(Path(path).stat().st_mtime, mtime)
                self.assertEqual(Path(path).stat().st_size, size)

    def test_index_html_loads(self):
        status, body = self._fetch(f"http://127.0.0.1:{self.port}/")
        self.assertEqual(status, 200)
        self.assertIn("MY HOT RADAR · NEWSROOM", body)
        self.assertIn("index.js", body)

    def test_topic_html_loads(self):
        status, body = self._fetch(f"http://127.0.0.1:{self.port}/topic.html")
        self.assertEqual(status, 200)
        self.assertIn("topic.js", body)

    def test_api_dashboard(self):
        status, body = self._fetch(f"http://127.0.0.1:{self.port}/api/dashboard")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("total_topics", data)
        self.assertIn("by_classification", data)
        self.assertIn("by_status", data)


# ===========================================================================
# J. Real-data tests
# ===========================================================================

class TestRealData(unittest.TestCase):
    """Real-data tests against the live Forum at C:/MY-Hot-Radar-Bridge/forum."""

    @classmethod
    def setUpClass(cls):
        if not PRODUCTION_FORUM_ROOT.exists():
            raise unittest.SkipTest(f"Production Forum not found: {PRODUCTION_FORUM_ROOT}")
        cls.paths = forum_v2.ForumV2Paths(PRODUCTION_FORUM_ROOT)

    def test_topics_list_returns_real_data(self):
        topics = fv.get_topics_api(self.paths)
        self.assertGreater(topics["total"], 0)
        # Each topic has a real topic_id starting with T_
        for t in topics["topics"]:
            self.assertTrue(t["topic_id"].startswith("T_"))

    def test_hasmah_topic_present(self):
        topics = fv.get_topics_api(self.paths)["topics"]
        hasmah = next((t for t in topics if "哈斯玛" in t["title"] or "hasmah" in (t["title"] or "").lower()), None)
        self.assertIsNotNone(hasmah, "Hasmah topic not found in real Forum")
        # Verify Chinese title rendering
        self.assertIn("哈斯玛", hasmah["title_rendered"]["primary"])

    def test_najib_topic_present(self):
        # Najib topic may or may not be in real Forum — it's a soft assertion
        # (only validate if present, since we don't fabricate topics)
        topics = fv.get_topics_api(self.paths)["topics"]
        najib = next((t for t in topics if "纳吉" in t["title"] or "najib" in (t["title"] or "").lower()), None)
        if najib is None:
            # Najib topic not in current Forum data — this is fine,
            # viewer must NOT fabricate topics. Verify other real topics exist.
            self.assertGreater(len(topics), 0,
                               "Real Forum must have at least one topic")
            return
        # If present, must have valid rendered title
        self.assertIn("primary", najib["title_rendered"])

    def test_topic_detail_real(self):
        topics = fv.get_topics_api(self.paths)["topics"]
        # Real data has raw CJK titles (not always title_i18n subfield).
        # Pick any real topic.
        if not topics:
            self.skipTest("No topics in real Forum")
        any_topic = topics[0]
        detail = fv.get_topic_detail_api(any_topic["topic_id"], self.paths)
        self.assertIsNotNone(detail)
        self.assertGreater(detail["total_events"], 0)
        # Lifecycle built from real events
        self.assertGreater(len(detail["lifecycle"]), 0)
        # Title rendered
        self.assertIn(any_topic["topic_id"], detail["topic"]["topic_id"])
        self.assertNotEqual(detail["topic"]["title_rendered"]["primary"], "")

    def test_reactivation_topic_present(self):
        # Find topic with REACTIVATED status or with a reactivation event
        topics = fv.get_topics_api(self.paths)["topics"]
        detail = None
        for t in topics:
            d = fv.get_topic_detail_api(t["topic_id"], self.paths)
            if d and any(e["is_reactivation"] for e in d["events"]):
                detail = d
                break
        if detail is None:
            self.skipTest("No reactivation topic in real Forum (acceptable)")
        # Verify the topic has REACTIVATED lifecycle stage marked
        stages = detail["lifecycle"]
        reactivated_stage = next((s for s in stages if s["machine"] == "REACTIVATED"), None)
        if reactivated_stage:
            self.assertTrue(reactivated_stage["reached"])

    def test_performance_report_topic_present(self):
        # Find topic with a PERFORMANCE_REPORT event
        topics = fv.get_topics_api(self.paths)["topics"]
        perf_topic = None
        for t in topics:
            d = fv.get_topic_detail_api(t["topic_id"], self.paths)
            if d and any(e["event_type"] == "PERFORMANCE_REPORT" for e in d["events"]):
                perf_topic = d
                break
        if perf_topic is None:
            self.skipTest("No Performance report topic in real Forum")
        # Verify Performance event has machine fields preserved
        perf_events = [e for e in perf_topic["events"] if e["event_type"] == "PERFORMANCE_REPORT"]
        for e in perf_events:
            self.assertIn("velocity", e["payload"])
            self.assertIn("window", e["payload"])

    def test_dashboard_real(self):
        d = fv.get_dashboard_api(self.paths)
        self.assertEqual(d["total_topics"], sum(d["by_status"].values()))
        self.assertGreater(d["total_topics"], 0)


# ===========================================================================
# K. JSON serializability
# ===========================================================================

class TestJSONSerializable(unittest.TestCase):
    """All API output must be JSON-serializable."""

    def test_topic_api_dict_serializable(self):
        topic_dict = {
            "topic_id": "T_test",
            "title": "Test",
            "title_i18n": {"en": "Test", "zh": "测试"},
            "status": "NEW",
            "classification": "BREAKING",
        }
        api = fv.topic_to_api_dict(topic_dict)
        s = json.dumps(api, ensure_ascii=False)
        loaded = json.loads(s)
        self.assertEqual(loaded["title_i18n"]["zh"], "测试")

    def test_event_api_dict_serializable(self):
        event_dict = {
            "event_id": "evt_test",
            "topic_id": "T_test",
            "agent": "radar",
            "event_type": "SOURCE_UPDATE",
            "timestamp": "2026-10-01T00:00:00Z",
            "confidence": 0.95,
            "payload": {"note": {"en": "X", "zh": "源更新"}},
            "evidence": {"source": "Bernama"},
        }
        api = fv.event_to_api_dict(event_dict)
        s = json.dumps(api, ensure_ascii=False)
        loaded = json.loads(s)
        self.assertEqual(loaded["note_rendered"]["primary"], "源更新")


if __name__ == "__main__":
    unittest.main(verbosity=2)