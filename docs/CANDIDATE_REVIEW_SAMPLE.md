# Editorial Sampling Report — Article Candidate Pipeline

- **Audit version:** phase2-b3b2-editorial-audit-v1
- **Generated at (UTC):** 2026-09-29T05:29:12Z
- **Source:** `C:\MY-Hot-Radar\radar_data\candidates\latest.json`

> Read-only audit. No candidate file is modified. No production JSON is touched. No editorial ranking is produced — this is a sampling report, not a score.

## 1. Summary

- **READY_FOR_REVIEW total:** 52
- **Sample size:** 20
- **Categories represented in sample:** ['MALAYSIA', 'WORLD']
- **Verification distribution (sample):** {'CONFIRMED': 2, 'REPORTED': 18}
- **Confidence distribution (sample):** {'HIGH': 2, 'MEDIUM': 18}
- **Source-count distribution (sample):** {4: 2, 2: 4, 1: 13, 6: 1}
- **Political flag distribution (sample):** {(True, 'CLAIM'): 4, (False, 'NOT_POLITICAL'): 15, (True, 'EVENT'): 1}

## 2. Sampling Method

Candidates are sorted by `candidate_id` (a deterministic SHA-256 prefix). Within each category bucket, a stride-pick (step = len(bucket) / n_slots) is used so the sample is reproducible and spread across the bucket. No category is fabricated: if a category has 0 READY candidates, it appears as 0 in the sample.

## 3. Per-Candidate Detail

### Candidate #1

- **Candidate ID:** `cand_0291d8fe5d13bd7232a8dd38`
- **Content Key:** `u:https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/ismail-tak-perlu-letak-jawatan-walaupun-tersilap-langkah-kata-penganalisis`
- **Headline:** Peletakan jawatan berkuat kuasa sebaik Najib jalani tahanan rumah, kata Loke
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** CONFIRMED
- **Confidence Label:** HIGH

- **Source Count:** 4
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/ismail-tak-perlu-letak-jawatan-walaupun-tersilap-langkah-kata-penganalisis (url_safe=True)
    - Source Title: Ismail tak perlu letak jawatan walau tersilap langkah, kata penganalisis
    - Published At: Tue, 29 Sep 2026 04:45:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/peletakan-jawatan-berkuat-kuasa-sebaik-najib-jalani-tahanan-rumah-kata-loke (url_safe=True)
    - Source Title: Peletakan jawatan berkuat kuasa sebaik Najib jalani tahanan rumah, kata Loke
    - Published At: Tue, 29 Sep 2026 04:30:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/saya-tak-tahu-kenapa-saksi-pinda-kenyataan-kata-pegawai-penyiasat (url_safe=True)
    - Source Title: Saya tak tahu kenapa saksi pinda kenyataan, kata pegawai penyiasat
    - Published At: Mon, 28 Sep 2026 10:34:00 +0000
  - `Borneo Post` [tier=B, type=RSS, country=MY]
    - URL: https://www.theborneopost.com/2026/09/29/loke-says-will-stay-as-transport-minister-until-najib-house-arrest-begins/ (url_safe=True)
    - Source Title: Loke says will stay as transport minister until Najib house arrest begins
    - Published At: Tue, 29 Sep 2026 04:49:20 +0000

- **First Seen:** Mon, 28 Sep 2026 10:34:00 +0000
- **Last Seen:** Tue, 29 Sep 2026 04:49:20 +0000
- **Last Seen Age:** 0.66 hours
- **Mention Count:** 4

- **Momentum:** current=4, previous=4, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** CLAIM
- **Political:** is_political=True, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, confirmed_evidence, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #2

- **Candidate ID:** `cand_24034fa2cdf3d35f24bc8815`
- **Content Key:** `u:https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/bekas-ceo-fic-didakwa-perdaya-lembaga-pengarah-berkait-projek-jalan-semarak`
- **Headline:** Bekas CEO FIC didakwa perdaya lembaga pengarah berkait projek Jalan Semarak
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 2
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/bekas-ceo-fic-didakwa-perdaya-lembaga-pengarah-berkait-projek-jalan-semarak (url_safe=True)
    - Source Title: Bekas CEO FIC didakwa perdaya lembaga pengarah berkait projek Jalan Semarak
    - Published At: Tue, 29 Sep 2026 01:38:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/bekas-ceo-fic-dituduh-esok-berkait-kes-klvc (url_safe=True)
    - Source Title: Bekas CEO FIC dituduh esok berkait kes KLVC
    - Published At: Mon, 28 Sep 2026 15:08:36 +0000

