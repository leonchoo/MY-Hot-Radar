#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Forum v2 (scripts/forum_v2.py).

Coverage:
  - Topic schema and deterministic topic_id from linkage_key
  - Event schema and JSONL append-only
  - Lifecycle transitions (legal + illegal)
  - Reactivation (same linkage_key never creates a duplicate)
  - Four-agent permission boundaries (Collector / Radar / Default / Performance)
  - Event types per agent (allowed vs rejected)
  - End-to-end Scenarios A-G
  - v1 transport preserved (outbox/, inbox/, state/ never touched)
  - Crash recovery / idempotency
  - Dashboard index rebuild

All tests use TempForumV2 which re-points paths at a temp directory and
restores on exit.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import forum_v2  # noqa: E402


# ---------------------------------------------------------------------------
# Test fixture
# ---------------------------------------------------------------------------

class TempForumV2:
    """Sets up a temp forum root pointing at a copy of the v1 layout.

    Re-points forum_v2 module constants at the temp paths; restores on exit.
    Also seeds inbox/ state/ outbox/ with the v1 layout so we can prove
    v2 never modifies them.
    """

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="forum_v2_test_"))
        self.root = self.tmp / "forum"
        self.root.mkdir(parents=True)
        # Seed v1 directories with placeholder files
        (self.root / "outbox").mkdir()
        (self.root / "inbox" / "collector").mkdir(parents=True)
        (self.root / "inbox" / "radar").mkdir(parents=True)
        (self.root / "inbox" / "default").mkdir(parents=True)
        (self.root / "inbox" / "mhr_performance").mkdir(parents=True)
        (self.root / "inbox" / "hermes").mkdir(parents=True)
        (self.root / "state").mkdir()
        # Drop a sentinel file in each v1 dir to detect any modification
        self.sentinel = {
            "outbox": (self.root / "outbox" / "v1_sentinel.json"),
            "inbox_collector": (self.root / "inbox" / "collector" / "v1_sentinel.json"),
            "state": (self.root / "state" / "v1_sentinel.state.json"),
        }
        for p in self.sentinel.values():
            p.write_text(json.dumps({"sentinel": True}), encoding="utf-8")
        self.v1_sentinel_sha = {
            k: hash_or_none(p) for k, p in self.sentinel.items()
        }

        self._saved = {}
        self._saved["DEFAULT_FORUM_ROOT"] = forum_v2.DEFAULT_FORUM_ROOT
        forum_v2.DEFAULT_FORUM_ROOT = self.root
        return self

    def __exit__(self, *exc):
        forum_v2.DEFAULT_FORUM_ROOT = self._saved["DEFAULT_FORUM_ROOT"]
        shutil.rmtree(self.tmp, ignore_errors=True)

    def paths(self):
        return forum_v2.ForumV2Paths(self.root)

    def assert_v1_preserved(self):
        for k, p in self.sentinel.items():
            sha = hash_or_none(p)
            assert sha == self.v1_sentinel_sha[k], (
                f"v1 sentinel {k} modified! sha before={self.v1_sentinel_sha[k]} after={sha}"
            )

    def write_dummy_state(self, mid: str, state: str):
        # Simulate an existing v1 state file — v2 must NOT touch it
        p = self.root / "state" / f"{mid}.state.json"
        p.write_text(json.dumps({"message_id": mid, "state": state}), encoding="utf-8")
        return p


def hash_or_none(p: Path):
    import hashlib
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Topic schema tests
# ---------------------------------------------------------------------------

class TestTopicIdDeterminism(unittest.TestCase):
    def test_same_linkage_key_same_topic_id(self):
        k = forum_v2.normalize_linkage_key("Siti Hasmah Passes Away")
        tid1 = forum_v2.topic_id_from_linkage(k)
        tid2 = forum_v2.topic_id_from_linkage(k)
        self.assertEqual(tid1, tid2)
        self.assertTrue(tid1.startswith("T_"))
        self.assertEqual(len(tid1), 2 + 16)

    def test_dates_stripped_from_linkage(self):
        k1 = forum_v2.normalize_linkage_key("Hasmah passes 2026-09-28")
        k2 = forum_v2.normalize_linkage_key("Hasmah passes 2026/10/01")
        self.assertEqual(k1, k2)

    def test_punctuation_stripped(self):
        k1 = forum_v2.normalize_linkage_key("Hasmah: wife of Mahathir!")
        k2 = forum_v2.normalize_linkage_key("Hasmah wife of Mahathir")
        self.assertEqual(k1, k2)


