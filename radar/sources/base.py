"""
Source Adapter interface.

A Source Adapter knows how to fetch raw items from one specific kind of feed
(RSS, NEWS_SITE scraping a single article, an OFFICIAL_SOURCE press release
endpoint) and then convert them into a list of `Story` objects.

Rule: an adapter never publishes, never logs in, never bypasses robots.txt.
If a request fails, the adapter raises and the scanner continues with others.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import socket
import json

from ..models import Story, Source


DEFAULT_TIMEOUT_SECS = 10   # respect reasonable limits per spec
DEFAULT_USER_AGENT = "MY-Hot-Radar/0.1 (+radar-discovery; manual-mode)"


class FetchError(Exception):
    """Raised when an adapter cannot complete its fetch step."""


class SourceAdapter(ABC):
    """Base class for all source adapters.

    Subclasses must implement:
      - source: a Source instance describing themselves
      - fetch() -> List[Story]: pull current items and convert each to Story.

    `fetch` should be:
      - read-only
      - timeout-bounded (use DEFAULT_TIMEOUT_SECS)
      - exception-safe (raise FetchError on any failure)
    """

    source: Source

    @abstractmethod
    def fetch(self) -> List[Story]:
        ...

    # --- small helpers available to subclasses ---

    def _http_get(self, url: str, *, as_bytes: bool = False) -> bytes:
        req = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        try:
            with urlopen(req, timeout=DEFAULT_TIMEOUT_SECS) as r:
                return r.read() if as_bytes else r.read().decode("utf-8", errors="replace")
        except (URLError, HTTPError, socket.timeout, TimeoutError) as e:
            raise FetchError(f"{self.source.name}: HTTP error: {e!r}") from e

    def _http_post_json(self, url: str, payload: dict, *, headers: dict | None = None) -> dict:
        # Only used by adapters that need POST. Default not used in Phase 1.
        body = json.dumps(payload).encode("utf-8")
        h = {"Content-Type": "application/json", "User-Agent": DEFAULT_USER_AGENT}
        if headers:
            h.update(headers)
        req = Request(url, data=body, headers=h, method="POST")
        try:
            with urlopen(req, timeout=DEFAULT_TIMEOUT_SECS) as r:
                return json.loads(r.read().decode("utf-8"))
        except (URLError, HTTPError, socket.timeout, TimeoutError) as e:
            raise FetchError(f"{self.source.name}: HTTP error: {e!r}") from e