- **First Seen:** Mon, 28 Sep 2026 15:08:36 +0000
- **Last Seen:** Tue, 29 Sep 2026 01:38:00 +0000
- **Last Seen Age:** 3.85 hours
- **Mention Count:** 2

- **Momentum:** current=2, previous=2, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #3

- **Candidate ID:** `cand_372c6455e8d1559dacf1147f`
- **Content Key:** `u:https://www.theborneopost.com/2026/09/29/mou-out-to-open-opportunities-for-neurodivergent-underprivileged-kids-through-music/`
- **Headline:** MoU out to open opportunities for neurodivergent, underprivileged kids through music
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `Borneo Post` [tier=B, type=RSS, country=MY]
    - URL: https://www.theborneopost.com/2026/09/29/mou-out-to-open-opportunities-for-neurodivergent-underprivileged-kids-through-music/ (url_safe=True)
    - Source Title: MoU out to open opportunities for neurodivergent, underprivileged kids through music
    - Published At: Tue, 29 Sep 2026 00:01:25 +0000

- **First Seen:** Tue, 29 Sep 2026 00:01:25 +0000
- **Last Seen:** Tue, 29 Sep 2026 00:01:25 +0000
- **Last Seen Age:** 5.46 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** CLAIM
- **Political:** is_political=True, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #4

- **Candidate ID:** `cand_4a46b36aa26f8da6c4dca778`
- **Content Key:** `u:https://www.theborneopost.com/2026/09/29/eight-sarawak-areas-record-unhealthy-api-at-noon-as-kanowit-joins-list/`
- **Headline:** Air quality worsens in Sarawak as 7 stations record ‘Unhealthy’ API readings
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 2
- **Sources:**
  - `Borneo Post` [tier=B, type=RSS, country=MY]
    - URL: https://www.theborneopost.com/2026/09/29/eight-sarawak-areas-record-unhealthy-api-at-noon-as-kanowit-joins-list/ (url_safe=True)
    - Source Title: Eight Sarawak areas record ‘Unhealthy’ API at noon as Kanowit joins list
    - Published At: Tue, 29 Sep 2026 04:44:43 +0000
  - `Borneo Post` [tier=B, type=RSS, country=MY]
    - URL: https://www.theborneopost.com/2026/09/29/air-quality-worsens-in-sarawak-as-7-stations-record-unhealthy-api-readings/ (url_safe=True)
    - Source Title: Air quality worsens in Sarawak as 7 stations record ‘Unhealthy’ API readings
    - Published At: Tue, 29 Sep 2026 01:39:39 +0000

- **First Seen:** Tue, 29 Sep 2026 01:39:39 +0000
- **Last Seen:** Tue, 29 Sep 2026 04:44:43 +0000
- **Last Seen Age:** 0.74 hours
- **Mention Count:** 2

- **Momentum:** current=2, previous=2, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #5

- **Candidate ID:** `cand_6c0a2c3f9bd52b09785a7789`
- **Content Key:** `u:https://www.theborneopost.com/2026/09/29/sarawak-seeks-additional-spectrum-to-ease-network-congestion/`
- **Headline:** Sarawak seeks additional spectrum to ease network congestion
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `Borneo Post` [tier=B, type=RSS, country=MY]
    - URL: https://www.theborneopost.com/2026/09/29/sarawak-seeks-additional-spectrum-to-ease-network-congestion/ (url_safe=True)
    - Source Title: Sarawak seeks additional spectrum to ease network congestion
    - Published At: Tue, 29 Sep 2026 04:20:13 +0000

- **First Seen:** Tue, 29 Sep 2026 04:20:13 +0000
- **Last Seen:** Tue, 29 Sep 2026 04:20:13 +0000
- **Last Seen Age:** 1.15 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** CLAIM
- **Political:** is_political=True, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #6

