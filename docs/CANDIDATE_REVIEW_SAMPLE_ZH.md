# Editorial Review Sample v2 — 中文审核版

- **版本 (Version):** phase2-b3b2-zh-review-v1
- **生成时间 (UTC):** 2026-09-29T07:37:37Z
- **数据源:** `C:\MY-Hot-Radar\radar_data\candidates\latest.json`

> **重要提示:** 中文标题与摘要仅为人工审核辅助 (review aid)。中文不会覆盖原始英文/马来文标题。原始标题逐字保留。系统不自动填写 A / B / C 编辑判断，必须由人工编辑填写。政治类候选保持严格中立，不评价任何政党或政治人物。

## 1. 摘要 / Summary

- **READY_FOR_REVIEW 总数 (当前):** 84
- **样本大小 (Sample size, pinned):** 20 (取自 `PINNED_SAMPLE_IDS` 固定列表)
- **样本 Category 分布:** {'MALAYSIA': 11, 'WORLD': 9}
- **样本 Verification 分布:** {'CONFIRMED': 2, 'REPORTED': 18}
- **样本 Confidence 分布:** {'HIGH': 2, 'MEDIUM': 18}
- **样本 Source-count 分布:** {4: 1, 2: 4, 1: 14, 3: 1}
- **样本政治类 (is_political=True) 数量:** 5
- **样本头条语言分布:** {'Malay': 6, 'English': 14}

> 本审核版 Sample 是**固定 20 个 candidate_id** 的快照；如需了解当前 READY 池的整体情况，请参考 `docs/CANDIDATE_REVIEW_SAMPLE.md`（英文版，含描述性观察）。本中文版主要用于人工逐条审核候选。


## 2. 取样方法 / Sampling Method

本审核版 Sample 使用一组**固定的 20 个 candidate_id**（见 `radar.audit.chinese_review.PINNED_SAMPLE_IDS`）。这 20 个 ID 是本批次开始时锁定的快照，与英文版 `docs/CANDIDATE_REVIEW_SAMPLE.md` 中使用相同 deterministic 算法在同一时刻选出的样本一致。如果某个 pinned candidate 因 freshness / 新 topic 出现等而暂时不在 READY 池中，本报告会自动跳过它（永不重新选样）。

锁定样本的原因是：每个 candidate 的中文标题与摘要都是人工撰写 (hand-authored) 的忠实翻译，不希望新 topic 出现后被自动换走。 下一次重新取样属于另一批次，需要新一组人工翻译。

## 3. 逐候选详情 / Per-Candidate Detail

## Sample 01

- **Candidate ID:** `cand_0291d8fe5d13bd7232a8dd38`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** CONFIRMED
- **Confidence Label:** HIGH

### 中文理解标题

> 陆兆福：纳吉开始居家服刑时，自己将正式卸下部长职务

### 中文事件摘要

据相关报道，行动党籍交通部长陆兆福表示，一旦纳吉进入居家服刑阶段，他本人将正式卸下部长职务。多家马来媒体同时报道了相关进展。此事件当前 Radar verification_status=CONFIRMED、confidence_label=HIGH，但仍属政治敏感内容，编辑审核时需保持严格中立，不评价任何政党或政治人物。

### Original Source

- **Headline language:** Malay
- **Original headline (verbatim, unchanged):**

> Peletakan jawatan berkuat kuasa sebaik Najib jalani tahanan rumah, kata Loke

- **Source count:** 4
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/ismail-tak-perlu-letak-jawatan-walaupun-tersilap-langkah-kata-penganalisis
    - Source Title (Malay): Ismail tak perlu letak jawatan walau tersilap langkah, kata penganalisis
    - Published At: Tue, 29 Sep 2026 04:45:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/peletakan-jawatan-berkuat-kuasa-sebaik-najib-jalani-tahanan-rumah-kata-loke
    - Source Title (Malay): Peletakan jawatan berkuat kuasa sebaik Najib jalani tahanan rumah, kata Loke
    - Published At: Tue, 29 Sep 2026 04:30:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/saya-tak-tahu-kenapa-saksi-pinda-kenyataan-kata-pegawai-penyiasat
    - Source Title (Malay): Saya tak tahu kenapa saksi pinda kenyataan, kata pegawai penyiasat
    - Published At: Mon, 28 Sep 2026 10:34:00 +0000
  - `Borneo Post` [tier=B, country=MY, type=RSS]
    - URL: https://www.theborneopost.com/2026/09/29/loke-says-will-stay-as-transport-minister-until-najib-house-arrest-begins/
    - Source Title (Malay): Loke says will stay as transport minister until Najib house arrest begins
    - Published At: Tue, 29 Sep 2026 04:49:20 +0000

