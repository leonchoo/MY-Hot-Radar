/* ============================================================================
   MY Hot Radar — Website Radar Feed Adapter
   ----------------------------------------------------------------------------
   Fetches /radar/latest.json and renders it into the home page.

   Design rules (per spec §18 / §24 / §26 / §27):

   * If anything fails (network error, 404, 500, invalid JSON, schema
     mismatch, empty topics, future-dated timestamp, stale > 6h),
     show "Radar Feed unavailable" and DO NOT touch the rest of the
     page (nav / footer / DEMO content / ad slots remain).
   * No framework. Vanilla JS. No innerHTML for user-controlled text.
     Use textContent + safe DOM construction. Only static HTML strings
     come from THIS file.
   * Source URL safety: only http(s) URLs. Anything else → no link,
     just text. rel="noopener noreferrer" + target="_blank".
   * Mobile-first, semantic HTML, keyboard-accessible.
   * The Radar feed NEVER replaces DEMO content. It only renders a new
     section ABOVE existing sections.
   * Loading state: "Loading Radar…" until fetch resolves.
   * Stale data warning: "Radar data may be delayed" when generated_at
     is older than 6 hours (configurable).
   * PARTIAL scan: "Some sources are temporarily unavailable" banner.
   * FAILED scan: never displayed (we keep the previous valid output).

   Schema contract (radar/public_output.py must agree):

     {
       schema_version: 1,
       public_schema_version: 1,
       generated_at: ISO8601 string,
       scan_id: string,
       scan_status: 'SUCCESS' | 'PARTIAL' | 'FAILED',
       summary: {
         topic_count, publishable_count, confirmed_count,
         reported_count, rumour_count, unverified_count,
         social_buzz_count, by_status, by_claim_kind
       },
       topics: [{
         content_key, title, category, language,
         status,            // BREAKING | RISING | HOT | WATCH | COOLING
         verification_status, // CONFIRMED | REPORTED | SOCIAL_BUZZ |
                              // UNVERIFIED | RUMOUR
         confidence_label,  // VERY_LOW..VERY_HIGH (5 levels)
         momentum: { current_mentions, previous_mentions, growth,
                     growth_rate, is_new },
         source_count, sources:[{ source_name, source_tier, url,
                                   published_at }],
         is_political, claim_kind, political_neutral, publishable
       }]
     }

   ========================================================================== */
