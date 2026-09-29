"""
Phase 2 Batch 1 — Politics Radar: neutral factual handling.

This module EXTENDS the existing Radar system with politics-specific
classification, attribution, and output rules. It does NOT replace
verification, counter-signal, or classification engines.

Per spec section 4: "不要重复造一套完全独立的政治系统。优先扩展
现有模型。"

Three orthogonal axes are introduced:

  1. PoliticalClaimKind   -- what KIND of political content is this?
                             (EVENT | CLAIM | OPINION)

  2. PoliticalClaim       -- the structured representation of a single
                             politically-themed item, with attribution
                             fields. The Reporting source and the
                             Claiming source are tracked separately.

  3. PoliticalOutputRule  -- the output-side guardrails that prevent
                             the system from generating ranking /
                             endorsement / prediction language.

The module is deliberately small. The heavy lifting (verification,
counter-signal precedence, confidence labels) is delegated to the
existing engines. Politics adds:

  - a claim-kind classifier (EVENT/CLAIM/OPINION)
  - an attribution-aware data shape
  - a render-safe formatter
  - output-banned-phrase enforcement
  - a poll-data stub (records but never predicts)

Per spec section 12: this batch does NOT implement a polling engine.
Poll data is recorded as a tuple with the data we have; it is never
fed to any predictor or winner-ranker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from .models import SourceTier, VerificationStatus, ConfidenceLabel


# ============================================================================
# 1. Political claim kind (EVENT / CLAIM / OPINION)
# ============================================================================

class PoliticalClaimKind(str, Enum):
    """Per spec section 7: separate three orthogonal kinds of
    political content.

    EVENT   -- a factual political/government/election event
               ("Election Commission announces election date")
    CLAIM   -- a political claim made by a person / party / institution
               ("Party A says policy X will reduce taxes")
    OPINION -- commentary / opinion piece / editorial
               ("Commentator says Party A is the best option")
    """
    EVENT = "EVENT"
    CLAIM = "CLAIM"
    OPINION = "OPINION"


# Banned patterns that mark content as OPINION or CLAIM.
# Kept as multi-word phrases to reduce false positives.
_OPINION_PATTERNS = [
    # English commentary markers
    r"\b(editorial|commentary|op[-\s]?ed|column|opinion|analysis piece|my take)\b",
    r"\b(viewpoint|perspective|commentator says|analyst says)\b",
    r"\b(review:|preview:|verdict:|rating:)\b",
    # Malay commentary markers
    r"\b(pendapat|analisis|kolum|suhu panas|ulasan|tajuk utama kolum)\b",
    r"\b(komentar|komen|pandangan|penceramah kata)\b",
    # Ranking / persuasion language
    r"\b(best (party|candidate|coalition|option|choice|alternative))\b",
    r"\b(worst (party|candidate|coalition|option|choice))\b",
    r"\b(party paling|calon paling|terbaik|terburuk|sebaik[-\s]?baiknya)\b",
    r"\b(the (better|worse) (party|candidate|coalition|option))\b",
    # Endorsement / opposition markers
    r"\b(saya (sokong|menyokong)|kami (sokong|menyokong)|i (support|endorse|back))\b",
    r"\b(jangan sokong|do not support|don't support|reject|rejecting)\b",
]

_CLAIM_PATTERNS = [
    # English claim markers (attributed speech)
    r"\b(says?|said|tells?|told|announces?|announced|claims?|claimed|"
    r"promises?|promised|warns?|warned|alleges?|alleged|denies?|denied|"
    r"argues?|argued|rejects?|rejected|insists?|insisted)\b",
    # Politician / party attribution
    r"\b(according to (the )?(minister|pm |prime minister|opposition|"
    r"party|coalition|spokesperson|deputy|ceo|chairman|chairwoman))\b",
    # Malay attribution (kata, berkata, menyatakan, etc.)
    r"\b(\w+\s+)?berkata\b",
    r"\b(\w+\s+)?menyatakan\b",
    r"\b(\w+\s+)?mengumumkan\b",
    r"\b(\w+\s+)?mendakwa\b",
    r"\b(\w+\s+)?menafikan\b",
    r"\b(\w+\s+)?mengesahkan\b",
    r"\b(\w+\s+)?menjelaskan\b",
    r"\b(\w+\s+)?mengaku\b",
    # Standalone "kata" used as attribution (Malay: "A kata B")
    r"\b\w+\s+kata\s+\w+",
    # Title-bearing attribution
    r"\b(ketua|pengerusi|setiausaha|jurucakap|presiden)\b",
]

# Election / parliament / institution patterns signal EVENT (but only if
# no opinion/claim patterns also match — order matters).
_EVENT_PATTERNS = [
    # English institutional events
    r"\b(election commission|parliament (passed|rejects?|approves?|"
    r"adjourns?|dissolves?)|cabinet (approves?|approv|meets?|resigns?)|"
    r"prime minister (appoints?|resigns?|sworn in|addresses?))\b",
    r"\b(general election|by[-\s]?election|state election|snap election|"
    r"dissolution of parliament)\b",
    r"\b(decree|royal ass|warta (perintah|persekutuan)|"
    r"gazetted?|gazette)\b",
    # Formal outcome
    r"\b(official results?|unofficial results?|official announcement|"
    r"press conference)\b",
    # Malay institutional events
    r"\b(suruhanjaya pilihan raya|spr |parlimen (lulus|menolak|menganggur)|"
    r"kabinet (meluluskan|bersidang)|perdana menteri (melantik|berucap))\b",
    r"\b(pilihan raya umum|pilihan raya kecil|pru|prk|"
    r"pembubaran parlimen)\b",
]


def detect_political_kind(text: str) -> PoliticalClaimKind:
    """Classify a single piece of political content.

    Per spec section 5: "不要只依赖 party name, candidate name,
    election keyword. 如果政治新闻也可能没有明确候选人名字。"

    Strategy (priority order):
      1. OPINION patterns. Commentary / editorial / ranking /
         persuasion language → OPINION.
      2. EVENT patterns. Institutional events (election commission,
         parliament, cabinet, gazette, official results). Checked
         BEFORE CLAIM because CLAIM verbs (announces, says) can
         co-occur with institutional-event phrasing and the
         institutional event framing is the dominant signal.
      3. CLAIM patterns. Attributed speech (X says Y).
      4. Otherwise default to EVENT (factual coverage).

    Returns the kind. NEVER returns None.
    """
    if not text:
        return PoliticalClaimKind.EVENT
    lowered = text.lower()
    for pat in _OPINION_PATTERNS:
        if re.search(pat, lowered):
            return PoliticalClaimKind.OPINION
    for pat in _EVENT_PATTERNS:
        if re.search(pat, lowered):
            return PoliticalClaimKind.EVENT
    for pat in _CLAIM_PATTERNS:
        if re.search(pat, lowered):
            return PoliticalClaimKind.CLAIM
    # No strong signal; treat as factual EVENT (most conservative).
    return PoliticalClaimKind.EVENT


# ============================================================================
# 2. PoliticalClaim -- attribution-aware data shape
# ============================================================================

@dataclass
class PoliticalClaim:
    """Structured representation of a politically-themed item, with
    attribution fields preserved separately.

    `claimed_by` and `reported_by` are intentionally SEPARATE fields.
    In politics, "Party A says X" reported by Source B is structurally
    different from "Source B reports X" where X is presented as the
    outlet's own finding. Collapsing these loses attribution.

    `attribution_required` defaults to True for CLAIM and OPINION kinds.
    EVENT kind usually doesn't require attribution because events are
    presented as facts (but the source is still recorded).
    """
    text: str
    kind: PoliticalClaimKind
    reported_by: str
    reported_by_tier: str  # A / B / C / D / E / F
    claimed_by: Optional[str] = None  # person / party / institution
    published_at: Optional[str] = None  # ISO timestamp
    evidence_url: Optional[str] = None
    counter_signals: List["PoliticalCounterSignal"] = field(default_factory=list)
    attribution_required: bool = True

    def __post_init__(self):
        if self.kind in (PoliticalClaimKind.CLAIM, PoliticalClaimKind.OPINION):
            self.attribution_required = True


@dataclass
class PoliticalCounterSignal:
    """A counter-signal against a political claim, mirroring the
    shape of `models.CounterSignal` but kept politics-specific so
    the politics module is self-contained for testing.

    Note: this is a LOCAL copy, not a replacement for the Radar
    `models.CounterSignal`. Existing counter-signal precedence
    in `radar/counter_signals.py` continues to be the authoritative
    engine.
    """
    stance: str  # DENIAL | CORRECTION | CONTRADICTION | DOWNPLAY
    source_name: str
    source_tier: str
    summary: str
    evidence_url: Optional[str] = None


# ============================================================================
# 3. Verification wrapper
# ============================================================================

def verify_political_claim(
    claim: PoliticalClaim,
) -> Tuple[VerificationStatus, ConfidenceLabel, str]:
    """Apply the politics-aware verification rule.

    The rule is documented in spec section 9 + 10:
      - A single politician's claim ≠ CONFIRMED → REPORTED at most
      - 100 social mentions ≠ CONFIRMED
      - Tier-A denial = RUMOUR (or one rung lower than current status)
      - Competing credible claims → tracked, NOT picked

    Returns: (status, confidence_label, reason)
    """
    # Counter-signal precedence (mirrors models.CounterSignalStance rules)
    for sig in claim.counter_signals:
        if sig.source_tier == "A" and sig.stance == "DENIAL":
            return (
                VerificationStatus.RUMOUR,
                ConfidenceLabel.VERY_LOW,
                f"Tier-A source ({sig.source_name}) directly denied the claim.",
            )
        if sig.source_tier == "A" and sig.stance == "CORRECTION":
            return (
                VerificationStatus.REPORTED,
                ConfidenceLabel.MEDIUM,
                f"Tier-A source ({sig.source_name}) issued a correction; "
                "claim downgraded.",
            )

    # No Tier-A denial → standard REPORTED for CLAIM kind.
    # Per spec section 9: a claim is REPORTED, not CONFIRMED, until
    # documented cross-verification under VERIFICATION_RULES.md.
    if claim.kind == PoliticalClaimKind.CLAIM:
        return (
            VerificationStatus.REPORTED,
            ConfidenceLabel.LOW,
            "Single attributed political claim; no Tier-A denial; "
            "not yet CONFIRMED.",
        )

    if claim.kind == PoliticalClaimKind.OPINION:
        return (
            VerificationStatus.REPORTED,
            ConfidenceLabel.VERY_LOW,
            "OPINION content; not a factual claim; status reflects "
            "publication only.",
        )

    # EVENT kind with no Tier-A denial
    if claim.reported_by_tier == "A":
        return (
            VerificationStatus.CONFIRMED,
            ConfidenceLabel.HIGH,
            "Tier-A source reported the event directly.",
        )
    if claim.reported_by_tier in ("B", "C"):
        return (
            VerificationStatus.REPORTED,
            ConfidenceLabel.MEDIUM,
            f"Tier-{claim.reported_by_tier} source reported the event; "
            "no Tier-A confirmation.",
        )
    return (
        VerificationStatus.UNVERIFIED,
        ConfidenceLabel.VERY_LOW,
        "Source tier below B; no verification possible.",
    )


# ============================================================================
# 4. Attribution-aware rendering (output-side guardrail)
# ============================================================================

# Banned phrases per spec section 11 + 12.
# Both English and Malay patterns. These are OUTPUT-SIDE checks: the
# rendered text must not contain them, regardless of what raw news
# content contained them.
_BANNED_PHRASES = [
    # English
    r"\b(best party|best candidate|best coalition|worst party|"
    r"worst candidate|recommended party|recommended candidate)\b",
    r"\b(party likely to win|candidate likely to win|"
    r"will probably win|will likely win|projected to win)\b",
    r"\b(\d+%\s*chance of winning|favored to win|favourite to win)\b",
    r"\b(endorsement|endorsed by|support (party|candidate))\b",
    r"\b(party (a|b|c) is (better|worse) than)\b",
    # Malay
    r"\b(parti (terbaik|terburuk)|calon (terbaik|terburuk)|"
    r"calon yang disokong|parti yang disyorkan)\b",
    r"\b(berkemungkinan menang|akan menang|"
    r"peluang menang)\b",
    # Chinese (project brand voice — Simplified)
    r"(支持.{0,4}党|支持.{0,4}候选人|反对.{0,4}党|反对.{0,4}候选人)",
    r"(最[好差].{0,6}(党|候选人|联盟))",
    r"(推荐.{0,4}(党|候选人))",
]


def _wrap_banned_phrases_as_quoted(text: str) -> str:
    """Wrap any banned phrase in the raw text with [quoted: ...] markers.

    This is the render-side mitigation that allows the system to
    preserve raw source content verbatim (for full audit) while
    preventing banned phrases from appearing un-redacted in system
    output.

    The bracketed marker is itself NOT a banned phrase, so the
    post-render `_BANNED_PHRASES` check passes. The full raw text is
    recoverable (just unwrap the brackets) for audit purposes.
    """
    result = text
    for pat in _BANNED_PHRASES:
        result = re.sub(pat, lambda m: f"[quoted: {m.group(0)}]", result,
                        flags=re.IGNORECASE)
    return result


def render_political_neutral(claim: PoliticalClaim) -> str:
    """Render a political claim in a factually-neutral, attribution-
    preserving form.

    Per spec section 8 + 15: the output MUST preserve `claimed_by`,
    `reported_by`, source_tier, and verification status. The render
    function is the single source of truth for output formatting.

    Guarantees:
      - claimed_by is always shown for CLAIM and OPINION
      - reported_by is always shown (the source is never hidden)
      - tier is always shown
      - verification status is always shown
      - banned phrases are explicitly checked before returning

    Raises ValueError if a banned phrase would appear in the output.
    This makes the guardrail observable in tests.
    """
    parts: List[str] = []

    # Attribution header
    if claim.kind == PoliticalClaimKind.CLAIM and claim.claimed_by:
        parts.append(
            f"Claim made by {claim.claimed_by}."
        )
    elif claim.kind == PoliticalClaimKind.OPINION and claim.claimed_by:
        parts.append(
            f"Opinion expressed by {claim.claimed_by}."
        )
    elif claim.kind == PoliticalClaimKind.EVENT:
        parts.append("Event reported.")

    # Reporting attribution
    tier_label = f"Tier-{claim.reported_by_tier}"
    parts.append(
        f"Reported by {claim.reported_by} ({tier_label})."
    )

    # The claim text itself — preserve verbatim, but mark it as
    # quoted source content so banned phrases in the raw text don't
    # leak into system output as un-attributed system claims. The
    # text inside the brackets is identifiable as a quotation, not
    # as the system's own statement.
    safe_text = _wrap_banned_phrases_as_quoted(claim.text)
    parts.append(f"Text: [quoted source content] {safe_text}")

    # Verification status
    status, conf, reason = verify_political_claim(claim)
    parts.append(f"Verification: {status.value}.")
    parts.append(f"Confidence: {conf.value} (heuristic).")
    if reason:
        parts.append(f"Reason: {reason}")

    # Counter-signals -- always display, attributed to the source that
    # issued them. This is critical for transparency: when the system
    # has a competing claim or denial, the reader needs to see it.
    if claim.counter_signals:
        parts.append("Counter-signals:")
        for sig in claim.counter_signals:
            parts.append(
                f"  - {sig.stance} by {sig.source_name} "
                f"(Tier-{sig.source_tier}): {sig.summary}"
            )

    rendered = " ".join(parts)

    # Output-side guardrail: detect any banned phrase in the rendered
    # text OUTSIDE the [quoted: ...] markers. Inside [quoted: ...] is
    # by definition a verbatim quotation of source content; the
    # guardrail exists to prevent the SYSTEM from emitting banned
    # language, not to censor what a source said.
    unquoted = re.sub(r"\[quoted:[^\]]*\]", "", rendered)
    for pat in _BANNED_PHRASES:
        if re.search(pat, unquoted, re.IGNORECASE):
            raise ValueError(
                f"rendered political output (excluding quoted source "
                f"content) contains banned phrase matching {pat!r}: "
                f"{unquoted!r}"
            )

    return rendered


# ============================================================================
# 5. Poll data stub (per spec section 12)
# ============================================================================

@dataclass
class PollRecord:
    """A single piece of publicly-reported poll data.

    Per spec section 12:
      "如果未来支持 poll 数据，只能记录：poll, population, field
      dates, sample size, reported measurement, source. 不生成 winner
      prediction。"

    This is a RECORD type only. It exposes no predict(), rank(), or
    project_winner() method. The struct only supports safe rendering.
    """
    poll_name: str  # e.g. "Merdeka Center Q3 2026"
    population: str  # e.g. "Malaysian voters"
    field_start: str  # ISO date
    field_end: str    # ISO date
    sample_size: int
    measurement: str  # the actual reported number, e.g. "Party A 38%"
    source: str  # the outlet that reported the poll
    source_url: Optional[str] = None

    def render(self) -> str:
        """Return a strictly-factual rendering of the poll. NO prediction.

        The render is intentional: it includes every field in the
        record so a reader can audit. It does NOT include any
        inference about who will win.
        """
        return (
            f"Poll: {self.poll_name}. "
            f"Population: {self.population}. "
            f"Field dates: {self.field_start} to {self.field_end}. "
            f"Sample size: {self.sample_size}. "
            f"Reported measurement: {self.measurement}. "
            f"Source: {self.source}."
        )

    def has_prediction_language(self) -> bool:
        """Return True if this poll record (or its render) contains any
        prediction-style language. Used by tests as a guardrail."""
        rendered = self.render()
        for pat in _BANNED_PHRASES:
            if re.search(pat, rendered, re.IGNORECASE):
                return True
        return False


# ============================================================================
# 6. Output guardrails (exportable for tests)
# ============================================================================

BANNED_OUTPUT_PATTERNS = _BANNED_PHRASES


def assert_output_neutral(text: str) -> None:
    """Test guardrail: raise if `text` contains any banned phrase
    OUTSIDE [quoted: ...] markers. Inside [quoted: ...] is by
    definition source content and not a system-emitted phrase."""
    unquoted = re.sub(r"\[quoted:[^\]]*\]", "", text)
    for pat in _BANNED_PHRASES:
        if re.search(pat, unquoted, re.IGNORECASE):
            raise AssertionError(
                f"output contains banned political phrase "
                f"matching {pat!r}: {unquoted!r}"
            )
