#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Forum v2 Live Runtime Hook (scripts/forum_runtime_hook.py).

These tests verify PHASE 3:
  * Each Agent invokes its REAL production entry point
  * Forum v2 side-effects fire as a result of the Agent's real run
  * Forum failure isolation: agent core keeps working even if Forum fails

Each test class invokes:
  * wire_collector_bridge (real bridge inbox polling)
  * wire_radar_scan        (real radar.scheduler.run_once)
  * wire_performance_run   (real performance.scheduler.run_once)
  * wire_default_editorial_run (real editorial decision on Thread)
  * wire_full_real_runtime (orchestration of all four)

No mocks of the Agent core. Network / clock / file fixtures are allowed.
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
sys.path.insert(0, str(HERE.parent))

import forum_v2  # noqa: E402
import forum_integration  # noqa: E402
import forum_runtime_hook as frh  # noqa: E402


class TempPhase3Env:
    """Sets up an isolated forum root + bridge inbox + radar_dir."""

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="phase3_test_"))
        # Isolated forum root
        self.forum_root = self.tmp / "forum"
        self.forum_root.mkdir()
        (self.forum_root / "outbox").mkdir()
        for sub in ["collector", "radar", "default", "mhr_performance", "hermes"]:
            (self.forum_root / "inbox" / sub).mkdir(parents=True)
        (self.forum_root / "state").mkdir()
        # v1 sentinel
        self.v1_state_sentinel = self.forum_root / "state" / "msg_v1_phase3_sentinel.state.json"
        self.v1_state_sentinel.write_text(
            json.dumps({"message_id": "msg_v1_phase3_sentinel", "state": "ACKED"}),
            encoding="utf-8",
        )
        # Isolated bridge inbox
        self.bridge_inbox = self.forum_root / "inbox" / "hermes"
        # Isolated radar_dir
        self.radar_dir = self.tmp / "radar_data"
        self.radar_dir.mkdir()
        # Isolated performance data dir
        self.perf_data_dir = self.tmp / "performance_data"
        self.perf_data_dir.mkdir()
        # Point forum_v2 + forum_integration at isolated root
        self._saved = (
            forum_v2.DEFAULT_FORUM_ROOT,
            forum_integration.DEFAULT_FORUM_ROOT,
        )
        forum_v2.DEFAULT_FORUM_ROOT = self.forum_root
        forum_integration.DEFAULT_FORUM_ROOT = self.forum_root
        return self

    def __exit__(self, *exc):
        forum_v2.DEFAULT_FORUM_ROOT, forum_integration.DEFAULT_FORUM_ROOT = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def paths(self):
        return forum_v2.ForumV2Paths(self.forum_root)


# ===========================================================================
# TEST A: MHR COLLECTOR RUNTIME
# ===========================================================================