- **Candidate ID:** `cand_9a79c7e76e7ec55c47800523`
- **Content Key:** `u:https://codeblue.galencentre.org/2026/09/concern-regarding-delayed-promotion-of-medical-officers-anonymous-medical-officer/`
- **Headline:** Concern Regarding Delayed Promotion Of Medical Officers
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `CodeBlue` [tier=B, type=RSS, country=MY]
    - URL: https://codeblue.galencentre.org/2026/09/concern-regarding-delayed-promotion-of-medical-officers-anonymous-medical-officer/ (url_safe=True)
    - Source Title: Concern Regarding Delayed Promotion Of Medical Officers
    - Published At: Tue, 29 Sep 2026 02:00:00 +0000

- **First Seen:** Tue, 29 Sep 2026 02:00:00 +0000
- **Last Seen:** Tue, 29 Sep 2026 02:00:00 +0000
- **Last Seen Age:** 3.49 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #7

- **Candidate ID:** `cand_afe4bd3302659eb99be0cc11`
- **Content Key:** `u:https://www.freemalaysiatoday.com/category/bahasa/pandangan/2026/09/29/mengapa-perpecahan-multikoalisi-mutlak-berlaku-dalam-pru16`
- **Headline:** Mengapa perpecahan multikoalisi mutlak berlaku dalam PRU16
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/pandangan/2026/09/29/mengapa-perpecahan-multikoalisi-mutlak-berlaku-dalam-pru16 (url_safe=True)
    - Source Title: Mengapa perpecahan multikoalisi mutlak berlaku dalam PRU16
    - Published At: Tue, 29 Sep 2026 01:00:00 +0000

- **First Seen:** Tue, 29 Sep 2026 01:00:00 +0000
- **Last Seen:** Tue, 29 Sep 2026 01:00:00 +0000
- **Last Seen Age:** 4.49 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** EVENT
- **Political:** is_political=True, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #8

- **Candidate ID:** `cand_bd9ccd3f4b764142ad7da6bd`
- **Content Key:** `u:https://www.theborneopost.com/2026/09/29/dr-sim-cancer-care-framework-must-consider-states-rural-remote-communities/`
- **Headline:** Dr Sim: Cancer care framework must consider state’s rural, remote communities
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `Borneo Post` [tier=B, type=RSS, country=MY]
    - URL: https://www.theborneopost.com/2026/09/29/dr-sim-cancer-care-framework-must-consider-states-rural-remote-communities/ (url_safe=True)
    - Source Title: Dr Sim: Cancer care framework must consider state’s rural, remote communities
    - Published At: Tue, 29 Sep 2026 00:00:06 +0000

- **First Seen:** Tue, 29 Sep 2026 00:00:06 +0000
- **Last Seen:** Tue, 29 Sep 2026 00:00:06 +0000
- **Last Seen Age:** 5.49 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #9

- **Candidate ID:** `cand_da5a22acbeb546e8556e365f`
- **Content Key:** `u:https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/penduduk-taman-sri-muda-menang-saman-kerajaan-berkait-banjir-2021`
- **Headline:** Penduduk Taman Sri Muda menang saman kerajaan berkait banjir 2021
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/penduduk-taman-sri-muda-menang-saman-kerajaan-berkait-banjir-2021 (url_safe=True)
    - Source Title: Penduduk Taman Sri Muda menang saman kerajaan berkait banjir 2021
    - Published At: Tue, 29 Sep 2026 04:18:25 +0000

- **First Seen:** Tue, 29 Sep 2026 04:18:25 +0000
- **Last Seen:** Tue, 29 Sep 2026 04:18:25 +0000
- **Last Seen Age:** 1.18 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** CLAIM
- **Political:** is_political=True, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #10

