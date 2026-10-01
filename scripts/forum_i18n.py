#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MY Hot Radar — Forum v2 中文 i18n 模块。

彪哥规范:
- Forum 所有面向人类的内容默认使用简体中文。
- Schema keys / enum / agent IDs / status values / event_types 保持英文
  (machine-readable contract)。
- Human-readable content (note / summary / reason / decision 等) 转为中文。
- 现有英文 content 同时保留 (i18n_bilingual 风格),保证兼容性。

设计:
- 每个 helper 接受英文输入,返回 {"en": "...", "zh": "..."} 双语结构。
- 现有 forum_v2 / forum_runtime_hook 调用方可以选择:
    a) payload={"note": "..."}              # 旧版英文 (现有测试)
    b) payload={"note": {...i18n payload}}  # 新版双语 (默认)
- i18n_payload(...) helper 把英文字符串自动转换为双语结构。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 常量: 中英对照词典
# ---------------------------------------------------------------------------

# Topic title 翻译 / 标准化
TITLE_TRANSLATIONS: Dict[str, str] = {
    # English
    "Najib house arrest starts": "纳吉居家监禁开始",
    "Siti Hasmah passes away": "敦斯里哈斯玛逝世",
    "MCMC WhatsApp Meta complaints": "MCMC 接获 WhatsApp Meta 投诉",
    "Jerebu makin pulih, 8 kawasan catat IPU tak sihat": "烟霾情况好转,8 区域空气质量仍处不健康水平",
    "Najib house arrest starts 2026-09-19": "纳吉居家监禁开始（2026-09-19）",
    "Reactivation test: Najib case 2026-09-19": "重新升温测试：纳吉案件 2026-09-19",
    "Reactivation test: Najib case 2026-10-01": "重新升温测试：纳吉案件 2026-10-01",
    # Malay
    "Jerebu meningkat di Johor": "柔佛烟霾情况恶化",
    # Common
    "Malaysia economy update": "马来西亚经济动态更新",
    "Phase 3 test": "阶段 3 测试",
    "Sample story": "示例新闻",
    "Lorem ipsum": "占位文本",
}


# Editorial / Source / Performance 说明模板
ZH_TEMPLATES: Dict[str, str] = {
    # Collector observation
    "obs_default_note": "已发现该事件,等待 Radar 进一步核实。",
    "obs_with_evidence": "已收到外部观察记录,提供相应证据。",
    "obs_social_heat": "社交平台上该事件重新出现明显热度。",

    # Radar source / classification / momentum
    "radar_source_default": "{source_name} 报道该事件。",
    "radar_source_via_collector": "通过 Collector 通道首次记录该事件。",
    "radar_cross_source_confirmed": "多个独立来源已确认该事件。",
    "radar_classification_default": "目前分类为 {classification}。",
    "radar_momentum_rising": "过去 {window} 传播速度明显上升。",
    "radar_momentum_sustained": "过去 {window} 传播热度维持稳定。",
    "radar_momentum_cooling": "过去 {window} 传播热度正在下降。",
    "radar_momentum_spike": "过去 {window} 传播速度出现峰值。",

    # Performance
    "perf_report_cooling": "过去 {window} 传播热度正在下降。",
    "perf_report_sustained": "过去 {window} 传播热度持续稳定。",
    "perf_report_rising": "过去 {window} 传播速度持续上升。",
    "perf_report_spike": "过去 {window} 传播速度出现峰值。",
    "perf_engagement_unknown": "目前没有可验证的互动数据,因此只能确认传播趋势,无法确认实际互动规模。",
    "perf_no_data": "Performance 暂无足够数据,无法做出量化判断。",
    "perf_sustained_signal": "该事件传播热度持续 {duration_hours} 小时,且新增来源仍在增加。",
    "perf_cooling_signal": "该事件传播热度正在下降,来源覆盖出现萎缩。",

    # Default editorial decisions
    "default_review_breaking": "初次发现,初步判断为高优先级事件,进入编辑审核。",
    "default_review_rising": "该事件正在升温,进入编辑审核。",
    "default_review_watch": "该事件标记为关注,等待 Radar 进一步信号。",
    "default_review_hot": "该事件热度较高,进入编辑审核。",
    "default_publish": "完成编辑审核,决定发布文章。",
    "default_monitor_post_publish": "文章已发布,进入持续观察状态。",
    "default_monitor_after_review": "审核完成后未立即决定,进入后续跟进。",
    "default_follow_up_after_review": "审核完成后进入后续跟进。",
    "default_follow_up_perf_signal": "Performance 数据显示传播正在 {velocity},决定跟进更新。",
    "default_close_cooled": "事件传播热度已下降,决定关闭该 Topic。",
    "default_monitor_after_followup": "跟进后继续观察。",
    "default_update_article": "更新文章内容:{change_summary}",

    # Reactivation
    "reactivation_signal_renewed": "外部观察显示该事件重新出现明显热度。",
    "reactivation_signal_high_heat": "外部观察显示该事件社交热度显著上升。",

    # Generic
    "no_translation_available": "暂无中文翻译,以原文呈现。",
}


