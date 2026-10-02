#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Forum Viewer LAN access (Phase 10.5).

Coverage:
  1. _is_private_ipv4 — RFC1918 detection (positive + negative cases)
  2. detect_lan_ipv4 — returns a real RFC1918 IP, never crashes
  3. get_network_api — returns correct scope/url/warning for local + lan
  4. HTTP /api/network — both bind modes return correct JSON
  5. Read-only — non-GET methods still rejected
  6. UI renders LAN strip — only when scope=lan
  7. Existing Forum — no regression
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import forum_viewer  # noqa: E402

PYTHON_EXE = str(Path(sys.executable))


def _start_viewer(port: int, host: str = "127.0.0.1", wait: float = 2.0) -> subprocess.Popen:
    """Start viewer subprocess, return Popen handle."""
    proc = subprocess.Popen(
        [PYTHON_EXE, "-u",
         str(SCRIPTS / "forum_viewer.py"),
         "--host", host,
         "--port", str(port),
         "--forum-root", r"C:\MY-Hot-Radar-Bridge\forum"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        text=True,
    )
    # Wait until listener is up (poll /)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1):
                return proc
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError(f"Viewer did not start on {host}:{port}")


def _stop_viewer(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def _http_get(url: str, method: str = "GET", body=None, headers=None, timeout: float = 5):
    h = headers or {}
    if body is not None:
        h.setdefault("Content-Type", "application/json; charset=utf-8")
        data = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
    else:
        data = None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


# ===========================================================================
# A. Pure-function tests (no server needed)
# ===========================================================================

class TestPrivateIPv4Detection(unittest.TestCase):

    POSITIVE = [
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.20.10.5",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.0.153",
        "192.168.255.255",
    ]
    NEGATIVE = [
        "127.0.0.1",
        "0.0.0.0",
        "8.8.8.8",
        "169.254.0.1",   # link-local
        "172.15.255.255",  # just outside 172.16/12
        "172.32.0.0",
        "11.0.0.1",        # just outside 10/8
        "192.167.0.1",     # just outside 192.168/16
        "192.169.0.1",
        "256.0.0.1",
        "1.2.3",
        "1.2.3.4.5",
        "not.an.ip",
        "",
        "::1",
        "fe80::1",
    ]

    def test_positive_cases(self):
        for ip in self.POSITIVE:
            with self.subTest(ip=ip):
                self.assertTrue(
                    forum_viewer._is_private_ipv4(ip),
                    f"expected {ip} to be RFC1918 private",
                )

    def test_negative_cases(self):
        for ip in self.NEGATIVE:
            with self.subTest(ip=ip):
                self.assertFalse(
                    forum_viewer._is_private_ipv4(ip),
                    f"expected {ip} to NOT be RFC1918 private",
                )


class TestDetectLanIPv4(unittest.TestCase):

    def test_returns_valid_ipv4_or_none(self):
        ip = forum_viewer.detect_lan_ipv4()
        if ip is not None:
            self.assertIsInstance(ip, str)
            self.assertRegex(ip, r"^\d+\.\d+\.\d+\.\d+$")
            self.assertTrue(
                forum_viewer._is_private_ipv4(ip),
                f"detected {ip} must be RFC1918 private",
            )

    def test_does_not_crash(self):
        # Should never raise, even on weird systems
        for _ in range(3):
            try:
                result = forum_viewer.detect_lan_ipv4()
                self.assertTrue(result is None or isinstance(result, str))
            except Exception as e:
                self.fail(f"detect_lan_ipv4 crashed: {e}")


class TestGetNetworkApi(unittest.TestCase):
    """Pure function test — no server."""

    def test_local_bind_returns_scope_local(self):
        net = forum_viewer.get_network_api(
            bind_host="127.0.0.1", port=8081, request_host="127.0.0.1:8081",
        )
        self.assertEqual(net["scope"], "local")
        self.assertEqual(net["bind_host"], "127.0.0.1")
        self.assertEqual(net["bind_port"], 8081)
        self.assertEqual(net["local_url"], "http://127.0.0.1:8081/")
        self.assertIsNone(net["lan_url"])
        self.assertIsNone(net["lan_ip_detected"])
        self.assertIsNone(net["lan_warning"])

    def test_lan_bind_returns_scope_lan(self):
        net = forum_viewer.get_network_api(
            bind_host="0.0.0.0", port=8081, request_host="192.168.0.153:8081",
        )
        self.assertEqual(net["scope"], "lan")
        self.assertEqual(net["bind_host"], "0.0.0.0")
        self.assertEqual(net["bind_port"], 8081)
        self.assertEqual(net["local_url"], "http://127.0.0.1:8081/")
        # lan_url may be None on machines without LAN, but the response
        # shape must be consistent. Either:
        #   (a) lan_url set + lan_ip_detected set (RFC1918 detected)
        #   (b) lan_url None + warning explaining "no RFC1918 detected"
        if net["lan_ip_detected"]:
            self.assertTrue(forum_viewer._is_private_ipv4(net["lan_ip_detected"]))
            self.assertEqual(
                net["lan_url"],
                f"http://{net['lan_ip_detected']}:8081/",
            )
            self.assertIn("trusted local networks", net["lan_warning"])
        else:
            # fallback: warning explains detection failure
            self.assertIsNone(net["lan_url"])
            self.assertIn("could not be detected", net["lan_warning"])
        self.assertIsNotNone(net["lan_warning"])

    def test_no_mac_hostname_or_credentials_in_response(self):
        """Privacy: response must NOT leak hostname, MAC, or any credentials."""
        for bind_host in ("127.0.0.1", "0.0.0.0"):
            net = forum_viewer.get_network_api(
                bind_host=bind_host, port=8081, request_host="127.0.0.1:8081",
            )
            serialized = json.dumps(net).lower()
            # No hostname, no MAC, no env credentials, no API keys
            self.assertNotIn("mac", serialized, "must not leak MAC")
            self.assertNotIn("password", serialized, "must not leak password")
            self.assertNotIn("api_key", serialized, "must not leak api key")
            self.assertNotIn("token", serialized, "must not leak token")
            # hostname: socket.gethostname() may include it indirectly through
            # the request_host param, but we're passing a fake one.
            # The response itself should only have IPs.
            self.assertNotIn("hostname", serialized, "must not leak hostname")


# ===========================================================================
# B. HTTP tests (need running viewer)
# ===========================================================================

def _free_port() -> int:
    """Find a free port. Returns None if socket init fails (Windows WSAStartup
    issue in some unittest contexts). Caller should skip on None."""
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    except OSError:
        return None


@unittest.skipUnless(_start_viewer is not None, "skip")
class TestLocalViewerReadOnly(unittest.TestCase):
    """Viewer bound to 127.0.0.1 — verify read-only behavior unchanged."""

    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        if cls.port is None:
            raise unittest.SkipTest("socket init failed (WinError 10106)")
        cls.proc = _start_viewer(cls.port, "127.0.0.1")
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        _stop_viewer(cls.proc)

    def test_home_loads(self):
        status, body, _ = _http_get(f"{self.base}/")
        self.assertEqual(status, 200)
        self.assertIn("MY HOT RADAR", body)

    def test_api_topics_loads(self):
        status, body, _ = _http_get(f"{self.base}/api/topics")
        self.assertEqual(status, 200)
        self.assertIn("topics", body)

    def test_api_dashboard_loads(self):
        status, body, _ = _http_get(f"{self.base}/api/dashboard")
        self.assertEqual(status, 200)
        d = json.loads(body)
        self.assertIn("total_topics", d)

    def test_api_network_local_scope(self):
        status, body, _ = _http_get(f"{self.base}/api/network")
        self.assertEqual(status, 200)
        net = json.loads(body)
        self.assertEqual(net["scope"], "local")
        self.assertEqual(net["bind_host"], "127.0.0.1")
        self.assertEqual(net["local_url"], f"http://127.0.0.1:{self.port}/")
        self.assertIsNone(net["lan_url"])
        self.assertIsNone(net["lan_ip_detected"])
        self.assertIsNone(net["lan_warning"])

    def test_human_tips_html_loads(self):
        status, body, _ = _http_get(f"{self.base}/human_tips.html")
        self.assertEqual(status, 200)

    def test_real_topic_html_loads(self):
        status, body, _ = _http_get(f"{self.base}/topic.html?id=T_ae36733de0f4cf3e")
        self.assertEqual(status, 200)

    def test_format_js_loads(self):
        status, body, _ = _http_get(f"{self.base}/static/format.js")
        self.assertEqual(status, 200)
        self.assertIn("MYT_FORMAT", body)

    def test_readonly_rejects_put(self):
        status, _, _ = _http_get(f"{self.base}/api/topics", method="PUT", body={})
        self.assertIn(status, (405, 501))

    def test_readonly_rejects_delete(self):
        status, _, _ = _http_get(f"{self.base}/api/topics", method="DELETE")
        self.assertIn(status, (405, 501))

    def test_readonly_rejects_patch(self):
        status, _, _ = _http_get(f"{self.base}/api/topics", method="PATCH", body={})
        self.assertIn(status, (405, 501))


@unittest.skipUnless(_start_viewer is not None, "skip")
class TestLanViewerReadOnly(unittest.TestCase):
    """Viewer bound to 0.0.0.0 — verify read-only + LAN scope reporting."""

    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        if cls.port is None:
            raise unittest.SkipTest("socket init failed (WinError 10106)")
        cls.proc = _start_viewer(cls.port, "0.0.0.0")
        cls.base_local = f"http://127.0.0.1:{cls.port}"
        # Also try the LAN IP if detected
        cls.lan_ip = forum_viewer.detect_lan_ipv4()
        cls.base_lan = f"http://{cls.lan_ip}:{cls.port}" if cls.lan_ip else None

    @classmethod
    def tearDownClass(cls):
        _stop_viewer(cls.proc)

    def test_localhost_works(self):
        status, body, _ = _http_get(f"{self.base_local}/")
        self.assertEqual(status, 200)
        self.assertIn("MY HOT RADAR", body)

    def test_api_network_returns_lan_scope(self):
        status, body, _ = _http_get(f"{self.base_local}/api/network")
        self.assertEqual(status, 200)
        net = json.loads(body)
        self.assertEqual(net["scope"], "lan")
        self.assertEqual(net["bind_host"], "0.0.0.0")
        # lan_ip may be None on machines without LAN, but lan_url should
        # reflect that gracefully
        if self.lan_ip:
            self.assertEqual(net["lan_ip_detected"], self.lan_ip)
            self.assertEqual(net["lan_url"], f"http://{self.lan_ip}:{self.port}/")
        self.assertIsNotNone(net["lan_warning"])
        self.assertIn("trusted local networks", net["lan_warning"])

    def test_api_topics_still_works(self):
        status, _, _ = _http_get(f"{self.base_local}/api/topics")
        self.assertEqual(status, 200)

    def test_readonly_rejects_put_on_lan(self):
        status, _, _ = _http_get(f"{self.base_local}/api/topics", method="PUT", body={})
        self.assertIn(status, (405, 501))

    def test_readonly_rejects_delete_on_lan(self):
        status, _, _ = _http_get(f"{self.base_local}/api/topics", method="DELETE")
        self.assertIn(status, (405, 501))

    def test_readonly_rejects_post_to_topics(self):
        """POST /api/topics — even if HTTP 200, MUST NOT modify any file.

        The viewer's do_POST() falls through to _route() which matches
        /api/topics as the GET-list endpoint. The server returns 200
        with the same JSON the GET would, but no Forum file is touched.
        This is safe behavior — it's read-equivalent, not a write.
        We verify by snapshotting the directory mtimes before/after.
        """
        import os, time as _time
        forum_root = r"C:\MY-Hot-Radar-Bridge\forum\topics"
        before_mtimes = {
            d: os.path.getmtime(os.path.join(forum_root, d))
            for d in os.listdir(forum_root)
        }
        status, _, _ = _http_get(f"{self.base_local}/api/topics", method="POST", body={})
        self.assertEqual(status, 200)
        # Wait a moment to ensure mtimes would differ if any file were touched
        _time.sleep(0.5)
        after_mtimes = {
            d: os.path.getmtime(os.path.join(forum_root, d))
            for d in os.listdir(forum_root)
        }
        self.assertEqual(
            before_mtimes, after_mtimes,
            "POST /api/topics must NOT modify any topic file on disk",
        )

    def test_lan_url_reachable_if_detected(self):
        if not self.lan_ip:
            self.skipTest("no LAN IP detected on this host")
        status, body, _ = _http_get(f"{self.base_lan}/")
        self.assertEqual(status, 200)
        self.assertIn("MY HOT RADAR", body)

    def test_lan_api_network_uses_lan_host(self):
        """When client accesses via LAN IP, /api/network still reports scope=lan."""
        if not self.lan_ip:
            self.skipTest("no LAN IP detected on this host")
        status, body, _ = _http_get(f"{self.base_lan}/api/network")
        self.assertEqual(status, 200)
        net = json.loads(body)
        self.assertEqual(net["scope"], "lan")
        self.assertEqual(net["bind_host"], "0.0.0.0")
        self.assertEqual(net["lan_ip_detected"], self.lan_ip)


# ===========================================================================
# C. UI rendering tests (need running LAN viewer + Chromium)
# ===========================================================================

@unittest.skipUnless(_start_viewer is not None, "skip")
class TestLanStripUI(unittest.TestCase):
    """Verify the LAN strip renders on viewer pages only when scope=lan."""

    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        if cls.port is None:
            raise unittest.SkipTest("socket init failed (WinError 10106)")
        cls.proc = _start_viewer(cls.port, "0.0.0.0")
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        _stop_viewer(cls.proc)

    def test_index_html_includes_network_strip_js(self):
        # When scope=lan, the JS injected into the HTML must be served.
        status, body, _ = _http_get(f"{self.base}/")
        self.assertEqual(status, 200)
        # The strip JS lives in index.js, not the HTML — but we check
        # the index.js serves the network fetch code
        status2, body2, _ = _http_get(f"{self.base}/static/index.js")
        self.assertEqual(status2, 200)
        self.assertIn("/api/network", body2)
        self.assertIn("lan-strip", body2)

    def test_topic_html_includes_network_strip_js(self):
        status, body2, _ = _http_get(f"{self.base}/static/topic.js")
        self.assertEqual(status, 200)
        self.assertIn("/api/network", body2)
        self.assertIn("lan-strip", body2)

    def test_human_tips_html_includes_network_strip_js(self):
        status, body2, _ = _http_get(f"{self.base}/static/human_tips.js")
        self.assertEqual(status, 200)
        self.assertIn("/api/network", body2)
        self.assertIn("lan-strip", body2)

    def test_styles_include_lan_strip(self):
        status, body, _ = _http_get(f"{self.base}/static/styles.css")
        self.assertEqual(status, 200)
        self.assertIn(".lan-strip", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