- **First Seen:** Mon, 28 Sep 2026 10:34:00 +0000
- **Last Seen:** Tue, 29 Sep 2026 04:49:20 +0000
- **Last Seen Age:** 2.80 hours
- **Mention Count:** 4
- **Momentum:** current=4, previous=4, growth=0
- **Claim Kind:** CLAIM
- **Political:** is_political=True, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, confirmed_evidence, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

此 candidate 是 dedup 集群（4 个 source），4 篇相关但不同角度的报道围绕 Najib house arrest / 部长职位变动；中文标题以 headline 为准。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 02

- **Candidate ID:** `cand_24034fa2cdf3d35f24bc8815`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 前 FIC 首席执行官被指控就 Jalan Semarak 项目欺骗董事会

### 中文事件摘要

据相关报道，前 FIC 首席执行官被指控在 Jalan Semarak 相关项目中欺骗董事会。相关案件已安排明日过堂。此事件当前 Radar verification_status=REPORTED，仅有 2 个同语种马来媒体来源作为佐证。

### Original Source

- **Headline language:** Malay
- **Original headline (verbatim, unchanged):**

> Bekas CEO FIC didakwa perdaya lembaga pengarah berkait projek Jalan Semarak

- **Source count:** 2
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/bekas-ceo-fic-didakwa-perdaya-lembaga-pengarah-berkait-projek-jalan-semarak
    - Source Title (Malay): Bekas CEO FIC didakwa perdaya lembaga pengarah berkait projek Jalan Semarak
    - Published At: Tue, 29 Sep 2026 01:38:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/bekas-ceo-fic-dituduh-esok-berkait-kes-klvc
    - Source Title (Malay): Bekas CEO FIC dituduh esok berkait kes KLVC
    - Published At: Mon, 28 Sep 2026 15:08:36 +0000

- **First Seen:** Mon, 28 Sep 2026 15:08:36 +0000
- **Last Seen:** Tue, 29 Sep 2026 01:38:00 +0000
- **Last Seen Age:** 5.99 hours
- **Mention Count:** 2
- **Momentum:** current=2, previous=2, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 03

- **Candidate ID:** `cand_3d097706f002b1e241be291b`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 公众受促警惕通过邮寄方式进行的「药品注册」骗局

### 中文事件摘要

据相关报道，主管部门提醒公众警惕以邮寄方式进行的所谓「药品注册」骗局，避免受骗上当。此事件当前 Radar verification_status=REPORTED，仅 1 个来源。

### Original Source

- **Headline language:** Malay
- **Original headline (verbatim, unchanged):**

> Orang ramai diingat jangan terpedaya ‘scam’ pendaftaran ubat melalui pos

- **Source count:** 1
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/orang-ramai-diingat-jangan-terpedaya-scam-pendaftaran-ubat-melalui-pos
    - Source Title (Malay): Orang ramai diingat jangan terpedaya ‘scam’ pendaftaran ubat melalui pos
    - Published At: Tue, 29 Sep 2026 03:16:41 +0000

- **First Seen:** Tue, 29 Sep 2026 03:16:41 +0000
- **Last Seen:** Tue, 29 Sep 2026 03:16:41 +0000
- **Last Seen Age:** 4.35 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 04

- **Candidate ID:** `cand_4a46b36aa26f8da6c4dca778`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 砂拉越 8 个地区中午录得「不健康」API 等级，Kanowit 也在名单上

### 中文事件摘要

据相关报道，砂拉越多个地区空气污染加剧，中午前已有 8 个地区录得「不健康」等级 API 读数，Kanowit 也被列入。此事件当前 Radar verification_status=REPORTED。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Eight Sarawak areas record ‘Unhealthy’ API at noon as Kanowit joins list

- **Source count:** 1
- **Sources:**
  - `Borneo Post` [tier=B, country=MY, type=RSS]
    - URL: https://www.theborneopost.com/2026/09/29/eight-sarawak-areas-record-unhealthy-api-at-noon-as-kanowit-joins-list/
    - Source Title (English): Eight Sarawak areas record ‘Unhealthy’ API at noon as Kanowit joins list
    - Published At: Tue, 29 Sep 2026 04:44:43 +0000