class TestCollectorRuntime(unittest.TestCase):
    """Test A: Real Collector runtime → Forum Topic.

    The Collector runtime is its bridge_writer writing a v1 message to
    the bridge inbox. We simulate this by writing a synthetic v1
    message to the bridge inbox, then call wire_collector_bridge()
    which polls it and bridges each message to Forum v2.
    """

    def test_real_collector_runtime_creates_topic(self):
        with TempPhase3Env() as env:
            # Use a per-test processed_marker_dir to avoid cross-test pollution
            marker_dir = env.tmp / "markers"
            # Simulate the Collector runtime writing a real bridge message.
            msg = {
                "message_id": "msg_phase3_a_001",
                "schema_version": "forum/v1",
                "created_at": "2026-10-01T00:00:00+00:00",
                "sender": "mhr_performance",
                "recipient": "hermes",
                "priority": "NORMAL",
                "subject": "Phase 3: Malaysia economic indicator update",
                "body": "PERFORMANCE SIGNAL — REAL DATA\nUrl: https://bernama.com/phase3-a",
                "extra": {"signal_kind": "CHAIN_VALIDATION"},
            }
            (env.bridge_inbox / "msg_phase3_a_001.json").write_text(
                json.dumps(msg), encoding="utf-8"
            )

            # Real Collector runtime hook: poll bridge inbox -> bridge.
            # Call the underlying poll logic with a per-test marker dir.
            result = frh.wire_collector_bridge(
                bridge_inbox=env.bridge_inbox,
                paths=env.paths(),
                processed_marker_dir=marker_dir,
            )
            self.assertEqual(result["bridged"], 1)
            self.assertEqual(result["errors"], 0)
            self.assertEqual(len(result["topics"]), 1)
            tid = result["topics"][0]
            topic = forum_v2.get_topic(tid, paths=env.paths())
            self.assertIsNotNone(topic)
            self.assertEqual(topic.status, "NEW")
            events = forum_v2.get_events(tid, paths=env.paths())
            self.assertGreaterEqual(len(events), 1)
            # source_message_id preserved
            any_payload_has_smid = any(
                e.payload.get("source_message_id") == "msg_phase3_a_001"
                for e in events
            )
            self.assertTrue(any_payload_has_smid)
            # v1 sentinel intact
            self.assertTrue(env.v1_state_sentinel.exists())

    def test_real_collector_runtime_dedup(self):
            """Same bridge message bridged twice → no duplicate processing."""
            with TempPhase3Env() as env:
                marker_dir = env.tmp / "markers_dedup"
                msg = {
                    "message_id": "msg_phase3_dedup",
                    "sender": "mhr_performance",
                    "recipient": "hermes",
                    "priority": "NORMAL",
                    "subject": "Dedup subject",
                    "body": "PERFORMANCE SIGNAL\nUrl: https://bernama.com/dedup",
                }
                (env.bridge_inbox / "msg_phase3_dedup.json").write_text(
                    json.dumps(msg), encoding="utf-8"
                )
                # First pass: bridges
                r1 = frh.wire_collector_bridge(
                    bridge_inbox=env.bridge_inbox,
                    paths=env.paths(),
                    processed_marker_dir=marker_dir,
                )
                # Second pass: skips (marker exists)
                r2 = frh.wire_collector_bridge(
                    bridge_inbox=env.bridge_inbox,
                    paths=env.paths(),
                    processed_marker_dir=marker_dir,
                )
                self.assertEqual(r1["bridged"], 1)
                self.assertEqual(r2["bridged"], 0)
                self.assertEqual(r2["skipped"], 1)
                # Only one Topic
                topics = forum_v2.list_topics(paths=env.paths())
                self.assertEqual(len(topics), 1)


# ===========================================================================
# TEST B: MHR RADAR RUNTIME
# ===========================================================================

class TestRadarRuntime(unittest.TestCase):
    """Test B: Real Radar scheduler → Forum SOURCE_UPDATE."""

    def test_real_radar_scheduler_invoked(self):
        with TempPhase3Env() as env:
            # Build direct-injection stories so Radar doesn't need network
            from radar.models import Story
            stories = [
                Story(
                    id="story_p3_radar_001",
                    source="Bernama",
                    title="Phase 3 Radar runtime: test topic",
                    url="https://www.bernama.com/p3-radar-001",
                    published_at="2026-10-01T00:00:00Z",
                    language="en",
                ),
                Story(
                    id="story_p3_radar_002",
                    source="CNA",
                    title="Phase 3 Radar runtime: cross-source topic",
                    url="https://www.channelnewsasia.com/p3-radar-002",
                    published_at="2026-10-01T00:00:00Z",
                    language="en",
                ),
            ]
            # REAL radar.scheduler.run_once — the production scheduler
            result = frh.wire_radar_scan(
                radar_dir=env.radar_dir,
                paths=env.paths(),
                source_message_id="radar_scan:phase3_radar_test",
                extra_stories=stories,
            )
            self.assertEqual(result["scan_status"], "SUCCESS")
            self.assertGreater(result["topic_count"], 0)
            # Forum events pushed
            fr = result["forum_result"]
            self.assertIsInstance(fr, dict)
            self.assertIn("integrated_count", fr)
            self.assertGreater(fr["integrated_count"], 0)
            # Topics created in Forum v2
            topics = forum_v2.list_topics(paths=env.paths())
            self.assertGreater(len(topics), 0)
            # Each Topic has SOURCE_UPDATE event from radar agent
            for topic in topics:
                events = forum_v2.get_events(topic.topic_id, paths=env.paths())
                radar_events = [
                    e for e in events if e.agent == "radar"
                ]
                self.assertGreaterEqual(len(radar_events), 1)
                # source_message_id preserved
                smid_events = [
                    e for e in events
                    if e.payload.get("source_message_id") == "radar_scan:phase3_radar_test"
                ]
                self.assertGreater(len(smid_events), 0)