class TestCreateTopic(unittest.TestCase):
    def test_create_new_topic(self):
        with TempForumV2() as tf:
            topic, evt, was_reactivated = forum_v2.create_topic(
                title="Hasmah passes away at 100",
                agent="collector",
                paths=tf.paths(),
                classification="WATCH",
                languages=["zh", "en"],
            )
            self.assertFalse(was_reactivated)
            self.assertEqual(topic.status, "NEW")
            self.assertEqual(topic.events_count, 1)
            self.assertEqual(topic.source_count, 1)
            self.assertIn("collector", topic.participants)
            self.assertEqual(evt.event_type, "CREATE_TOPIC")

    def test_reactivation_returns_same_topic_id(self):
        with TempForumV2() as tf:
            t1, _, _ = forum_v2.create_topic(
                title="Hasmah passes away at 100",
                agent="collector",
                paths=tf.paths(),
            )
            t2, evt2, was_reactivated = forum_v2.create_topic(
                title="Hasmah passes away at 100",
                agent="collector",
                paths=tf.paths(),
            )
            self.assertTrue(was_reactivated)
            self.assertEqual(t1.topic_id, t2.topic_id)
            self.assertEqual(t2.status, "REACTIVATED")
            self.assertEqual(evt2.event_type, "REACTIVATION_SIGNAL")

    def test_reactivation_with_date_variant_merges(self):
        with TempForumV2() as tf:
            t1, _, _ = forum_v2.create_topic(
                title="Hasmah passes away 2026-09-28",
                agent="collector",
                paths=tf.paths(),
            )
            t2, _, was_reactivated = forum_v2.create_topic(
                title="Hasmah passes away 2026-10-01",
                agent="collector",
                paths=tf.paths(),
            )
            self.assertTrue(was_reactivated)
            self.assertEqual(t1.topic_id, t2.topic_id)

    def test_distinct_topics_for_distinct_titles(self):
        with TempForumV2() as tf:
            t1, _, _ = forum_v2.create_topic(title="Hasmah passes", agent="collector", paths=tf.paths())
            t2, _, _ = forum_v2.create_topic(title="Najib house arrest", agent="collector", paths=tf.paths())
            self.assertNotEqual(t1.topic_id, t2.topic_id)


# ---------------------------------------------------------------------------
# Event append
# ---------------------------------------------------------------------------

class TestAppendEvent(unittest.TestCase):
    def test_append_event_increments_count(self):
        with TempForumV2() as tf:
            topic, _, _ = forum_v2.create_topic(
                title="Hasmah passes", agent="collector", paths=tf.paths()
            )
            t2, evt = forum_v2.append_event(
                topic_id=topic.topic_id,
                agent="radar",
                event_type="SOURCE_UPDATE",
                payload={"url": "https://example.com/x"},
                paths=tf.paths(),
                next_status="RADAR_TRACKING",
            )
            self.assertEqual(t2.events_count, 2)
            self.assertEqual(t2.status, "RADAR_TRACKING")
            self.assertIn("radar", t2.participants)

    def test_events_persisted_to_jsonl(self):
        with TempForumV2() as tf:
            topic, _, _ = forum_v2.create_topic(title="X", agent="collector", paths=tf.paths())
            forum_v2.append_event(
                topic_id=topic.topic_id,
                agent="radar",
                event_type="SOURCE_UPDATE",
                paths=tf.paths(),
            )
            events = forum_v2.get_events(topic.topic_id, paths=tf.paths())
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0].event_type, "CREATE_TOPIC")
            self.assertEqual(events[1].event_type, "SOURCE_UPDATE")


