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
_HTML_ENTITY_RX = re.compile(r"&#(\d+);", re.UNICODE)
_HTML_NAMED_RX = re.compile(r"&(amp|lt|gt|apos|quot|nbsp);", re.IGNORECASE)
_NONBREAK_RX = re.compile(r"[\u00a0\u200b\u200c\u200d\ufeff]")
_PUNCT_RX = re.compile(r"[\u2000-\u206F\u2E00-\u2E7F'\"!?,;:\(\)\[\]\{\}\-_/\\\|`~@#\$%\^&\*\+=<>]")
_PUNCT_LIGHT = re.compile(r"[^\w\s\u4e00-\u9fff\u3400-\u4dbf]", re.UNICODE)


def unescape_html(s: str) -> str:
    """Light HTML entity unescape for the small set seen in real-world feeds."""
    if not s:
        return s
    # Numeric entities
    s = _HTML_ENTITY_RX.sub(lambda m: chr(int(m.group(1))), s)
    # Common named entities
    table = {"amp": "&", "lt": "<", "gt": ">", "apos": "'",
             "quot": '"', "nbsp": " "}
    def rep(m):
        return table.get(m.group(1).lower(), m.group(0))
    s = _HTML_NAMED_RX.sub(rep, s)
    return s


def normalize_title(title: str) -> str:
    """Return a lowercase, accent-stripped, punctuation-stripped string.

    Suitable for token-set operations and as a human-readable 'this is the same
    event' fingerprint.

    Order:
      1. unescape HTML entities
      2. normalize Unicode (NFKC)
      3. strip smart quotes
      4. lowercase
      5. drop non-breaking / zero-width spaces
      6. drop noise punctuation but keep word chars, whitespace, CJK
      7. collapse whitespace
    """
    if not title:
        return ""
    s = unescape_html(title)
    s = unicodedata.normalize("NFKC", s)
    s = _NORM_RX.sub("", s)
    s = s.lower()
    s = _NONBREAK_RX.sub(" ", s)
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

def extract_entities(text_in: str) -> set:
    """Return a set of named-entity-ish tokens (lowercased) from raw title text.

    This isn't perfect NER — it's a cheap structural signal that two
    headlines both mention "Trump", "Xi", "Anwar", "Mahathir", "Hasmah",
    "Samsung", "OpenAI", etc. When two titles share enough entities, they
    probably describe the same event.

    Tokenization handles:
      - Hyphenated names: "Trump-Xi" -> {"trump", "xi"}
      - Apostrophes:    "Trump's"    -> {"trump"}
      - "Dr Mahathir"   -> {"dr", "mahathir"} (dr is kept; harmless)
      - Two-letter caps: "Xi", "KL", "US" pass through
    """
    if not text_in:
        return set()
    out = set()
    # First: extract word tokens including hyphens/apostrophes
    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", text_in)
    for tok in raw_tokens:
        # Split on hyphen so "Trump-Xi" yields "trump", "xi"
        for piece in re.split(r"[-']", tok):
            piece = piece.strip()
            if len(piece) < 2:
                continue
            # Pure-digits pieces are dropped
            if piece.isdigit():
                continue
            low = piece.lower()
            if low in _ENTITY_STOPWORDS:
                continue
            out.add(low)
    return out


_ENTITY_STOPWORDS = frozenset({
    # Common English determiners / prepositions / conjunctions
    "the", "a", "an", "and", "or", "but", "nor", "yet", "so",
    "for", "from", "with", "without", "after", "before", "over", "into",
    "out", "off", "on", "in", "at", "by", "to", "of", "as", "per", "via",
    "amid", "amidst", "between", "during", "since", "until", "about",
    # Common English verbs (catches false-entity extraction of headlines)
    "is", "are", "was", "were", "be", "been", "being", "am",
    "have", "has", "had", "having",
    "do", "does", "did", "doing", "done",
    "go", "goes", "went", "gone", "going",
    "make", "makes", "made", "making",
    "say", "says", "said", "saying", "tell", "told", "telling",
    "take", "takes", "taken", "taking",
    "give", "gives", "given", "giving",
    "get", "gets", "got", "gotten", "getting",
    "see", "sees", "saw", "seen", "seeing",
    "use", "uses", "used", "using",
    # Common pronouns / demonstratives / possessives
    "his", "her", "its", "their", "my", "your", "our",
    "this", "that", "these", "those",
    # Common question words
    "why", "how", "what", "when", "where", "who", "which",
    # Common adjectives / determiners
    "all", "any", "no", "not", "only", "own", "same", "such",
    "now", "new", "old", "top", "two", "one",
    "most", "more", "less", "much", "many", "few",
    "than", "just", "also", "very", "even", "still",
    "back", "here", "there",
    # Modal verbs (often capitalized in headlines)
    "could", "would", "should", "might", "must", "shall", "will",
    "can", "may",
    # Ordinals / numerals
    "first", "last", "next",
    "five", "three", "six", "four", "seven", "eight", "nine", "ten",
    "some", "every", "each",
    # Common headline nouns that aren't real entities
    "deal", "deals", "death", "killed",
    "year", "years", "day", "days", "week", "weeks", "month", "months",
    "today", "tomorrow", "yesterday",
    # Common headline verbs (lowercase)
    "openai",
    "knew", "knows", "knowing",
    "wants", "want", "wanted",
    "faces", "faced", "facing",
    "plans", "planned", "planning",
    "asks", "asked", "asking",
    "calls", "called", "calling",
})


def entity_overlap(a: str, b: str) -> Tuple[int, int, float]:
    """Return (overlap_count, smaller_set_size, jaccard) of entity tokens.

    Two stories about the same event typically share 2+ named entities.
    """
    ea, eb = extract_entities(a), extract_entities(b)
    if not ea or not eb:
        return (0, 0, 0.0)
    inter = ea & eb
    smaller = min(len(ea), len(eb))
    union = ea | eb
    jacc = len(inter) / max(1, len(union))
    return (len(inter), smaller, jacc)