- **First Seen:** Tue, 29 Sep 2026 04:44:43 +0000
- **Last Seen:** Tue, 29 Sep 2026 04:44:43 +0000
- **Last Seen Age:** 2.88 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

headline 在多次 scan 中曾出现两个版本（7 个站 vs 8 个地区，含 Kanowit），Radar dedup 后的最新 headline 为 8 个地区版。本中文翻译以最新 headline 为准。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 05

- **Candidate ID:** `cand_6ebf1458cb71ebdc5a6afdf7`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> MIDA 支持砂拉越的工业转型

### 中文事件摘要

据相关报道，马来西亚投资发展局（MIDA）表示支持砂拉越的工业转型进程。此事件当前 Radar verification_status=REPORTED，仅 1 个来源。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> MIDA supports Sarawak’s industrial transformation

- **Source count:** 1
- **Sources:**
  - `Borneo Post` [tier=B, country=MY, type=RSS]
    - URL: https://www.theborneopost.com/2026/09/29/mida-supports-sarawaks-industrial-transformation/
    - Source Title (English): MIDA supports Sarawak’s industrial transformation
    - Published At: Tue, 29 Sep 2026 05:32:07 +0000

- **First Seen:** Tue, 29 Sep 2026 05:32:07 +0000
- **Last Seen:** Tue, 29 Sep 2026 05:32:07 +0000
- **Last Seen Age:** 2.09 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本条内容为官方机构立场声明，编辑判断时需考虑：是否值得作为独立文章，还是作为本地工业简讯合并报道。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 06

- **Candidate ID:** `cand_723ee28556026defb5d628eb`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 砂拉越选区重划公告展期明日下午 5 时结束

### 中文事件摘要

据相关报道，砂拉越选区重划的公众查阅期将在明日下午 5 时结束。此事件属程序性政治公告，Radar 标记为 political=True、claim_kind=EVENT、verification_status=REPORTED，仅1 个来源。编辑审核时需保持中立，仅作为程序性事实呈现，不评论选区划分本身的合理性。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Public display for Sarawak electoral redelineation closes 5pm tomorrow

- **Source count:** 1
- **Sources:**
  - `Borneo Post` [tier=B, country=MY, type=RSS]
    - URL: https://www.theborneopost.com/2026/09/29/public-display-for-sarawak-electoral-redelineation-closes-5pm-tomorrow/
    - Source Title (English): Public display for Sarawak electoral redelineation closes 5pm tomorrow
    - Published At: Tue, 29 Sep 2026 05:14:49 +0000

- **First Seen:** Tue, 29 Sep 2026 05:14:49 +0000
- **Last Seen:** Tue, 29 Sep 2026 05:14:49 +0000
- **Last Seen Age:** 2.38 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** EVENT
- **Political:** is_political=True, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 07

- **Candidate ID:** `cand_afe4bd3302659eb99be0cc11`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> （标题翻译）为何多党联盟在第十六届全国大选出现明显分裂

### 中文事件摘要

据相关报道，本篇报道讨论第十六届全国大选（PRU16）中多党联盟出现明显分裂的现象。Radar 标记为 political=True、claim_kind=EVENT、verification_status=REPORTED，仅 1 个来源。中文标题仅为原文翻译，不添加编辑判断，不对任何政党或联盟做评价、排名或预测。

### Original Source

- **Headline language:** Malay
- **Original headline (verbatim, unchanged):**

> Mengapa perpecahan multikoalisi mutlak berlaku dalam PRU16

- **Source count:** 1
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/pandangan/2026/09/29/mengapa-perpecahan-multikoalisi-mutlak-berlaku-dalam-pru16
    - Source Title (Malay): Mengapa perpecahan multikoalisi mutlak berlaku dalam PRU16
    - Published At: Tue, 29 Sep 2026 01:00:00 +0000

- **First Seen:** Tue, 29 Sep 2026 01:00:00 +0000
- **Last Seen:** Tue, 29 Sep 2026 01:00:00 +0000
- **Last Seen Age:** 6.63 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** EVENT
- **Political:** is_political=True, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