# ---------------------------------------------------------------------------
# Agent permission boundaries
# ---------------------------------------------------------------------------

class TestAgentPermissions(unittest.TestCase):
    def test_collector_allowed_event_types(self):
        for et in ["OBSERVATION", "SOCIAL_HEAT_SIGNAL", "REACTIVATION_SIGNAL",
                   "EVIDENCE", "CREATE_TOPIC"]:
            forum_v2._check_event_permission("collector", et)  # should not raise

    def test_radar_allowed_event_types(self):
        for et in ["SOURCE_UPDATE", "TOPIC_UPDATE", "CROSS_SOURCE_CONFIRMATION",
                   "MOMENTUM_UPDATE", "CLASSIFICATION_UPDATE"]:
            forum_v2._check_event_permission("radar", et)

    def test_default_allowed_event_types(self):
        for et in ["EDITORIAL_REVIEW", "PUBLISH", "UPDATE_ARTICLE",
                   "FOLLOW_UP", "MONITOR", "CLOSE"]:
            forum_v2._check_event_permission("default", et)

    def test_performance_allowed_event_types(self):
        for et in ["PERFORMANCE_REPORT", "VELOCITY_UPDATE", "ENGAGEMENT_UPDATE",
                   "SUSTAINED_SIGNAL", "COOLING_SIGNAL", "REACTIVATION_SIGNAL"]:
            forum_v2._check_event_permission("mhr_performance", et)

    def test_cross_agent_violation_rejected(self):
        # Collector cannot emit PUBLISH (editorial decision)
        with self.assertRaises(forum_v2.AgentPermissionError):
            forum_v2._check_event_permission("collector", "PUBLISH")
        # Radar cannot emit CLOSE
        with self.assertRaises(forum_v2.AgentPermissionError):
            forum_v2._check_event_permission("radar", "CLOSE")
        # Performance cannot emit PUBLISH (Performance doesn't decide)
        with self.assertRaises(forum_v2.AgentPermissionError):
            forum_v2._check_event_permission("mhr_performance", "PUBLISH")
        # Default cannot emit VELOCITY_UPDATE
        with self.assertRaises(forum_v2.AgentPermissionError):
            forum_v2._check_event_permission("default", "VELOCITY_UPDATE")

    def test_unknown_agent_rejected(self):
        with self.assertRaises(forum_v2.AgentPermissionError):
            forum_v2._check_event_permission("random_actor", "PUBLISH")


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

class TestLifecycleTransitions(unittest.TestCase):
    def test_legal_transition_new_to_radar_tracking(self):
        forum_v2._check_lifecycle_transition("NEW", "RADAR_TRACKING")

    def test_legal_published_to_monitoring(self):
        forum_v2._check_lifecycle_transition("PUBLISHED", "MONITORING")

    def test_legal_any_to_reactivated(self):
        for s in ["RADAR_TRACKING", "EDITORIAL_REVIEW", "PUBLISHED",
                  "MONITORING", "FOLLOW_UP", "CLOSED"]:
            forum_v2._check_lifecycle_transition(s, "REACTIVATED")

    def test_illegal_transition_rejected(self):
        # CLOSED -> NEW is illegal
        with self.assertRaises(forum_v2.LifecycleError):
            forum_v2._check_lifecycle_transition("CLOSED", "NEW")
        # NEW -> PUBLISHED is illegal (must go through RADAR_TRACKING/EDITORIAL_REVIEW)
        with self.assertRaises(forum_v2.LifecycleError):
            forum_v2._check_lifecycle_transition("NEW", "PUBLISHED")


# ---------------------------------------------------------------------------
# End-to-end Scenarios
# ---------------------------------------------------------------------------