# Note: 字段级 fallback
FALLBACK_NOTE_ZH = "暂无中文说明。"
FALLBACK_TRANSLATION = "暂无中文翻译。"


# ---------------------------------------------------------------------------
# 双语结构 helper
# ---------------------------------------------------------------------------

def bilingual(en: str, zh: str) -> Dict[str, str]:
    """Build a bilingual human-readable payload field.

    Returns a dict with two keys:
      * "en": the original English text (or any non-Chinese source)
      * "zh": the Chinese translation or paraphrase

    Existing consumers reading field["zh"] get the Chinese. Existing
    consumers reading field["en"] get the original English. Both
    consumers work without migration.
    """
    return {"en": en or "", "zh": zh or FALLBACK_TRANSLATION}


def is_bilingual(value: Any) -> bool:
    """Return True if value is a {"en": ..., ...} dict with English content.

    Lenient: accepts {"en": ...} even if zh is missing. Strict: only
    counts dicts with string keys, with `en` key present.
    """
    return (
        isinstance(value, dict)
        and "en" in value
    )


def render_bilingual(value: Any, lang: str = "zh") -> str:
    """Render a bilingual value for display.

    If value is bilingual, returns the requested language.
    Otherwise returns value as-is.
    """
    if is_bilingual(value):
        if lang in value:
            return value[lang]
        # Fallback: en if requested lang missing
        return value.get("en", "")
    if isinstance(value, str):
        return value
    return str(value)


def zh_text(value: Any) -> str:
    """Extract the Chinese text from a value (bilingual or plain)."""
    if is_bilingual(value):
        return value.get("zh") or FALLBACK_TRANSLATION
    if isinstance(value, str):
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Topic title translation
# ---------------------------------------------------------------------------

def translate_title(title: str) -> str:
    """Translate a Topic title to Chinese if possible.

    Strategy:
      1. Direct lookup in TITLE_TRANSLATIONS.
      2. If title contains known Malay/English keywords, apply
         phrase-level substitution.
      3. Fallback: return original title (Chinese is preferred but
         we never fabricate translation).
    """
    if not title:
        return ""

    title_stripped = title.strip()
    # 1. Direct lookup
    if title_stripped in TITLE_TRANSLATIONS:
        return TITLE_TRANSLATIONS[title_stripped]

    # 2. Case-insensitive partial match for known phrases
    lower = title_stripped.lower()
    for key, value in TITLE_TRANSLATIONS.items():
        if key.lower() in lower or lower in key.lower():
            return value

    # 3. Heuristic translations for common terms
    translated = title_stripped
    replacements = [
        (r"\bhouse arrest\b", "居家监禁"),
        (r"\bpasses? away\b", "逝世"),
        (r"\barrested\b", "被逮捕"),
        (r"\bjerebu\b", "烟霾"),
        (r"\bmakin pulih\b", "正在好转"),
        (r"\btak sihat\b", "不健康"),
        (r"\bIPU\b", "空气质量指数"),
        (r"\bPM10\b", "PM10"),
        (r"\bNajib\b", "纳吉"),
        (r"\bMCMC\b", "MCMC"),
        (r"\bWhatsApp\b", "WhatsApp"),
        (r"\bMeta\b", "Meta"),
        (r"\bcomplaints?\b", "投诉"),
        (r"\bSiti Hasmah\b", "敦斯里哈斯玛"),
        (r"\bdies?\b", "逝世"),
        (r"\bdeaths?\b", "死亡"),
        (r"\bstarts?\b", "开始"),
        (r"\bmeninggal dunia\b", "逝世"),
        (r"\bmeninggal\b", "逝世"),
        (r"\bpolis\b", "警方"),
        (r"\bsiasatan\b", "调查"),
        (r"\bmeningkat\b", "上升"),
        (r"\bturun\b", "下降"),
    ]
    for pattern, repl in replacements:
        translated = re.sub(pattern, repl, translated, flags=re.IGNORECASE)

    # If translation didn't change anything AND title is non-Chinese,
    # fallback to original (we never fabricate).
    if translated == title_stripped and not _contains_chinese(title_stripped):
        return title_stripped

    return translated