- **Candidate ID:** `cand_e3c6eb1fb4dd754179d5f29f`
- **Content Key:** `u:https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/sebelum-malaysia-mengenali-mahathir-dan-hasmah`
- **Headline:** Sultan Pahang, Tengku Ampuan beri penghormatan terakhir buat Hasmah
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 6
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/sebelum-malaysia-mengenali-mahathir-dan-hasmah (url_safe=True)
    - Source Title: Sebelum Malaysia mengenali Mahathir dan Hasmah
    - Published At: Tue, 29 Sep 2026 00:30:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/sentuhan-keibuan-hasmah-buat-badminton-malaysia (url_safe=True)
    - Source Title: Sentuhan keibuan Hasmah buat badminton Malaysia
    - Published At: Mon, 28 Sep 2026 23:30:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/hasmah-ceria-sehari-sebelum-meninggal-dunia-kata-mokhzani (url_safe=True)
    - Source Title: Hasmah ceria sehari sebelum meninggal dunia, kata Mokhzani
    - Published At: Mon, 28 Sep 2026 13:15:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/radio-tv-diarah-ubah-program-tanda-penghormatan-buat-hasmah (url_safe=True)
    - Source Title: Radio, TV diarah ubah program tanda penghormatan buat Hasmah
    - Published At: Mon, 28 Sep 2026 07:45:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/sultan-pahang-tengku-ampuan-beri-penghormatan-terakhir-buat-hasmah (url_safe=True)
    - Source Title: Sultan Pahang, Tengku Ampuan beri penghormatan terakhir buat Hasmah
    - Published At: Mon, 28 Sep 2026 06:46:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/tokoh-kenamaan-beri-penghormatan-terakhir-buat-hasmah (url_safe=True)
    - Source Title: Tokoh kenamaan beri penghormatan terakhir buat Hasmah
    - Published At: Mon, 28 Sep 2026 06:05:00 +0000

- **First Seen:** Mon, 28 Sep 2026 06:05:00 +0000
- **Last Seen:** Tue, 29 Sep 2026 00:30:00 +0000
- **Last Seen Age:** 4.99 hours
- **Mention Count:** 6

- **Momentum:** current=6, previous=6, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #11

- **Candidate ID:** `cand_f8a6ac609d8e40c6ac9865bd`
- **Content Key:** `u:https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/belum-ada-perbincangan-rasmi-ph-bersatu-kata-fahmi`
- **Headline:** Pemimpin PH, Bersatu makan malam bersama di tengah spekulasi rundingan PRN Melaka
- **Category:** MALAYSIA

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 4
- **Sources:**
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/belum-ada-perbincangan-rasmi-ph-bersatu-kata-fahmi (url_safe=True)
    - Source Title: Belum ada perbincangan rasmi PH-Bersatu, kata Fahmi
    - Published At: Tue, 29 Sep 2026 02:46:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/opinion/2026/09/29/bukan-pas-atau-ph-umno-ada-kekuatan-sendiri-atau-tidak (url_safe=True)
    - Source Title: Bukan PAS atau PH, Umno ada kekuatan sendiri atau tidak?
    - Published At: Tue, 29 Sep 2026 00:00:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/pemimpin-ph-bersatu-makan-malam-bersama-di-tengah-spekulasi-rundingan-prn-melaka (url_safe=True)
    - Source Title: Pemimpin PH, Bersatu makan malam bersama di tengah spekulasi rundingan PRN Melaka
    - Published At: Mon, 28 Sep 2026 15:53:00 +0000
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/28/ph-p-pinang-tangguh-mesyuarat-bincang-kedudukan-umno (url_safe=True)
    - Source Title: PH P Pinang tangguh mesyuarat bincang kedudukan Umno
    - Published At: Mon, 28 Sep 2026 09:32:00 +0000

- **First Seen:** Mon, 28 Sep 2026 09:32:00 +0000
- **Last Seen:** Tue, 29 Sep 2026 02:46:00 +0000
- **Last Seen Age:** 2.72 hours
- **Mention Count:** 4

- **Momentum:** current=4, previous=4, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #12

- **Candidate ID:** `cand_004b328404b99afc338208bc`
- **Content Key:** `u:https://www.bbc.co.uk/news/articles/cmj4jg2vxvpdo?at_medium=RSS&at_campaign=rss`
- **Headline:** Sign before praying: A new conversion law is affecting churchgoers in Indian state
- **Category:** WORLD

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `BBC News Asia` [tier=B, type=RSS, country=GB]
    - URL: https://www.bbc.co.uk/news/articles/cmj4jg2vxvpdo?at_medium=RSS&at_campaign=rss (url_safe=True)
    - Source Title: Sign before praying: A new conversion law is affecting churchgoers in Indian state
    - Published At: Tue, 29 Sep 2026 00:50:19 GMT

