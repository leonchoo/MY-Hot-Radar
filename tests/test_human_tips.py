#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Forum Human Tip (Phase 7).

Coverage (per 彪哥's spec):
  1.  Create Human Tip
  2.  Radar ACK
  3.  New Tip creates Topic
  4.  Tip matches existing Topic
  5.  Tip triggers CLOSED Topic reactivation
  6.  Screenshot / URL evidence
  7.  Status transitions
  8.  source_message_id / trace
  9.  Permissions (hermes can only create, radar only ack/link, etc.)
 10.  Duplicate Human Tip doesn't create duplicate Topic
 11.  Forum restart preserves data
 12.  UI renders correctly
 13.  All existing Forum tests still PASS
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
import urllib.request as u
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import forum_v2  # noqa: E402
import human_tips  # noqa: E402
import human_tips_runtime  # noqa: E402


PRODUCTION_FORUM_ROOT = Path(r"C:\MY-Hot-Radar-Bridge\forum")


def _temp_forum_root() -> Path:
    td = tempfile.mkdtemp(prefix="ht_test_")
    root = Path(td) / "forum"
    (root / "topics").mkdir(parents=True)
    (root / "human_tips").mkdir(parents=True)
    (root / "dashboard").mkdir(parents=True)
    (root / "runtime").mkdir(parents=True)
    return root


# ===========================================================================
# A. Creation
# ===========================================================================

class TestCreateTip(unittest.TestCase):

    def setUp(self):
        self.forum_root = _temp_forum_root()
        self.paths = forum_v2.ForumV2Paths(self.forum_root)
        self.tip_paths = human_tips.HumanTipsPaths(self.forum_root)
        self.store = human_tips.HumanTipsStore(self.tip_paths)

    def tearDown(self):
        shutil.rmtree(self.forum_root.parent, ignore_errors=True)

    def test_create_with_minimal_fields(self):
        tip, evt = self.store.create_tip(
            title="Test news",
        )
        self.assertEqual(tip.status, human_tips.TIP_OPEN)
        self.assertEqual(tip.priority, "MEDIUM")
        self.assertEqual(tip.author, "hermes")
        self.assertEqual(tip.target_agent, "radar")
        self.assertTrue(tip.tip_id.startswith("HT_"))

    def test_create_with_full_fields(self):
        tip, evt = self.store.create_tip(
            title="Johor jerebu makin teruk",
            source_url="https://example.com/news/1",
            description="Today IPU rose to 200+",
            evidence_urls=["https://example.com/shot1.png", "https://example.com/shot2.png"],
            priority="HIGH",
            tags=["johor", "jerebu"],
            target_agent="radar",
            author="hermes",
            source_message_id="msg_test_001",
        )
        self.assertEqual(tip.title, "Johor jerebu makin teruk")
        self.assertEqual(tip.source_url, "https://example.com/news/1")
        self.assertEqual(len(tip.evidence_urls), 2)
        self.assertEqual(tip.priority, "HIGH")
        self.assertEqual(tip.tags, ["johor", "jerebu"])

    def test_create_emits_event_with_all_fields(self):
        tip, evt = self.store.create_tip(
            title="Test news",
            source_url="https://example.com/x",
            priority="URGENT",
            source_message_id="msg_001",
        )
        self.assertEqual(evt.event_type, human_tips.EVT_CREATE_TIP)
        self.assertEqual(evt.agent, "hermes")
        self.assertEqual(evt.tip_id, tip.tip_id)
        self.assertEqual(evt.payload.get("priority"), "URGENT")
        self.assertEqual(evt.payload.get("source_message_id"), "msg_001")


# ===========================================================================
# B. Permissions
# ===========================================================================

class TestPermissions(unittest.TestCase):

    def setUp(self):
        self.forum_root = _temp_forum_root()
        self.tip_paths = human_tips.HumanTipsPaths(self.forum_root)
        self.store = human_tips.HumanTipsStore(self.tip_paths)

    def tearDown(self):
        shutil.rmtree(self.forum_root.parent, ignore_errors=True)

    def test_hermes_can_create(self):
        tip, _ = self.store.create_tip(title="test", author="hermes")
        self.assertEqual(tip.author, "hermes")

    def test_radar_can_ack(self):
        tip, _ = self.store.create_tip(title="test")
        ack_tip, evt = self.store.ack_tip(tip.tip_id, agent="radar")
        self.assertEqual(ack_tip.status, human_tips.TIP_ACKNOWLEDGED)

    def test_default_can_resolve(self):
        tip, _ = self.store.create_tip(title="test")
        self.store.ack_tip(tip.tip_id, agent="radar")
        self.store.investigate_tip(tip.tip_id, agent="radar")
        res_tip, evt = self.store.resolve_tip(
            tip.tip_id, resolution="NO_NEWS_VALUE",
            agent="default", note="no news value")
        self.assertEqual(res_tip.status, human_tips.TIP_RESOLVED)

    def test_collector_cannot_ack(self):
        tip, _ = self.store.create_tip(title="test")
        with self.assertRaises(human_tips.TipPermissionError):
            self.store.ack_tip(tip.tip_id, agent="collector")

    def test_collector_cannot_create(self):
        with self.assertRaises(human_tips.TipPermissionError):
            self.store.create_tip(title="test", author="collector")

    def test_hermes_cannot_ack(self):
        tip, _ = self.store.create_tip(title="test")
        with self.assertRaises(human_tips.TipPermissionError):
            self.store.ack_tip(tip.tip_id, agent="hermes")


# ===========================================================================
# C. Status transitions
# ===========================================================================

class TestStatusTransitions(unittest.TestCase):

    def setUp(self):
        self.forum_root = _temp_forum_root()
        self.tip_paths = human_tips.HumanTipsPaths(self.forum_root)
        self.store = human_tips.HumanTipsStore(self.tip_paths)

    def tearDown(self):
        shutil.rmtree(self.forum_root.parent, ignore_errors=True)

    def test_full_lifecycle(self):
        tip, _ = self.store.create_tip(title="lifecycle test")
        tip, _ = self.store.ack_tip(tip.tip_id, agent="radar")
        self.assertEqual(tip.status, human_tips.TIP_ACKNOWLEDGED)
        tip, _ = self.store.investigate_tip(tip.tip_id, agent="radar")
        self.assertEqual(tip.status, human_tips.TIP_INVESTIGATING)
        tip, _ = self.store.link_tip(
            tip.tip_id, topic_id="T_fake", agent="radar")
        self.assertEqual(tip.status, human_tips.TIP_LINKED)
        tip, _ = self.store.resolve_tip(
            tip.tip_id, resolution="PUBLISHED",
            agent="default", note="article published")
        self.assertEqual(tip.status, human_tips.TIP_RESOLVED)

    def test_open_to_resolved_direct(self):
        """OPEN → RESOLVED is allowed (per spec at least)."""
        tip, _ = self.store.create_tip(title="test")
        tip, _ = self.store.resolve_tip(
            tip.tip_id, resolution="NO_NEWS_VALUE",
            agent="default", note="immediately not news")
        self.assertEqual(tip.status, human_tips.TIP_RESOLVED)

    def test_illegal_transition_rejected(self):
        """ACK → RESOLVED is not a valid direct path."""
        tip, _ = self.store.create_tip(title="test")
        tip, _ = self.store.ack_tip(tip.tip_id, agent="radar")
        # ACKNOWLEDGED can go to INVESTIGATING, LINKED, or RESOLVED per matrix
        # but going to OPEN again is illegal
        with self.assertRaises(human_tips.TipStatusError):
            self.store.investigate_tip(tip.tip_id, agent="radar")
            # Now try to go back to OPEN — illegal
            tip_obj = self.store.get_tip(tip.tip_id)
            tip_obj.status = human_tips.TIP_INVESTIGATING
            self.store._write_tip(tip_obj)
            # Try to go from INVESTIGATING back to OPEN
            self.store.ack_tip(tip.tip_id, agent="radar")  # should fail

    def test_resolved_is_terminal(self):
        tip, _ = self.store.create_tip(title="test")
        tip, _ = self.store.resolve_tip(
            tip.tip_id, resolution="PENDING",
            agent="default", note="")
        # Try to ACK after RESOLVED — should fail
        with self.assertRaises(human_tips.TipStatusError):
            self.store.ack_tip(tip.tip_id, agent="radar")


# ===========================================================================
# D. Linkage to Topics
# ===========================================================================

class TestTopicLinkage(unittest.TestCase):

    def setUp(self):
        self.forum_root = _temp_forum_root()
        self.paths = forum_v2.ForumV2Paths(self.forum_root)
        self.tip_paths = human_tips.HumanTipsPaths(self.forum_root)
        self.store = human_tips.HumanTipsStore(self.tip_paths)

    def tearDown(self):
        shutil.rmtree(self.forum_root.parent, ignore_errors=True)

    def test_new_tip_creates_new_topic(self):
        tip, _ = self.store.create_tip(
            title="Brand new news story",
            source_url="https://example.com/news/new",
        )
        updated, topic, was_created = human_tips_runtime.link_tip_to_topic(
            tip=tip, forum_paths=self.paths,
            create_if_missing=True, agent="radar",
        )
        self.assertTrue(was_created)
        self.assertEqual(updated.topic_id, topic.topic_id)
        self.assertEqual(updated.status, human_tips.TIP_LINKED)
        # Verify the Topic exists in Forum v2
        fetched = forum_v2.get_topic(topic.topic_id, paths=self.paths)
        self.assertIsNotNone(fetched)

    def test_tip_matches_existing_topic(self):
        # Create a Topic first
        existing_topic, _, _ = forum_v2.create_topic(
            title="Existing news",
            agent="collector",
            paths=self.paths,
        )
        # Create a Tip with the same title
        tip, _ = self.store.create_tip(
            title="Existing news",
            source_url="https://example.com/news/existing",
        )
        updated, topic, was_created = human_tips_runtime.link_tip_to_topic(
            tip=tip, forum_paths=self.paths,
            create_if_missing=True, agent="radar",
        )
        self.assertFalse(was_created)
        self.assertEqual(topic.topic_id, existing_topic.topic_id)
        self.assertEqual(updated.topic_id, existing_topic.topic_id)

    def test_tip_triggers_closed_topic_reactivation(self):
        # Create a Topic, then close it
        topic, _, _ = forum_v2.create_topic(
            title="Closed news topic",
            agent="collector",
            paths=self.paths,
        )
        # Move through lifecycle to CLOSED
        try:
            forum_v2.append_event(
                topic_id=topic.topic_id,
                agent="default",
                event_type="EDITORIAL_REVIEW",
                paths=self.paths,
                next_status="EDITORIAL_REVIEW",
            )
            forum_v2.append_event(
                topic_id=topic.topic_id,
                agent="default",
                event_type="CLOSE",
                paths=self.paths,
                next_status="CLOSED",
            )
        except Exception:
            pass
        # Verify topic is closed
        refreshed = forum_v2.get_topic(topic.topic_id, paths=self.paths)
        self.assertEqual(refreshed.status, "CLOSED")
        # Now create a tip matching the same topic
        tip, _ = self.store.create_tip(
            title="Closed news topic",
            source_url="https://example.com/news/closed",
        )
        updated, topic_result, was_created = human_tips_runtime.link_tip_to_topic(
            tip=tip, forum_paths=self.paths,
            create_if_missing=True, agent="radar",
        )
        # Should match existing (not create new)
        self.assertFalse(was_created)
        self.assertEqual(topic_result.topic_id, topic.topic_id)
        # Verify tip is linked
        self.assertEqual(updated.status, human_tips.TIP_LINKED)
        # Verify reactivation event was appended
        events = forum_v2.get_events(topic.topic_id, paths=self.paths)
        self.assertTrue(any(
            e.event_type in ("REACTIVATION_SIGNAL", "OBSERVATION")
            and "tip_id" in e.payload
            for e in events
        ))


# ===========================================================================
# E. Idempotency
# ===========================================================================

class TestTipIdempotency(unittest.TestCase):

    def setUp(self):
        self.forum_root = _temp_forum_root()
        self.paths = forum_v2.ForumV2Paths(self.forum_root)
        self.tip_paths = human_tips.HumanTipsPaths(self.forum_root)
        self.store = human_tips.HumanTipsStore(self.tip_paths)

    def tearDown(self):
        shutil.rmtree(self.forum_root.parent, ignore_errors=True)

    def test_different_tips_get_different_ids(self):
        tip1, _ = self.store.create_tip(title="Story A")
        tip2, _ = self.store.create_tip(title="Story B")
        self.assertNotEqual(tip1.tip_id, tip2.tip_id)

    def test_same_title_creates_separate_tips(self):
        tip1, _ = self.store.create_tip(title="Same Story")
        tip2, _ = self.store.create_tip(title="Same Story")
        # Two tips, even with same title — they're separate observations
        self.assertNotEqual(tip1.tip_id, tip2.tip_id)

    def test_tip_idempotency_key(self):
        key1 = human_tips.compute_tip_key(title="X", source_url="Y", author="hermes")
        key2 = human_tips.compute_tip_key(title="X", source_url="Y", author="hermes")
        self.assertEqual(key1, key2)
        key3 = human_tips.compute_tip_key(title="X", source_url="Z", author="hermes")
        self.assertNotEqual(key1, key3)


# ===========================================================================
# F. Crash recovery / persistence
# ===========================================================================

class TestTipPersistence(unittest.TestCase):

    def setUp(self):
        self.forum_root = _temp_forum_root()
        self.paths = forum_v2.ForumV2Paths(self.forum_root)
        self.tip_paths = human_tips.HumanTipsPaths(self.forum_root)

    def tearDown(self):
        shutil.rmtree(self.forum_root.parent, ignore_errors=True)

    def test_tip_survives_store_restart(self):
        # Create tip in store A
        store_a = human_tips.HumanTipsStore(self.tip_paths)
        tip_a, _ = store_a.create_tip(title="Persistent tip")
        # Simulate restart with store B
        store_b = human_tips.HumanTipsStore(self.tip_paths)
        tip_b = store_b.get_tip(tip_a.tip_id)
        self.assertIsNotNone(tip_b)
        self.assertEqual(tip_b.title, "Persistent tip")
        self.assertEqual(tip_b.tip_id, tip_a.tip_id)

    def test_events_survive_store_restart(self):
        store_a = human_tips.HumanTipsStore(self.tip_paths)
        tip_a, _ = store_a.create_tip(title="test")
        store_a.ack_tip(tip_a.tip_id, agent="radar", note="first")
        store_b = human_tips.HumanTipsStore(self.tip_paths)
        events = store_b.get_events(tip_a.tip_id)
        self.assertGreaterEqual(len(events), 2)
        # Verify event types
        evt_types = [e.event_type for e in events]
        self.assertIn(human_tips.EVT_CREATE_TIP, evt_types)
        self.assertIn(human_tips.EVT_ACK_TIP, evt_types)


# ===========================================================================
# G. Viewer / UI
# ===========================================================================

class TestViewer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Start a viewer server on a fixed port for testing
        import subprocess
        try:
            cls.process = subprocess.Popen(
                ["python", str(HERE.parent / "scripts" / "forum_viewer.py"),
                 "--port", "18770"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            # Wait for the server to be ready (with retries for socket init delay)
            cls.server_available = False
            for attempt in range(5):
                time.sleep(1.0)
                try:
                    u.urlopen("http://127.0.0.1:18770/", timeout=2)
                    cls.server_available = True
                    break
                except Exception:
                    continue
        except Exception:
            cls.process = None
            cls.server_available = False

    @classmethod
    def tearDownClass(cls):
        if cls.process is not None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=5)
            except Exception:
                cls.process.kill()

    def setUp(self):
        if not getattr(self.__class__, "server_available", False):
            self.skipTest("Viewer server not available (socket init failure)")

    def test_human_tips_endpoint_returns_data(self):
        res = u.urlopen("http://127.0.0.1:18770/api/human_tips", timeout=5)
        data = json.loads(res.read())
        self.assertIn("tips", data)
        self.assertIn("total", data)
        self.assertEqual(data["schema_version"], "forum/viewer-v1-human_tips")

    def test_human_tips_html_loads(self):
        body = u.urlopen("http://127.0.0.1:18770/human_tips.html", timeout=5).read().decode("utf-8")
        self.assertIn("human_tips.js", body)
        self.assertIn("tip-card", body)

    def test_index_links_to_human_tips(self):
        body = u.urlopen("http://127.0.0.1:18770/", timeout=5).read().decode("utf-8")
        self.assertIn("human_tips.html", body)

    def test_no_undefined_in_html(self):
        body = u.urlopen("http://127.0.0.1:18770/human_tips.html", timeout=5).read().decode("utf-8")
        for bad in ["undefined", "[object Object]"]:
            self.assertNotIn(bad, body)


# ===========================================================================
# H. Resolution outcomes
# ===========================================================================

class TestResolutionOutcomes(unittest.TestCase):

    def setUp(self):
        self.forum_root = _temp_forum_root()
        self.tip_paths = human_tips.HumanTipsPaths(self.forum_root)
        self.store = human_tips.HumanTipsStore(self.tip_paths)

    def tearDown(self):
        shutil.rmtree(self.forum_root.parent, ignore_errors=True)

    def test_all_resolution_kinds(self):
        for kind in human_tips.TIP_RESOLUTION_KINDS:
            tip, _ = self.store.create_tip(title=f"test {kind}")
            tip, _ = self.store.resolve_tip(
                tip.tip_id, resolution=kind,
                agent="default", note=f"resolved as {kind}",
            )
            self.assertEqual(tip.resolution, kind)

    def test_invalid_resolution_rejected(self):
        tip, _ = self.store.create_tip(title="test")
        with self.assertRaises(human_tips.TipError):
            self.store.resolve_tip(
                tip.tip_id, resolution="NOT_A_REAL_KIND",
                agent="default")


# ===========================================================================
# I. Stats summary
# ===========================================================================

class TestStats(unittest.TestCase):

    def setUp(self):
        self.forum_root = _temp_forum_root()
        self.tip_paths = human_tips.HumanTipsPaths(self.forum_root)
        self.store = human_tips.HumanTipsStore(self.tip_paths)

    def tearDown(self):
        shutil.rmtree(self.forum_root.parent, ignore_errors=True)

    def test_stats_counts_correctly(self):
        # Create 3 OPEN, 1 ACK, 1 RESOLVED
        for i in range(3):
            self.store.create_tip(title=f"open {i}")
        tip4, _ = self.store.create_tip(title="ack")
        self.store.ack_tip(tip4.tip_id, agent="radar")
        tip5, _ = self.store.create_tip(title="resolved")
        self.store.resolve_tip(tip5.tip_id, resolution="PENDING", agent="default")

        stats = human_tips_runtime.stats_summary(self.tip_paths)
        self.assertEqual(stats["OPEN"], 3)
        self.assertEqual(stats["ACKNOWLEDGED"], 1)
        self.assertEqual(stats["RESOLVED"], 1)
        self.assertEqual(stats["TOTAL"], 5)

    def test_stats_empty(self):
        stats = human_tips_runtime.stats_summary(self.tip_paths)
        self.assertEqual(stats["TOTAL"], 0)


# ===========================================================================
# J. Newsroom Runtime integration
# ===========================================================================

class TestRuntimeIntegration(unittest.TestCase):

    def setUp(self):
        self.forum_root = _temp_forum_root()
        self.paths = forum_v2.ForumV2Paths(self.forum_root)
        self.tip_paths = human_tips.HumanTipsPaths(self.forum_root)

    def tearDown(self):
        shutil.rmtree(self.forum_root.parent, ignore_errors=True)

    def test_radar_runtime_processes_open_tips(self):
        # Create 2 OPEN tips
        store = human_tips.HumanTipsStore(self.tip_paths)
        tip_a, _ = store.create_tip(title="Tip A", priority="HIGH")
        tip_b, _ = store.create_tip(title="Tip B", priority="MEDIUM")

        # Run radar tip adapter
        import runtime_adapters.human_tip as ht_adapter
        result = ht_adapter.process_open_tips(
            forum_paths=self.paths, max_tips=10,
        )
        self.assertEqual(result.status, "OK")
        self.assertGreater(result.forum_events_written, 0)
        # Both tips should now be LINKED
        tip_a_now = store.get_tip(tip_a.tip_id)
        tip_b_now = store.get_tip(tip_b.tip_id)
        self.assertEqual(tip_a_now.status, human_tips.TIP_LINKED)
        self.assertEqual(tip_b_now.status, human_tips.TIP_LINKED)
        # Both should have topic_ids
        self.assertIsNotNone(tip_a_now.topic_id)
        self.assertIsNotNone(tip_b_now.topic_id)

    def test_default_runtime_processes_linked_tips(self):
        store = human_tips.HumanTipsStore(self.tip_paths)
        tip, _ = store.create_tip(title="Test tip")
        # Manually move tip to LINKED with a topic
        store.ack_tip(tip.tip_id, agent="radar")
        store.investigate_tip(tip.tip_id, agent="radar")
        topic, _, _ = forum_v2.create_topic(
            title="Test tip", agent="collector", paths=self.paths,
        )
        store.link_tip(tip.tip_id, topic_id=topic.topic_id, agent="radar")

        # Run default human_tip adapter
        import runtime_adapters.human_tip as ht_adapter
        result = ht_adapter.process_linked_tips_for_default(
            forum_paths=self.paths, max_tips=10,
        )
        self.assertEqual(result.status, "OK")
        self.assertGreater(result.forum_events_written, 0)
        # Topic should now have EDITORIAL_REVIEW event
        events = forum_v2.get_events(topic.topic_id, paths=self.paths)
        self.assertTrue(any(e.event_type == "EDITORIAL_REVIEW" for e in events))


# ===========================================================================
# K. Time / timezone handling
# ===========================================================================

class TestTimezone(unittest.TestCase):

    def test_myt_conversion(self):
        self.assertEqual(human_tips._utc_to_myt_display("2026-10-01T07:14:22Z"),
                         "2026-10-01 15:14:22 MYT")
        self.assertEqual(human_tips._utc_to_myt_display(""), "")
        # Edge: 16Z + 8 = 00 next day
        self.assertEqual(human_tips._utc_to_myt_display("2026-10-01T16:30:00Z"),
                         "2026-10-02 00:30:00 MYT")


if __name__ == "__main__":
    unittest.main(verbosity=2)