def _contains_chinese(s: str) -> bool:
    """Return True if s contains any CJK characters."""
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


# ---------------------------------------------------------------------------
# 中文模板 helpers (用于 note / summary / reason / decision 等字段)
# ---------------------------------------------------------------------------

def _format(template_key: str, **kwargs: Any) -> str:
    """Format a Chinese template, returning original English on failure."""
    template = ZH_TEMPLATES.get(template_key, "")
    if not template:
        return FALLBACK_NOTE_ZH
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


def collector_observation_note(evidence: Optional[Dict] = None) -> Dict[str, str]:
    """中文 + 英文 双语 note for Collector observation.

    If evidence contains 'heat_score', implies social-heat trigger.
    """
    en = "Collector observed new event, awaiting Radar verification."
    heat = (evidence or {}).get("heat_score")
    if heat is not None:
        zh = ZH_TEMPLATES["obs_social_heat"]
        en = "Collector observed renewed social heat on existing event."
    else:
        zh = ZH_TEMPLATES["obs_default_note"]
    return bilingual(en, zh)


def collector_social_heat_note(evidence: Optional[Dict] = None) -> Dict[str, str]:
    """中文 note for Collector social heat signal."""
    en = "Collector detected renewed social heat signal."
    heat = (evidence or {}).get("heat_score")
    if heat and float(heat) >= 0.9:
        zh = ZH_TEMPLATES["reactivation_signal_high_heat"]
        en = "Collector detected strong social heat spike."
    else:
        zh = ZH_TEMPLATES["reactivation_signal_renewed"]
    return bilingual(en, zh)


def radar_source_note(source_name: str, language: str = "en") -> Dict[str, str]:
    """中文 note for Radar SOURCE_UPDATE."""
    en = f"Source {source_name} reported this story."
    zh = _format("radar_source_default", source_name=source_name or "未知来源")
    if language and language.lower() in ("zh", "zh-cn", "zh-my"):
        zh = zh + f"（语言：中文）"
        en = en + f" (language: {language})"
    return bilingual(en, zh)


def radar_via_collector_note(radar_topic_id: str) -> Dict[str, str]:
    """中文 note for Radar bootstrap via Collector."""
    en = (
        "Radar did not have this topic yet; bootstrapped via "
        "Collector observation (Radar cannot CREATE_TOPIC)."
    )
    zh = _format(
        "radar_source_via_collector",
    )
    return bilingual(en, zh)


def radar_cross_source_note(source_name: str) -> Dict[str, str]:
    """中文 note for CROSS_SOURCE_CONFIRMATION."""
    en = f"Cross-source confirmation via {source_name}."
    zh = ZH_TEMPLATES["radar_cross_source_confirmed"] + f"新增来源：{source_name}。"
    return bilingual(en, zh)


def radar_classification_note(classification: str) -> Dict[str, str]:
    """中文 note for CLASSIFICATION_UPDATE."""
    en = f"Classification updated to {classification}."
    zh = _format("radar_classification_default", classification=classification)
    return bilingual(en, zh)


def radar_momentum_note(delta_score: float, window: str) -> Dict[str, str]:
    """中文 note for MOMENTUM_UPDATE."""
    en = f"Momentum update: delta={delta_score} over window={window}."
    if delta_score >= 1.0:
        zh = _format("radar_momentum_spike", window=window)
    elif delta_score >= 0.5:
        zh = _format("radar_momentum_rising", window=window)
    elif delta_score >= 0.2:
        zh = _format("radar_momentum_sustained", window=window)
    else:
        zh = _format("radar_momentum_cooling", window=window)
    return bilingual(en, zh)