原文 Malay 标题为「为何…」句式，Radar 分类为 EVENT 而非OPINION（按 Phase 2 B1 政治规则，OPINION 才会被 BLOCK）。编辑审核时需特别注意：标题虽为分析性，但本候选仍属Radar 标记为 EVENT 的政治类报道，请按 political_neutral=True 的处理原则严格中立呈现。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 08

- **Candidate ID:** `cand_b5d224889f3fedd9ecd68188`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 沈桂鸿：癌症医疗框架须考虑砂拉越的乡村与偏远地区

### 中文事件摘要

据相关报道，砂拉越副总理兼公共卫生、房屋与地方政府部长沈桂鸿（Dr Sim）表示，砂拉越的癌症医疗框架须考虑该州的乡村与偏远社区特点。3 个 Borneo Post 来源覆盖同一议题的不同角度（健康城市、癌症框架、Sarawak Beyond 2026）。当前 Radar verification_status=REPORTED。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Dr Sim: Cancer care framework must consider state’s rural, remote communities

- **Source count:** 3
- **Sources:**
  - `Borneo Post` [tier=B, country=MY, type=RSS]
    - URL: https://www.theborneopost.com/2026/09/29/dr-sim-sarawak-must-redesign-cities-communities-to-improve-health-outcomes/
    - Source Title (English): Dr Sim: Sarawak must redesign cities, communities to improve health outcomes
    - Published At: Tue, 29 Sep 2026 05:08:34 +0000
  - `Borneo Post` [tier=B, country=MY, type=RSS]
    - URL: https://www.theborneopost.com/2026/09/29/dr-sim-cancer-care-framework-must-consider-states-rural-remote-communities/
    - Source Title (English): Dr Sim: Cancer care framework must consider state’s rural, remote communities
    - Published At: Tue, 29 Sep 2026 00:00:06 +0000
  - `Borneo Post` [tier=B, country=MY, type=RSS]
    - URL: https://www.theborneopost.com/2026/09/29/sarawak-beyond-2026-brings-global-biz-market-closer-to-local-communities/
    - Source Title (English): Sarawak Beyond 2026 brings global biz market closer to local communities
    - Published At: Mon, 28 Sep 2026 23:02:51 +0000

- **First Seen:** Mon, 28 Sep 2026 23:02:51 +0000
- **Last Seen:** Tue, 29 Sep 2026 05:08:34 +0000
- **Last Seen Age:** 2.48 hours
- **Mention Count:** 3
- **Momentum:** current=3, previous=3, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本 candidate 是 dedup 集群，3 篇相关但不同角度的报道；中文标题以 headline 为准。涉及官方政策表态，编辑判断时需注意属「政策声明」还是「实质政策行动」。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 09

- **Candidate ID:** `cand_da5a22acbeb546e8556e365f`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> Taman Sri Muda 居民就 2021 年水灾起诉政府胜诉

### 中文事件摘要

据相关报道，雪兰莪州 Taman Sri Muda 居民就 2021 年发生的水灾起诉政府一案取得胜诉。此事件属 Radar 标记 political=True、claim_kind=CLAIM、verification_status=REPORTED，仅 1 个来源。中文标题仅为原文翻译，不评价政府或任何政党在灾害管理上的表现，不预测后续司法程序。

### Original Source

- **Headline language:** Malay
- **Original headline (verbatim, unchanged):**

> Penduduk Taman Sri Muda menang saman kerajaan berkait banjir 2021

- **Source count:** 1
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/penduduk-taman-sri-muda-menang-saman-kerajaan-berkait-banjir-2021
    - Source Title (Malay): Penduduk Taman Sri Muda menang saman kerajaan berkait banjir 2021
    - Published At: Tue, 29 Sep 2026 04:18:25 +0000

- **First Seen:** Tue, 29 Sep 2026 04:18:25 +0000
- **Last Seen:** Tue, 29 Sep 2026 04:18:25 +0000
- **Last Seen Age:** 3.32 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** CLAIM
- **Political:** is_political=True, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 10

- **Candidate ID:** `cand_e3667c642a5b8cfcf9e7a069`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 面对健康挑战，夫妇向 NGO 寻求家庭支援

### 中文事件摘要

据相关报道，一对夫妇因面对健康方面的挑战，转向非政府组织（NGO）寻求家庭支援服务。此事件当前 Radar verification_status=REPORTED，仅 1 个来源。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Couple turn to NGO for family support amid health challenges

