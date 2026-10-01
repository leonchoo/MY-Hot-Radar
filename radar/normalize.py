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

# ============================================================================
# Chinese place-name alias map (Phase A1, see docs/CHINESE_DEDUP_A1_IMPLEMENTATION.md)
# ============================================================================
#
# A frozen, version-pinned alias map for cross-language dedup of
# place names. Each entry maps a Chinese place-name string to ONE ASCII
# canonical form. The canonical form is the same as the English / Malay
# rendering so that entity_overlap() can match across languages.
#
# SCOPE DISCIPLINE — the alias map contains ONLY place names (countries,
# states, capitals, districts, border landmarks). It does NOT contain:
#   * Concept words (宣布 / announces / 措施 / measures / 事件 / event)
#   * Verbs (公布 / releases)
#   * Generic nouns (新闻 / news / 国家 / country)
# Concept aliases would explode false-merge risk because most articles
# in the same category share such words. Place-name aliases are
# specific: "柔佛" maps to "johor" and nothing else, "新山" maps to
# "johorbahru" and nothing else.
#
# ORDER DISCIPLINE — Python dict iteration is insertion-ordered (Py 3.7+),
# so longer / more-specific entries are listed FIRST. This prevents
# "马来西亚" from being fragmented into "马" + "来西亚" + ...
#
# DETERMINISM — the alias map is a module-level frozenset-style constant
# (plain ``dict`` but frozen by version). No runtime mutation. No I/O.
# No external dependency.
#
# NOT-MUTATION CONTRACT — _apply_aliases() returns a NEW string. The
# caller's text is never modified. Alias substitution only feeds into
# the entity-extraction path; the original `title` in Story, in
# public/radar/latest.json, and in any user-visible output remains
# the raw input text (including the Chinese characters).
#
# Each alias entry was reviewed against the safety test fixtures in
# ``radar/tests/test_dedup_cjk.py``. Adding a new alias requires a new
# positive AND negative fixture, plus a justification added to the
# implementation report. Do not expand scope informally.

_ZH_TO_CANONICAL_VERSION = "phase-chinese-1-integration-v1"

_ZH_TO_CANONICAL = {
    # ------------------------------------------------------------------
    # Countries (longest first)
    # ------------------------------------------------------------------
    "马来西亚": "malaysia",       # Malaysia
    "新加坡": "singapore",        # Singapore

    # ------------------------------------------------------------------
    # State / federal-territory capitals
    # ------------------------------------------------------------------
    "吉隆坡": "kuala_lumpur",    # Kuala Lumpur (federal territory)

    # ------------------------------------------------------------------
    # Johor state and districts (the highest-value cross-border source set)
    # ------------------------------------------------------------------
    "柔佛": "johor",              # Johor (state)
        "新山": "johor_bahru",         # Johor Bahru (state capital)
    # NOTE: smaller district names like 古来 (Kulai), 麻坡 (Muar),
    # 笨珍 (Pontian), 居銮 (Kluang), 丰盛港 (Mersing),
    # 巴西古当 (Pasir Gudang) are deliberately NOT aliased. Aliasing
    # them to their district name would still leave them as place-name
    # matches, but cross-language inference for small Johor towns is
    # risky (a Chinese article mentioning 古来 may describe a Johor
    # *state*-wide event, not a Kulai-specific one). Per Audit §7.6
    # and §9.3 the safe rule is: only alias unambiguous / unique
    # place-name pairs where the Chinese form is unambiguous in
    # Malaysian context.

    # ------------------------------------------------------------------
    # Cross-border pair (used for RTS, Causeway, border-news context)
    # Both 马新 and 新马 are common short forms. Both substituted to the
    # SAME canonical form so that entity_overlap matches them.
    # ------------------------------------------------------------------
    "马新": "malaysia_singapore",
    "新马": "malaysia_singapore",
}


