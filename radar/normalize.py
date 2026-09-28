"""
Normalize a Story's title for dedup.

Goals:
- Stable across Unicode and whitespace differences.
- Useful for similarity (token-set Jaccard) AND for keyword extraction.
- Cheap to compute. No external models.

NOT in scope for Phase 1:
- Entity extraction (no NER).
- Embedding-based similarity.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List


# A small, conservative list of multi-lingual noise words.
_STOPWORDS = {
    # English
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "at", "with",
    "is", "are", "was", "were", "be", "been", "being", "by", "as", "from",
    "this", "that", "these", "those", "it", "its", "but", "not", "no", "yes",
    "have", "has", "had", "do", "does", "did", "will", "would", "can", "could",
    "should", "may", "might", "must", "shall", "i", "you", "he", "she", "we",
    "they", "them", "his", "her", "their", "my", "your", "our",
    # Chinese (very light)
    "的", "了", "在", "是", "和", "与", "或", "为", "有", "无", "对", "从",
    "到", "上", "下", "中", "里", "外", "以", "及", "之", "亦", "並", "与",
    # Malay (common)
    "di", "yang", "dan", "itu", "ini", "dengan", "tidak", "ada", "untuk",
    "pada", "ke", "dari", "oleh", "atau", "juga",
}

# Strip quotes, dots near alphanumerics, soft hyphens, and (optionally) trailing / leading digits.
_NORM_RX = re.compile(r"[‘’“”]", re.UNICODE)
_PUNCT_RX = re.compile(r"[\u2000-\u206F\u2E00-\u2E7F'\"!?,;:\(\)\[\]\{\}\-_/\\\|`~@#\$%\^&\*\+=<>]")
_PUNCT_LIGHT = re.compile(r"[^\w\s\u4e00-\u9fff\u3400-\u4dbf]", re.UNICODE)


def normalize_title(title: str) -> str:
    """Return a lowercase, accent-stripped, punctuation-stripped string.

    Suitable for token-set operations and as a human-readable 'this is the same
    event' fingerprint.
    """
    if not title:
        return ""
    s = unicodedata.normalize("NFKC", title)
    s = _NORM_RX.sub("", s)
    s = s.lower()
    s = _PUNCT_LIGHT.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(title_norm: str) -> List[str]:
    """Crude whitespace + CJK-aware tokenizer. Returns a stable token list."""
    if not title_norm:
        return []
    out: List[str] = []

    # 1. ASCII runs
    ascii_runs = re.split(r"\s+", title_norm)
    cjk_buf: List[str] = []
    for run in ascii_runs:
        run = run.strip()
        if not run:
            continue
        # If this run has CJK characters, flush and switch to per-character mode.
        if any("　" <= ch <= "〿" or "一" <= ch <= "鿿" for ch in run):
            # Flush any pending ascii tokens
            for t in out:
                pass  # noop; we already append straight below
            # Walk this run character by character
            for ch in run:
                if "一" <= ch <= "鿿" or "　" <= ch <= "〿":
                    if cjk_buf:
                        out.append("".join(cjk_buf))
                        cjk_buf = []
                    out.append(ch)
                else:
                    if ch.strip():
                        cjk_buf.append(ch)
        else:
            if cjk_buf:
                out.append("".join(cjk_buf))
                cjk_buf = []
            out.append(run)
    if cjk_buf:
        out.append("".join(cjk_buf))

    # remove empties, length 1 ASCII noise (kept CJK single chars which are meaningful)
    cleaned: List[str] = []
    for t in out:
        if not t:
            continue
        if len(t) == 1 and ord(t[0]) < 128 and t in _STOPWORDS:
            continue
        cleaned.append(t)
    return cleaned


def extract_keywords(title: str, *, max_k: int = 8) -> List[str]:
    """Return stable, stopword-filtered, length-sorted keywords for a title.

    Used as a fallback when normalized title token sets disagree.
    """
    norm = normalize_title(title)
    toks = tokens(norm)
    seen: List[str] = []
    seen_set = set()
    for t in toks:
        if t in _STOPWORDS:
            continue
        if len(t) < 2:
            continue
        if t in seen_set:
            continue
        seen.append(t)
        seen_set.add(t)
    # longer first
    seen.sort(key=lambda s: (-len(s), s))
    return seen[:max_k]


def token_jaccard(a: str, b: str) -> float:
    """Jaccard similarity on token sets from two normalized titles."""
    sa = set(tokens(normalize_title(a)))
    sb = set(tokens(normalize_title(b)))
    if not sa and not sb:
        return 0.0
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union) if union else 0.0


def keyword_overlap(a: List[str], b: List[str]) -> float:
    """Fraction of the smaller list that's also in the larger list."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))