- **First Seen:** Tue, 29 Sep 2026 00:50:19 GMT
- **Last Seen:** Tue, 29 Sep 2026 00:50:19 GMT
- **Last Seen Age:** 4.65 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #13

- **Candidate ID:** `cand_0ff87c74934633cf2fa5279a`
- **Content Key:** `u:https://www.bbc.co.uk/news/articles/cw980vje6l3eo?at_medium=RSS&at_campaign=rss`
- **Headline:** Why some Indian civil servants become heroes for doing their jobs
- **Category:** WORLD

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `BBC News Asia` [tier=B, type=RSS, country=GB]
    - URL: https://www.bbc.co.uk/news/articles/cw980vje6l3eo?at_medium=RSS&at_campaign=rss (url_safe=True)
    - Source Title: Why some Indian civil servants become heroes for doing their jobs
    - Published At: Sun, 27 Sep 2026 23:01:37 GMT

- **First Seen:** Sun, 27 Sep 2026 23:01:37 GMT
- **Last Seen:** Sun, 27 Sep 2026 23:01:37 GMT
- **Last Seen Age:** 30.46 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #14

- **Candidate ID:** `cand_2813b65d572c0146f8f3ab5c`
- **Content Key:** `u:https://www.channelnewsasia.com/business/tata-stocks-slip-after-trusts-propose-move-prevent-holding-company-listing-6417496`
- **Headline:** Tata stocks slip after Trusts propose move to prevent holding company listing
- **Category:** WORLD

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, type=RSS, country=SG]
    - URL: https://www.channelnewsasia.com/business/tata-stocks-slip-after-trusts-propose-move-prevent-holding-company-listing-6417496 (url_safe=True)
    - Source Title: Tata stocks slip after Trusts propose move to prevent holding company listing
    - Published At: Tue, 29 Sep 2026 12:27:48 +0800

- **First Seen:** Tue, 29 Sep 2026 12:27:48 +0800
- **Last Seen:** Tue, 29 Sep 2026 12:27:48 +0800
- **Last Seen Age:** 1.02 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #15

- **Candidate ID:** `cand_3ff7d48665fc8b7686376413`
- **Content Key:** `u:https://www.channelnewsasia.com/asia/malaysia-myanmar-rohingya-refugees-repatriation-6417266`
- **Headline:** Malaysia starts sending Myanmar migrants home
- **Category:** WORLD

- **Radar Status:** WATCH
- **Verification Status:** CONFIRMED
- **Confidence Label:** HIGH

- **Source Count:** 2
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, type=RSS, country=SG]
    - URL: https://www.channelnewsasia.com/asia/malaysia-myanmar-rohingya-refugees-repatriation-6417266 (url_safe=True)
    - Source Title: Malaysia starts sending Myanmar migrants home
    - Published At: Tue, 29 Sep 2026 10:48:33 +0800
  - `Free Malaysia Today (Bahasa)` [tier=B, type=RSS, country=MY]
    - URL: https://www.freemalaysiatoday.com/category/bahasa/tempatan/2026/09/29/malaysia-mula-hantar-pulang-pelarian-myanmar (url_safe=True)
    - Source Title: Malaysia mula hantar pulang pelarian Myanmar
    - Published At: Tue, 29 Sep 2026 01:24:13 +0000

- **First Seen:** Tue, 29 Sep 2026 01:24:13 +0000
- **Last Seen:** Tue, 29 Sep 2026 10:48:33 +0800
- **Last Seen Age:** 2.68 hours
- **Mention Count:** 2

- **Momentum:** current=2, previous=2, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, confirmed_evidence, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #16