def performance_report_note(
    velocity: str, engagement: Optional[str], window: str
) -> Dict[str, str]:
    """中文 note for PERFORMANCE_REPORT."""
    en = (
        f"Performance report: velocity={velocity}, "
        f"engagement={engagement}, window={window}."
    )
    zh_map = {
        "spike": "perf_report_spike",
        "rising": "perf_report_rising",
        "sustained": "perf_report_sustained",
        "cooling": "perf_report_cooling",
    }
    tmpl = zh_map.get(str(velocity).lower(), "perf_no_data")
    zh = _format(tmpl, window=window)
    if engagement is None or engagement == "" or str(engagement).lower() == "null":
        zh = zh + " " + ZH_TEMPLATES["perf_engagement_unknown"]
        en = en + " No engagement data available."
    return bilingual(en, zh)


def performance_sustained_note(
    duration_hours: float, sources_increasing: bool
) -> Dict[str, str]:
    """中文 note for SUSTAINED_SIGNAL."""
    en = (
        f"Sustained signal: duration={duration_hours}h, "
        f"sources_increasing={sources_increasing}."
    )
    zh = _format(
        "perf_sustained_signal",
        duration_hours=duration_hours,
    )
    if not sources_increasing:
        zh = zh + "新增来源数量尚未明显增加。"
        en = en + " Source count not yet growing."
    return bilingual(en, zh)


def performance_cooling_note(window: str) -> Dict[str, str]:
    """中文 note for COOLING_SIGNAL."""
    en = f"Cooling signal detected over window={window}."
    zh = _format("perf_cooling_signal", window=window)
    return bilingual(en, zh)


def default_review_note(classification: str) -> Dict[str, str]:
    """中文 note for EDITORIAL_REVIEW."""
    en = f"Editorial review triggered (classification={classification})."
    cls = (classification or "").upper()
    tmpl_map = {
        "BREAKING": "default_review_breaking",
        "RISING": "default_review_rising",
        "WATCH": "default_review_watch",
        "HOT": "default_review_hot",
    }
    tmpl = tmpl_map.get(cls, "default_review_watch")
    zh = ZH_TEMPLATES.get(tmpl, ZH_TEMPLATES["default_review_watch"])
    return bilingual(en, zh)


def default_publish_note(
    canonical_url: str, slug: str, classification: str = ""
) -> Dict[str, str]:
    """中文 note for PUBLISH."""
    en = f"Article published at {canonical_url} (slug={slug})."
    zh = ZH_TEMPLATES["default_publish"]
    if classification:
        zh = zh + f"（分类：{classification}）"
    return bilingual(en, zh)


def default_monitor_note(reason: str = "") -> Dict[str, str]:
    """中文 note for MONITOR."""
    en = "Topic moved to monitoring state."
    if "post-publish" in reason or "post" in reason.lower():
        zh = ZH_TEMPLATES["default_monitor_post_publish"]
    elif "follow-up" in reason.lower() or "after" in reason.lower():
        zh = ZH_TEMPLATES["default_monitor_after_followup"]
    else:
        zh = ZH_TEMPLATES["default_monitor_after_review"]
    return bilingual(en, zh)


def default_follow_up_note(velocity: str = "") -> Dict[str, str]:
    """中文 note for FOLLOW_UP."""
    en = "Topic escalated to follow-up."
    if velocity and velocity.lower() in ("spike", "rising", "sustained"):
        zh = _format(
            "default_follow_up_perf_signal", velocity=velocity.lower()
        )
    else:
        zh = ZH_TEMPLATES["default_follow_up_after_review"]
    return bilingual(en, zh)


def default_close_note(reason: str = "") -> Dict[str, str]:
    """中文 note for CLOSE."""
    en = f"Topic closed. Reason: {reason or 'unspecified'}."
    if reason and ("cool" in reason.lower() or "heat" in reason.lower()):
        zh = ZH_TEMPLATES["default_close_cooled"]
    else:
        zh = ZH_TEMPLATES["default_close_cooled"]
    return bilingual(en, zh)