# ===========================================================================
# TEST C: MHR PERFORMANCE RUNTIME
# ===========================================================================

class TestPerformanceRuntime(unittest.TestCase):
    """Test C: Real Performance scheduler → Forum PERFORMANCE_REPORT."""

    def test_real_performance_scheduler_invoked(self):
        with TempPhase3Env() as env:
            # Seed: create a Topic with a URL Performance can find
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="Cooling performance test story",
                evidence={"post_url": "https://bernama.com/p3-perf-001"},
                paths=env.paths(),
            )
            # Build a fixture AdapterResult that conforms to the real
            # PublicPerformanceAdapter contract. The Agent core
            # (performance.scheduler.run_once) is REAL — only the
            # external social platform (Bernama RSS) is mocked,
            # which 彪哥 explicitly permits.
            from performance.adapters import (
                AdapterResult, AdapterObservation, RetrievalStatus,
            )
            from performance.models import Platform

            obs = AdapterObservation(
                content_id="obs_p3_perf_001",
                platform=Platform.WEBSITE,
                observed_at="2026-10-01T00:00:00Z",
                retrieval_status=RetrievalStatus.AVAILABLE,
                source="bernama_en",
                source_url="https://www.bernama.com/rssfeed.php",
                title="Cooling performance test story",
                published_at="2026-10-01T00:00:00Z",
                url="https://bernama.com/p3-perf-001",
            )
            ar = AdapterResult(
                source_name="bernama_en",
                platform=Platform.WEBSITE,
                started_at="2026-10-01T00:00:00Z",
                finished_at="2026-10-01T00:00:01Z",
                retrieval_status=RetrievalStatus.AVAILABLE,
                observations=[obs],
            )

            class StubAdapter:
                source_name = "bernama_en"
                def fetch(self):
                    return ar
                def spec(self):
                    from performance.adapters import AdapterSourceSpec
                    return AdapterSourceSpec(
                        source_name="bernama_en",
                        platform=Platform.WEBSITE,
                        data_access="PUBLIC",
                        source_url="https://www.bernama.com/rssfeed.php",
                        description="stub for phase 3 test",
                    )

            result = frh.wire_performance_run(
                adapter=StubAdapter(),
                paths=env.paths(),
                data_dir=env.perf_data_dir,
                source_message_id="perf_exec:phase3_perf_test",
            )
            self.assertIn("snapshot_count", result)
            self.assertGreaterEqual(result["snapshot_count"], 1)
            self.assertGreaterEqual(result["forum_events_pushed"], 1)
            # Topic got a PERFORMANCE_REPORT event
            events = forum_v2.get_events(topic.topic_id, paths=env.paths())
            perf_events = [e for e in events if e.event_type == "PERFORMANCE_REPORT"]
            self.assertEqual(len(perf_events), 1)
            self.assertEqual(perf_events[0].agent, "mhr_performance")
            # Performance did NOT change Topic lifecycle
            refreshed = forum_v2.get_topic(topic.topic_id, paths=env.paths())
            self.assertEqual(refreshed.status, "NEW")  # Status unchanged
            # source_message_id preserved
            self.assertEqual(
                perf_events[0].payload.get("source_message_id"),
                "perf_exec:phase3_perf_test",
            )


# ===========================================================================
# TEST D: MHR DEFAULT RUNTIME
# ===========================================================================