- **Candidate ID:** `cand_7a444c025f7799935aed43ac`
- **Content Key:** `u:https://www.channelnewsasia.com/business/south-korean-exports-seen-rising-16th-month-solid-ai-chip-demand-reuters-poll-6417096`
- **Headline:** South Korean exports seen rising for 16th month on solid AI chip demand: Reuters poll
- **Category:** WORLD

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, type=RSS, country=SG]
    - URL: https://www.channelnewsasia.com/business/south-korean-exports-seen-rising-16th-month-solid-ai-chip-demand-reuters-poll-6417096 (url_safe=True)
    - Source Title: South Korean exports seen rising for 16th month on solid AI chip demand: Reuters poll
    - Published At: Tue, 29 Sep 2026 09:08:01 +0800

- **First Seen:** Tue, 29 Sep 2026 09:08:01 +0800
- **Last Seen:** Tue, 29 Sep 2026 09:08:01 +0800
- **Last Seen Age:** 4.35 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #17

- **Candidate ID:** `cand_80941ad52fc379b56018af45`
- **Content Key:** `u:https://www.channelnewsasia.com/business/shares-fast-fashion-platform-shein-fall-6-after-quarterly-profit-slides-67-6417151`
- **Headline:** Shares of fast-fashion platform Shein fall 6% after quarterly profit slides 67%
- **Category:** WORLD

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, type=RSS, country=SG]
    - URL: https://www.channelnewsasia.com/business/shares-fast-fashion-platform-shein-fall-6-after-quarterly-profit-slides-67-6417151 (url_safe=True)
    - Source Title: Shares of fast-fashion platform Shein fall 6% after quarterly profit slides 67%
    - Published At: Tue, 29 Sep 2026 09:46:09 +0800

- **First Seen:** Tue, 29 Sep 2026 09:46:09 +0800
- **Last Seen:** Tue, 29 Sep 2026 09:46:09 +0800
- **Last Seen Age:** 3.72 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #18

- **Candidate ID:** `cand_9320c8d872e52efae142d74d`
- **Content Key:** `u:https://www.channelnewsasia.com/business/stocks-drop-and-oil-rises-hormuz-hopes-fade-6417441`
- **Headline:** Stocks drop and oil rises as Hormuz hopes fade
- **Category:** WORLD

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, type=RSS, country=SG]
    - URL: https://www.channelnewsasia.com/business/stocks-drop-and-oil-rises-hormuz-hopes-fade-6417441 (url_safe=True)
    - Source Title: Stocks drop and oil rises as Hormuz hopes fade
    - Published At: Tue, 29 Sep 2026 12:12:58 +0800

- **First Seen:** Tue, 29 Sep 2026 12:12:58 +0800
- **Last Seen:** Tue, 29 Sep 2026 12:12:58 +0800
- **Last Seen Age:** 1.27 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #19

- **Candidate ID:** `cand_a96fa2bdb36199a9c1527114`
- **Content Key:** `u:https://www.channelnewsasia.com/business/google-challenges-eu-orders-open-up-ai-search-engine-rivals-6417651`
- **Headline:** Man charged over AI-generated image of crocodile that led to search operations at Pandan Reservoir
- **Category:** WORLD

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 2
- **Sources:**
  - `Channel News Asia (Asia section)` [tier=B, type=RSS, country=SG]
    - URL: https://www.channelnewsasia.com/business/google-challenges-eu-orders-open-up-ai-search-engine-rivals-6417651 (url_safe=True)
    - Source Title: Google challenges EU orders to open up to AI, search-engine rivals
    - Published At: Tue, 29 Sep 2026 13:06:22 +0800
  - `Channel News Asia (Asia section)` [tier=B, type=RSS, country=SG]
    - URL: https://www.channelnewsasia.com/singapore/ai-generated-crocodile-image-pandan-reservoir-man-charged-6417156 (url_safe=True)
    - Source Title: Man charged over AI-generated image of crocodile that led to search operations at Pandan Reservoir
    - Published At: Tue, 29 Sep 2026 12:34:38 +0800

- **First Seen:** Tue, 29 Sep 2026 12:34:38 +0800
- **Last Seen:** Tue, 29 Sep 2026 13:06:22 +0800
- **Last Seen Age:** 0.38 hours
- **Mention Count:** 2

- **Momentum:** current=2, previous=2, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


### Candidate #20