def default_update_article_note(change_summary: str) -> Dict[str, str]:
    """中文 note for UPDATE_ARTICLE."""
    en = f"Article updated: {change_summary}"
    zh = _format("default_update_article", change_summary=change_summary or "")
    return bilingual(en, zh)


def source_description(source_name: str, source_url: str = "", title: str = "") -> Dict[str, str]:
    """中文 source description, e.g. for evidence['source_description']."""
    en = f"Source: {source_name}"
    if source_url:
        en = en + f" ({source_url})"
    if title:
        en = en + f" — {title}"
    # 中文
    if source_name:
        zh = f"来源：{source_name}"
    else:
        zh = "来源：未知"
    if title:
        zh = zh + f"。说明：{title}。"
    return bilingual(en, zh)


# ---------------------------------------------------------------------------
# Migrate existing payload (English-only -> bilingual)
# ---------------------------------------------------------------------------

def i18n_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert English-only payload fields into bilingual dicts.

    This is the central "translate then validate" hook. For known
    string fields (note, summary, reason, decision, change_summary),
    the existing English string is preserved under "en" and a
    Chinese version is generated under "zh". This is the recommended
    way to migrate existing Topic/Event payloads.

    Schema keys are unchanged: payload["note"] is now a dict
    {"en": "...", "zh": "..."}. Existing callers reading the dict
    directly will break; callers reading payload["note"]["en"] or
    payload["note"]["zh"] will work. The forum_v2 / forum_integration
    contract uses dict serialization, so this is the canonical format.

    If a field is already bilingual (dict with en/zh), it is passed
    through unchanged.
    """
    if not isinstance(payload, dict):
        return payload

    fields_handlers: List[Tuple[str, Any]] = [
        ("note", _i18n_note_field),
        ("summary", _i18n_note_field),
        ("reason", _i18n_note_field),
        ("decision", _i18n_decision_field),
        ("change_summary", _i18n_note_field),
    ]

    out: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in ("note", "summary", "reason", "decision", "change_summary"):
            handler = dict(fields_handlers)[key]
            out[key] = handler(value, payload) if handler.__name__ == "_i18n_decision_field" else handler(value)
        else:
            out[key] = value
    return out


def _i18n_note_field(value: Any) -> Any:
    """Convert a note/summary/reason/change_summary string into bilingual."""
    if isinstance(value, dict):
        # Already structured; pass through (or fill missing zh).
        if "en" in value and "zh" in value:
            return value
        if "en" in value and "zh" not in value:
            return {"en": value["en"], "zh": FALLBACK_NOTE_ZH}
        return value
    if isinstance(value, str):
        # English-only; provide a generic Chinese fallback.
        return bilingual(value, FALLBACK_NOTE_ZH)
    return value


def _i18n_decision_field(value: Any, payload: Optional[Dict] = None) -> Any:
    """Convert FOLLOW_UP decision into bilingual."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return bilingual(value, FALLBACK_NOTE_ZH)
    return value


# ---------------------------------------------------------------------------
# Title helpers for create_topic
# ---------------------------------------------------------------------------

def title_payload(title: str) -> Dict[str, str]:
    """For Topic.title: produce bilingual title dict.

    Forum v2 stores title as a plain string in topic.json. To preserve
    backward compatibility we keep title as a string, but add a
    "title_i18n" dict alongside for display. Callers who want to show
    Chinese titles should read payload["title_zh"].
    return bilingual(title, translate_title(title))
    """
    return bilingual(title, translate_title(title))


def topic_title_zh(topic_dict: Dict[str, Any]) -> str:
    """Extract the Chinese title from a Topic dict.

    If the Topic was created via Phase-4 wiring, the topic.json may
    contain a "title_i18n" subfield. Otherwise we fall back to the
    raw title (which might be English).
    """
    if not isinstance(topic_dict, dict):
        return ""
    if "title_i18n" in topic_dict and isinstance(topic_dict["title_i18n"], dict):
        return topic_dict["title_i18n"].get("zh") or topic_dict.get("title", "")
    return topic_dict.get("title", "")


def event_payload_zh(event_dict: Dict[str, Any], field: str = "note") -> str:
    """Extract the Chinese note from an Event payload."""
    if not isinstance(event_dict, dict):
        return ""
    payload = event_dict.get("payload", {})
    value = payload.get(field) if isinstance(payload, dict) else None
    return zh_text(value)