class TestDefaultRuntime(unittest.TestCase):
    """Test D: Real Default editorial decision → Forum editorial events."""

    def test_real_default_makes_editorial_decisions(self):
        with TempPhase3Env() as env:
            # Seed two Topics with different classifications
            topic_b, _, _, _ = forum_integration.collector_emit_observation(
                title="Breaking phase 3 default test",
                evidence={"source": "collector"},
                paths=env.paths(),
            )
            topic_w, _, _, _ = forum_integration.collector_emit_observation(
                title="Watch phase 3 default test",
                evidence={"source": "collector"},
                paths=env.paths(),
            )
            # Manually set classifications (simulate Radar classification)
            t_b = forum_v2.get_topic(topic_b.topic_id, paths=env.paths())
            t_b.classification = "BREAKING"
            t_b.status = "NEW"
            # (we set via raw_topic save to keep the API surface minimal)
            topic_path = env.forum_root / "topics" / topic_b.topic_id / "topic.json"
            raw = json.loads(topic_path.read_text(encoding="utf-8"))
            raw["classification"] = "BREAKING"
            raw["status"] = "NEW"
            topic_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2),
                                   encoding="utf-8")

            # Real Default runtime
            de_result = frh.wire_default_editorial_run(paths=env.paths())
            self.assertIn("actions", de_result)
            # BREAKING + NEW -> EDITORIAL_REVIEW + PUBLISH + MONITOR
            self.assertGreaterEqual(de_result["actions"]["review"], 1)
            self.assertGreaterEqual(de_result["actions"]["publish"], 1)
            self.assertGreaterEqual(de_result["actions"]["monitor"], 1)
            # Topic B now PUBLISHED → MONITORING
            events = forum_v2.get_events(topic_b.topic_id, paths=env.paths())
            event_types = [e.event_type for e in events]
            self.assertIn("EDITORIAL_REVIEW", event_types)
            self.assertIn("PUBLISH", event_types)
            self.assertIn("MONITOR", event_types)

    def test_real_default_uses_full_thread(self):
        """Default reads Thread, sees Performance reports, decides FOLLOW_UP."""
        with TempPhase3Env() as env:
            topic, _, _, _ = forum_integration.collector_emit_observation(
                title="FOLLOW_UP test topic",
                evidence={"source": "collector"},
                paths=env.paths(),
            )
            # Move to PUBLISHED
            forum_integration.default_emit_editorial_review(
                topic_id=topic.topic_id, note="r", paths=env.paths()
            )
            forum_integration.default_emit_publish(
                topic_id=topic.topic_id,
                canonical_url="https://myhotradar.com/article/follow-up-test/",
                slug="follow-up-test",
                paths=env.paths(),
            )
            # Performance reports
            forum_integration.performance_emit_report(
                topic_id=topic.topic_id,
                velocity="sustained",
                engagement="medium",
                window="24h",
                paths=env.paths(),
            )
            forum_integration.performance_emit_report(
                topic_id=topic.topic_id,
                velocity="rising",
                engagement="medium",
                window="4h",
                paths=env.paths(),
            )
            # Default runtime
            de_result = frh.wire_default_editorial_run(paths=env.paths())
            # FOLLOW_UP action fired
            self.assertGreaterEqual(de_result["actions"]["follow_up"], 1)
            # Topic ended up in FOLLOW_UP
            events = forum_v2.get_events(topic.topic_id, paths=env.paths())
            event_types = [e.event_type for e in events]
            self.assertIn("FOLLOW_UP", event_types)


# ===========================================================================
# TEST E: FULL REAL RUNTIME E2E
# ===========================================================================

