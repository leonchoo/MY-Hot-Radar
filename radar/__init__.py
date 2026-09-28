"""
MY Hot Radar - radar package.

This package is the Phase 1 Radar: a source-discovery + dedup + verification +
momentum + classification pipeline that produces human-readable + machine-readable
reports.

Design rules:
- No external dependencies. Pure Python stdlib only.
- No automatic publishing, no Facebook, no scheduler.
- Dedup, verification, momentum, classification must all be explainable.
- Everything that touches the network respects timeouts and graceful failure.
"""
__version__ = "0.1.0"