class TestScenarioA(unittest.TestCase):
    """A: Collector → CREATE → Radar → Default → Performance → Default"""

    def test_full_lifecycle(self):
        with TempForumV2() as tf:
            # 1. Collector discovers new Topic
            topic, _, _ = forum_v2.create_topic(
                title="Mahathir admitted to hospital",
                agent="collector",
                paths=tf.paths(),
            )
            self.assertEqual(topic.status, "NEW")
            # 2. Radar — SOURCE_UPDATE → RADAR_TRACKING
            forum_v2.append_event(
                topic_id=topic.topic_id, agent="radar",
                event_type="SOURCE_UPDATE", paths=tf.paths(),
                next_status="RADAR_TRACKING",
            )
            # 3. Radar — CLASSIFICATION_UPDATE
            forum_v2.append_event(
                topic_id=topic.topic_id, agent="radar",
                event_type="CLASSIFICATION_UPDATE",
                payload={"classification": "RISING"}, paths=tf.paths(),
            )
            # 4. Default — EDITORIAL_REVIEW
            t_after, _ = forum_v2.append_event(
                topic_id=topic.topic_id, agent="default",
                event_type="EDITORIAL_REVIEW", paths=tf.paths(),
                next_status="EDITORIAL_REVIEW",
            )
            self.assertEqual(t_after.status, "EDITORIAL_REVIEW")
            # 5. Performance — PERFORMANCE_REPORT (no status change)
            forum_v2.append_event(
                topic_id=topic.topic_id, agent="mhr_performance",
                event_type="PERFORMANCE_REPORT", paths=tf.paths(),
            )
            # 6. Default — PUBLISH
            t_pub, _ = forum_v2.append_event(
                topic_id=topic.topic_id, agent="default",
                event_type="PUBLISH", paths=tf.paths(),
                next_status="PUBLISHED",
            )
            self.assertEqual(t_pub.status, "PUBLISHED")
            # 7. Default — MONITOR
            t_mon, _ = forum_v2.append_event(
                topic_id=topic.topic_id, agent="default",
                event_type="MONITOR", paths=tf.paths(),
                next_status="MONITORING",
            )
            self.assertEqual(t_mon.status, "MONITORING")
            # Verify events count and participants
            self.assertEqual(t_mon.events_count, 7)
            self.assertSetEqual(
                set(t_mon.participants),
                {"collector", "radar", "default", "mhr_performance"},
            )


class TestScenarioB(unittest.TestCase):
    """B: Collector reactivates existing Topic (no second Topic)."""

    def test_reactivation_merges(self):
        with TempForumV2() as tf:
            # Day 1
            t1, _, was_reactivated1 = forum_v2.create_topic(
                title="Najib house arrest 2026-09-19", agent="collector", paths=tf.paths()
            )
            self.assertFalse(was_reactivated1)
            forum_v2.append_event(
                topic_id=t1.topic_id, agent="radar",
                event_type="SOURCE_UPDATE", paths=tf.paths(),
                next_status="RADAR_TRACKING",
            )
            # Day 4: same news resurfaces
            t2, evt, was_reactivated2 = forum_v2.create_topic(
                title="Najib house arrest 2026-10-01",
                agent="collector", paths=tf.paths(),
            )
            self.assertTrue(was_reactivated2)
            self.assertEqual(t1.topic_id, t2.topic_id)
            self.assertEqual(t2.status, "REACTIVATED")
            self.assertEqual(evt.event_type, "REACTIVATION_SIGNAL")
            # Verify events.jsonl has both CREATE_TOPIC and REACTIVATION_SIGNAL
            events = forum_v2.get_events(t2.topic_id, paths=tf.paths())
            types = [e.event_type for e in events]
            self.assertIn("CREATE_TOPIC", types)
            self.assertIn("SOURCE_UPDATE", types)
            self.assertIn("REACTIVATION_SIGNAL", types)