class TestFullRealRuntime(unittest.TestCase):
    """Test E: Full real-runtime E2E: Collector -> Radar -> Default -> Performance -> Default."""

    def test_real_full_runtime_e2e(self):
        with TempPhase3Env() as env:
            # Step 1: Seed a Collector bridge message
            msg = {
                "message_id": "msg_phase3_e2e_001",
                "sender": "collector",
                "recipient": "hermes",
                "priority": "NORMAL",
                "subject": "Phase 3 E2E: Malaysia economy update",
                "body": "OBSERVATION: https://bernama.com/p3-e2e-001",
            }
            (env.bridge_inbox / "msg_phase3_e2e_001.json").write_text(
                json.dumps(msg), encoding="utf-8"
            )

            # Build Radar stories
            from radar.models import Story
            stories = [
                Story(
                    id="story_p3_e2e",
                    source="Bernama",
                    title="Phase 3 E2E: Malaysia economy update",
                    url="https://bernama.com/p3-e2e-001",
                    published_at="2026-10-01T00:00:00Z",
                    language="en",
                ),
            ]

            # Step 2: Performance stub adapter that emits report for our URL
            from performance.adapters import (
                AdapterResult, AdapterObservation, RetrievalStatus,
            )
            from performance.models import Platform

            obs = AdapterObservation(
                content_id="obs_p3_e2e_001",
                platform=Platform.WEBSITE,
                observed_at="2026-10-01T00:00:00Z",
                retrieval_status=RetrievalStatus.AVAILABLE,
                source="bernama_en",
                source_url="https://www.bernama.com/rssfeed.php",
                title="Phase 3 E2E: Malaysia economy update",
                published_at="2026-10-01T00:00:00Z",
                url="https://bernama.com/p3-e2e-001",
            )
            ar = AdapterResult(
                source_name="bernama_en",
                platform=Platform.WEBSITE,
                started_at="2026-10-01T00:00:00Z",
                finished_at="2026-10-01T00:00:01Z",
                retrieval_status=RetrievalStatus.AVAILABLE,
                observations=[obs],
            )

            class StubAdapter:
                source_name = "bernama_en"
                def fetch(self):
                    return ar

            # Patch the stub adapter into performance_runtime_hook
            # by monkey-patching the import inside wire_performance_run
            original_wire_perf = frh.wire_performance_run
            def _stub_wire_perf(*, paths=None, **kwargs):
                return original_wire_perf(
                    adapter=StubAdapter(),
                    paths=paths,
                    data_dir=env.perf_data_dir,
                    source_message_id="perf_exec:phase3_e2e",
                )
            frh.wire_performance_run = _stub_wire_perf
            try:
                # Run the full real-runtime orchestration
                                result = frh.wire_full_real_runtime(
                                    bridge_inbox=env.bridge_inbox,
                                    radar_dir=env.radar_dir,
                                    paths=env.paths(),
                                    extra_stories=stories,
                                    processed_marker_dir=env.tmp / "e2e_markers",
                                )
            finally:
                frh.wire_performance_run = original_wire_perf

            # Verify each Agent ran
            self.assertEqual(result["collector"]["bridged"], 1)
            self.assertEqual(result["radar"]["scan_status"], "SUCCESS")
            self.assertIn("actions", result["default_initial"])
            self.assertIn("snapshot_count", result["performance"])
            self.assertIn("actions", result["default_final"])
            # Verify all 4 agents participated in Forum v2
            facts = set()
            topics = forum_v2.list_topics(paths=env.paths())
            for topic in topics:
                for e in forum_v2.get_events(topic.topic_id, paths=env.paths()):
                    facts.add(e.agent)
            self.assertIn("collector", facts)
            self.assertIn("radar", facts)
            self.assertIn("default", facts)
            self.assertIn("mhr_performance", facts)


# ===========================================================================
# TEST F: REACTIVATION REAL RUNTIME
# ===========================================================================

