// MY Hot Radar Forum Newsroom Viewer — index page logic
// READ-ONLY: never modifies Forum data.

const CLASS_LABEL = {
  BREAKING: "突发",
  RISING: "上升",
  HOT: "热门",
  COOLING: "降温",
  WATCH: "关注",
};

const STATUS_LABEL = {
  NEW: "新发现",
  RADAR_TRACKING: "Radar 跟踪中",
  EDITORIAL_REVIEW: "编辑审核",
  PUBLISHED: "已发布",
  MONITORING: "持续监测",
  FOLLOW_UP: "后续跟进",
  REACTIVATED: "重新升温",
  CLOSED: "已关闭",
};

const state = {
  topics: [],
  filterClassification: "ALL",
  filterStatus: "ALL",
  labels: null,
};

function escapeHtml(s) {
  if (s === undefined || s === null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatTimestamp(iso) {
  // Phase 8A — delegate to shared MYT formatter. Do NOT strip "Z" or
  // do "+8 hours" arithmetic here — that was the bug that caused
  // "07:15:40" to display instead of "15:15:40 MYT".
  return MYT_FORMAT.formatMyt(iso);
}

function buildStats() {
  const stats = document.getElementById("stats");
  stats.innerHTML = "";
  const byClass = {};
  for (const t of state.topics) {
    const c = t.classification || "UNKNOWN";
    byClass[c] = (byClass[c] || 0) + 1;
  }
  for (const k of ["BREAKING", "RISING", "HOT", "COOLING", "WATCH"]) {
    const div = document.createElement("div");
    div.className = `stat ${k.toLowerCase()}`;
    div.innerHTML = `
      <div class="stat-num">${byClass[k] || 0}</div>
      <div class="stat-label">${CLASS_LABEL[k]} ${escapeHtml(k)}</div>
    `;
    stats.appendChild(div);
  }
}

function buildFilterChips() {
  const classEl = document.getElementById("classification-filters");
  for (const [key, label] of Object.entries(CLASS_LABEL)) {
    const chip = document.createElement("span");
    chip.className = "filter-chip";
    chip.dataset.classification = key;
    chip.innerHTML = `${label}<span class="machine">${key}</span>`;
    chip.onclick = () => {
      document.querySelectorAll("#classification-filters .filter-chip")
        .forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      state.filterClassification = key;
      renderTopics();
    };
    classEl.appendChild(chip);
  }

  const statusEl = document.getElementById("status-filters");
  for (const [key, label] of Object.entries(STATUS_LABEL)) {
    const chip = document.createElement("span");
    chip.className = "filter-chip";
    chip.dataset.status = key;
    chip.innerHTML = `${label}<span class="machine">${key}</span>`;
    chip.onclick = () => {
      document.querySelectorAll("#status-filters .filter-chip")
        .forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      state.filterStatus = key;
      renderTopics();
    };
    statusEl.appendChild(chip);
  }
}

function renderTopics() {
  const list = document.getElementById("topic-list");
  const filtered = state.topics.filter(t => {
    if (state.filterClassification !== "ALL" && t.classification !== state.filterClassification) return false;
    if (state.filterStatus !== "ALL" && t.status !== state.filterStatus) return false;
    return true;
  });
  if (filtered.length === 0) {
    list.innerHTML = '<div class="empty">无符合条件的 Topic</div>';
    return;
  }
  list.innerHTML = filtered.map(t => topicCardHtml(t)).join("");
}

function topicCardHtml(t) {
  const titlePrimary = (t.title_rendered && t.title_rendered.primary) || t.title || "未命名";
  const titleSecondary = t.title_rendered && t.title_rendered.secondary;
  const cls = (t.classification || "watch").toLowerCase();
  const status = t.status || "NEW";
  const participants = (t.participants || []).join(" · ");
  const langs = (t.languages || []).join(" / ") || "—";
  const sources = t.source_count || 0;
  const lastSeen = formatTimestamp(t.last_seen);

  return `
    <a class="topic-card ${cls}" href="/topic.html?id=${encodeURIComponent(t.topic_id)}">
      <h2>${escapeHtml(titlePrimary)}</h2>
      ${titleSecondary ? `<span class="secondary-title">${escapeHtml(titleSecondary)}</span>` : ""}
      <div class="topic-meta">
        <span class="pill classification ${cls}">${escapeHtml(t.classification_label || CLASS_LABEL[t.classification] || t.classification)} <span class="machine">${escapeHtml(t.classification)}</span></span>
        <span class="pill status ${status.toLowerCase()}">${escapeHtml(t.status_label || STATUS_LABEL[status] || status)} <span class="machine">${escapeHtml(status)}</span></span>
        <span class="pill">${sources} 来源</span>
        <span class="pill">语言：${escapeHtml(langs)}</span>
        <span class="pill">最后更新：${escapeHtml(lastSeen)}</span>
        ${participants ? `<span class="pill">参与：${escapeHtml(participants)}</span>` : ""}
      </div>
    </a>
  `;
}

async function loadTopics() {
  const res = await fetch("/api/topics");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  state.topics = data.topics || [];
  buildStats();
  buildFilterChips();
  renderTopics();
}

(async () => {
  try {
    await loadTopics();
  } catch (e) {
    document.getElementById("topic-list").innerHTML =
      `<div class="empty">加载失败: ${escapeHtml(e.message)}</div>`;
  }
})();


// Phase 10.5 — Network scope + LAN URL strip
(async function() {
  try {
    const res = await fetch("/api/network");
    if (!res.ok) return;
    const net = await res.json();
    if (net.scope !== "lan") return;  // local scope — show nothing

    const strip = document.createElement("section");
    strip.className = "lan-strip";
    let html = `<div class="lan-strip-row">`;
    html += `<span class="lan-strip-label">LOCAL</span>`;
    html += `<span class="lan-strip-url"><a href="${escapeHtml(net.local_url)}">${escapeHtml(net.local_url)}</a></span>`;
    html += `</div>`;
    html += `<div class="lan-strip-row">`;
    html += `<span class="lan-strip-label">LAN</span>`;
    if (net.lan_url) {
      html += `<span class="lan-strip-url"><a href="${escapeHtml(net.lan_url)}">${escapeHtml(net.lan_url)}</a></span>`;
    } else {
      html += `<span class="lan-strip-url">(no RFC1918 IPv4 detected)</span>`;
    }
    html += `</div>`;
    if (net.lan_warning) {
      html += `<div class="lan-strip-warning">⚠ <strong>${escapeHtml(net.lan_warning)}</strong></div>`;
    }
    strip.innerHTML = html;

    // Insert before the breadcrumb
    const breadcrumb = document.querySelector(".breadcrumb");
    if (breadcrumb && breadcrumb.parentNode) {
      breadcrumb.parentNode.insertBefore(strip, breadcrumb);
    } else {
      const container = document.querySelector(".container");
      if (container) container.insertBefore(strip, container.firstChild);
    }
  } catch (e) {
    // network detection failed silently — no strip shown
  }
})();
