// MY Hot Radar Forum Newsroom Viewer — Topic Thread page
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

const AGENT_LABEL = {
  collector: "Collector",
  radar: "Radar",
  default: "MHR Default",
  mhr_performance: "MHR Performance",
};

const AGENT_COLOR = {
  collector: "#16a34a",
  radar: "#2563eb",
  default: "#9333ea",
  mhr_performance: "#ea580c",
};

const EVENT_TYPE_LABEL = {
  CREATE_TOPIC: "创建 Topic",
  OBSERVATION: "观察记录",
  SOCIAL_HEAT_SIGNAL: "社交热度信号",
  REACTIVATION_SIGNAL: "重新升温信号",
  EVIDENCE: "证据",
  SOURCE_UPDATE: "来源更新",
  TOPIC_UPDATE: "Topic 更新",
  CROSS_SOURCE_CONFIRMATION: "多来源确认",
  MOMENTUM_UPDATE: "热度变化",
  CLASSIFICATION_UPDATE: "分类变更",
  PUBLISH: "发布决定",
  UPDATE_ARTICLE: "更新文章",
  EDITORIAL_REVIEW: "编辑审核",
  FOLLOW_UP: "后续跟进",
  MONITOR: "持续监测",
  CLOSE: "关闭 Topic",
  PERFORMANCE_REPORT: "传播表现报告",
  VELOCITY_UPDATE: "速度更新",
  ENGAGEMENT_UPDATE: "互动更新",
  SUSTAINED_SIGNAL: "持续热度信号",
  COOLING_SIGNAL: "降温信号",
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

function lifecycleHtml(stages) {
  if (!stages || stages.length === 0) return "";
  const parts = stages.map((s, i) => {
    const reached = s.reached;
    const current = s.current;
    const cls = `lifecycle-stage ${reached ? "reached" : ""} ${current ? "current" : ""}`;
    const label = reached ? s.label : "";
    let arrow = "";
    if (i < stages.length - 1) {
      arrow = `<div class="lifecycle-arrow"></div>`;
    }
    return `
      <div class="${cls}">
        <div class="stage-dot"></div>
        <div class="stage-label">${escapeHtml(label)}<br><span style="font-size:9px; color:#9ca3af;">${escapeHtml(s.machine)}</span></div>
      </div>
      ${arrow}
    `;
  }).join("");
  return `
    <section class="lifecycle">
      <div class="lifecycle-title">Topic 生命周期（基于真实事件渲染）</div>
      <div class="lifecycle-track">${parts}</div>
    </section>
  `;
}

function headerHtml(topic) {
  const titlePrimary = (topic.title_rendered && topic.title_rendered.primary) || topic.title || "未命名";
  const titleSecondary = topic.title_rendered && topic.title_rendered.secondary;
  const cls = (topic.classification || "watch").toLowerCase();
  const status = topic.status || "NEW";
  const langs = (topic.languages || []).join(" / ") || "—";
  const sources = topic.source_count || 0;
  const first = formatTimestamp(topic.first_seen);
  const last = formatTimestamp(topic.last_seen);

  const participantsHtml = (topic.participants || []).map(p => {
    const label = AGENT_LABEL[p] || p;
    const color = AGENT_COLOR[p] || "#6b7280";
    return `<span class="agent-chip" style="background:${color}">${escapeHtml(label)}</span>`;
  }).join(" · ");

  return `
    <section class="thread-header ${cls}">
      <h1>${escapeHtml(titlePrimary)}</h1>
      ${titleSecondary ? `<div class="secondary-title">${escapeHtml(titleSecondary)}</div>` : ""}
      <div class="header-meta">
        <span class="pill classification ${cls}">${escapeHtml(topic.classification_label || CLASS_LABEL[topic.classification] || topic.classification)} <span class="machine">${escapeHtml(topic.classification)}</span></span>
        <span class="pill status ${status.toLowerCase()}">${escapeHtml(topic.status_label || STATUS_LABEL[status] || status)} <span class="machine">${escapeHtml(status)}</span></span>
        <span class="pill">${sources} 来源</span>
        <span class="pill">语言：${escapeHtml(langs)}</span>
        <span class="pill">首次发现：${escapeHtml(first)}</span>
        <span class="pill">最后更新：${escapeHtml(last)}</span>
      </div>
      <div class="participants-row">
        <span style="margin-right:4px;">参与 Agent：</span>
        ${participantsHtml || '<span style="color:#9ca3af;">暂无</span>'}
      </div>
    </section>
  `;
}

function eventCardHtml(e) {
  const agentClass = (e.agent || "unknown").toLowerCase();
  const agentLabel = AGENT_LABEL[e.agent] || e.agent || "Unknown";
  const agentColor = AGENT_COLOR[e.agent] || "#6b7280";
  const evtTypeLabel = EVENT_TYPE_LABEL[e.event_type] || e.event_type;
  const ts = formatTimestamp(e.timestamp);
  const isReactivation = e.is_reactivation;

  const noteRendered = e.note_rendered || { primary: "", primary_lang: null };
  const primary = noteRendered.primary || "";
  const lang = noteRendered.primary_lang;
  let primaryHtml = "";
  if (primary) {
    const langPill = lang === "zh" ? '<span class="lang-pill zh">ZH</span>' :
                      lang === "en" ? '<span class="lang-pill en">EN</span>' : "";
    const cls = lang === "zh" ? "primary zh" : (lang === "en" ? "primary en" : "primary");
    primaryHtml = `<div class="${cls}">${langPill}${escapeHtml(primary)}</div>`;
  }

  const urls = e.urls || [];
  const urlsHtml = urls.map(u => {
    const safeUrl = escapeHtml(u.url);
    const label = escapeHtml(u.label);
    return `<a class="url-link" href="${safeUrl}" target="_blank" rel="noopener noreferrer">查看 ${label} →</a>`;
  }).join("");

  const evidenceSummary = e.evidence_summary || "";
  const evidenceJson = e.evidence ? JSON.stringify(e.evidence, null, 2) : "";
  const evidenceId = "ev-" + (e.event_id || Math.random().toString(36).slice(2));
  const evidenceHtml = (evidenceJson && evidenceJson !== "{}" && evidenceJson !== "null") ? `
    <button class="evidence-toggle" onclick="document.getElementById('${evidenceId}').classList.toggle('show')">查看技术详情</button>
    <div class="evidence-detail" id="${evidenceId}">${escapeHtml(evidenceJson)}</div>
  ` : "";

  const machineFields = `
    <div class="machine-fields">
      <span>event_id: ${escapeHtml(e.event_id || "")}</span>
      <span>agent: ${escapeHtml(e.agent || "")}</span>
      <span>event_type: ${escapeHtml(e.event_type || "")}</span>
      <span>timestamp: ${escapeHtml(e.timestamp || "")}</span>
      ${e.confidence !== undefined && e.confidence !== null ? `<span>confidence: ${escapeHtml(String(e.confidence))}</span>` : ""}
    </div>
  `;

  return `
    <div class="event-card agent-${agentClass} ${isReactivation ? "reactivation" : ""}">
      <div class="event-head">
        <div class="agent-bar">
          <span class="agent-dot" style="background:${agentColor}"></span>
          <span class="agent-name">${escapeHtml(agentLabel)}</span>
          <span class="event-type">${escapeHtml(e.event_type || "")}</span>
          <span class="event-type-zh">${escapeHtml(evtTypeLabel)}</span>
          ${isReactivation ? '<span class="reactivation-badge">↻ 重新升温</span>' : ""}
        </div>
        <span class="event-time">${escapeHtml(ts)}</span>
      </div>
      <div class="event-body">
        ${primaryHtml || '<div class="primary" style="color:#9ca3af;">(无内容)</div>'}
        ${urlsHtml ? `<div class="urls">${urlsHtml}</div>` : ""}
        ${evidenceSummary ? `<div class="evidence-summary">${escapeHtml(evidenceSummary)}</div>` : ""}
        ${evidenceHtml}
        ${machineFields}
      </div>
    </div>
  `;
}

async function loadTopic() {
  const params = new URLSearchParams(location.search);
  const id = params.get("id");
  if (!id) {
    document.getElementById("thread-content").innerHTML =
      '<div class="empty">缺少 id 参数</div>';
    return;
  }
  const res = await fetch("/api/topics/" + encodeURIComponent(id));
  if (res.status === 404) {
    document.getElementById("thread-content").innerHTML =
      '<div class="empty">未找到 Topic: ' + escapeHtml(id) + '</div>';
    return;
  }
  if (!res.ok) throw new Error("HTTP " + res.status);
  const data = await res.json();
  renderTopic(data);
  document.title = data.topic.title + " · Newsroom";
}

function renderTopic(data) {
  const header = headerHtml(data.topic);
  const lifecycle = lifecycleHtml(data.lifecycle);
  const eventsHtml = (data.events || []).map(eventCardHtml).join("");
  document.getElementById("thread-content").innerHTML = `
    ${header}
    ${lifecycle}
    <section class="timeline">
      ${eventsHtml || '<div class="empty">该 Topic 暂无事件</div>'}
    </section>
  `;
}

(async () => {
  try {
    await loadTopic();
  } catch (e) {
    document.getElementById("thread-content").innerHTML =
      `<div class="empty">加载失败: ${escapeHtml(e.message)}</div>`;
  }
})();