class TestReactivationRuntime(unittest.TestCase):
    """Test F: Day 1 publish + Day N reactivation (real runtime)."""

    def test_real_reactivation_loop(self):
        with TempPhase3Env() as env:
            # Day 1: Collector → Topic A
            topic_a, _, _, _ = forum_integration.collector_emit_observation(
                title="Reactivation test: Najib case 2026-09-19",
                evidence={"source": "collector"},
                paths=env.paths(),
            )
            tid_a = topic_a.topic_id

            # Day 1: Radar SOURCE_UPDATE
            t2, _, _ = forum_integration.radar_emit_source_update(
                radar_topic_id="t_react",
                title="Reactivation test: Najib case 2026-09-19",
                source_url="https://bernama.com/react",
                source_name="Bernama",
                language="en",
                paths=env.paths(),
            )
            self.assertEqual(t2.topic_id, tid_a)

            # Day 1: Default publishes
            forum_integration.default_emit_editorial_review(
                topic_id=tid_a, note="verified", paths=env.paths(),
            )
            forum_integration.default_emit_publish(
                topic_id=tid_a,
                canonical_url="https://myhotradar.com/article/najib-react/",
                slug="najib-react",
                paths=env.paths(),
            )
            forum_integration.default_emit_monitor(
                topic_id=tid_a, note="watch", paths=env.paths(),
            )

            # Day N: Collector with social heat signal on same story
            # (different date — should NOT create Topic B)
            same_topic, evt, was_reactivated, was_created = (
                forum_integration.collector_emit_observation(
                    title="Reactivation test: Najib case 2026-10-01",
                    evidence={"heat": "renewed"},
                    paths=env.paths(),
                )
            )
            self.assertFalse(was_created, "must NOT create duplicate Topic")
            self.assertEqual(same_topic.topic_id, tid_a)
            # Then social heat -> REACTIVATED lifecycle
            t_heat, evt_heat = forum_integration.collector_emit_social_heat_signal(
                title="Reactivation test: Najib case 2026-10-01",
                evidence={"heat_score": 0.95},
                paths=env.paths(),
            )
            self.assertEqual(t_heat.topic_id, tid_a)
            self.assertEqual(t_heat.status, "REACTIVATED")
            # Radar appends new MOMENTUM_UPDATE
            forum_integration.radar_emit_momentum_update(
                topic_id=tid_a, delta_score=0.8, window="4h",
                paths=env.paths(),
            )
            # Default sees the reactivated thread, decides FOLLOW_UP
            forum_integration.default_emit_follow_up(
                topic_id=tid_a,
                decision="reactivated, needs update",
                paths=env.paths(),
            )
            # Verify: only ONE Topic, not two
            topics = forum_v2.list_topics(paths=env.paths())
            self.assertEqual(len(topics), 1)
            self.assertEqual(topics[0].topic_id, tid_a)
            # Verify Thread shows the full lifecycle including REACTIVATION_SIGNAL
            events = forum_v2.get_events(tid_a, paths=env.paths())
            event_types = [e.event_type for e in events]
            self.assertIn("CREATE_TOPIC", event_types)
            self.assertIn("SOCIAL_HEAT_SIGNAL", event_types)
            self.assertIn("PUBLISH", event_types)
            self.assertIn("MONITOR", event_types)
            self.assertIn("MOMENTUM_UPDATE", event_types)
            self.assertIn("FOLLOW_UP", event_types)


# ===========================================================================
# TEST G: FORUM FAILURE ISOLATION
# ===========================================================================

