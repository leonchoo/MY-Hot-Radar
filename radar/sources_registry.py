"""
Source registry.

Phase 1 ships with zero hard-coded real news feed URLs. To add a real source
in a future batch, register it here with its Source metadata and a category.
For now, sources live entirely under radar_data/ as JSONL files readable by
FileAdapter.
"""

from __future__ import annotations

from typing import Dict, List

from .models import Source, SourceType, Category, Language


# Empty on purpose in Phase 1. Future batches will populate this list after
# explicit user approval of each Source (name, url, reliability, category).
#
# Example placeholder (commented out):
#
#     Source(
#         name="Example Outlet - RSS",
#         type=SourceType.RSS,
#         url="https://example.com/feed",
#         reliability=4,
#         country="MY",
#         languages=[Language.EN],
#         notes="Placeholder. Do not enable until reviewed.",
#     ),
REGISTERED_SOURCES: List[Source] = []


def load_sources() -> List[Source]:
    """Return the current source list. Right now: empty list.

    Future: read from a YAML/JSON config. Phase 1 keeps it explicit and empty
    so the Radar can be exercised deterministically with FileAdapter only.
    """
    return list(REGISTERED_SOURCES)


def get_registered_source(name: str) -> Source | None:
    for s in REGISTERED_SOURCES:
        if s.name == name:
            return s
    return None