- **Candidate ID:** `cand_b9d84ef52022e9ec12b52ce2`
- **Content Key:** `u:https://www.bbc.co.uk/news/articles/cq39me84zrkdo?at_medium=RSS&at_campaign=rss`
- **Headline:** Before BTS and Blackpink, there was Big Bang: Now the Kings of K-pop are back
- **Category:** WORLD

- **Radar Status:** WATCH
- **Verification Status:** REPORTED
- **Confidence Label:** MEDIUM

- **Source Count:** 1
- **Sources:**
  - `BBC News Asia` [tier=B, type=RSS, country=GB]
    - URL: https://www.bbc.co.uk/news/articles/cq39me84zrkdo?at_medium=RSS&at_campaign=rss (url_safe=True)
    - Source Title: Before BTS and Blackpink, there was Big Bang: Now the Kings of K-pop are back
    - Published At: Sun, 27 Sep 2026 08:51:23 GMT

- **First Seen:** Sun, 27 Sep 2026 08:51:23 GMT
- **Last Seen:** Sun, 27 Sep 2026 08:51:23 GMT
- **Last Seen Age:** 44.63 hours
- **Mention Count:** 1

- **Momentum:** current=1, previous=1, growth=0, growth_rate=0.0, is_new=False
- **Claim Kind:** NOT_POLITICAL
- **Political:** is_political=False, political_neutral=True

- **Eligibility:** eligible=True
  - Reasons: publishable, valid_title, valid_source, valid_source_url, not_rumour, not_unverified, reported_or_confirmed, no_blocking_counter_signal, politically_neutral, has_independent_sources, not_opinion
  - Blocking Reasons: (none — this is why the candidate is READY_FOR_REVIEW)

- **Editorial Review:**
  - [ ] A — Worth developing into an article
  - [ ] B — Worth monitoring
  - [ ] C — Not suitable as an article candidate
- **Reason:**
  _____________________________________________


---

## A. Eligibility Precision Observations

- 38/52 (73%) of READY candidates have exactly one source in the Radar evidence row.
- 48/52 (92%) of READY candidates carry verification_status=REPORTED (not CONFIRMED).
- No READY candidate has confidence_label LOW/MINIMAL/NONE. All 52 are MEDIUM or HIGH (48 MEDIUM, 4 HIGH).
- 4 READY candidate(s) have confidence_label=HIGH.
- Categories represented in READY pool: ['MALAYSIA', 'WORLD']. The current Radar source registry covers ['MALAYSIA', 'WORLD'] only; Viral/Celebrity/Food sections on the website have no corresponding Radar source yet (this is a source-coverage observation, not a candidate-layer rule).

## B. Category Observations

- [MALAYSIA] count=27, REPORTED=24, CONFIRMED=3, single_source=17.
- [WORLD] count=25, REPORTED=24, CONFIRMED=1, single_source=21.

## C. Freshness Observations

- last_seen ages (hours) — min=0.13, median=2.69, max=44.63, count_within_24h=50, count_within_48h=52.
- No candidate is currently within 1h of the 48h freshness boundary.

## D. Political Observations

- Political READY count: 13 (political_neutral=True in all of them per Radar).
- Political claim_kind distribution: {'CLAIM': 7, 'EVENT': 6}.
- Political verification distribution: {'CONFIRMED': 2, 'REPORTED': 11}.
- No political+OPINION candidate appears in READY — consistent with the BLOCKED political_non_neutral rule.

## E. Source Evidence Audit

- Total source rows across 52 READY candidates: 77 (avg=1.48 per candidate).
- Source tier distribution (per source row, total 77): {'B': 77}
- Source type distribution (per source row, total 77): {'RSS': 77}
- Source country distribution (per source row, total 77): {'GB': 4, 'MY': 49, 'SG': 24}


## 9. Audit Properties

- **Read-only:** This report reads `radar_data/candidates/latest.json` and `by_day/**/*.json`. It never writes back to those files.
- **No production impact:** No change to public/radar/latest.json, the website, the scheduler, or git.
- **No ranking:** No score, no winner, no top-N, no probability. Each sample row is a flat observation, intended for a human reviewer to fill in A / B / C.
- **Reproducible:** The same input file + sample_size produces the same sample every run (sort by candidate_id, stride by category).