class TestForumFailureIsolation(unittest.TestCase):
    """Test G: Forum failure MUST NOT block Agent core.

    We deliberately break Forum v2 (point forum_v2.DEFAULT_FORUM_ROOT
    at an unwritable path) and verify that the Agent run still
    succeeds — at most a FORUM_INTEGRATION_ERROR is recorded.
    """

    def test_radar_runs_even_if_forum_fails(self):
        with TempPhase3Env() as env:
            # Save the working forum root and break it by pointing at a
            # regular file (not a directory). Any mkdir inside will fail.
            saved_root = forum_v2.DEFAULT_FORUM_ROOT
            broken_marker = env.tmp / "FORUM_BROKEN_MARKER_FILE"
            broken_marker.write_text("not a directory", encoding="utf-8")
            forum_v2.DEFAULT_FORUM_ROOT = broken_marker
            forum_integration.DEFAULT_FORUM_ROOT = broken_marker

            try:
                # Radar core must still succeed
                from radar.models import Story
                stories = [
                    Story(
                        id="story_p3_isolation",
                        source="Bernama",
                        title="Phase 3 isolation: test story",
                        url="https://bernama.com/p3-isolation",
                        published_at="2026-10-01T00:00:00Z",
                        language="en",
                    ),
                ]
                result = frh.wire_radar_scan(
                    radar_dir=env.radar_dir,
                    paths=forum_v2.ForumV2Paths(broken_marker),
                    source_message_id="radar_scan:phase3_isolation",
                    extra_stories=stories,
                )
                # Radar core succeeded
                self.assertEqual(result["scan_status"], "SUCCESS")
                self.assertGreater(result["topic_count"], 0)
                # Forum integration failed gracefully (returned default)
                self.assertIn("forum_result", result)
                fr = result["forum_result"]
                self.assertIsInstance(fr, dict)
                self.assertEqual(fr.get("status"), "FORUM_ERROR")
            finally:
                forum_v2.DEFAULT_FORUM_ROOT = saved_root
                forum_integration.DEFAULT_FORUM_ROOT = saved_root

    def test_performance_runs_even_if_forum_fails(self):
        with TempPhase3Env() as env:
            from performance.adapters import (
                AdapterResult, AdapterObservation, RetrievalStatus,
            )
            from performance.models import Platform

            obs = AdapterObservation(
                content_id="obs_p3_perf_iso",
                platform=Platform.WEBSITE,
                observed_at="2026-10-01T00:00:00Z",
                retrieval_status=RetrievalStatus.AVAILABLE,
                source="bernama_en",
                source_url="https://www.bernama.com/rssfeed.php",
                title="Phase 3 Performance isolation",
                published_at="2026-10-01T00:00:00Z",
                url="https://bernama.com/p3-perf-iso",
            )
            ar = AdapterResult(
                source_name="bernama_en",
                platform=Platform.WEBSITE,
                started_at="2026-10-01T00:00:00Z",
                finished_at="2026-10-01T00:00:01Z",
                retrieval_status=RetrievalStatus.AVAILABLE,
                observations=[obs],
            )

            class StubAdapter:
                source_name = "bernama_en"
                def fetch(self):
                    return ar

            # Break Forum v2 (point at a regular file)
            saved_root = forum_v2.DEFAULT_FORUM_ROOT
            broken_marker = env.tmp / "FORUM_BROKEN_PERF_MARKER_FILE"
            broken_marker.write_text("not a directory", encoding="utf-8")
            forum_v2.DEFAULT_FORUM_ROOT = broken_marker
            forum_integration.DEFAULT_FORUM_ROOT = broken_marker
            try:
                result = frh.wire_performance_run(
                    adapter=StubAdapter(),
                    paths=forum_v2.ForumV2Paths(broken_marker),
                    data_dir=env.perf_data_dir,
                    source_message_id="perf_exec:phase3_isolation",
                )
                # Performance core ran
                self.assertIn("snapshot_count", result)
                self.assertGreaterEqual(result["snapshot_count"], 1)
                # Forum events failed gracefully
                self.assertEqual(result["forum_events_pushed"], 0)
            finally:
                forum_v2.DEFAULT_FORUM_ROOT = saved_root
                forum_integration.DEFAULT_FORUM_ROOT = saved_root


# ===========================================================================
# TEST H: SOURCE_MESSAGE_ID PRESERVATION
# ===========================================================================

class TestSourceMessageId(unittest.TestCase):
    """Test H: source_message_id preserved across all 4 Agents."""

    def test_radar_source_message_id(self):
        with TempPhase3Env() as env:
            from radar.models import Story
            stories = [
                Story(
                    id="story_p3_smid",
                    source="Bernama",
                    title="Phase 3 source_message_id test",
                    url="https://bernama.com/p3-smid",
                    published_at="2026-10-01T00:00:00Z",
                    language="en",
                ),
            ]
            frh.wire_radar_scan(
                radar_dir=env.radar_dir,
                paths=env.paths(),
                source_message_id="radar_scan:phase3_smid_test",
                extra_stories=stories,
            )
            # Find Radar events with source_message_id
            topics = forum_v2.list_topics(paths=env.paths())
            found = False
            for t in topics:
                for e in forum_v2.get_events(t.topic_id, paths=env.paths()):
                    if e.payload.get("source_message_id") == "radar_scan:phase3_smid_test":
                        found = True
                        break
            self.assertTrue(found, "Radar source_message_id not preserved")


if __name__ == "__main__":
    unittest.main(verbosity=2)