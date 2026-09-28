"""
Adapter package init.
"""

from .base import SourceAdapter, FetchError, DEFAULT_TIMEOUT_SECS, DEFAULT_USER_AGENT

__all__ = ["SourceAdapter", "FetchError", "DEFAULT_TIMEOUT_SECS", "DEFAULT_USER_AGENT"]