class TestScenarioC(unittest.TestCase):
    """C: Radar finds a new source → existing Topic, SOURCE_UPDATE."""

    def test_radar_adds_source_to_existing_topic(self):
        with TempForumV2() as tf:
            t, _, _ = forum_v2.create_topic(
                title="Hasmah passes away", agent="collector", paths=tf.paths()
            )
            forum_v2.append_event(
                topic_id=t.topic_id, agent="radar",
                event_type="SOURCE_UPDATE",
                payload={"url": "https://bernama.com/x", "lang": "en"},
                paths=tf.paths(),
            )
            t_after, _ = forum_v2.append_event(
                topic_id=t.topic_id, agent="radar",
                event_type="SOURCE_UPDATE",
                payload={"url": "https://sinchew.com.my/y", "lang": "zh"},
                paths=tf.paths(),
            )
            self.assertEqual(t_after.events_count, 3)


class TestScenarioD(unittest.TestCase):
    """D: Performance finds sustained heat → PERFORMANCE_REPORT → Default."""

    def test_performance_then_default_follow_up(self):
        with TempForumV2() as tf:
            t, _, _ = forum_v2.create_topic(title="Sustained heat story", agent="collector", paths=tf.paths())
            forum_v2.append_event(topic_id=t.topic_id, agent="radar", event_type="SOURCE_UPDATE", paths=tf.paths(), next_status="RADAR_TRACKING")
            forum_v2.append_event(topic_id=t.topic_id, agent="mhr_performance", event_type="SUSTAINED_SIGNAL", paths=tf.paths())
            t_after, _ = forum_v2.append_event(topic_id=t.topic_id, agent="default", event_type="FOLLOW_UP", paths=tf.paths(), next_status="FOLLOW_UP")
            self.assertEqual(t_after.status, "FOLLOW_UP")


class TestScenarioE(unittest.TestCase):
    """E: Performance sees cooling → COOLING_SIGNAL → Default CLOSE."""

    def test_cooling_close(self):
        with TempForumV2() as tf:
            t, _, _ = forum_v2.create_topic(title="Cooling story", agent="collector", paths=tf.paths())
            forum_v2.append_event(topic_id=t.topic_id, agent="mhr_performance", event_type="COOLING_SIGNAL", paths=tf.paths())
            t_after, _ = forum_v2.append_event(topic_id=t.topic_id, agent="default", event_type="CLOSE", paths=tf.paths(), next_status="CLOSED")
            self.assertEqual(t_after.status, "CLOSED")


class TestScenarioF(unittest.TestCase):
    """F: Collector + Radar simultaneously update — no lost events."""

    def test_concurrent_appends_no_loss(self):
        import threading
        with TempForumV2() as tf:
            t, _, _ = forum_v2.create_topic(title="Concurrent updates", agent="collector", paths=tf.paths())

            def radar_task():
                for _ in range(5):
                    forum_v2.append_event(
                        topic_id=t.topic_id, agent="radar",
                        event_type="SOURCE_UPDATE", paths=tf.paths(),
                    )

            def collector_task():
                for _ in range(5):
                    forum_v2.append_event(
                        topic_id=t.topic_id, agent="collector",
                        event_type="OBSERVATION", paths=tf.paths(),
                    )

            t1 = threading.Thread(target=radar_task)
            t2 = threading.Thread(target=collector_task)
            t1.start(); t2.start()
            t1.join(); t2.join()

            events = forum_v2.get_events(t.topic_id, paths=tf.paths())
            # CREATE_TOPIC + 5 radar + 5 collector = 11 events
            self.assertEqual(len(events), 11)
            # Each event has unique event_id
            ids = [e.event_id for e in events]
            self.assertEqual(len(ids), len(set(ids)))


class TestScenarioG(unittest.TestCase):
    """G: Agent restart — no event loss, no duplicate."""

    def test_restart_continues_idempotently(self):
        with TempForumV2() as tf:
            t, _, _ = forum_v2.create_topic(title="Restart story", agent="collector", paths=tf.paths())
            forum_v2.append_event(topic_id=t.topic_id, agent="radar", event_type="SOURCE_UPDATE", paths=tf.paths(), next_status="RADAR_TRACKING")
            t_mid, _ = forum_v2.append_event(topic_id=t.topic_id, agent="default", event_type="EDITORIAL_REVIEW", paths=tf.paths(), next_status="EDITORIAL_REVIEW")
            # Simulate restart by re-reading the Topic and appending more events
            t_loaded = forum_v2.get_topic(t.topic_id, paths=tf.paths())
            self.assertIsNotNone(t_loaded)
            self.assertEqual(t_loaded.status, t_mid.status)
            # Append more events — PUBLISH is allowed from EDITORIAL_REVIEW
            forum_v2.append_event(topic_id=t.topic_id, agent="default", event_type="PUBLISH", paths=tf.paths(), next_status="PUBLISHED")
            events = forum_v2.get_events(t.topic_id, paths=tf.paths())
            self.assertEqual(len(events), 4)