- **Source count:** 1
- **Sources:**
  - `Borneo Post` [tier=B, country=MY, type=RSS]
    - URL: https://www.theborneopost.com/2026/09/29/couple-turn-to-ngo-for-family-support-amid-health-challenges/
    - Source Title (English): Couple turn to NGO for family support amid health challenges
    - Published At: Mon, 28 Sep 2026 23:01:51 +0000

- **First Seen:** Mon, 28 Sep 2026 23:01:51 +0000
- **Last Seen:** Mon, 28 Sep 2026 23:01:51 +0000
- **Last Seen Age:** 8.60 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本条属「人物故事」类素材，编辑判断时需考虑：是否值得独立报道，还是与本地 NGO 专题合并。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 11

- **Candidate ID:** `cand_f8a6ac609d8e40c6ac9865bd`
- **Category:** MALAYSIA
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 不是 PAS，也不是 PH——Umno 自身是否还有独立力量？

### 中文事件摘要

据相关报道，本篇报道讨论 Umno 是否仍拥有独立于 PAS 与 PH 之外的政治力量。同 candidate 集群中其他来源还包括法米否认希盟与土团党已有正式讨论、以及早前希盟与土团党领袖在马六甲州选协商传闻中共进晚餐的报道。Radar 标记 is_political=False、verification_status=REPORTED。中文标题仅为原文翻译，编辑审核时需保持严格中立，不评价任何政党、不预测选举结果。

### Original Source

- **Headline language:** Malay
- **Original headline (verbatim, unchanged):**

> Bukan PAS atau PH, Umno ada kekuatan sendiri atau tidak?

- **Source count:** 2
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/belum-ada-perbincangan-rasmi-ph-bersatu-kata-fahmi
    - Source Title (Malay): Belum ada perbincangan rasmi PH-Bersatu, kata Fahmi
    - Published At: Tue, 29 Sep 2026 02:46:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/opinion/2026/09/29/bukan-pas-atau-ph-umno-ada-kekuatan-sendiri-atau-tidak
    - Source Title (Malay): Bukan PAS atau PH, Umno ada kekuatan sendiri atau tidak?
    - Published At: Tue, 29 Sep 2026 00:00:00 +0000

- **First Seen:** Tue, 29 Sep 2026 00:00:00 +0000
- **Last Seen:** Tue, 29 Sep 2026 02:46:00 +0000
- **Last Seen Age:** 4.86 hours
- **Mention Count:** 2
- **Momentum:** current=2, previous=2, growth=0
- **Claim Kind:** EVENT
- **Political:** is_political=True, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本 candidate 是 dedup 集群，集群中混合了不同角度的报道：当前 headline（Umno 力量分析）、法米否认官方协商（正面否认）、早前希盟与土团党共进晚餐的报道等。Radar 将其标记为 is_political=True、political_neutral=True、claim_kind=EVENT（虽然内容涉及政治讨论，但 Radar 判定为中性事件类）。编辑审核时需特别注意：verification 仍为 REPORTED，不应写为「已确认」。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 12

- **Candidate ID:** `cand_004b328404b99afc338208bc`
- **Category:** WORLD
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 祈祷前先签到：印度某邦新颁布的改宗法律正影响当地教会信徒

### 中文事件摘要

据相关报道，印度某邦新颁布的改宗相关法律正影响当地教会信徒，有信徒反映在参加祈祷前须先进行登记或签署文件。Radar 标记 verification_status=REPORTED、来源为 BBC News Asia（英国，Tier-B）。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Sign before praying: A new conversion law is affecting churchgoers in Indian state

- **Source count:** 1
- **Sources:**
  - `BBC News Asia` [tier=B, country=GB, type=RSS]
    - URL: https://www.bbc.co.uk/news/articles/cmj4jg2vxvpdo?at_medium=RSS&at_campaign=rss
    - Source Title (English): Sign before praying: A new conversion law is affecting churchgoers in Indian state
    - Published At: Tue, 29 Sep 2026 00:50:19 GMT

- **First Seen:** Tue, 29 Sep 2026 00:50:19 GMT
- **Last Seen:** Tue, 29 Sep 2026 00:50:19 GMT
- **Last Seen Age:** 6.79 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本条涉及宗教政策，编辑判断时需注意：不评价印度政府的宗教政策，不对任何宗教做倾向性表达，仅作为国际新闻报道。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 13

- **Candidate ID:** `cand_0ff87c74934633cf2fa5279a`
- **Category:** WORLD
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 为何部分印度公务员因做好本职工作而被视为公众英雄

