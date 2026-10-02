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
  // Phase 8A — delegate to shared MYT formatter (forum/viewer/format.js).
  // The previous manual +8 arithmetic produced invalid dates like
  // "2026-09-31" and "2026-12-32" because day overflow didn't roll
  // into the next month or year. The shared formatter uses
  // Intl.DateTimeFormat with Asia/Kuala_Lumpur which handles all edge
  // cases correctly. See forum/viewer/format.js for the implementation.
  return MYT_FORMAT.formatMyt(utc);
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


async function submitTip(payload) {
  // POST /api/human_tips — server handles agent="hermes" hard-coded
  const res = await fetch("/api/human_tips", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload),
  });
  let body = null;
  try {
    body = await res.json();
  } catch (e) {
    // ignore parse error; will be reported below
  }
  return { status: res.status, body };
}

function showFormSuccess(tip) {
  const successEl = document.getElementById("form-success");
  const tipId = tip.tip_id;
  const status = tip.status || "OPEN";
  const priority = tip.priority || "MEDIUM";
  const target = tip.target_agent || "radar";
  const topicId = tip.topic_id || "";
  successEl.innerHTML = `
    <strong>已提交给 Radar</strong>
    <span class="success-line">状态: <code>${escapeHtml(status)}</code></span>
    <span class="success-line">优先级: <code>${escapeHtml(priority)}</code></span>
    <span class="success-line">目标: <code>${escapeHtml(target)}</code></span>
    <span class="success-line">Tip ID: <code>${escapeHtml(tipId)}</code></span>
    ${topicId ? `<span class="success-line">Topic: <a href="/topic.html?id=${encodeURIComponent(topicId)}">${escapeHtml(topicId)}</a></span>` : ""}
  `;
  successEl.hidden = false;
}

function showFormError(message) {
  const errorEl = document.getElementById("form-error");
  errorEl.textContent = "提交失败: " + message;
  errorEl.hidden = false;
}

function hideFormMessages() {
  document.getElementById("form-error").hidden = true;
  document.getElementById("form-success").hidden = true;
}

function clearForm() {
  document.getElementById("f-title").value = "";
  document.getElementById("f-description").value = "";
  document.getElementById("f-source-url").value = "";
  document.getElementById("f-evidence").value = "";
  document.getElementById("f-tags").value = "";
  document.getElementById("f-priority").value = "MEDIUM";
  document.getElementById("f-target-agent").value = "radar";
  document.getElementById("err-title").textContent = "";
}

function toggleCreatePanel(show) {
  const panel = document.getElementById("create-panel");
  const btn = document.getElementById("b-new-tip");
  if (show === undefined) {
    show = panel.hidden;
  }
  panel.hidden = !show;
  btn.textContent = show ? "✕ 取消" : "📝 我要报料";
  if (show) {
    document.getElementById("f-title").focus();
  }
}

async function handleSubmit(event) {
  event.preventDefault();
  hideFormMessages();

  const title = document.getElementById("f-title").value.trim();
  if (!title) {
    document.getElementById("err-title").textContent = "标题必填";
    showFormError("标题不能为空");
    return;
  }
  document.getElementById("err-title").textContent = "";

  // Parse comma-separated fields
  const evidenceRaw = document.getElementById("f-evidence").value.trim();
  const evidenceUrls = evidenceRaw
    ? evidenceRaw.split(",").map(s => s.trim()).filter(Boolean)
    : [];
  const tagsRaw = document.getElementById("f-tags").value.trim();
  const tags = tagsRaw
    ? tagsRaw.split(",").map(s => s.trim()).filter(Boolean)
    : [];

  const payload = {
    title,
    description: document.getElementById("f-description").value.trim(),
    source_url: document.getElementById("f-source-url").value.trim(),
    evidence_urls: evidenceUrls,
    priority: document.getElementById("f-priority").value,
    target_agent: document.getElementById("f-target-agent").value,
    tags,
  };

  // Disable submit button while in flight
  const submitBtn = document.getElementById("b-submit-tip");
  submitBtn.disabled = true;
  submitBtn.textContent = "提交中…";

  try {
    const { status, body } = await submitTip(payload);
    if (status === 200 || status === 201) {
      showFormSuccess(body.tip || body);
      clearForm();
      // Reload tip list to show the new one
      try { await loadTips(); } catch (e) { /* ignore */ }
    } else {
      const errMsg = (body && (body.message || body.error)) || `服务器返回: ${status}`;
      showFormError(errMsg);
      if (body && body.trace) {
        console.error("Server traceback:", body.trace);
      }
    }
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "提交给 Radar";
  }
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

  // Create form handlers (Phase 8B)
  document.getElementById("b-new-tip").onclick = () => toggleCreatePanel();
  document.getElementById("b-cancel").onclick = () => {
    clearForm();
    hideFormMessages();
    toggleCreatePanel(false);
  };
  document.getElementById("tip-form").addEventListener("submit", handleSubmit);
  try {
    await loadTips();
  } catch (e) {
    document.getElementById("tip-list").innerHTML =
      `<div class="empty-tip">加载失败: ${escapeHtml(e.message)}</div>`;
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
