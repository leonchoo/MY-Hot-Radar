"""
Counter-signal registry.

Per VERIFICATION_RULES.md: a credible counter-signal (especially from a
Tier-A source) drops the topic at least one status rung. A confirmed
official denial = RUMOUR.

This module is a deliberately minimal in-memory registry. Phase 1 has no
automated ingestion of denial/correction feeds; counter-signals come from:

  1. Tests (register a CounterSignal before a scan)
  2. Manual additions by an operator (e.g. a verified journalist adds a
     denial they confirmed from a Tier-A press release)

We DO NOT auto-crawl for denial patterns ("X is a hoax", "this is false")
because:
  - That's a claims-database problem, not a feed problem.
  - False positives would be catastrophic for the brand.

The registry is intentionally simple. A future batch may add persistence
and an admin UI; right now it lives only in process memory.
"""

from __future__ import annotations

import threading
from typing import Dict, Iterable, List, Optional

from .models import CounterSignal, CounterSignalStance, SourceTier


# Singleton, but testable: tests can construct a fresh CounterSignalRegistry()
# to avoid leakage between tests.
class CounterSignalRegistry:
    """In-memory store of CounterSignals, keyed by Topic.content_key()."""

    def __init__(self) -> None:
        self._by_key: Dict[str, List[CounterSignal]] = {}
        self._lock = threading.RLock()

    def register(self, signal: CounterSignal) -> None:
        with self._lock:
            self._by_key.setdefault(signal.topic_content_key, []).append(signal)

    def register_many(self, signals: Iterable[CounterSignal]) -> None:
        with self._lock:
            for s in signals:
                self._by_key.setdefault(s.topic_content_key, []).append(s)

    def for_topic(self, topic_content_key: str) -> List[CounterSignal]:
        with self._lock:
            return list(self._by_key.get(topic_content_key, []))

    def clear(self) -> None:
        with self._lock:
            self._by_key.clear()

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_key.values())


# Process-wide default registry (so the verification engine has a place to
# look). Tests can construct their own and inject via attach_verification().
_default: Optional[CounterSignalRegistry] = None


def default_registry() -> CounterSignalRegistry:
    global _default
    if _default is None:
        _default = CounterSignalRegistry()
    return _default


def reset_default_registry() -> None:
    """Used by tests to start fresh."""
    global _default
    _default = None
