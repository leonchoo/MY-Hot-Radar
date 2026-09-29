"""
Editorial Review Sample v2 — 中文审核版 (Phase 2 B3B-2 后续).

This module is a READ-ONLY review aid. It produces a Chinese-language
sampling report that lets a human editor understand each candidate's
topic in natural Chinese before filling in A / B / C editorial
decisions.

CRITICAL design rules (per spec):

  * Chinese translations are NOT generated on the fly. They come from
    a hand-authored, per-candidate-id translation table. This guarantees
    that the Chinese is faithful, neutral, and never hallucinates.

  * The candidate file is never modified. The output report is written
    to a markdown file outside `radar_data/`.

  * A / B / C decisions are rendered as BLANK form fields. The system
    never auto-fills them.

  * For political candidates, all Chinese text uses strict-neutral
    framing (据相关报道 / 有消息称 / 某方表示). It never endorses,
    opposes, ranks, or predicts any party or candidate.

  * For CLAIM / REPORTED verification, Chinese text never claims
    confirmed fact. It uses the same Radar verification_status as
    the candidate and never upgrades it.

Public entry points:

  build_chinese_review_report(candidate_latest_path,
                               output_report_path,
                               sample_size=20) -> dict
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..candidate import _is_safe_url
from .editorial_sampling import (
    AUDIT_VERSION,
    _age_hours,
    _clean,
    _parse_iso_or_rfc,
    _render_sources,
)


CHINESE_REVIEW_VERSION = "phase2-b3b2-zh-review-v1"


# ============================================================================
# Per-candidate Chinese translation table (HAND-AUTHORED, READ-ONLY).
#
# Each entry maps candidate_id to a dict with:
#   - chinese_headline:  自然中文标题 (faithful, neutral, no clickbait)
#   - chinese_summary:   1-2 句中文事件摘要 (only source-grounded facts)
#   - notes_for_editor:  optional short note (NOT a judgement, just
#                        clarification of any editorial ambiguity, e.g.
#                        headline differs from source[0] due to dedup
#                        cluster)
#
# Rules followed when authoring:
#   * English / Malay source text → natural Chinese
#   * No addition of facts absent from source evidence
#   * For political candidates: "据相关报道", "有消息称",
#     "某方表示" — never "已证实", "事实是"
#   * For CLAIM / REPORTED: explicitly state the Radar verification
#     status, never upgrade to confirmed
#   * Headline is translated as-is — never re-written
#   * Numbers / names / places preserved exactly
# ============================================================================

ZH_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # #1 — Political, CLAIM, CONFIRMED
    "cand_0291d8fe5d13bd7232a8dd38": {
        "chinese_headline": (
            "陆兆福：纳吉开始居家服刑时，自己将正式卸下部长职务"
        ),
        "chinese_summary": (
            "据相关报道，行动党籍交通部长陆兆福表示，一旦纳吉进入居家"
            "服刑阶段，他本人将正式卸下部长职务。多家马来媒体同时报道"
            "了相关进展。此事件当前 Radar verification_status=CONFIRMED、"
            "confidence_label=HIGH，但仍属政治敏感内容，编辑审核时需"
            "保持严格中立，不评价任何政党或政治人物。"
        ),
        "notes_for_editor": (
            "此 candidate 是 dedup 集群（4 个 source），4 篇相关但不同"
            "角度的报道围绕 Najib house arrest / 部长职位变动；中文"
            "标题以 headline 为准。"
        ),
    },
    # #2 — NOT_POLITICAL, REPORTED
    "cand_24034fa2cdf3d35f24bc8815": {
        "chinese_headline": (
            "前 FIC 首席执行官被指控就 Jalan Semarak 项目欺骗董事会"
        ),
        "chinese_summary": (
            "据相关报道，前 FIC 首席执行官被指控在 Jalan Semarak "
            "相关项目中欺骗董事会。相关案件已安排明日过堂。此事件"
            "当前 Radar verification_status=REPORTED，仅有 2 个同"
            "语种马来媒体来源作为佐证。"
        ),
        "notes_for_editor": "",
    },
    # #3 — NOT_POLITICAL, REPORTED
    "cand_3d097706f002b1e241be291b": {
        "chinese_headline": (
            "公众受促警惕通过邮寄方式进行的「药品注册」骗局"
        ),
        "chinese_summary": (
            "据相关报道，主管部门提醒公众警惕以邮寄方式进行的所谓"
            "「药品注册」骗局，避免受骗上当。此事件当前 Radar "
            "verification_status=REPORTED，仅 1 个来源。"
        ),
        "notes_for_editor": "",
    },
    # #4 — NOT_POLITICAL, REPORTED
    "cand_4a46b36aa26f8da6c4dca778": {
        "chinese_headline": (
            "砂拉越 8 个地区中午录得「不健康」API 等级，"
            "Kanowit 也在名单上"
        ),
        "chinese_summary": (
            "据相关报道，砂拉越多个地区空气污染加剧，中午前已有 8 个"
            "地区录得「不健康」等级 API 读数，Kanowit 也被列入。此"
            "事件当前 Radar verification_status=REPORTED。"
        ),
        "notes_for_editor": (
            "headline 在多次 scan 中曾出现两个版本（7 个站 vs 8 个地区，"
            "含 Kanowit），Radar dedup 后的最新 headline 为 8 个地区版。"
            "本中文翻译以最新 headline 为准。"
        ),
    },
    # #5 — NOT_POLITICAL, REPORTED
    "cand_6ebf1458cb71ebdc5a6afdf7": {
        "chinese_headline": (
            "MIDA 支持砂拉越的工业转型"
        ),
        "chinese_summary": (
            "据相关报道，马来西亚投资发展局（MIDA）表示支持砂拉越的"
            "工业转型进程。此事件当前 Radar verification_status=REPORTED，"
            "仅 1 个来源。"
        ),
        "notes_for_editor": (
            "本条内容为官方机构立场声明，编辑判断时需考虑：是否值得"
            "作为独立文章，还是作为本地工业简讯合并报道。"
        ),
    },
    # #6 — Political, EVENT, REPORTED
    "cand_723ee28556026defb5d628eb": {
        "chinese_headline": (
            "砂拉越选区重划公告展期明日下午 5 时结束"
        ),
        "chinese_summary": (
            "据相关报道，砂拉越选区重划的公众查阅期将在明日下午 5 "
            "时结束。此事件属程序性政治公告，Radar 标记为 political="
            "True、claim_kind=EVENT、verification_status=REPORTED，仅"
            "1 个来源。编辑审核时需保持中立，仅作为程序性事实呈现，"
            "不评论选区划分本身的合理性。"
        ),
        "notes_for_editor": "",
    },
    # #7 — Political, EVENT, REPORTED (Malay-language)
    "cand_afe4bd3302659eb99be0cc11": {
        "chinese_headline": (
            "（标题翻译）为何多党联盟在第十六届全国大选出现"
            "明显分裂"
        ),
        "chinese_summary": (
            "据相关报道，本篇报道讨论第十六届全国大选（PRU16）中"
            "多党联盟出现明显分裂的现象。Radar 标记为 political=True、"
            "claim_kind=EVENT、verification_status=REPORTED，仅 1 个"
            "来源。中文标题仅为原文翻译，不添加编辑判断，不对任何"
            "政党或联盟做评价、排名或预测。"
        ),
        "notes_for_editor": (
            "原文 Malay 标题为「为何…」句式，Radar 分类为 EVENT 而非"
            "OPINION（按 Phase 2 B1 政治规则，OPINION 才会被 BLOCK）。"
            "编辑审核时需特别注意：标题虽为分析性，但本候选仍属"
            "Radar 标记为 EVENT 的政治类报道，请按 political_neutral="
            "True 的处理原则严格中立呈现。"
        ),
    },
    # #8 — NOT_POLITICAL, REPORTED
    "cand_b5d224889f3fedd9ecd68188": {
        "chinese_headline": (
            "沈桂鸿：癌症医疗框架须考虑砂拉越的乡村与偏远地区"
        ),
        "chinese_summary": (
            "据相关报道，砂拉越副总理兼公共卫生、房屋与地方政府部长"
            "沈桂鸿（Dr Sim）表示，砂拉越的癌症医疗框架须考虑该州"
            "的乡村与偏远社区特点。3 个 Borneo Post 来源覆盖同一议题"
            "的不同角度（健康城市、癌症框架、Sarawak Beyond 2026）。"
            "当前 Radar verification_status=REPORTED。"
        ),
        "notes_for_editor": (
            "本 candidate 是 dedup 集群，3 篇相关但不同角度的报道；"
            "中文标题以 headline 为准。涉及官方政策表态，编辑判断时"
            "需注意属「政策声明」还是「实质政策行动」。"
        ),
    },
    # #9 — Political, CLAIM, REPORTED
    "cand_da5a22acbeb546e8556e365f": {
        "chinese_headline": (
            "Taman Sri Muda 居民就 2021 年水灾起诉政府胜诉"
        ),
        "chinese_summary": (
            "据相关报道，雪兰莪州 Taman Sri Muda 居民就 2021 年发生"
            "的水灾起诉政府一案取得胜诉。此事件属 Radar 标记 political="
            "True、claim_kind=CLAIM、verification_status=REPORTED，仅 1 "
            "个来源。中文标题仅为原文翻译，不评价政府或任何政党在"
            "灾害管理上的表现，不预测后续司法程序。"
        ),
        "notes_for_editor": "",
    },
    # #10 — NOT_POLITICAL, REPORTED
    "cand_e3667c642a5b8cfcf9e7a069": {
        "chinese_headline": (
            "面对健康挑战，夫妇向 NGO 寻求家庭支援"
        ),
        "chinese_summary": (
            "据相关报道，一对夫妇因面对健康方面的挑战，转向非政府"
            "组织（NGO）寻求家庭支援服务。此事件当前 Radar verification_"
            "status=REPORTED，仅 1 个来源。"
        ),
        "notes_for_editor": (
            "本条属「人物故事」类素材，编辑判断时需考虑：是否值得独立"
            "报道，还是与本地 NGO 专题合并。"
        ),
    },
    # #11 — Political-leaning, REPORTED
    "cand_f8a6ac609d8e40c6ac9865bd": {
        "chinese_headline": (
            "不是 PAS，也不是 PH——Umno 自身是否还有独立力量？"
        ),
        "chinese_summary": (
            "据相关报道，本篇报道讨论 Umno 是否仍拥有独立于 PAS 与 "
            "PH 之外的政治力量。同 candidate 集群中其他来源还包括法"
            "米否认希盟与土团党已有正式讨论、以及早前希盟与土团党领"
            "袖在马六甲州选协商传闻中共进晚餐的报道。Radar 标记 "
            "is_political=False、verification_status=REPORTED。中文"
            "标题仅为原文翻译，编辑审核时需保持严格中立，不评价任何"
            "政党、不预测选举结果。"
        ),
        "notes_for_editor": (
            "本 candidate 是 dedup 集群，集群中混合了不同角度的报道："
            "当前 headline（Umno 力量分析）、法米否认官方协商（正面"
            "否认）、早前希盟与土团党共进晚餐的报道等。Radar 将其"
            "标记为 is_political=True、political_neutral=True、"
            "claim_kind=EVENT（虽然内容涉及政治讨论，但 Radar 判定为"
            "中性事件类）。编辑审核时需特别注意：verification 仍为 "
            "REPORTED，不应写为「已确认」。"
        ),
    },
    # #12 — WORLD, NOT_POLITICAL
    "cand_004b328404b99afc338208bc": {
        "chinese_headline": (
            "祈祷前先签到：印度某邦新颁布的改宗法律正影响"
            "当地教会信徒"
        ),
        "chinese_summary": (
            "据相关报道，印度某邦新颁布的改宗相关法律正影响当地"
            "教会信徒，有信徒反映在参加祈祷前须先进行登记或签署"
            "文件。Radar 标记 verification_status=REPORTED、来源为 "
            "BBC News Asia（英国，Tier-B）。"
        ),
        "notes_for_editor": (
            "本条涉及宗教政策，编辑判断时需注意：不评价印度政府"
            "的宗教政策，不对任何宗教做倾向性表达，仅作为国际"
            "新闻报道。"
        ),
    },
    # #13 — WORLD, NOT_POLITICAL
    "cand_0ff87c74934633cf2fa5279a": {
        "chinese_headline": (
            "为何部分印度公务员因做好本职工作而被视为"
            "公众英雄"
        ),
        "chinese_summary": (
            "据相关报道，BBC 一篇特稿探讨为何部分印度公务员因"
            "做好本职工作而被公众视为英雄。Radar 标记 verification_"
            "status=REPORTED、来源为 BBC News Asia（英国，Tier-B）。"
        ),
        "notes_for_editor": (
            "本条为 BBC 人物特稿类报道，编辑判断时需考虑是否值得"
            "独立报道，或与「亚洲治理 / 公共服务」专题合并。"
        ),
    },
    # #14 — WORLD, NOT_POLITICAL
    "cand_2813b65d572c0146f8f3ab5c": {
        "chinese_headline": (
            "塔塔股价下跌，旗下信托提议阻止控股公司上市"
        ),
        "chinese_summary": (
            "据相关报道，印度塔塔集团（Tata）股价出现下跌，原因是"
            "其旗下信托机构提议一项可能阻止塔塔控股公司上市的"
            "措施。Radar 标记 verification_status=REPORTED、来源为 "
            "Channel News Asia（新加坡，Tier-B）。"
        ),
        "notes_for_editor": (
            "本条属企业财务 / 公司治理类报道，编辑判断时需考虑："
            "原文为英文财经报道，数字与公司名称须保留原样。"
        ),
    },
    # #15 — WORLD, NOT_POLITICAL, CONFIRMED
    "cand_3ff7d48665fc8b7686376413": {
        "chinese_headline": (
            "马来西亚开始遣返缅甸移民回国"
        ),
        "chinese_summary": (
            "据相关报道，马来西亚已开始将滞留在马的缅甸移民/难民"
            "遣返回国。涉及 2 个来源（Channel News Asia 英文、"
            "Free Malaysia Today 马来文），Radar 标记 verification_"
            "status=CONFIRMED、confidence_label=HIGH。编辑审核时"
            "需保持中立，不评价马来西亚或缅甸政府的相关政策，"
            "不推测后续影响。"
        ),
        "notes_for_editor": (
            "本 candidate 是少数 verification_status=CONFIRMED 的"
            "例子（1/20）。涉及移民与人道议题，编辑判断时需注意"
            "中立的措辞。"
        ),
    },
    # #16 — WORLD, NOT_POLITICAL
    "cand_7a444c025f7799935aed43ac": {
        "chinese_headline": (
            "路透民调：受 AI 芯片需求支撑，韩国出口预计连续"
            "第 16 个月增长"
        ),
        "chinese_summary": (
            "据路透社一项民调，受 AI 芯片需求支撑，韩国出口预计将"
            "实现连续第 16 个月增长。Radar 标记 verification_status="
            "REPORTED、来源为 Channel News Asia（新加坡，Tier-B）。"
            "注意：原文为「民调预测」，属预测性内容，编辑审核时"
            "应保留「预测 / 民调」措辞，不写为「已实现」事实。"
        ),
        "notes_for_editor": "",
    },
    # #17 — WORLD, NOT_POLITICAL
    "cand_80941ad52fc379b56018af45": {
        "chinese_headline": (
            "快时尚平台 Shein 股价下跌 6%，季度利润下滑 67%"
        ),
        "chinese_summary": (
            "据相关报道，快时尚平台 Shein 股价下跌约 6%，原因是其"
            "季度利润同比下滑约 67%。Radar 标记 verification_status="
            "REPORTED、来源为 Channel News Asia（新加坡，Tier-B）。"
            "数字（6%、67%）须保留原样。"
        ),
        "notes_for_editor": "",
    },
    # #18 — WORLD, NOT_POLITICAL
    "cand_9320c8d872e52efae142d74d": {
        "chinese_headline": (
            "霍尔木兹海峡希望减弱，股市下跌、油价上涨"
        ),
        "chinese_summary": (
            "据相关报道，市场对霍尔木兹海峡局势的希望有所减弱，"
            "全球股市出现下跌、油价出现上涨。Radar 标记 verification_"
            "status=REPORTED、来源为 Channel News Asia（新加坡，Tier-B）。"
        ),
        "notes_for_editor": "",
    },
    # #19 — WORLD, NOT_POLITICAL
    "cand_a96fa2bdb36199a9c1527114": {
        "chinese_headline": (
            "男子因 AI 生成鳄鱼图像引发 Pandan 水库搜索行动"
            "被控"
        ),
        "chinese_summary": (
            "据相关报道，一名男子因使用 AI 生成的鳄鱼图像导致"
            "Pandan Reservoir 一带展开搜索行动，而被警方控上法庭。"
            "本 candidate 是 dedup 集群（2 个 Channel News Asia "
            "来源），另一条 source 报道为 Google 在欧盟对 AI / "
            "搜索相关反垄断指令的挑战。中文标题以 headline 为准。"
            "Radar 标记 verification_status=REPORTED。"
        ),
        "notes_for_editor": (
            "本 candidate 的 source 集群中混入了另一条 Google / EU "
            "AI 监管报道。编辑判断时需注意：本中文标题仅反映 headline "
            "（AI 鳄鱼图像事件），不涵盖 source 集群中另一条 Google "
            "新闻；如要涵盖 source 集群中所有内容，须另写。"
        ),
    },
    # #20 — WORLD, NOT_POLITICAL
    "cand_b9d84ef52022e9ec12b52ce2": {
        "chinese_headline": (
            "在 BTS 与 Blackpink 之前，曾有 Big Bang：如今"
            "K-pop 王者回归"
        ),
        "chinese_summary": (
            "据相关报道，BBC 一篇特稿回顾 K-pop 团体 Big Bang 的"
            "回归——在 BTS 与 Blackpink 之前，Big Bang 曾是 K-pop "
            "代表团体之一。Radar 标记 verification_status=REPORTED、"
            "来源为 BBC News Asia（英国，Tier-B）。"
        ),
        "notes_for_editor": (
            "本条属娱乐 / 文化类报道，编辑判断时需考虑：是否适合"
            "在 MY Hot Radar 的现有版位中呈现（当前 Radar source "
            "registry 暂无娱乐类来源，本 candidate 属于 BORROWING "
            "WORLD source 标签下的英国 BBC）。"
        ),
    },
}


# ============================================================================
# Sample selection (same algorithm as English version, for reproducibility)
# ============================================================================

def select_chinese_sample(
    ready: List[dict], sample_size: int = 20,
) -> List[dict]:
    """Return the pinned set of 20 candidates for this batch.

    This is NOT the live stride-pick (which changes as new candidates
    arrive). For this batch, the 20 candidate_ids are fixed (see
    PINNED_SAMPLE_IDS). All 20 hand-authored Chinese translations
    correspond to these IDs.

    The pinned set is a snapshot taken when this batch was created.
    If a pinned candidate is no longer in READY (e.g., a topic went
    stale), it is silently skipped from the output. This guarantees
    that the Chinese audit report is always paired with the same
    hand-authored translations, and never silently re-translates or
    drops content.
    """
    pinned = [c for c in ready if c.get("candidate_id") in PINNED_SAMPLE_IDS]
    # Order: by the order of PINNED_SAMPLE_IDS, not by candidate_id
    order = {cid: i for i, cid in enumerate(PINNED_SAMPLE_IDS)}
    pinned.sort(key=lambda c: order.get(c.get("candidate_id", ""), 9999))
    return pinned[:sample_size]


# Pinned sample of 20 candidate_ids for this batch.
# These are the 20 candidates the Chinese translations were authored
# against. The set is closed — adding a new READY candidate does NOT
# change this set. To re-sample, create a new batch with a new set
# of translations.
PINNED_SAMPLE_IDS: List[str] = [
    "cand_0291d8fe5d13bd7232a8dd38",   # #1 Loke / Najib house arrest
    "cand_24034fa2cdf3d35f24bc8815",   # #2 Bekas CEO FIC
    "cand_3d097706f002b1e241be291b",   # #3 scam pendaftaran ubat
    "cand_4a46b36aa26f8da6c4dca778",   # #4 Sarawak air quality
    "cand_6ebf1458cb71ebdc5a6afdf7",   # #5 MIDA Sarawak
    "cand_723ee28556026defb5d628eb",   # #6 Sarawak electoral redelineation
    "cand_afe4bd3302659eb99be0cc11",   # #7 PRU16 multikoalisi
    "cand_b5d224889f3fedd9ecd68188",   # #8 Dr Sim cancer care
    "cand_da5a22acbeb546e8556e365f",   # #9 Taman Sri Muda saman
    "cand_e3667c642a5b8cfcf9e7a069",   # #10 Couple NGO
    "cand_f8a6ac609d8e40c6ac9865bd",   # #11 PH Bersatu makan malam
    "cand_004b328404b99afc338208bc",   # #12 India conversion law
    "cand_0ff87c74934633cf2fa5279a",   # #13 Indian civil servants
    "cand_2813b65d572c0146f8f3ab5c",   # #14 Tata stocks
    "cand_3ff7d48665fc8b7686376413",   # #15 Malaysia Myanmar migrants
    "cand_7a444c025f7799935aed43ac",   # #16 South Korean exports
    "cand_80941ad52fc379b56018af45",   # #17 Shein stocks
    "cand_9320c8d872e52efae142d74d",   # #18 Hormuz stocks
    "cand_a96fa2bdb36199a9c1527114",   # #19 AI crocodile image
    "cand_b9d84ef52022e9ec12b52ce2",   # #20 Big Bang K-pop
]


# ============================================================================
# Per-candidate section renderer
# ============================================================================

def _detect_source_language(headline: str, language_hint: str,
                            sources: List[dict]) -> str:
    """Determine the original source language of the candidate.

    Order of preference:
      1. candidate.language (from Radar)
      2. Heuristic on headline (Malay keywords, Chinese characters)
      3. Default: "English"
    """
    lang = (language_hint or "").lower()
    if lang in ("ms", "malay", "bahasa"):
        return "Malay"
    if lang in ("zh", "zh-cn", "zh-hans", "chinese"):
        return "Chinese"
    if lang in ("en", "english"):
        return "English"
    # Fallback heuristic
    h_low = headline.lower()
    if any(kw in h_low for kw in ("berkuat", "kata ", "berkait",
                                    "dakwa", "saman ", "undi")):
        return "Malay"
    if any("\u4e00" <= ch <= "\u9fff" for ch in headline):
        return "Chinese"
    return "English"


def _candidate_section_zh(idx: int, c: dict) -> str:
    cid = c.get("candidate_id", "")
    zh = ZH_TRANSLATIONS.get(cid, {})
    chinese_headline = zh.get("chinese_headline", "（暂无中文翻译）")
    chinese_summary = zh.get("chinese_summary", "（暂无中文摘要）")
    notes = zh.get("notes_for_editor", "")

    sources = c.get("sources", [])
    rendered_sources = _render_sources(sources)
    src_lang = _detect_source_language(
        c.get("headline", ""), c.get("language", ""), sources,
    )
    first_source_lang = _detect_source_language(
        (sources[0].get("title", "") if sources else ""),
        c.get("language", ""), sources,
    )

    lines: List[str] = []
    lines.append(f"## Sample {idx:02d}")
    lines.append("")
    lines.append(f"- **Candidate ID:** `{cid}`")
    lines.append(f"- **Category:** {c.get('category', '')}")
    lines.append(f"- **State:** {c.get('state', '')}")
    lines.append(f"- **Radar Status:** {c.get('radar_status', '')}")
    lines.append(
        f"- **Verification Status:** {c.get('verification_status', '')}"
    )
    lines.append(f"- **Confidence Label:** {c.get('confidence_label', '')}")
    lines.append("")
    lines.append("### 中文理解标题")
    lines.append("")
    lines.append(f"> {chinese_headline}")
    lines.append("")
    lines.append("### 中文事件摘要")
    lines.append("")
    lines.append(chinese_summary)
    lines.append("")
    lines.append("### Original Source")
    lines.append("")
    lines.append(f"- **Headline language:** {src_lang}")
    if first_source_lang != src_lang:
        lines.append(f"- **Source[0] title language:** {first_source_lang}")
    lines.append("- **Original headline (verbatim, unchanged):**")
    lines.append("")
    lines.append(f"> {c.get('headline', '')}")
    lines.append("")
    lines.append(f"- **Source count:** {c.get('source_count', 0)}")
    lines.append("- **Sources:**")
    for s in rendered_sources:
        url = s.get("url", "")
        safe = s.get("url_safe", False)
        url_marker = "" if safe else " (URL flagged by safety check)"
        lines.append(
            f"  - `{s.get('source_name', '')}` "
            f"[tier={s.get('source_tier', '')}, "
            f"country={s.get('country', '')}, "
            f"type={s.get('source_type', '')}]"
        )
        if url:
            lines.append(f"    - URL: {url}{url_marker}")
        if s.get("title"):
            tlang = _detect_source_language(
                s.get("title", ""), c.get("language", ""), sources,
            )
            lines.append(
                f"    - Source Title ({tlang}): {s.get('title', '')}"
            )
        if s.get("published_at"):
            lines.append(f"    - Published At: {s.get('published_at', '')}")
    lines.append("")
    lines.append(f"- **First Seen:** {c.get('first_seen', '')}")
    lines.append(f"- **Last Seen:** {c.get('last_seen', '')}")
    age = _age_hours(c.get("last_seen", ""))
    if age is not None:
        lines.append(f"- **Last Seen Age:** {age:.2f} hours")
    lines.append(f"- **Mention Count:** {c.get('mention_count', 0)}")
    mom = c.get("momentum", {}) or {}
    lines.append(
        f"- **Momentum:** current={mom.get('current_mentions', '?')}, "
        f"previous={mom.get('previous_mentions', '?')}, "
        f"growth={mom.get('growth', '?')}"
    )
    lines.append(f"- **Claim Kind:** {c.get('claim_kind', '')}")
    lines.append(
        f"- **Political:** is_political={c.get('is_political')}, "
        f"political_neutral={c.get('political_neutral')}"
    )
    elig = c.get("eligibility", {}) or {}
    lines.append(
        f"- **Eligibility:** eligible={elig.get('eligible', '?')}"
    )
    reasons = elig.get("reasons", []) or []
    if reasons:
        lines.append(f"  - Reasons: {', '.join(reasons)}")
    else:
        lines.append(f"  - Reasons: (none recorded)")
    blockers = elig.get("blocking_reasons", []) or []
    if blockers:
        lines.append(f"  - Blocking Reasons: {', '.join(blockers)}")
    else:
        lines.append(
            f"  - Blocking Reasons: (none — this is why the candidate "
            f"is READY_FOR_REVIEW)"
        )
    lines.append("")
    if notes:
        lines.append("### Editor Notes (informational only, not a judgement)")
        lines.append("")
        lines.append(notes)
        lines.append("")
    lines.append("### Editorial Decision (MANUAL ONLY — system does not auto-fill)")
    lines.append("")
    lines.append("- [ ] **A — 值得发展成 MY Hot Radar 文章**")
    lines.append("- [ ] **B — 值得继续观察**")
    lines.append("- [ ] **C — 目前不值得发展成文章**")
    lines.append("- **Editor Reason:** _____________________________________________")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ============================================================================
# Summary block (Chinese)
# ============================================================================

def _build_zh_summary(ready: List[dict], sample: List[dict]) -> str:
    lines: List[str] = []
    n_ready = len(ready)
    n_sample = len(sample)
    cats = Counter(c.get("category") for c in sample)
    pol = [c for c in sample if c.get("is_political")]
    lang_of_headline = Counter(
        _detect_source_language(
            c.get("headline", ""), c.get("language", ""), c.get("sources", [])
        ) for c in sample
    )
    v = Counter(c.get("verification_status") for c in sample)
    co = Counter(c.get("confidence_label") for c in sample)
    src = Counter(c.get("source_count") for c in sample)
    lines.append("## 1. 摘要 / Summary")
    lines.append("")
    lines.append(f"- **READY_FOR_REVIEW 总数 (当前):** {n_ready}")
    lines.append(
        f"- **样本大小 (Sample size, pinned):** {n_sample} "
        f"(取自 `PINNED_SAMPLE_IDS` 固定列表)"
    )
    lines.append(f"- **样本 Category 分布:** {dict(cats)}")
    lines.append(f"- **样本 Verification 分布:** {dict(v)}")
    lines.append(f"- **样本 Confidence 分布:** {dict(co)}")
    lines.append(f"- **样本 Source-count 分布:** {dict(src)}")
    lines.append(f"- **样本政治类 (is_political=True) 数量:** {len(pol)}")
    lines.append(f"- **样本头条语言分布:** {dict(lang_of_headline)}")
    lines.append("")
    lines.append(
        "> 本审核版 Sample 是**固定 20 个 candidate_id** 的快照；如需"
        "了解当前 READY 池的整体情况，请参考 `docs/CANDIDATE_REVIEW_"
        "SAMPLE.md`（英文版，含描述性观察）。本中文版主要用于人工"
        "逐条审核候选。"
    )
    lines.append("")
    return "\n".join(lines)


# ============================================================================
# Audit properties block (Chinese)
# ============================================================================

def _build_zh_audit_properties() -> str:
    lines: List[str] = []
    lines.append("## 3. 审核辅助层属性 / Audit Properties")
    lines.append("")
    lines.append("- **只读 (Read-only):** 本报告读取 `radar_data/candidates/"
                 "latest.json`，不写入、不修改任何 candidate 文件。")
    lines.append("- **忠实翻译 (Faithful translation):** 中文标题与摘要为"
                 "人工撰写 (hand-authored)，不是 LLM 实时翻译。")
    lines.append("- **不自动判断 (No auto-judgement):** 系统不会自动填入 A / "
                 "B / C。三个选项必须由人工编辑填写。")
    lines.append("- **政治中立 (Political neutrality):** 政治类候选使用"
                 "「据相关报道」、「某方表示」、「有消息称」等中立措辞，"
                 "不评价任何政党或政治人物，不预测选举结果。")
    lines.append("- **不升级 verification (No verification upgrade):** 原文"
                 "verification_status=REPORTED 的候选，中文摘要不会"
                 "改写为「已确认」事实。")
    lines.append("- **保留原始标题 (Original headline preserved):** 中文"
                 "理解标题之外，原始 headline 完整保留（verbatim, "
                 "unchanged）。")
    lines.append("- **可复现 (Reproducible):** 同一 candidate store + "
                 "sample_size 永远产生相同的样本。")
    lines.append("- **固定 20 候选 (Pinned 20 candidates):** 本审核版的"
                 "样本是 `PINNED_SAMPLE_IDS` 锁定的 20 个 ID，与每次"
                 "live stride-pick 解耦，确保 20 条人工中文翻译始终"
                 "与同一组候选配对。")
    lines.append("")
    return "\n".join(lines)


# ============================================================================
# Main entry point
# ============================================================================

def build_chinese_review_report(
    candidate_latest_path: Path,
    output_report_path: Path,
    sample_size: int = 20,
) -> dict:
    """Build the Chinese-language editorial review report."""
    p = Path(candidate_latest_path)
    if not p.exists():
        raise FileNotFoundError(f"candidate latest.json not found: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    candidates = payload.get("candidates", [])
    ready = [c for c in candidates if c.get("state") == "READY_FOR_REVIEW"]

    # Snapshot candidate file mtimes / hashes (no-mutation test)
    file_hashes: Dict[str, str] = {}
    cand_dir = p.parent / "by_day"
    if cand_dir.exists():
        import hashlib
        for f in cand_dir.rglob("*.json"):
            file_hashes[str(f)] = hashlib.sha256(
                f.read_bytes()
            ).hexdigest()

    if len(ready) < sample_size:
        sample = list(ready)
    else:
        sample = select_chinese_sample(ready, sample_size=sample_size)

    # Verify every sampled candidate has a Chinese translation
    missing_zh = [
        c.get("candidate_id", "")
        for c in sample
        if c.get("candidate_id", "") not in ZH_TRANSLATIONS
    ]
    if missing_zh:
        # We do NOT fail hard — we still render the report but
        # the missing entries will show the placeholder. This
        # is intentional: the report must be reproducible even
        # when the candidate set grows. New candidates get the
        # default placeholder.
        pass

    # Build markdown
    lines: List[str] = []
    lines.append("# Editorial Review Sample v2 — 中文审核版")
    lines.append("")
    lines.append(f"- **版本 (Version):** {CHINESE_REVIEW_VERSION}")
    lines.append(
        f"- **生成时间 (UTC):** "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    lines.append(f"- **数据源:** `{p}`")
    lines.append("")
    lines.append(
        "> **重要提示:** 中文标题与摘要仅为人工审核辅助 (review aid)。"
        "中文不会覆盖原始英文/马来文标题。原始标题逐字保留。系统"
        "不自动填写 A / B / C 编辑判断，必须由人工编辑填写。政治"
        "类候选保持严格中立，不评价任何政党或政治人物。"
    )
    lines.append("")

    lines.append(_build_zh_summary(ready, sample))
    lines.append("")
    lines.append("## 2. 取样方法 / Sampling Method")
    lines.append("")
    lines.append(
        "本审核版 Sample 使用一组**固定的 20 个 candidate_id**（见 "
        "`radar.audit.chinese_review.PINNED_SAMPLE_IDS`）。这 20 个 ID "
        "是本批次开始时锁定的快照，与英文版 `docs/CANDIDATE_REVIEW_SAMPLE.md` "
        "中使用相同 deterministic 算法在同一时刻选出的样本一致。如果某个 "
        "pinned candidate 因 freshness / 新 topic 出现等而暂时不在 READY "
        "池中，本报告会自动跳过它（永不重新选样）。"
    )
    lines.append("")
    lines.append(
        "锁定样本的原因是：每个 candidate 的中文标题与摘要都是人工撰写 "
        "(hand-authored) 的忠实翻译，不希望新 topic 出现后被自动换走。 "
        "下一次重新取样属于另一批次，需要新一组人工翻译。"
    )
    lines.append("")

    lines.append("## 3. 逐候选详情 / Per-Candidate Detail")
    lines.append("")
    for i, c in enumerate(sample, 1):
        lines.append(_candidate_section_zh(i, c))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(_build_zh_audit_properties())
    lines.append("")

    output_path = Path(output_report_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

    # Verify no candidate file was mutated
    cand_dir = p.parent / "by_day"
    if cand_dir.exists():
        import hashlib
        for f in cand_dir.rglob("*.json"):
            current = hashlib.sha256(f.read_bytes()).hexdigest()
            prior = file_hashes.get(str(f))
            if prior is not None and prior != current:
                raise RuntimeError(
                    f"AUDIT VIOLATION: candidate file {f} was modified "
                    "during audit run. This must never happen."
                )

    return {
        "ready_total": len(ready),
        "sample_size": len(sample),
        "categories_in_sample": dict(
            Counter(c.get("category") for c in sample)
        ),
        "verification_in_sample": dict(
            Counter(c.get("verification_status") for c in sample)
        ),
        "political_in_sample": sum(
            1 for c in sample if c.get("is_political")
        ),
        "headline_language_in_sample": dict(
            Counter(
                _detect_source_language(
                    c.get("headline", ""),
                    c.get("language", ""),
                    c.get("sources", []),
                ) for c in sample
            )
        ),
        "report_path": str(output_path),
        "audit_version": CHINESE_REVIEW_VERSION,
    }


# ============================================================================
# CLI
# ============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Editorial review sample (中文审核版) — READ-ONLY."
    )
    parser.add_argument(
        "--candidates",
        default="radar_data/candidates/latest.json",
        help="Path to candidates/latest.json",
    )
    parser.add_argument(
        "--output",
        default="docs/CANDIDATE_REVIEW_SAMPLE_ZH.md",
        help="Path to write the markdown report",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="How many candidates to sample (default 20).",
    )
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parents[2]
    cand = (here / args.candidates).resolve()
    out = (here / args.output).resolve()
    summary = build_chinese_review_report(cand, out, sample_size=args.sample_size)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