### 中文事件摘要

据相关报道，BBC 一篇特稿探讨为何部分印度公务员因做好本职工作而被公众视为英雄。Radar 标记 verification_status=REPORTED、来源为 BBC News Asia（英国，Tier-B）。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Why some Indian civil servants become heroes for doing their jobs

- **Source count:** 1
- **Sources:**
  - `BBC News Asia` [tier=B, country=GB, type=RSS]
    - URL: https://www.bbc.co.uk/news/articles/cw980vje6l3eo?at_medium=RSS&at_campaign=rss
    - Source Title (English): Why some Indian civil servants become heroes for doing their jobs
    - Published At: Sun, 27 Sep 2026 23:01:37 GMT

- **First Seen:** Sun, 27 Sep 2026 23:01:37 GMT
- **Last Seen:** Sun, 27 Sep 2026 23:01:37 GMT
- **Last Seen Age:** 32.60 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本条为 BBC 人物特稿类报道，编辑判断时需考虑是否值得独立报道，或与「亚洲治理 / 公共服务」专题合并。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 14

- **Candidate ID:** `cand_2813b65d572c0146f8f3ab5c`
- **Category:** WORLD
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 塔塔股价下跌，旗下信托提议阻止控股公司上市

### 中文事件摘要

据相关报道，印度塔塔集团（Tata）股价出现下跌，原因是其旗下信托机构提议一项可能阻止塔塔控股公司上市的措施。Radar 标记 verification_status=REPORTED、来源为 Channel News Asia（新加坡，Tier-B）。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Tata stocks slip after Trusts propose move to prevent holding company listing

- **Source count:** 1
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, country=SG, type=RSS]
    - URL: https://www.channelnewsasia.com/business/tata-stocks-slip-after-trusts-propose-move-prevent-holding-company-listing-6417496
    - Source Title (English): Tata stocks slip after Trusts propose move to prevent holding company listing
    - Published At: Tue, 29 Sep 2026 12:27:48 +0800

- **First Seen:** Tue, 29 Sep 2026 12:27:48 +0800
- **Last Seen:** Tue, 29 Sep 2026 12:27:48 +0800
- **Last Seen Age:** 3.16 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本条属企业财务 / 公司治理类报道，编辑判断时需考虑：原文为英文财经报道，数字与公司名称须保留原样。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 15

- **Candidate ID:** `cand_3ff7d48665fc8b7686376413`
- **Category:** WORLD
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** CONFIRMED
- **Confidence Label:** HIGH

### 中文理解标题

> 马来西亚开始遣返缅甸移民回国

### 中文事件摘要

据相关报道，马来西亚已开始将滞留在马的缅甸移民/难民遣返回国。涉及 2 个来源（Channel News Asia 英文、Free Malaysia Today 马来文），Radar 标记 verification_status=CONFIRMED、confidence_label=HIGH。编辑审核时需保持中立，不评价马来西亚或缅甸政府的相关政策，不推测后续影响。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Malaysia starts sending Myanmar migrants home

- **Source count:** 2
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, country=SG, type=RSS]
    - URL: https://www.channelnewsasia.com/asia/malaysia-myanmar-rohingya-refugees-repatriation-6417266
    - Source Title (English): Malaysia starts sending Myanmar migrants home
    - Published At: Tue, 29 Sep 2026 10:48:33 +0800
  - `Free Malaysia Today (Bahasa)` [tier=B, country=MY, type=RSS]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/malaysia-mula-hantar-pulang-pelarian-myanmar
    - Source Title (English): Malaysia mula hantar pulang pelarian Myanmar
    - Published At: Tue, 29 Sep 2026 01:24:13 +0000

- **First Seen:** Tue, 29 Sep 2026 01:24:13 +0000
- **Last Seen:** Tue, 29 Sep 2026 10:48:33 +0800
- **Last Seen Age:** 4.82 hours
- **Mention Count:** 2
- **Momentum:** current=2, previous=2, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, confirmed_evidence, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本 candidate 是少数 verification_status=CONFIRMED 的例子（1/20）。涉及移民与人道议题，编辑判断时需注意中立的措辞。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 16

- **Candidate ID:** `cand_7a444c025f7799935aed43ac`
- **Category:** WORLD
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 路透民调：受 AI 芯片需求支撑，韩国出口预计连续第 16 个月增长