# ---------------------------------------------------------------------------
# v1 preservation
# ---------------------------------------------------------------------------

class TestV1Preservation(unittest.TestCase):
    def test_v1_files_not_touched(self):
        with TempForumV2() as tf:
            # Add a v1 state file as if MHR Performance had sent a message
            tf.write_dummy_state("msg_existing", "ACKED")
            # Do a bunch of v2 operations
            t, _, _ = forum_v2.create_topic(title="X", agent="collector", paths=tf.paths())
            forum_v2.append_event(topic_id=t.topic_id, agent="radar", event_type="SOURCE_UPDATE", paths=tf.paths(), next_status="RADAR_TRACKING")
            forum_v2.append_event(topic_id=t.topic_id, agent="default", event_type="EDITORIAL_REVIEW", paths=tf.paths(), next_status="EDITORIAL_REVIEW")
            forum_v2.append_event(topic_id=t.topic_id, agent="default", event_type="PUBLISH", paths=tf.paths(), next_status="PUBLISHED")
            forum_v2.build_dashboard_index(paths=tf.paths())
            # All v1 sentinels must be unchanged
            tf.assert_v1_preserved()
            # msg_existing.state.json must be unchanged
            p = tf.root / "state" / "msg_existing.state.json"
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["state"], "ACKED")


# ---------------------------------------------------------------------------
# Dashboard index
# ---------------------------------------------------------------------------

class TestDashboard(unittest.TestCase):
    def test_dashboard_aggregate(self):
        with TempForumV2() as tf:
            t1, _, _ = forum_v2.create_topic(title="A", agent="collector", paths=tf.paths())
            t2, _, _ = forum_v2.create_topic(title="B", agent="collector", paths=tf.paths())
            forum_v2.append_event(topic_id=t1.topic_id, agent="radar", event_type="SOURCE_UPDATE", paths=tf.paths(), next_status="RADAR_TRACKING")
            idx = forum_v2.build_dashboard_index(paths=tf.paths())
            self.assertEqual(idx["total_topics"], 2)
            self.assertEqual(idx["by_status"].get("NEW"), 1)
            self.assertEqual(idx["by_status"].get("RADAR_TRACKING"), 1)
            self.assertEqual(idx["by_agent_participation"].get("collector"), 2)
            self.assertEqual(idx["by_agent_participation"].get("radar"), 1)
            # File written
            self.assertTrue((tf.root / "dashboard" / "index.json").exists())


# ---------------------------------------------------------------------------
# Crash recovery (best-effort)
# ---------------------------------------------------------------------------

class TestCrashRecovery(unittest.TestCase):
    def test_partial_topic_jsonl_readable(self):
        with TempForumV2() as tf:
            t, _, _ = forum_v2.create_topic(title="X", agent="collector", paths=tf.paths())
            forum_v2.append_event(topic_id=t.topic_id, agent="radar", event_type="SOURCE_UPDATE", paths=tf.paths())
            # Append a corrupted line manually
            with open(tf.root / "topics" / t.topic_id / "events.jsonl", "a", encoding="utf-8") as f:
                f.write("corrupted line that is not json\n")
            forum_v2.append_event(topic_id=t.topic_id, agent="default", event_type="PUBLISH", paths=tf.paths())
            events = forum_v2.get_events(t.topic_id, paths=tf.paths())
            # 2 valid events; the corrupt line is skipped
            self.assertEqual(len(events), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