(function () {
  'use strict';

  // ---------- Config ----------
  var CONFIG = {
    // Public path served by Cloudflare Pages (relative to site root).
    // The radar runtime writes to public/radar/latest.json, which Pages
    // serves at this URL.
    jsonUrl: '/radar/latest.json',

    // DOM id of the host element where Radar Feed will render.
    hostId: 'radar-feed-host',

    // DOM id of the loading-state placeholder (pre-render).
    loadingId: 'radar-feed-loading',

    // Maximum topics to display. We respect the upstream cap (200) but
    // also cap visually so the homepage isn't dominated by the feed.
    maxTopics: 12,

    // Stale threshold: if generated_at is older than this many ms,
    // show "Radar data may be delayed" warning.
    staleAfterMs: 6 * 60 * 60 * 1000, // 6 hours

    // Maximum age (in the future) allowed; anything beyond this is
    // treated as a malformed timestamp.
    futureToleranceMs: 5 * 60 * 1000, // 5 minutes

    // Fetch timeout.
    fetchTimeoutMs: 8000,

    // Cache strategy: 'no-store' is safest; 'default' lets the
    // browser honour Cache-Control.
    cache: 'no-store',
  };

  // ---------- URL safety (must mirror radar.public_output.is_safe_url) ----
  function isSafeUrl(u) {
    if (typeof u !== 'string') return false;
    if (!u) return false;
    if (u.length >= 2048) return false;
    for (var i = 0; i < u.length; i++) {
      var ch = u.charAt(i);
      var o = ch.charCodeAt(0);
      if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') return false;
      if (o < 32 || o === 127) return false;
    }
    var lower = u.toLowerCase();
    if (lower.indexOf('http://') !== 0 && lower.indexOf('https://') !== 0) {
      return false;
    }
    return true;
  }

  // ---------- Status mapping ----------
  // Maps Radar Status → CSS badge class + display label.
  var STATUS_MAP = {
    BREAKING: { cls: 'badge--breaking', label: 'Breaking', icon: '🚨' },
    RISING:   { cls: 'badge--rising',   label: 'Rising',   icon: '📈' },
    HOT:      { cls: 'badge--hot',      label: 'Hot',      icon: '🔥' },
    WATCH:    { cls: 'badge--watch',    label: 'Watch',    icon: '👁' },
    COOLING:  { cls: 'badge--cooling',  label: 'Cooling',  icon: '🐢' },
  };

  var VERIFICATION_MAP = {
    CONFIRMED:    { cls: 'verify--confirmed', label: 'Confirmed' },
    REPORTED:     { cls: 'verify--reported',  label: 'Reported' },
    SOCIAL_BUZZ:  { cls: 'verify--socialbuzz', label: 'Social Buzz' },
    UNVERIFIED:   { cls: 'verify--unverified', label: 'Unverified' },
    RUMOUR:       { cls: 'verify--rumour',     label: 'Rumour' },
  };

  // ---------- Fetch with timeout ----------
  function fetchWithTimeout(url, opts, timeoutMs) {
    if (typeof AbortController === 'function') {
      var controller = new AbortController();
      var timer = setTimeout(function () { controller.abort(); }, timeoutMs);
      var signal = controller.signal;
      var merged = {};
      for (var k in opts) { if (Object.prototype.hasOwnProperty.call(opts, k)) merged[k] = opts[k]; }
      merged.signal = signal;
      return fetch(url, merged).finally(function () { clearTimeout(timer); });
    }
    // Fallback: race fetch against a setTimeout.
    return new Promise(function (resolve, reject) {
      var done = false;
      var timer = setTimeout(function () {
        if (done) return;
        done = true;
        reject(new Error('timeout'));
      }, timeoutMs);
      fetch(url, opts).then(function (r) {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve(r);
      }, function (e) {
        if (done) return;
        done = true;
        clearTimeout(timer);
        reject(e);
      });
    });
  }

  // ---------- Schema validation ----------
  function validatePayload(p) {
    if (!p || typeof p !== 'object') return 'not an object';
    if (p.schema_version !== 1) return 'bad schema_version';
    if (p.public_schema_version !== 1) return 'bad public_schema_version';
    if (typeof p.scan_id !== 'string' || !p.scan_id) return 'missing scan_id';
    if (typeof p.generated_at !== 'string' || !p.generated_at) return 'missing generated_at';
    var ss = ['SUCCESS', 'PARTIAL', 'FAILED'];
    if (ss.indexOf(p.scan_status) < 0) return 'bad scan_status';
    if (!p.summary || typeof p.summary !== 'object') return 'missing summary';
    if (!Array.isArray(p.topics)) return 'topics not an array';
    return null;
  }

  // ---------- Helpers ----------
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
        if (k === 'class') node.className = attrs[k];
        else if (k === 'text') node.textContent = attrs[k];
        else if (k === 'href') node.setAttribute('href', attrs[k]);
        else if (k === 'rel') node.setAttribute('rel', attrs[k]);
        else if (k === 'target') node.setAttribute('target', attrs[k]);
        else if (k === 'aria-label') node.setAttribute('aria-label', attrs[k]);
        else if (k === 'data-key') node.setAttribute('data-key', attrs[k]);
        else node.setAttribute(k, attrs[k]);
      }
    }
    if (children) {
      for (var i = 0; i < children.length; i++) {
        var c = children[i];
        if (c == null) continue;
        if (typeof c === 'string') node.appendChild(document.createTextNode(c));
        else node.appendChild(c);
      }
    }
    return node;
  }

  function formatTimeAgo(isoStr) {
    var ts = Date.parse(isoStr);
    if (!isFinite(ts)) return '';
    var diffMs = Date.now() - ts;
    if (diffMs < 0) return 'just now';
    var s = Math.floor(diffMs / 1000);
    if (s < 60) return s + 's ago';
    var m = Math.floor(s / 60);
    if (m < 60) return m + ' min ago';
    var h = Math.floor(m / 60);
    if (h < 24) return h + ' h ago';
    var d = Math.floor(h / 24);
    return d + ' d ago';
  }

  function isStale(isoStr) {
    var ts = Date.parse(isoStr);
    if (!isFinite(ts)) return true;
    var age = Date.now() - ts;
    return age > CONFIG.staleAfterMs;
  }

  function isFutureDated(isoStr) {
    var ts = Date.parse(isoStr);
    if (!isFinite(ts)) return true;
    return ts - Date.now() > CONFIG.futureToleranceMs;
  }

  // ---------- DOM builders ----------
  function buildStatusBadge(topic) {
    var m = STATUS_MAP[topic.status] || STATUS_MAP.WATCH;
    var span = el('span', { class: 'badge ' + m.cls, 'aria-label': 'Status: ' + m.label });
    span.appendChild(document.createTextNode(m.label));
    return span;
  }

  function buildVerificationBadge(topic) {
    var m = VERIFICATION_MAP[topic.verification_status] || VERIFICATION_MAP.REPORTED;
    var span = el('span', { class: 'verify-pill ' + m.cls, 'aria-label': 'Verification: ' + m.label });
    span.appendChild(document.createTextNode(m.label));
    return span;
  }

  function buildConfidence(topic) {
    var label = topic.confidence_label || '';
    if (!label) return null;
    // Map to user-friendly display but keep the underlying value.
    var friendly;
    switch (label) {
      case 'VERY_HIGH': friendly = 'Very High'; break;
      case 'HIGH':      friendly = 'High'; break;
      case 'MEDIUM':    friendly = 'Medium'; break;
      case 'LOW':       friendly = 'Low'; break;
      case 'VERY_LOW':  friendly = 'Very Low'; break;
      default:          friendly = label;
    }
    return el('span', {
      class: 'confidence-pill',
      'aria-label': 'Confidence: ' + friendly,
      title: 'Radar evidence confidence (heuristic, not probability)'
    }, [document.createTextNode(friendly)]);
  }

  function buildSourceList(topic) {
    var wrap = el('div', { class: 'rf-sources' });
    var header = el('button', {
      class: 'rf-sources__toggle',
      type: 'button',
      'aria-expanded': 'false',
      'aria-controls': 'rf-src-' + topic.content_key,
    });
    header.appendChild(document.createTextNode(
      'Sources (' + topic.source_count + ')'
    ));
    wrap.appendChild(header);

    var list = el('ul', {
      class: 'rf-sources__list',
      id: 'rf-src-' + topic.content_key,
      hidden: 'hidden',
    });

    var topics_srcs = topic.sources || [];
    for (var i = 0; i < topics_srcs.length; i++) {
      var s = topics_srcs[i];
      var li = el('li', { class: 'rf-sources__item' });
      // Tier badge first (so order is consistent)
      var tierSpan = el('span', {
        class: 'rf-tier rf-tier--' + (s.source_tier || 'X'),
        'aria-label': 'Source tier ' + (s.source_tier || 'X')
      }, [document.createTextNode('T' + (s.source_tier || '?'))]);
      li.appendChild(tierSpan);

      if (isSafeUrl(s.url)) {
        var a = el('a', {
          href: s.url,
          target: '_blank',
          rel: 'noopener noreferrer',
          class: 'rf-sources__link',
        }, [document.createTextNode(s.source_name || 'Source')]);
        li.appendChild(a);
      } else {
        var span = el('span', { class: 'rf-sources__name' });
        span.appendChild(document.createTextNode(s.source_name || 'Source'));
        li.appendChild(span);
      }
      list.appendChild(li);
    }
    wrap.appendChild(list);

    // Toggle handler (keyboard accessible by default since it's a button).
    header.addEventListener('click', function () {
      var expanded = header.getAttribute('aria-expanded') === 'true';
      var nextExpanded = !expanded;
      header.setAttribute('aria-expanded', String(nextExpanded));
      if (nextExpanded) {
        list.removeAttribute('hidden');
      } else {
        list.setAttribute('hidden', 'hidden');
      }
    });

    return wrap;
  }

  function buildTopicCard(topic, isFeatured) {
    var cardCls = 'card rf-card' + (isFeatured ? ' rf-card--featured' : '');
    var card = el('article', { class: cardCls, 'data-key': topic.content_key });

    // Body container (no fake hero image; per spec we don't generate imagery)
    var body = el('div', { class: 'card__body' });

    // Meta row: status badge + category + verification + confidence
    var meta = el('div', { class: 'card__meta' });
    meta.appendChild(buildStatusBadge(topic));
    if (topic.category) {
      var cat = el('span', { class: 'card__cat' });
      cat.appendChild(document.createTextNode(topic.category));
      meta.appendChild(cat);
    }
    meta.appendChild(buildVerificationBadge(topic));
    var conf = buildConfidence(topic);
    if (conf) meta.appendChild(conf);
    body.appendChild(meta);

    // Title — no link out to articles in this batch (DEMO article only
    // exists; we don't want radar topics to look like real articles).
    var title = el('h3', { class: 'card__title' });
    title.appendChild(document.createTextNode(topic.title));
    body.appendChild(title);

    // Sources block
    body.appendChild(buildSourceList(topic));

    // Footer row
    var footer = el('div', { class: 'card__footer' });
    var updatedSpan = el('span', { class: 'text-muted' });
    var ago = topic.momentum && topic.momentum.last_seen
              ? formatTimeAgo(topic.momentum.last_seen)
              : '';
    if (!ago && topic.momentum && topic.momentum.first_seen) {
      ago = formatTimeAgo(topic.momentum.first_seen);
    }
    updatedSpan.appendChild(document.createTextNode(ago ? 'Updated ' + ago : 'New'));
    footer.appendChild(updatedSpan);
    if (topic.is_political) {
      var pol = el('span', {
        class: topic.political_neutral ? 'rf-pol rf-pol--ok' : 'rf-pol rf-pol--no',
        title: topic.political_neutral
               ? 'Political topic. Neutral factual reporting.'
               : 'Political topic with opinion content.',
        'aria-label': topic.political_neutral
                      ? 'Political, neutral'
                      : 'Political, opinion',
      }, [document.createTextNode(
        topic.political_neutral ? 'Political · neutral' : 'Political · opinion'
      )]);
      footer.appendChild(pol);
    }
    body.appendChild(footer);

    card.appendChild(body);
    return card;
  }

  // ---------- Section skeleton ----------
  function buildSection(payload) {
    var section = el('section', {
      class: 'section',
      'aria-labelledby': 'radar-heading',
    });
    var container = el('div', { class: 'container' });

    var head = el('div', { class: 'section-head' });
    var h2 = el('h2', {
      class: 'section-head__title',
      id: 'radar-heading',
    });
    var iconSpan = el('span', { 'aria-hidden': 'true' });
    iconSpan.appendChild(document.createTextNode('📡'));
    h2.appendChild(iconSpan);
    h2.appendChild(document.createTextNode(' Radar now'));
    head.appendChild(h2);
    var meta = el('span', {
      class: 'rf-meta',
      'aria-label': 'Radar data freshness',
    });
    if (payload.generated_at && !isFutureDated(payload.generated_at)) {
      meta.appendChild(document.createTextNode(
        'Updated ' + formatTimeAgo(payload.generated_at)
      ));
    } else {
      meta.appendChild(document.createTextNode('Updated recently'));
    }
    head.appendChild(meta);
    container.appendChild(head);

    // Sub-explanation: clearly mark this as Radar-detected topics.
    var lede = el('p', { class: 'rf-lede' });
    lede.appendChild(document.createTextNode(
      'Topics detected by MY Hot Radar across Malaysian and international sources. ' +
      'Each topic links to the original sources; the Radar does not independently ' +
      'confirm every claim.'
    ));
    container.appendChild(lede);

    // PARTIAL scan banner
    if (payload.scan_status === 'PARTIAL') {
      var warn = el('div', {
        class: 'rf-banner',
        role: 'status',
      });
      warn.appendChild(document.createTextNode(
        'Radar partially updated — some sources are temporarily unavailable.'
      ));
      container.appendChild(warn);
    }

    // Stale data warning
    if (payload.generated_at && isStale(payload.generated_at)) {
      var stale = el('div', {
        class: 'rf-banner rf-banner--stale',
        role: 'status',
      });
      stale.appendChild(document.createTextNode(
        'Radar data may be delayed. Showing the most recent successful scan.'
      ));
      container.appendChild(stale);
    }

    // Topics grid
    var grid = el('div', { class: 'grid rf-grid' });
    var topics = (payload.topics || []).slice(0, CONFIG.maxTopics);
    var featured = topics[0];
    if (featured) {
      grid.appendChild(buildTopicCard(featured, true));
    }
    for (var i = 1; i < topics.length; i++) {
      grid.appendChild(buildTopicCard(topics[i], false));
    }
    container.appendChild(grid);

    // Footer line: source count + scan id
    var summary = payload.summary || {};
    var footer = el('p', { class: 'rf-footer' });
    var sm = summary.topic_count + ' topic' + (summary.topic_count === 1 ? '' : 's');
    var pm = summary.publishable_count + ' publishable';
    footer.appendChild(document.createTextNode(sm + ' · ' + pm + ' · '));
    var scanSpan = el('span', { class: 'text-muted' });
    scanSpan.appendChild(document.createTextNode('scan ' + (payload.scan_id || '')));
    footer.appendChild(scanSpan);
    container.appendChild(footer);

    section.appendChild(container);
    return section;
  }

  // ---------- Empty / fallback state ----------
  function buildFallback(reason) {
    var section = el('section', {
      class: 'section section--tight',
      'aria-labelledby': 'radar-heading',
    });
    var container = el('div', { class: 'container' });

    var head = el('div', { class: 'section-head' });
    var h2 = el('h2', {
      class: 'section-head__title',
      id: 'radar-heading',
    });
    var iconSpan = el('span', { 'aria-hidden': 'true' });
    iconSpan.appendChild(document.createTextNode('📡'));
    h2.appendChild(iconSpan);
    h2.appendChild(document.createTextNode(' Radar now'));
    head.appendChild(h2);
    container.appendChild(head);

    var note = el('p', { class: 'rf-unavailable' });
    var msg;
    switch (reason) {
      case 'empty':
        msg = 'Radar data temporarily unavailable.';
        break;
      case 'failed':
        // FAILED scan: spec §20 says don't expose this. Use neutral
        // "temporarily unavailable" wording.
        msg = 'Radar data temporarily unavailable.';
        break;
      case 'stale':
        msg = 'Radar data may be delayed. The most recent successful scan is still shown below.';
        break;
      default:
        msg = 'Radar Feed unavailable.';
    }
    note.appendChild(document.createTextNode(msg));
    container.appendChild(note);

    section.appendChild(container);
    return section;
  }

  // ---------- Main render ----------
  function render(payload) {
    var host = document.getElementById(CONFIG.hostId);
    if (!host) {
      // No host = Radar section not embedded on this page. Bail silently.
      return;
    }
    // Remove loading placeholder
    var loading = document.getElementById(CONFIG.loadingId);
    if (loading && loading.parentNode) loading.parentNode.removeChild(loading);

    // Defensive: if scan_status is FAILED, fall back.
    if (payload.scan_status === 'FAILED') {
      host.appendChild(buildFallback('failed'));
      return;
    }

    var topics = payload.topics || [];
    if (topics.length === 0) {
      host.appendChild(buildFallback('empty'));
      return;
    }

    // Future-dated timestamp -> treat as malformed.
    if (isFutureDated(payload.generated_at)) {
      host.appendChild(buildFallback('empty'));
      console.warn('MY Hot Radar: generated_at is in the future; hiding feed');
      return;
    }

    host.appendChild(buildSection(payload));
  }

  function showFatal(reason) {
    var host = document.getElementById(CONFIG.hostId);
    if (!host) return;
    var loading = document.getElementById(CONFIG.loadingId);
    if (loading && loading.parentNode) loading.parentNode.removeChild(loading);
    host.appendChild(buildFallback(reason || 'error'));
  }

  function init() {
    var host = document.getElementById(CONFIG.hostId);
    if (!host) return; // page doesn't embed Radar Feed

    fetchWithTimeout(
      CONFIG.jsonUrl,
      { cache: CONFIG.cache, headers: { 'Accept': 'application/json' } },
      CONFIG.fetchTimeoutMs
    ).then(function (resp) {
      if (!resp || !resp.ok) {
        // 404 / 500 / etc — non-fatal fallback
        console.warn('MY Hot Radar: fetch failed with status', resp && resp.status);
        showFatal('error');
        return null;
      }
      return resp.text();
    }).then(function (text) {
      if (text == null) return;
      var payload;
      try {
        payload = JSON.parse(text);
      } catch (e) {
        console.warn('MY Hot Radar: invalid JSON:', e && e.message);
        showFatal('error');
        return;
      }
      var v = validatePayload(payload);
      if (v) {
        console.warn('MY Hot Radar: schema mismatch:', v);
        showFatal('error');
        return;
      }
      try {
        render(payload);
      } catch (e) {
        console.warn('MY Hot Radar: render failed:', e && e.message);
        showFatal('error');
      }
    }).catch(function (err) {
      console.warn('MY Hot Radar: fetch error:', err && err.message);
      showFatal('error');
    });
  }

  // Expose internals for test harnesses (read-only).
  window.MYHotRadar = window.MYHotRadar || {};
  window.MYHotRadar.feed = {
    isSafeUrl: isSafeUrl,
    validatePayload: validatePayload,
    isStale: isStale,
    isFutureDated: isFutureDated,
    CONFIG: CONFIG,
    STATUS_MAP: STATUS_MAP,
    VERIFICATION_MAP: VERIFICATION_MAP,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