### 中文事件摘要

据路透社一项民调，受 AI 芯片需求支撑，韩国出口预计将实现连续第 16 个月增长。Radar 标记 verification_status=REPORTED、来源为 Channel News Asia（新加坡，Tier-B）。注意：原文为「民调预测」，属预测性内容，编辑审核时应保留「预测 / 民调」措辞，不写为「已实现」事实。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> South Korean exports seen rising for 16th month on solid AI chip demand: Reuters poll

- **Source count:** 1
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, country=SG, type=RSS]
    - URL: https://www.channelnewsasia.com/business/south-korean-exports-seen-rising-16th-month-solid-ai-chip-demand-reuters-poll-6417096
    - Source Title (English): South Korean exports seen rising for 16th month on solid AI chip demand: Reuters poll
    - Published At: Tue, 29 Sep 2026 09:08:01 +0800

- **First Seen:** Tue, 29 Sep 2026 09:08:01 +0800
- **Last Seen:** Tue, 29 Sep 2026 09:08:01 +0800
- **Last Seen Age:** 6.49 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 17

- **Candidate ID:** `cand_80941ad52fc379b56018af45`
- **Category:** WORLD
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 快时尚平台 Shein 股价下跌 6%，季度利润下滑 67%

### 中文事件摘要

据相关报道，快时尚平台 Shein 股价下跌约 6%，原因是其季度利润同比下滑约 67%。Radar 标记 verification_status=REPORTED、来源为 Channel News Asia（新加坡，Tier-B）。数字（6%、67%）须保留原样。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Shares of fast-fashion platform Shein fall 6% after quarterly profit slides 67%

- **Source count:** 1
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, country=SG, type=RSS]
    - URL: https://www.channelnewsasia.com/business/shares-fast-fashion-platform-shein-fall-6-after-quarterly-profit-slides-67-6417151
    - Source Title (English): Shares of fast-fashion platform Shein fall 6% after quarterly profit slides 67%
    - Published At: Tue, 29 Sep 2026 09:46:09 +0800

- **First Seen:** Tue, 29 Sep 2026 09:46:09 +0800
- **Last Seen:** Tue, 29 Sep 2026 09:46:09 +0800
- **Last Seen Age:** 5.86 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 18

- **Candidate ID:** `cand_9320c8d872e52efae142d74d`
- **Category:** WORLD
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 霍尔木兹海峡希望减弱，股市下跌、油价上涨

### 中文事件摘要

据相关报道，市场对霍尔木兹海峡局势的希望有所减弱，全球股市出现下跌、油价出现上涨。Radar 标记 verification_status=REPORTED、来源为 Channel News Asia（新加坡，Tier-B）。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Stocks drop and oil rises as Hormuz hopes fade

- **Source count:** 1
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, country=SG, type=RSS]
    - URL: https://www.channelnewsasia.com/business/stocks-drop-and-oil-rises-hormuz-hopes-fade-6417441
    - Source Title (English): Stocks drop and oil rises as Hormuz hopes fade
    - Published At: Tue, 29 Sep 2026 12:12:00 +0800

- **First Seen:** Tue, 29 Sep 2026 12:12:00 +0800
- **Last Seen:** Tue, 29 Sep 2026 12:12:00 +0800
- **Last Seen Age:** 3.43 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 19

- **Candidate ID:** `cand_a96fa2bdb36199a9c1527114`
- **Category:** WORLD
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 男子因 AI 生成鳄鱼图像引发 Pandan 水库搜索行动被控

### 中文事件摘要

据相关报道，一名男子因使用 AI 生成的鳄鱼图像导致Pandan Reservoir 一带展开搜索行动，而被警方控上法庭。本 candidate 是 dedup 集群（2 个 Channel News Asia 来源），另一条 source 报道为 Google 在欧盟对 AI / 搜索相关反垄断指令的挑战。中文标题以 headline 为准。Radar 标记 verification_status=REPORTED。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Man charged over AI-generated image of crocodile that led to search operations at Pandan Reservoir

- **Source count:** 2
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, country=SG, type=RSS]
    - URL: https://www.channelnewsasia.com/business/google-challenges-eu-orders-open-up-ai-search-engine-rivals-6417651
    - Source Title (English): Google challenges EU orders to open up to AI, search-engine rivals
    - Published At: Tue, 29 Sep 2026 13:06:22 +0800
  - `Channel News Asia (Asia section)` [tier=B, country=SG, type=RSS]
    - URL: https://www.channelnewsasia.com/singapore/ai-generated-crocodile-image-pandan-reservoir-man-charged-6417156
    - Source Title (English): Man charged over AI-generated image of crocodile that led to search operations at Pandan Reservoir
    - Published At: Tue, 29 Sep 2026 12:34:38 +0800