def _apply_aliases(text: str) -> str:
    """Apply Chinese place-name alias substitution. Returns a NEW string.

    Short-circuits on text that contains no CJK characters — existing
    English / Malay paths are bit-identical to before this function was
    added (zero overhead, zero behavioral change).

    The substitution is a single pass over the (Chinese-containing)
    text, replacing each ``_ZH_TO_CANONICAL`` key with the canonical
    form padded by ASCII token boundaries. The pad is necessary so
    that ``malaysia`` and an immediately adjacent ASCII token like
    ``RTS`` become two distinct entities instead of being glued
    together into ``malaysiarts`` by the existing entity regex
    ``[A-Za-z][A-Za-z0-9'-]*``.

    Each canonical form is prefixed with a leading ASCII space and
    suffixed with a trailing ASCII space (then whitespace is
    collapsed at the end). This guarantees that ``马来西亚RTS进展``
    becomes ``malaysia RTS 进展`` (two distinct entities) and that
    ``前往马来西亚`` becomes ``前往 malaysia 进展``.

    Because the dict is longest-first (insertion-ordered), longer
    entries are applied before shorter ones, so ``马来西亚`` is
    substituted as a whole before any 2-char fragment could match.

    The caller's string is not modified. The returned string is what
    the existing ASCII regex sees. Alias substitution therefore cannot
    leak into the original title, into Story.title, or into the public
    output JSON — only into the entity-extraction set returned by
    ``extract_entities()``.

    The output is lowercase (canonical forms are lowercase ASCII), but
    the surrounding non-Chinese context retains its original case
    because ``str.replace`` only touches the matched substrings.

    Idempotent: applying twice is the same as applying once (canonical
    forms are surrounded by spaces that are then collapsed; a second
    pass has nothing to substitute because they are now pure ASCII).
    """
    if not text:
        return text
    # CJK-block short-circuit: skip substitution when no Chinese chars.
    # This is the bit-identical fast path for English / Malay inputs.
    has_cjk = False
    for ch in text:
        if (
            '一' <= ch <= '鿿'
            or '　' <= ch <= '〿'
            or '㐀' <= ch <= '䶿'
        ):
            has_cjk = True
            break
    if not has_cjk:
        return text
    out = text
    for zh, canonical in _ZH_TO_CANONICAL.items():
        if zh in out:
            # Surround the canonical form with spaces so it tokenizes
            # independently from any adjacent ASCII letters. Whitespace
            # is collapsed at the end so input-side spaces are not
            # preserved as double spaces.
            out = out.replace(zh, f" {canonical} ")
    # Collapse whitespace runs to single spaces and trim.
    out = re.sub(r"\s+", " ", out).strip()
    return out


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
      - Chinese place-name aliases: "柔佛" -> "johor", "新山" -> "johorbahru",
        etc. Applied to a *copy* of the text via ``_apply_aliases`` BEFORE
        the ASCII regex runs. The original title is NOT mutated; only the
        entity-extraction view sees the alias-substituted form.

    The alias map is a frozen ``dict`` keyed by Chinese string -> ASCII
    canonical form. It contains NO concepts / verbs / nouns — only place
    names — so it cannot introduce false merges of events that share only
    a location but differ in actors / actions / timing. See
    ``docs/CHINESE_DEDUP_A1_IMPLEMENTATION.md`` for the safety analysis.
    """
    if not text_in:
        return set()
    # Apply Chinese place-name alias normalization on a string view.
    # The original text_in is untouched; only this view is used for
    # entity extraction. This is the documented A1 hook.
    view = _apply_aliases(text_in)
    out = set()
    # First: extract word tokens including hyphens/apostrophes
    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", view)
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
        # A2.8-R1 — Minimal entity bridge guard.
        # A2.5 chain investigation replay proved these two tokens were the *first*
        # false bridge of t_d687fc (CNA ↔ Borneo Post merged via shared {period,
        # transition}). Adding them here eliminates that bridge while leaving every
        # other entity token (including `man`, `kata`, `dr`) intact for legitimate
        # same-source analyst merges and cross-language dedup.
        # Do NOT expand this list without a documented A2.5/A2.7 replay showing
        # the new token is the root cause of a verified false merge. See
        # docs/CHINESE_DEDUP_ENTITY_GUARD_A28R1.md.
        "period", "transition",
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
