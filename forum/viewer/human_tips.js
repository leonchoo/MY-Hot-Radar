// MY Hot Radar Forum Newsroom Viewer — Human Tips page
// READ-ONLY: never modifies Forum data.

const TIP_STATUS_LABEL = {
  OPEN: "OPEN",
  ACKNOWLEDGED: "已接手",
  INVESTIGATING: "调查中",
  LINKED: "已关联 Topic",
  RESOLVED: "已关闭",
};

const TIP_PRIORITY_LABEL = {
  LOW: "低",
  MEDIUM: "中",
  HIGH: "高",
  URGENT: "紧急",
};

const TIP_RESOLUTION_LABEL = {
  NO_NEWS_VALUE: "无新闻价值",
  ALREADY_COVERED: "已存在覆盖",
  PUBLISHED: "已发布",
  TOPIC_CLOSED: "Topic 已关闭",
  MERGED: "已合并",
  REACTIVATED: "触发重新升温",
  PENDING: "暂未决定",
};

const state = {
  tips: [],
  filterStatus: "ALL",
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

function utcToMyt(utc) {
  if (!utc) return "";
  // Parse UTC ISO timestamp and convert to UTC+8
  const m = utc.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
  if (!m) return utc;
  const [, y, mo, d, h, mi, s] = m.map(Number);
  // UTC + 8 hours
  let hh = h + 8;
  let dd = d;
  if (hh >= 24) { hh -= 24; dd += 1; }
  // Pad
  const pad = n => String(n).padStart(2, "0");
  return `${y}-${pad(mo)}-${pad(dd)} ${pad(hh)}:${pad(mi)}:${pad(s)} MYT`;
}

function buildStats() {
  const stats = document.getElementById("stats");
  stats.innerHTML = "";
  const byStatus = {};
  for (const t of state.tips) {
    byStatus[t.status] = (byStatus[t.status] || 0) + 1;
  }
  const total = state.tips.length;
  const totalDiv = document.createElement("div");
  totalDiv.className = "stat";
  totalDiv.innerHTML = `<div class="stat-num">${total}</div>
    <div class="stat-label">总线索</div>`;
  stats.appendChild(totalDiv);
  for (const status of ["OPEN", "ACKNOWLEDGED", "INVESTIGATING", "LINKED", "RESOLVED"]) {
    const div = document.createElement("div");
    div.className = `stat status-${status.toLowerCase()}`;
    div.style.borderLeftColor = ({
      OPEN: "#dc2626",
      ACKNOWLEDGED: "#f59e0b",
      INVESTIGATING: "#ea580c",
      LINKED: "#16a34a",
      RESOLVED: "#6b7280",
    })[status] || "#94a3b8";
    div.innerHTML = `<div class="stat-num">${byStatus[status] || 0}</div>
      <div class="stat-label">${TIP_STATUS_LABEL[status]}</div>`;
    stats.appendChild(div);
  }
}

function renderTips() {
  const list = document.getElementById("tip-list");
  const filtered = state.tips.filter(t => {
    if (state.filterStatus !== "ALL" && t.status !== state.filterStatus) return false;
    return true;
  });
  if (filtered.length === 0) {
    list.innerHTML = '<div class="empty-tip">无符合条件的人工线索</div>';
    return;
  }
  list.innerHTML = filtered.map(t => tipCardHtml(t)).join("");
}

function tipCardHtml(t) {
  const priority = t.priority || "MEDIUM";
  const status = t.status || "OPEN";
  const isResolved = status === "RESOLVED";
  const myt = utcToMyt(t.created_at);

  const evidenceItems = [];
  if (t.source_url) {
    evidenceItems.push(`<a href="${escapeHtml(t.source_url)}" target="_blank" rel="noopener noreferrer">原始来源 ↗</a>`);
  }
  for (const ev of (t.evidence_urls || [])) {
    evidenceItems.push(`<a href="${escapeHtml(ev)}" target="_blank" rel="noopener noreferrer">${escapeHtml(ev.length > 50 ? ev.slice(0, 47) + "..." : ev)} ↗</a>`);
  }

  const timelineEvents = (t._events || []);
  const timelineHtml = timelineEvents.map(e => {
    const agentLabel = ({
      hermes: "彪哥",
      radar: "Radar",
      default: "Default",
      mhr_performance: "Performance",
      collector: "Collector",
    })[e.agent] || e.agent;
    const evtLabel = ({
      CREATE_TIP: "创建",
      ACK_TIP: "接手",
      INVESTIGATE_TIP: "调查",
      LINK_TIP: "关联",
      RESOLVE_TIP: "关闭",
      TIP_REPORT: "传播报告",
    })[e.event_type] || e.event_type;
    const note = (e.payload || {}).note || (e.payload || {}).description || "";
    return `<div class="timeline-event">
      <span class="ts">${escapeHtml(utcToMyt(e.timestamp))}</span>
      <span class="agent-name">${escapeHtml(agentLabel)}</span>
      <span class="evt-type">${escapeHtml(evtLabel)}</span>
      <span class="evt-note">${escapeHtml(note)}</span>
    </div>`;
  }).join("");

  return `
    <div class="tip-card priority-${priority} ${isResolved ? 'resolved' : ''}">
      <div class="tip-header">
        <h3 class="tip-title">📝 ${escapeHtml(t.title)}</h3>
        <div style="display: flex; gap: 6px;">
          <span class="tip-priority ${priority}">${escapeHtml(TIP_PRIORITY_LABEL[priority])} ${escapeHtml(priority)}</span>
          <span class="tip-status ${status}">${escapeHtml(TIP_STATUS_LABEL[status])}</span>
        </div>
      </div>
      ${t.description ? `<div class="tip-description">${escapeHtml(t.description)}</div>` : ""}
      <div class="tip-meta">
        <span>👤 ${escapeHtml(t.author || "hermes")}</span>
        <span>🕒 ${escapeHtml(myt)}</span>
        ${t.target_agent ? `<span>🎯 ${escapeHtml(t.target_agent)}</span>` : ""}
        ${t.topic_id ? `<span>📂 <a href="/topic.html?id=${encodeURIComponent(t.topic_id)}">Topic ${escapeHtml(t.topic_id)}</a></span>` : ""}
        ${t.resolution ? `<span>📋 ${escapeHtml(TIP_RESOLUTION_LABEL[t.resolution] || t.resolution)}</span>` : ""}
        ${t.tags && t.tags.length ? `<span>🏷️ ${t.tags.map(escapeHtml).join(", ")}</span>` : ""}
      </div>
      ${evidenceItems.length ? `<div class="tip-evidence">📎 ${evidenceItems.join(" · ")}</div>` : ""}
      ${timelineHtml ? `<div class="tip-timeline">${timelineHtml}</div>` : ""}
      ${t.resolution_note ? `<div class="tip-description" style="font-style: italic; color: #6b7280;">处理说明：${escapeHtml(t.resolution_note)}</div>` : ""}
    </div>
  `;
}

async function loadTips() {
  const res = await fetch("/api/human_tips");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  state.tips = data.tips || [];
  buildStats();
  renderTips();
}

(async () => {
  document.querySelectorAll(".filter-chip").forEach(chip => {
    chip.onclick = () => {
      document.querySelectorAll(".filter-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      state.filterStatus = chip.dataset.status;
      renderTips();
    };
  });
  try {
    await loadTips();
  } catch (e) {
    document.getElementById("tip-list").innerHTML =
      `<div class="empty-tip">加载失败: ${escapeHtml(e.message)}</div>`;
  }
})();