- **First Seen:** Tue, 29 Sep 2026 12:34:38 +0800
- **Last Seen:** Tue, 29 Sep 2026 13:06:22 +0800
- **Last Seen Age:** 2.52 hours
- **Mention Count:** 2
- **Momentum:** current=2, previous=2, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本 candidate 的 source 集群中混入了另一条 Google / EU AI 监管报道。编辑判断时需注意：本中文标题仅反映 headline （AI 鳄鱼图像事件），不涵盖 source 集群中另一条 Google 新闻；如要涵盖 source 集群中所有内容，须另写。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


## Sample 20

- **Candidate ID:** `cand_b9d84ef52022e9ec12b52ce2`
- **Category:** WORLD
- **State:** READY_FOR_REVIEW
- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

### 中文理解标题

> 在 BTS 与 Blackpink 之前，曾有 Big Bang：如今K-pop 王者回归

### 中文事件摘要

据相关报道，BBC 一篇特稿回顾 K-pop 团体 Big Bang 的回归——在 BTS 与 Blackpink 之前，Big Bang 曾是 K-pop 代表团体之一。Radar 标记 verification_status=REPORTED、来源为 BBC News Asia（英国，Tier-B）。

### Original Source

- **Headline language:** English
- **Original headline (verbatim, unchanged):**

> Before BTS and Blackpink, there was Big Bang: Now the Kings of K-pop are back

- **Source count:** 1
- **Sources:**
  - `BBC News Asia` [tier=B, country=GB, type=RSS]
    - URL: https://www.bbc.co.uk/news/articles/cq39me84zrkdo?at_medium=RSS&at_campaign=rss
    - Source Title (English): Before BTS and Blackpink, there was Big Bang: Now the Kings of K-pop are back
    - Published At: Sun, 27 Sep 2026 08:51:23 GMT

- **First Seen:** Sun, 27 Sep 2026 08:51:23 GMT
- **Last Seen:** Sun, 27 Sep 2026 08:51:23 GMT
- **Last Seen Age:** 46.77 hours
- **Mention Count:** 1
- **Momentum:** current=1, previous=1, growth=0
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True
- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

### Editor Notes (informational only, not a judgement)

本条属娱乐 / 文化类报道，编辑判断时需考虑：是否适合在 MY Hot Radar 的现有版位中呈现（当前 Radar source registry 暂无娱乐类来源，本 candidate 属于 BORROWING WORLD source 标签下的英国 BBC）。

### Editorial Decision (MANUAL ONLY — system does not auto-fill)

- [ ] **A — 值得发展成 MY Hot Radar 文章**
- [ ] **B — 值得继续观察**
- [ ] **C — 目前不值得发展成文章**
- **Editor Reason:** _____________________________________________

---


---

## 3. 审核辅助层属性 / Audit Properties

- **只读 (Read-only):** 本报告读取 `radar_data/candidates/latest.json`，不写入、不修改任何 candidate 文件。
- **忠实翻译 (Faithful translation):** 中文标题与摘要为人工撰写 (hand-authored)，不是 LLM 实时翻译。
- **不自动判断 (No auto-judgement):** 系统不会自动填入 A / B / C。三个选项必须由人工编辑填写。
- **政治中立 (Political neutrality):** 政治类候选使用「据相关报道」、「某方表示」、「有消息称」等中立措辞，不评价任何政党或政治人物，不预测选举结果。
- **不升级 verification (No verification upgrade):** 原文verification_status=REPORTED 的候选，中文摘要不会改写为「已确认」事实。
- **保留原始标题 (Original headline preserved):** 中文理解标题之外，原始 headline 完整保留（verbatim, unchanged）。
- **可复现 (Reproducible):** 同一 candidate store + sample_size 永远产生相同的样本。
- **固定 20 候选 (Pinned 20 candidates):** 本审核版的样本是 `PINNED_SAMPLE_IDS` 锁定的 20 个 ID，与每次live stride-pick 解耦，确保 20 条人工中文翻译始终与同一组候选配对。

