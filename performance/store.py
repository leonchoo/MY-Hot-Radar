"""
Atomic JSON persistence for Performance Intelligence.

Layout (all under `performance_data/`, gitignored):

  performance_data/
    content/
      <content_id>.json              ContentIdentity
    snapshots/
      <snapshot_id>.json             PerformanceSnapshot
    observations/
      <observation_id>.json          PerformanceObservation
    features/
      <feature_id>.json              ContentFeatureSnapshot
    market/
      <observation_id>.json          MarketObservation
    insights/
      <insight_id>.json              Insight
    latest.json                      Index (synthetic-flag aware)

All writes are atomic:
  1. Build dict in memory.
  2. validate_payload() (raise on failure).
  3. Write to a `.tmp` sibling file.
  4. flush() + os.fsync().
  5. os.replace(tmp, final).

A failure at any step preserves the previous file. The store never
deletes data; users can purge via explicit `delete_*` calls.

The store refuses to persist anything tagged SYNTHETIC. Synthetic
fixtures live only in `tests/` and are not exposed to production
output.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    ContentFeatureSnapshot,
    ContentIdentity,
    Insight,
    MarketObservation,
    PerformanceObservation,
    PerformanceSnapshot,
)
from .models_validate import (
    validate_content_identity,
    validate_feature_snapshot,
    validate_insight,
    validate_market_observation,
    validate_snapshot,
)
from .validation import ValidationError


# Default storage root. Lives outside the repo (gitignored via
# `performance_data/` rule added to .gitignore).
DEFAULT_PERFORMANCE_DATA_DIR = (
    Path(__file__).resolve().parent.parent / "performance_data"
)


class SyntheticFixtureError(ValueError):
    """Raised when an attempt is made to persist a SYNTHETIC fixture
    through the production store. Synthetic data must stay in tests."""


SYNTHETIC_FLAG = "_synthetic"


def _is_synthetic(payload: Dict[str, Any]) -> bool:
    return bool(payload.get(SYNTHETIC_FLAG))


def _validate_payload(payload: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """Strip the synthetic flag if present (refuses to store synthetics)
    and return a JSON-safe dict."""
    if _is_synthetic(payload):
        raise SyntheticFixtureError(
            f"refusing to store SYNTHETIC {kind}: {payload.get('content_id') or payload.get('id')}"
        )
    # Must be JSON-serializable
    try:
        json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"{kind} is not JSON-serializable: {e}")
    return payload


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Atomic write: tmp + flush + fsync + os.replace.

    On any failure between tmp write and os.replace, the previous
    file (if any) is preserved.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Build a unique tmp file in the same directory (os.replace
    # must stay on the same filesystem).
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                # fsync may not be supported on some Windows configs.
                pass
        os.replace(tmp_name, path)
    except Exception:
        # Clean up the tmp file
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class PerformanceStore:
    """File-backed JSON store for Performance Intelligence.

    The store is intentionally simple: one file per entity, indexed
    by deterministic id. There is no database, no schema migration,
    no global lock. Multi-process access is not supported.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_PERFORMANCE_DATA_DIR
        self.content_dir = self.data_dir / "content"
        self.snapshots_dir = self.data_dir / "snapshots"
        self.observations_dir = self.data_dir / "observations"
        self.features_dir = self.data_dir / "features"
        self.market_dir = self.data_dir / "market"
        self.insights_dir = self.data_dir / "insights"
        self.latest_path = self.data_dir / "latest.json"

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def ensure_dirs(self) -> None:
        for d in (
            self.content_dir,
            self.snapshots_dir,
            self.observations_dir,
            self.features_dir,
            self.market_dir,
            self.insights_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # ContentIdentity
    # ------------------------------------------------------------------

    def put_content(self, content: ContentIdentity) -> Path:
        validate_content_identity(content)
        payload = content.to_dict()
        _validate_payload(payload, "ContentIdentity")
        path = self.content_dir / f"{content.content_id}.json"
        _atomic_write_json(path, payload)
        return path

    def get_content(self, content_id: str) -> Optional[Dict[str, Any]]:
        return _read_json(self.content_dir / f"{content_id}.json")

    def list_content(self) -> List[Dict[str, Any]]:
        if not self.content_dir.exists():
            return []
        out = []
        for f in self.content_dir.glob("*.json"):
            d = _read_json(f)
            if d is not None:
                out.append(d)
        return out

    # ------------------------------------------------------------------
    # PerformanceSnapshot
    # ------------------------------------------------------------------

    def put_snapshot(self, snap: PerformanceSnapshot) -> Path:
        validate_snapshot(snap)
        payload = snap.to_dict()
        _validate_payload(payload, "PerformanceSnapshot")
        # Sanitize captured_at for filesystem (replace ':' and '+').
        # We keep the original captured_at IN the payload; only the
        # filename gets the sanitized form. This makes the store
        # portable across Windows / Linux.
        safe_cap = snap.captured_at.replace(":", "-").replace("+", "p")
        path = self.snapshots_dir / f"{safe_cap}__{snap.content_id}.json"
        _atomic_write_json(path, payload)
        return path

    def list_snapshots_for(self, content_id: str) -> List[Dict[str, Any]]:
        if not self.snapshots_dir.exists():
            return []
        out = []
        for f in self.snapshots_dir.glob(f"*__{content_id}.json"):
            d = _read_json(f)
            if d is not None:
                out.append(d)
        # Sort by captured_at for deterministic ordering
        out.sort(key=lambda d: d.get("captured_at", ""))
        return out

    # ------------------------------------------------------------------
    # PerformanceObservation
    # ------------------------------------------------------------------

    def put_observation(self, obs: PerformanceObservation) -> Path:
        payload = obs.to_dict()
        _validate_payload(payload, "PerformanceObservation")
        # Sanitize timestamps for filesystem
        safe_from = obs.from_captured_at.replace(":", "-").replace("+", "p")
        safe_to = obs.to_captured_at.replace(":", "-").replace("+", "p")
        # P3-B-4: include observation_id in filename for indexing.
        # Filename keeps (content_id, from, to) tuple ordering so
        # two observations of the same content with different
        # timestamps land in different files; same (from, to)
        # overwrite (idempotent).
        oid = obs.observation_id or "unidentified"
        path = self.observations_dir / (
            f"{obs.content_id}__{safe_from}__{safe_to}__{oid}.json"
        )
        _atomic_write_json(path, payload)
        return path

    def list_observations_for(self, content_id: str) -> List[Dict[str, Any]]:
        if not self.observations_dir.exists():
            return []
        out = []
        for f in self.observations_dir.glob(f"{content_id}__*.json"):
            d = _read_json(f)
            if d is not None:
                out.append(d)
        out.sort(key=lambda d: (d.get("from_captured_at", ""),
                                  d.get("to_captured_at", "")))
        return out

    # ------------------------------------------------------------------
    # ContentFeatureSnapshot
    # ------------------------------------------------------------------

    def put_feature(self, f: ContentFeatureSnapshot) -> Path:
        validate_feature_snapshot(f)
        payload = f.to_dict()
        _validate_payload(payload, "ContentFeatureSnapshot")
        # Sanitize captured_at for filesystem
        safe_cap = f.captured_at.replace(":", "-").replace("+", "p")
        path = self.features_dir / f"{f.content_id}__{safe_cap}.json"
        _atomic_write_json(path, payload)
        return path

    def get_feature(self, content_id: str, captured_at: str) -> Optional[Dict[str, Any]]:
        safe_cap = captured_at.replace(":", "-").replace("+", "p")
        return _read_json(self.features_dir / f"{content_id}__{safe_cap}.json")

    # ------------------------------------------------------------------
    # MarketObservation
    # ------------------------------------------------------------------

    def put_market_observation(self, m: MarketObservation) -> Path:
        validate_market_observation(m)
        payload = m.to_dict()
        _validate_payload(payload, "MarketObservation")
        path = self.market_dir / f"{m.observation_id}.json"
        _atomic_write_json(path, payload)
        return path

    def list_market_observations(self) -> List[Dict[str, Any]]:
        if not self.market_dir.exists():
            return []
        out = []
        for f in self.market_dir.glob("*.json"):
            d = _read_json(f)
            if d is not None:
                out.append(d)
        return out

    # ------------------------------------------------------------------
    # Insight
    # ------------------------------------------------------------------

    def put_insight(self, i: Insight) -> Path:
        validate_insight(i)
        payload = i.to_dict()
        _validate_payload(payload, "Insight")
        path = self.insights_dir / f"{i.insight_id}.json"
        _atomic_write_json(path, payload)
        return path

    def list_insights(self) -> List[Dict[str, Any]]:
        if not self.insights_dir.exists():
            return []
        out = []
        for f in self.insights_dir.glob("*.json"):
            d = _read_json(f)
            if d is not None:
                out.append(d)
        return out

    # ------------------------------------------------------------------
    # Latest index
    # ------------------------------------------------------------------

    def rebuild_latest(self) -> Path:
        """Rebuild the index file. Refuses to include synthetic data.

        The index lists counts only. It does NOT include payload
        bodies, to keep it small and safe to surface externally.
        """
        self.ensure_dirs()
        content = [c for c in self.list_content()
                   if not _is_synthetic(c)]
        # Filter content that is OWN or MARKET (both are valid; we
        # only exclude the SYNTHETIC flag).
        own = sum(1 for c in content if c.get("source_type") == "OWN")
        market = sum(1 for c in content if c.get("source_type") == "MARKET")
        payload = {
            "schema_version": 1,
            "generated_at": self._utcnow_iso(),
            "counts": {
                "content": len(content),
                "content_own": own,
                "content_market": market,
                "snapshots": sum(
                    1 for _ in self.snapshots_dir.glob("*.json")
                    if not _is_synthetic(_read_json(_) or {})
                ),
                "observations": sum(
                    1 for _ in self.observations_dir.glob("*.json")
                ),
                "features": sum(
                    1 for _ in self.features_dir.glob("*.json")
                    if not _is_synthetic(_read_json(_) or {})
                ),
                "market_observations": sum(
                    1 for _ in self.market_dir.glob("*.json")
                ),
                "insights": sum(
                    1 for _ in self.insights_dir.glob("*.json")
                ),
            },
        }
        _atomic_write_json(self.latest_path, payload)
        return self.latest_path

    @staticmethod
    def _utcnow_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
