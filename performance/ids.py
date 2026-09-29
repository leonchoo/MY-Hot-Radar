"""
Deterministic IDs for Performance Intelligence.

All IDs are stable SHA-256 hex digests of a canonical JSON payload.
A short namespace prefix (`p_`, `s_`, `o_`, `f_`, `m_`) makes the
type clear and prevents accidental collision with Radar / Candidate IDs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from .enums import Platform, SourceType


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    )


def _hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def content_id_for(
    *,
    source_type: SourceType,
    platform: Platform,
    publisher: str,
    url: str,
    title: str,
) -> str:
    """Deterministic content id. Same canonical fields → same id."""
    payload = {
        "kind": "content_id_v1",
        "source_type": source_type.value,
        "platform": platform.value,
        "publisher": publisher,
        "url": url,
        "title": title,
    }
    return "p_" + _hash(payload)[:32]


def snapshot_id_for(content_id: str, captured_at: str) -> str:
    payload = {
        "kind": "snapshot_id_v1",
        "content_id": content_id,
        "captured_at": captured_at,
    }
    return "s_" + _hash(payload)[:32]


def observation_id_for(
    content_id: str,
    from_captured_at: str,
    to_captured_at: str,
) -> str:
    payload = {
        "kind": "observation_id_v1",
        "content_id": content_id,
        "from_captured_at": from_captured_at,
        "to_captured_at": to_captured_at,
    }
    return "o_" + _hash(payload)[:32]


def feature_id_for(content_id: str, captured_at: str) -> str:
    payload = {
        "kind": "feature_id_v1",
        "content_id": content_id,
        "captured_at": captured_at,
    }
    return "f_" + _hash(payload)[:32]


def market_observation_id_for(
    *,
    publisher: str,
    platform: Platform,
    content_url: str,
    captured_at: str,
) -> str:
    payload = {
        "kind": "market_obs_id_v1",
        "publisher": publisher,
        "platform": platform.value,
        "content_url": content_url,
        "captured_at": captured_at,
    }
    return "m_" + _hash(payload)[:32]
