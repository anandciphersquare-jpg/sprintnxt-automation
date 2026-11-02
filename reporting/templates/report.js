/* ==========================================================================
   SprintNXT execution report - client application (vanilla JS, no dependencies,
   works from file:// and from CI artifact viewers).
   Data comes from <script id="report-data" type="application/json">.
   ========================================================================== */
(function () {
  'use strict';

  // ------------------------------------------------------------------ data
  const DATA = JSON.parse(document.getElementById('report-data').textContent || '{}');
  const RUN = DATA.run || {};
  const SUM = DATA.summary || {};
  const TESTS = DATA.tests || [];
  const HISTORY = DATA.history || [];
  const TEST_HISTORY = DATA.test_history || {};
  const PRINT_QUERY = /[?&]print=1\b/.test(location.search);
  const ART_ROOT = '../';                                   // html/index.html -> run folder
  const REPORTS_ROOT = /\/runs\//.test(location.pathname.replace(/\\/g, '/')) ? '../../../' : '../../';
  const ORDER = { FAIL: 0, BLOCKED: 1, SKIPPED: 2, PASS: 3 };
  const STATUSES = ['PASS', 'FAIL', 'BLOCKED', 'SKIPPED'];

  TESTS.forEach((t, i) => {
    t._i = i;
    t._bad = t.status === 'FAIL' || t.status === 'BLOCKED';
    t._search = [t.id, t.title, t.module, t.feature, (t.types || []).join(' '), t.status, t.failure_reason,
      t.failure_category, t.nodeid, (t.markers || []).join(' '), JSON.stringify(t.test_data || {})].join(' ').toLowerCase();
  });

  // ------------------------------------------------------------------ icons
  const svg = (body, extra = '', cls = '') => `<svg class="ic${cls ? ' ' + cls : ''}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra}>${body}</svg>`;
  const I = {
    check: svg('<path d="M3.5 8.5l3 3 6-7"/>', 'stroke-width="2.2"'),
    x: svg('<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>', 'stroke-width="2.2"'),
    blocked: svg('<circle cx="8" cy="8" r="5.6"/><path d="M4.1 11.9l7.8-7.8"/>', 'stroke-width="2"'),
    skip: svg('<path d="M4 3.8l5.6 4.2L4 12.2z"/><path d="M12 3.8v8.4"/>'),
    chevron: svg('<path d="M6 3.5l4.5 4.5L6 12.5"/>', '', 'chev'),
    search: svg('<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/>'),
    sun: svg('<circle cx="8" cy="8" r="3"/><path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1"/>'),
    moon: svg('<path d="M13.5 9.5A5.5 5.5 0 016.5 2.5a5.5 5.5 0 107 7z"/>'),
    download: svg('<path d="M8 2.5v8M4.5 7L8 10.5 11.5 7M3 13.5h10"/>'),
    print: svg('<path d="M4.5 6V2.5h7V6M4.5 11.5h-2v-5h11v5h-2M4.5 9.5h7v4h-7z"/>'),
    file: svg('<path d="M9 1.5H4a1 1 0 00-1 1v11a1 1 0 001 1h8a1 1 0 001-1V5.5z"/><path d="M9 1.5v4h4"/>'),
    clock: svg('<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/>'),
    globe: svg('<circle cx="8" cy="8" r="6"/><path d="M2 8h12M8 2c1.8 2 1.8 10 0 12M8 2c-1.8 2-1.8 10 0 12"/>'),
    browser: svg('<rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><path d="M1.5 5.5h13"/>'),
    tag: svg('<path d="M2 2h5.5L14 8.5 8.5 14 2 7.5z"/><circle cx="5" cy="5" r="1"/>'),
    user: svg('<circle cx="8" cy="5.5" r="2.8"/><path d="M2.5 14c.8-2.8 3-4.2 5.5-4.2s4.7 1.4 5.5 4.2"/>'),
    layers: svg('<path d="M8 1.8L14.5 5 8 8.2 1.5 5z"/><path d="M1.5 8L8 11.2 14.5 8M1.5 11L8 14.2 14.5 11"/>'),
    info: svg('<circle cx="8" cy="8" r="6"/><path d="M8 7.2v4M8 4.8v.1"/>'),
    nav: svg('<path d="M2.5 8h10M9 4.5L12.5 8 9 11.5"/>'),
    copy: svg('<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 5.5V3.5a1 1 0 00-1-1h-6a1 1 0 00-1 1v6a1 1 0 001 1h2"/>'),
    ext: svg('<path d="M9 2.5h4.5V7M13.5 2.5L7 9M11.5 9.5v3a1 1 0 01-1 1h-7a1 1 0 01-1-1v-7a1 1 0 011-1h3"/>'),
    expand: svg('<path d="M3 6l5 5 5-5"/>'),
    collapse: svg('<path d="M3 10l5-5 5 5"/>'),
    link: svg('<path d="M6.5 9.5l3-3M7 4.5l1.2-1.2a2.8 2.8 0 014 4L11 8.5M9 11.5l-1.2 1.2a2.8 2.8 0 01-4-4L5 7.5"/>'),
    logo: svg('<path d="M2.5 12.5l3.5-4 3 2.5 4.5-7"/><path d="M10.5 4h3v3"/>', 'stroke-width="2"'),
    empty: svg('<rect x="2" y="3" width="12" height="10" rx="2"/><path d="M5 7h6M5 10h3"/>'),
  };

  const ST = {
    PASS: { label: 'Passed', cls: 'pass', icon: I.check, color: 'var(--pass)' },
    FAIL: { label: 'Failed', cls: 'fail', icon: I.x, color: 'var(--fail)' },
    BLOCKED: { label: 'Blocked', cls: 'blocked', icon: I.blocked, color: 'var(--blocked)' },
    SKIPPED: { label: 'Skipped', cls: 'skip', icon: I.skip, color: 'var(--skip)' },
  };

  // ------------------------------------------------------------------ helpers
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const trunc = (s, n) => (s = String(s || ''), s.length > n ? s.slice(0, n - 1) + '…' : s);
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  const uniq = (arr) => Array.from(new Set(arr.filter(Boolean))).sort((a, b) => String(a).localeCompare(String(b)));
  const fmtNum = (n) => Number(n || 0).toLocaleString();

  function fmtMs(ms) {
    if (ms == null || isNaN(ms)) return '—';
    ms = Math.max(0, Math.round(ms));
    if (ms < 1000) return `${ms} ms`;
    const s = ms / 1000;
    if (s < 60) return `${s.toFixed(s < 10 ? 2 : 1)} s`;
    const m = Math.floor(s / 60), rs = Math.round(s % 60);
    if (m < 60) return `${m}m ${String(rs).padStart(2, '0')}s`;
    return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`;
  }
  function fmtDate(iso, withSeconds = true) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return esc(iso);
    return d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: withSeconds ? '2-digit' : undefined });
  }
  function fmtShortDate(iso) {
    const d = new Date(iso);
    return isNaN(d) ? '' : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  const badge = (status) => { const s = ST[status] || ST.SKIPPED; return `<span class="badge s-${s.cls}">${s.icon}${s.label}</span>`; };
  const artUrl = (p) => (/^(data:|https?:)/.test(p) ? p : ART_ROOT + p.split('/').map(encodeURIComponent).join('/'));
  const shots = (t) => (t.artifacts || []).filter((a) => a.kind === 'screenshot');
  const pctOf = (n, d) => (d ? Math.round((n * 1000) / d) / 10 : 0);

  function httpClass(a) {
    if (a.failure || a.status == null) return 'err';
    if (a.status >= 500) return 'c5';
    if (a.status >= 400) return 'c4';
    if (a.status >= 300) return 'redir';
    return 'ok';
  }
  function shortUrl(u) {
    try { const x = new URL(u); return x.pathname + x.search; } catch (e) { return u; }
  }
  function flips(statuses) {
    const seq = (statuses || []).filter((s) => s && s !== '-');
    let n = 0;
    for (let i = 1; i < seq.length; i++) if (seq[i] !== seq[i - 1]) n++;
    return n;
  }
  function histDots(t) {
    const h = TEST_HISTORY[t.nodeid];
    if (!h || h.length < 2) return '<span class="hist" aria-hidden="true"></span>';
    const dots = h.map((s, i) => `<i class="${s === '-' ? '' : s}${i === h.length - 1 ? ' cur' : ''}"></i>`).join('');
    const label = h.map((s) => (s === '-' ? 'not run' : (ST[s] || {}).label || s)).join(' → ');
    return `<span class="hist" data-tip="Last ${h.length} runs (oldest → this run)\n${esc(label)}">${dots}</span>`;
  }

  // ------------------------------------------------------------------ state
  const state = {
    tab: 'tests', q: '', statuses: new Set(STATUSES), module: '', type: '', feature: '', category: '',
    sort: 'status', group: true, limit: 150, open: new Set(), collapsed: new Set(), failCat: '',
    print: PRINT_QUERY,
  };

  function matches(t) {
    if (!state.statuses.has(t.status)) return false;
    if (state.module && t.module !== state.module) return false;
    if (state.type && !(t.types || []).includes(state.type)) return false;
    if (state.feature && t.feature !== state.feature) return false;
    if (state.category && t.failure_category !== state.category) return false;
    if (state.q) {
      const terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
      if (!terms.every((term) => t._search.includes(term))) return false;
    }
    return true;
  }
  const SORTS = {
    status: (a, b) => ORDER[a.status] - ORDER[b.status] || a.id.localeCompare(b.id, undefined, { numeric: true }),
    id: (a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }),
    title: (a, b) => a.title.localeCompare(b.title),
    slowest: (a, b) => (b.duration_ms || 0) - (a.duration_ms || 0),
    fastest: (a, b) => (a.duration_ms || 0) - (b.duration_ms || 0),
    start: (a, b) => String(a.start).localeCompare(String(b.start)),
    retries: (a, b) => (b.retries || 0) - (a.retries || 0) || ORDER[a.status] - ORDER[b.status],
  };
  const visibleTests = () => TESTS.filter(matches).sort(SORTS[state.sort] || SORTS.status);

  // ------------------------------------------------------------------ layout
  function renderShell() {
    const bad = (SUM.failed || 0) + (SUM.blocked || 0);
    const verdict = !SUM.total ? '<span class="verdict bad">No tests</span>'
      : bad ? `<span class="verdict bad">${I.x}Failed</span>` : `<span class="verdict ok">${I.check}Passed</span>`;
    const ci = RUN.ci && RUN.ci.provider ? (RUN.ci.url ? `<a href="${esc(RUN.ci.url)}" target="_blank" rel="noopener">${esc(RUN.ci.provider)}</a>` : esc(RUN.ci.provider)) : 'Local run';
    const app = $('#app');
    app.innerHTML = `
      <header class="topbar">
        <div class="brand">
          <div class="brand-mark">${I.logo}</div>
          <div style="min-width:0">
            <h1>${esc(RUN.project || 'Test')} · Execution report — ${esc(RUN.name || '')}</h1>
            <div class="sub">${esc(RUN.id || '')} · ${fmtDate(RUN.start)} · ${ci}</div>
          </div>
          ${verdict}
        </div>
        <div class="top-actions">
          <button type="button" class="btn" id="theme-btn" aria-label="Toggle dark mode">${I.moon}<span class="label-text">Theme</span></button>
          <div class="menu">
            <button type="button" class="btn btn-primary" id="export-btn" aria-haspopup="true" aria-expanded="false">${I.download}<span class="label-text">Export</span></button>
            <div class="menu-list" id="export-menu" role="menu" hidden>
              <button type="button" role="menuitem" data-export="pdf">${I.file}<span>PDF report<small>${RUN.pdf ? 'Open the generated report.pdf' : 'Print-optimised layout → Save as PDF'}</small></span></button>
              <button type="button" role="menuitem" data-export="print">${I.print}<span>Print / Save as PDF<small>Failures expanded, all rows</small></span></button>
              <button type="button" role="menuitem" data-export="html">${I.file}<span>HTML (single file)<small>This report as a standalone file</small></span></button>
              <button type="button" role="menuitem" data-export="csv">${I.download}<span>CSV — filtered view<small>Rows matching the current filters</small></span></button>
              <button type="button" role="menuitem" data-export="json">${I.download}<span>JSON — full data<small>Run, summary, tests, history</small></span></button>
              <a role="menuitem" href="../json/results.csv">${I.file}<span>results.csv (all tests)<small>Generated on disk</small></span></a>
              <a role="menuitem" href="${REPORTS_ROOT}index.html">${I.layers}<span>All runs<small>reports/index.html</small></span></a>
            </div>
          </div>
        </div>
      </header>
      <div class="meta-strip">
        <span>${I.browser}Browser <b>${esc(RUN.browser || 'n/a')}</b></span>
        <span>${I.globe}Environment <b>${esc(RUN.environment || '—')}</b></span>
        <span>${I.tag}Build <b>${esc(RUN.build || '—')}</b></span>
        <span>${I.user}Executed by <b>${esc(RUN.executed_by || '—')}</b></span>
        <span>${I.clock}Started <b>${fmtDate(RUN.start)}</b></span>
        ${RUN.base_url ? `<span>${I.link}<b class="mono" style="font-weight:500">${esc(RUN.base_url)}</b></span>` : ''}
      </div>
      <section class="kpis" aria-label="Execution summary">${kpisHtml()}</section>
      <section class="charts" aria-label="Charts">
        ${chartCard('status', 'Result distribution', `${fmtNum(SUM.total)} tests in this run`, '<div id="chart-status"></div>', statusTable())}
        ${chartCard('modules', 'Module-wise results', `${plural((SUM.modules || []).length, 'module')} executed`, '<div id="chart-modules"></div>', modulesTable())}
        ${chartCard('categories', 'Failure categories', 'Failed + blocked tests by root-cause category', '<div id="chart-categories"></div>', categoriesTable())}
        ${chartCard('trend', 'Pass-rate trend', `Last ${Math.min(HISTORY.length, 20)} run(s) · pass rate excludes skipped`, '<div id="chart-trend" class="trend"></div>', trendTable())}
      </section>
      <nav class="tabs" role="tablist" aria-label="Report sections">${tabsHtml()}</nav>
      <section class="panel" id="panel-tests" role="tabpanel" data-print="true"><h2 class="print-title">Test cases</h2></section>
      <section class="panel" id="panel-failures" role="tabpanel" data-print="${(SUM.failed || 0) + (SUM.blocked || 0) > 0}" hidden><h2 class="print-title">Failure summary</h2></section>
      <section class="panel" id="panel-retries" role="tabpanel" data-print="false" hidden></section>
      <section class="panel" id="panel-modules" role="tabpanel" data-print="false" hidden></section>
      <section class="panel" id="panel-run" role="tabpanel" data-print="true" hidden><h2 class="print-title">Run details</h2></section>
      <footer class="footer">Generated ${fmtDate(RUN.generated)} · pytest ${esc(RUN.pytest || '')} · Playwright ${esc(RUN.playwright || '')} · Python ${esc(RUN.python || '')} · ${esc(RUN.platform || '')}</footer>`;
    app.removeAttribute('aria-busy');
  }

  function kpisHtml() {
    const total = SUM.total || 0;
    const meter = STATUSES.map((s) => {
      const n = { PASS: SUM.passed, FAIL: SUM.failed, BLOCKED: SUM.blocked, SKIPPED: SUM.skipped }[s] || 0;
      return n ? `<i style="width:${(n * 100) / total}%;background:${ST[s].color}" data-tip="${ST[s].label}: ${n}"></i>` : '';
    }).join('');
    const tile = (status, label, value, hint) => `
      <div class="tile${status ? ' clickable' : ''}" ${status ? `data-filter-status="${status}" role="button" tabindex="0" aria-label="Show ${label.toLowerCase()} tests"` : ''}>
        <span class="label">${status ? `<i style="background:${ST[status].color}"></i>` : ''}${label}</span>
        <span class="value">${value}</span>${hint ? `<span class="hint">${hint}</span>` : ''}
      </div>`;
    return `
      <div class="tile hero">
        <div style="flex:1;min-width:0">
          <span class="label">Pass percentage</span>
          <span class="value">${SUM.pass_rate != null ? SUM.pass_rate : 0}%</span>
          <div class="meter" style="margin:8px 0 6px">${meter}</div>
          <span class="hint">${fmtNum(SUM.passed)} of ${fmtNum(SUM.executed)} executed tests passed${SUM.skipped ? ` · ${fmtNum(SUM.skipped)} skipped excluded` : ''}</span>
        </div>
      </div>
      ${tile('', 'Total tests', fmtNum(total), `${plural(SUM.retried || 0, 'retried test')}`)}
      ${tile('PASS', 'Passed', fmtNum(SUM.passed), SUM.flaky ? `${SUM.flaky} flaky (passed on retry)` : '')}
      ${tile('FAIL', 'Failed', fmtNum(SUM.failed), '')}
      ${tile('BLOCKED', 'Blocked', fmtNum(SUM.blocked), 'setup / precondition')}
      ${tile('SKIPPED', 'Skipped', fmtNum(SUM.skipped), '')}
      ${tile('', 'Duration', fmtMs(RUN.duration_ms), `${RUN.workers > 1 ? RUN.workers + ' workers · ' : ''}test time ${fmtMs(SUM.test_time_ms)}`)}
      ${tile('', 'Modules', fmtNum((SUM.modules || []).length), esc(trunc((SUM.modules || []).map((m) => m.module).join(', '), 60)))}`;
  }

  function chartCard(key, title, sub, chart, table) {
    return `<article class="card" id="card-${key}">
      <div class="card-head"><div><h2>${title}</h2><p>${sub}</p></div>
        <button type="button" class="btn btn-ghost btn-sm toggle-table" data-toggle-table="${key}" aria-pressed="false">Table</button></div>
      <div class="card-body"><div class="chart-view">${chart}</div><div class="table-view table-scroll" hidden>${table}</div></div>
    </article>`;
  }

  function tabsHtml() {
    const bad = TESTS.filter((t) => t._bad).length;
    const retried = retryRows().length;
    const tabs = [['tests', 'Test cases', TESTS.length], ['failures', 'Failures', bad], ['retries', 'Retries & flaky', retried],
      ['modules', 'Modules', (SUM.modules || []).length], ['run', 'Run details', '']];
    return tabs.map(([k, label, n]) => `<button type="button" class="tab" role="tab" data-tab="${k}" aria-selected="${state.tab === k}" aria-controls="panel-${k}">${label}${n !== '' ? ` <span class="count">${n}</span>` : ''}</button>`).join('');
  }

  // ------------------------------------------------------------------ charts
  function renderStatusChart() {
    const host = $('#chart-status');
    const segs = [['PASS', SUM.passed], ['FAIL', SUM.failed], ['BLOCKED', SUM.blocked], ['SKIPPED', SUM.skipped]]
      .map(([s, n]) => ({ s, n: n || 0 }));
    const total = SUM.total || 0;
    const R = 66, SW = 22, C = 2 * Math.PI * R, live = segs.filter((x) => x.n > 0);
    const gap = live.length > 1 ? 2.5 : 0;
    let off = 0;
    const arcs = live.map((x) => {
      const len = (x.n / total) * C, dash = Math.max(len - gap, 0.8);
      const el = `<circle cx="88" cy="88" r="${R}" fill="none" style="stroke:${ST[x.s].color};cursor:pointer" stroke-width="${SW}"
        stroke-dasharray="${dash} ${C - dash}" stroke-dashoffset="${-off}" transform="rotate(-90 88 88)"
        data-tip="${ST[x.s].label}: ${x.n} (${pctOf(x.n, total)}%)" data-filter-status="${x.s}"></circle>`;
      off += len;
      return el;
    }).join('');
    host.innerHTML = `<div class="donut-wrap">
      <svg class="donut" viewBox="0 0 176 176" role="img" aria-label="Pass ${SUM.passed}, fail ${SUM.failed}, blocked ${SUM.blocked}, skipped ${SUM.skipped}">
        <circle cx="88" cy="88" r="${R}" fill="none" style="stroke:var(--line)" stroke-width="${SW}" opacity="${total ? 0 : 1}"></circle>
        ${arcs}
        <text x="88" y="88" text-anchor="middle" font-size="30" font-weight="650">${SUM.pass_rate || 0}%</text>
        <text x="88" y="108" text-anchor="middle" font-size="12" style="fill:var(--ink-2)">pass rate</text>
      </svg>
      <ul class="legend">${segs.map((x) => `<li data-filter-status="${x.s}" style="cursor:pointer"><span class="sw" style="background:${ST[x.s].color}"></span><span>${ST[x.s].label}</span><span class="n">${fmtNum(x.n)}</span><span class="p">${pctOf(x.n, total)}%</span></li>`).join('')}</ul>
    </div>`;
  }
  function statusTable() {
    const rows = [['PASS', SUM.passed], ['FAIL', SUM.failed], ['BLOCKED', SUM.blocked], ['SKIPPED', SUM.skipped]];
    return `<table class="data-table"><thead><tr><th>Status</th><th class="num">Tests</th><th class="num">Share</th></tr></thead><tbody>
      ${rows.map(([s, n]) => `<tr><td>${badge(s)}</td><td class="num">${n || 0}</td><td class="num">${pctOf(n || 0, SUM.total)}%</td></tr>`).join('')}</tbody></table>`;
  }

  function renderModulesChart() {
    const host = $('#chart-modules');
    const mods = SUM.modules || [];
    if (!mods.length) { host.innerHTML = '<div class="chart-empty">No modules executed</div>'; return; }
    const max = Math.max(...mods.map((m) => m.total));
    host.innerHTML = `<div class="legend-inline">${STATUSES.map((s) => `<span><i style="background:${ST[s].color}"></i>${ST[s].label}</span>`).join('')}</div>
      <div class="hbars">${mods.map((m) => {
        const segs = STATUSES.filter((s) => m[s]).map((s) => `<span class="seg" style="width:${(m[s] * 100) / max}%;background:${ST[s].color}" data-tip="${esc(m.module)} · ${ST[s].label}: ${m[s]} of ${m.total}"></span>`).join('');
        return `<div class="hbar"><span class="name"><button type="button" data-filter-module="${esc(m.module)}" title="Show ${esc(m.module)} tests">${esc(m.module)}</button></span>
          <span class="track">${segs}</span><span class="val">${m.PASS}/${m.total} passed</span></div>`;
      }).join('')}</div>`;
  }
  function modulesTable() {
    const mods = SUM.modules || [];
    return `<table class="data-table"><thead><tr><th>Module</th><th class="num">Total</th><th class="num">Pass</th><th class="num">Fail</th><th class="num">Blocked</th><th class="num">Skip</th></tr></thead><tbody>
      ${mods.map((m) => `<tr><td>${esc(m.module)}</td><td class="num">${m.total}</td><td class="num">${m.PASS}</td><td class="num">${m.FAIL}</td><td class="num">${m.BLOCKED}</td><td class="num">${m.SKIPPED}</td></tr>`).join('')}</tbody></table>`;
  }

  function renderCategoriesChart() {
    const host = $('#chart-categories');
    const cats = Object.entries(SUM.categories || {});
    if (!cats.length) { host.innerHTML = `<div class="chart-empty">${I.check}<br>No failed or blocked tests</div>`; return; }
    const max = Math.max(...cats.map(([, n]) => n));
    host.innerHTML = `<div class="hbars wide">${cats.map(([c, n]) => `<div class="hbar"><span class="name"><button type="button" data-filter-category="${esc(c)}" title="${esc(c)}">${esc(c)}</button></span>
      <span class="track"><span class="seg" style="width:${(n * 100) / max}%;background:var(--accent);border-radius:0 4px 4px 0" data-tip="${esc(c)}: ${n} test(s)"></span></span>
      <span class="val">${n}</span></div>`).join('')}</div>`;
  }
  function categoriesTable() {
    const cats = Object.entries(SUM.categories || {});
    if (!cats.length) return '<div class="chart-empty">No failures</div>';
    return `<table class="data-table"><thead><tr><th>Category</th><th class="num">Tests</th></tr></thead><tbody>${cats.map(([c, n]) => `<tr><td>${esc(c)}</td><td class="num">${n}</td></tr>`).join('')}</tbody></table>`;
  }

  function renderTrendChart() {
    const host = $('#chart-trend');
    const runs = HISTORY.slice(-20);
    if (!runs.length) { host.innerHTML = '<div class="chart-empty">Trend appears after the first recorded run</div>'; return; }
    const W = Math.max(280, host.clientWidth || 560), H = 210, m = { l: 40, r: 56, t: 14, b: 30 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b, n = runs.length;
    const x = (i) => m.l + (n === 1 ? iw / 2 : (i * iw) / (n - 1));
    const y = (v) => m.t + ih - (Math.max(0, Math.min(100, v)) / 100) * ih;
    const grid = [0, 25, 50, 75, 100].map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"></line>`).join('');
    const yl = [0, 50, 100].map((v) => `<text x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end">${v}%</text>`).join('');
    const pts = runs.map((r, i) => [x(i), y(r.pass_rate || 0)]);
    const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('');
    const area = n > 1 ? `${line}L${pts[n - 1][0].toFixed(1)},${y(0)}L${pts[0][0].toFixed(1)},${y(0)}Z` : '';
    const last = runs[n - 1];
    const xl = n > 1
      ? `<text x="${x(0)}" y="${H - 8}" text-anchor="start">${esc(fmtShortDate(runs[0].start))}</text><text x="${x(n - 1)}" y="${H - 8}" text-anchor="end">${esc(fmtShortDate(last.start))}</text>`
      : `<text x="${x(0)}" y="${H - 8}" text-anchor="middle">${esc(fmtShortDate(last.start))}</text>`;
    host.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Pass rate over the last ${n} runs, latest ${last.pass_rate}%">
      <g class="grid">${grid}</g><g class="axis">${yl}${xl}</g>
      ${area ? `<path d="${area}" style="fill:var(--accent)" opacity=".10"></path>` : ''}
      <path d="${line}" fill="none" style="stroke:var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>
      ${pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="${i === n - 1 ? 5 : 4}" style="fill:var(--accent);stroke:var(--card)" stroke-width="2"></circle>`).join('')}
      <text class="lbl" x="${pts[n - 1][0] + 10}" y="${pts[n - 1][1] + 4}">${last.pass_rate}%</text>
      <line class="xh" x1="0" x2="0" y1="${m.t}" y2="${m.t + ih}" style="stroke:var(--axis)" stroke-width="1" visibility="hidden"></line>
      <circle class="xh-dot" r="6" style="fill:var(--accent);stroke:var(--card)" stroke-width="2" visibility="hidden"></circle>
      <rect class="hit" x="${m.l - 10}" y="0" width="${iw + 20}" height="${H}" fill="transparent"></rect>
    </svg>`;
    const svgEl = $('svg', host), hit = $('.hit', host), xh = $('.xh', host), dot = $('.xh-dot', host);
    hit.addEventListener('mousemove', (e) => {
      const rect = svgEl.getBoundingClientRect();
      const px = (e.clientX - rect.left) * (W / rect.width);
      const i = n === 1 ? 0 : Math.max(0, Math.min(n - 1, Math.round(((px - m.l) / iw) * (n - 1))));
      const r = runs[i];
      xh.setAttribute('x1', pts[i][0]); xh.setAttribute('x2', pts[i][0]); xh.setAttribute('visibility', 'visible');
      dot.setAttribute('cx', pts[i][0]); dot.setAttribute('cy', pts[i][1]); dot.setAttribute('visibility', 'visible');
      showTip(`${r.name}${r.run_id === RUN.id ? ' (this run)' : ''}\n${fmtDate(r.start, false)}\nPass rate ${r.pass_rate}%\n${r.passed} passed · ${r.failed} failed · ${r.blocked || 0} blocked · ${r.skipped} skipped`, e);
    });
    hit.addEventListener('mouseleave', () => { xh.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); hideTip(); });
  }
  function trendTable() {
    return `<table class="data-table"><thead><tr><th>Run</th><th>Started</th><th class="num">Pass rate</th><th class="num">Pass</th><th class="num">Fail</th><th class="num">Blocked</th><th class="num">Skip</th></tr></thead><tbody>
      ${HISTORY.slice(-20).reverse().map((r) => `<tr><td>${esc(r.name)}</td><td>${fmtDate(r.start, false)}</td><td class="num">${r.pass_rate}%</td><td class="num">${r.passed}</td><td class="num">${r.failed}</td><td class="num">${r.blocked || 0}</td><td class="num">${r.skipped}</td></tr>`).join('')}</tbody></table>`;
  }
  function renderCharts() { renderStatusChart(); renderModulesChart(); renderCategoriesChart(); renderTrendChart(); }

  // ------------------------------------------------------------------ tests panel
  function renderTestsPanel() {
    const panel = $('#panel-tests');
    const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(label)}</option>`;
    const counts = Object.fromEntries(STATUSES.map((s) => [s, TESTS.filter((t) => t.status === s).length]));
    const cats = uniq(TESTS.map((t) => t.failure_category));
    panel.innerHTML = `<h2 class="print-title">Test cases</h2>
      <div class="toolbar" role="search">
        <label class="search"><span class="visually-hidden">Search tests</span>${I.search}
          <input id="q" type="search" placeholder="Search ID, name, module, error, test data…" value="${esc(state.q)}" autocomplete="off"><kbd>/</kbd></label>
        <div class="chips" role="group" aria-label="Status filter">${STATUSES.map((s) => `<button type="button" class="chip" data-chip="${s}" aria-pressed="${state.statuses.has(s)}"><span class="ic-${ST[s].cls}">${ST[s].icon}</span>${ST[s].label} <span class="count">${counts[s]}</span></button>`).join('')}</div>
        <select id="f-module" aria-label="Module">${opt('', 'All modules', state.module)}${uniq(TESTS.map((t) => t.module)).map((m) => opt(m, m, state.module)).join('')}</select>
        <select id="f-type" aria-label="Test type">${opt('', 'All types', state.type)}${uniq(TESTS.flatMap((t) => t.types || [])).map((m) => opt(m, m, state.type)).join('')}</select>
        <select id="f-feature" aria-label="Feature">${opt('', 'All features', state.feature)}${uniq(TESTS.map((t) => t.feature)).map((m) => opt(m, m, state.feature)).join('')}</select>
        ${cats.length ? `<select id="f-category" aria-label="Failure category">${opt('', 'All failure categories', state.category)}${cats.map((m) => opt(m, m, state.category)).join('')}</select>` : ''}
        <select id="f-sort" aria-label="Sort">${[['status', 'Sort: status (failures first)'], ['id', 'Sort: test case ID'], ['title', 'Sort: name'], ['slowest', 'Sort: slowest first'], ['fastest', 'Sort: fastest first'], ['start', 'Sort: execution order'], ['retries', 'Sort: most retries']].map(([v, l]) => opt(v, l, state.sort)).join('')}</select>
        <label class="check"><input type="checkbox" id="f-group" ${state.group ? 'checked' : ''}> Group by module</label>
      </div>
      <div class="result-line"><span id="result-count"></span>
        <span class="no-print" style="display:flex;gap:6px">
          <button type="button" class="btn btn-sm" data-act="reset">Reset filters</button>
          <button type="button" class="btn btn-sm" data-act="expand-all">${I.expand}Expand all</button>
          <button type="button" class="btn btn-sm" data-act="collapse-all">${I.collapse}Collapse all</button>
        </span></div>
      <div id="list"></div>`;
    updateList();
  }

  function rowHtml(t) {
    const open = state.open.has(t._i);
    const reason = t._bad && t.failure_reason ? ` — <span class="reason">${esc(trunc(t.failure_reason, 150))}</span>` : '';
    const tags = (t.types || []).map((x) => `<span class="tag">${esc(x)}</span>`).join('')
      + (t.retries ? `<span class="tag" data-tip="${t.retries} retr${t.retries === 1 ? 'y' : 'ies'}">↻ ${t.retries}</span>` : '')
      + (t.flaky ? '<span class="tag flaky" data-tip="Failed first, passed on retry">flaky</span>' : '');
    return `<div class="tc${open ? ' open' : ''}" id="tc-${t._i}" data-i="${t._i}">
      <button type="button" class="tc-head" data-act="toggle" aria-expanded="${open}" aria-controls="tcb-${t._i}">
        ${badge(t.status)}
        <span class="tc-id" title="${esc(t.id)}">${esc(t.id)}</span>
        <span class="tc-title"><b title="${esc(t.title)}">${esc(t.title)}</b><small>${esc(t.module)} › ${esc(t.feature)}${reason}</small></span>
        <span class="tc-tags">${tags}</span>
        ${histDots(t)}
        <span class="tc-dur">${fmtMs(t.duration_ms)}</span>
        ${I.chevron}
      </button>
      <div class="tc-body" id="tcb-${t._i}"${open ? '' : ' hidden'}>${open ? detailsHtml(t) : ''}</div>
    </div>`;
  }

  function updateList() {
    const list = $('#list');
    if (!list) return;
    if (state.print) TESTS.forEach((t) => { if (t._bad) state.open.add(t._i); });
    const items = visibleTests();
    const limit = state.print ? Infinity : state.limit;
    const shown = items.slice(0, limit);
    $('#result-count').textContent = `Showing ${Math.min(items.length, limit)} of ${items.length} matching · ${TESTS.length} total`;
    if (!items.length) {
      list.innerHTML = `<div class="empty">${I.empty}<p>No tests match the current filters.</p><button type="button" class="btn" data-act="reset">Reset filters</button></div>`;
      return;
    }
    let html = '';
    if (state.group) {
      const groups = new Map();
      shown.forEach((t) => { if (!groups.has(t.module)) groups.set(t.module, []); groups.get(t.module).push(t); });
      const allByModule = new Map();
      items.forEach((t) => allByModule.set(t.module, (allByModule.get(t.module) || []).concat(t)));
      for (const [mod, rows] of groups) {
        const all = allByModule.get(mod) || rows;
        const c = Object.fromEntries(STATUSES.map((s) => [s, all.filter((t) => t.status === s).length]));
        const meter = STATUSES.map((s) => (c[s] ? `<i style="width:${(c[s] * 100) / all.length}%;background:${ST[s].color}"></i>` : '')).join('');
        const collapsed = state.collapsed.has(mod) && !state.print;
        html += `<section class="group" data-module="${esc(mod)}" data-collapsed="${collapsed}">
          <button type="button" class="group-head" data-act="group" aria-expanded="${!collapsed}">
            ${I.chevron}<h3>${esc(mod)}</h3><span class="meter">${meter}</span>
            <span class="gstats">${c.PASS} passed · ${c.FAIL} failed · ${c.BLOCKED} blocked · ${c.SKIPPED} skipped</span></button>
          <div class="rows">${rows.map(rowHtml).join('')}</div></section>`;
      }
    } else {
      html = `<div class="rows flat">${shown.map(rowHtml).join('')}</div>`;
    }
    if (items.length > limit) {
      html += `<div class="more"><button type="button" class="btn" data-act="more">Show ${Math.min(150, items.length - limit)} more (${items.length - limit} hidden)</button></div>`;
    }
    list.innerHTML = html;
  }

  // ------------------------------------------------------------------ test details
  function detailsHtml(t) {
    const kv = (rows) => `<dl class="kv">${rows.filter((r) => r[1] !== '' && r[1] != null).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
    const pre = (t.preconditions || []).length
      ? `<ol class="plain">${t.preconditions.map((p) => `<li>${esc(p)}</li>`).join('')}</ol>` : '<span style="color:var(--muted)">None declared</span>';
    const dataRows = Object.entries(t.test_data || {});
    const data = dataRows.length
      ? `<table class="kvtable">${dataRows.map(([k, v]) => `<tr><td>${esc(k)}</td><td class="mono">${esc(typeof v === 'string' ? (v === '' ? '"" (empty)' : v) : JSON.stringify(v))}</td></tr>`).join('')}</table>`
      : '<span style="color:var(--muted)">No test data recorded</span>';
    const attempts = (t.attempts || []).length > 1
      ? t.attempts.map((a) => `<span class="badge s-${ST[a.status].cls}" data-tip="Attempt ${a.attempt}: ${ST[a.status].label} in ${fmtMs(a.duration_ms)}${a.failure_reason ? '\n' + esc(trunc(a.failure_reason, 200)) : ''}">${ST[a.status].icon}#${a.attempt}</span>`).join(' ')
      : '1';
    const facts = kv([
      ['Test case ID', `<span class="mono">${esc(t.id)}</span>`],
      ['Status', badge(t.status) + (t.flaky ? ' <span class="tag flaky">flaky</span>' : '')],
      ['Module', esc(t.module)], ['Feature / flow', esc(t.feature)],
      ['Type', (t.types || []).map((x) => `<span class="tag">${esc(x)}</span>`).join(' ')],
      ['Started', fmtDate(t.start)], ['Finished', fmtDate(t.end)], ['Duration', fmtMs(t.duration_ms)],
      ['Browser', esc(t.browser || RUN.browser || 'n/a')], ['Environment', esc(RUN.environment)],
      ['Executed by', esc(RUN.executed_by)], ['Build', esc(RUN.build)], ['Attempts', attempts],
      ['Worker', esc(t.worker)], ['Markers', (t.markers || []).map((x) => `<span class="tag">${esc(x)}</span>`).join(' ')],
      ['Location', `<span class="mono">${esc(t.file)}:${t.line}</span>`],
      ['Node ID', `<span class="mono">${esc(t.nodeid)}</span> <button type="button" class="btn btn-ghost btn-sm copy" data-copy="${esc(t.nodeid)}" aria-label="Copy node id">${I.copy}</button>`],
    ]);
    const reason = t.failure_reason ? `<div class="box reason-box"><h4>${t.status === 'SKIPPED' ? 'Skip reason' : 'Failure reason'} ${t.failure_category ? `<span class="tag cat">${esc(t.failure_category)}</span>` : ''}</h4><div class="mono">${esc(t.failure_reason)}</div></div>` : '';
    const left = `${t.description ? `<div class="box"><h4>Description</h4>${esc(t.description)}</div>` : ''}
      <div class="box"><h4>Preconditions</h4>${pre}</div>
      <div class="box"><h4>Test data used</h4>${data}</div>
      <div class="box"><div class="result-pair"><div class="box"><h4>Expected result</h4>${esc(t.expected)}</div>
        <div class="box actual-${t.status}"><h4>Actual result</h4>${esc(t.actual)}</div></div></div>
      ${reason}`;

    const sub = subtabsFor(t);
    const first = (t._bad && sub.find((s) => s.key === 'evidence')) ? 'evidence' : (t._bad && sub.find((s) => s.key === 'error')) ? 'error' : 'steps';
    const nav = `<div class="subtabs" role="tablist">${sub.map((s) => `<button type="button" class="subtab" role="tab" data-subtab="${s.key}" aria-selected="${s.key === first}">${s.label}${s.n !== '' ? ` <span class="count">${s.n}</span>` : ''}</button>`).join('')}</div>`;
    const panels = sub.map((s) => `<div class="subpanel" data-subpanel="${s.key}"${s.key === first ? '' : ' hidden'}><h4 class="print-only">${s.label}</h4>${s.html()}</div>`).join('');
    return `<div class="detail-grid"><div>${left}</div><div><div class="box"><h4>Execution</h4>${facts}</div></div></div>${nav}${panels}`;
  }

  function subtabsFor(t) {
    const steps = (t.steps || []);
    const list = [{ key: 'steps', label: 'Steps executed', n: steps.filter((s) => s.kind === 'step').length, html: () => stepsHtml(t) }];
    if ((t.artifacts || []).length) list.push({ key: 'evidence', label: 'Screenshots & media', n: t.artifacts.length, html: () => evidenceHtml(t) });
    if (t.error) list.push({ key: 'error', label: 'Stack trace', n: '', html: () => codeBlock(t.error) });
    if ((t.api_logs || []).length) list.push({ key: 'api', label: 'API calls', n: t.api_logs.length, html: () => apiHtml(t) });
    if ((t.console || []).length) list.push({ key: 'console', label: 'Console errors', n: t.console.length, html: () => consoleHtml(t) });
    if ((t.network_failures || []).length) list.push({ key: 'network', label: 'Network failures', n: t.network_failures.length, html: () => networkHtml(t) });
    if (t.captured_output) list.push({ key: 'output', label: 'Captured output', n: '', html: () => codeBlock(t.captured_output) });
    if ((t.attempts || []).length > 1) list.push({ key: 'attempts', label: 'Attempts', n: t.attempts.length, html: () => attemptsHtml(t) });
    if (Object.keys(t.user_properties || {}).length) list.push({ key: 'props', label: 'Properties', n: '', html: () => `<table class="kvtable">${Object.entries(t.user_properties).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>` });
    return list;
  }

  function stepsHtml(t) {
    const steps = t.steps || [];
    if (!steps.length) return '<div class="empty" style="padding:20px">No steps recorded. Decorate page-object methods with <code>@step</code> or wrap actions in <code>with step("…")</code>.</div>';
    let n = 0;
    return `<ol class="steps">${steps.map((s) => {
      const icon = s.kind === 'navigation' ? `<span style="color:var(--muted)">${I.nav}</span>`
        : s.kind === 'note' ? `<span style="color:var(--muted)">${I.info}</span>`
          : s.status === 'failed' ? `<span class="ic-fail">${I.x}</span>` : `<span class="ic-pass">${I.check}</span>`;
      const params = Object.entries(s.params || {}).map(([k, v]) => `${k}=${typeof v === 'string' ? JSON.stringify(trunc(v, 80)) : v}`).join(', ');
      const label = s.kind === 'step' ? `<b style="font-weight:600;color:var(--muted);margin-right:6px">${++n}.</b>` : '';
      return `<li class="step ${s.kind} ${s.status}" style="padding-left:${4 + (s.depth || 0) * 22}px">${icon}
        <span class="t">${label}${esc(s.title)}${params ? `<span class="params">${esc(trunc(params, 300))}</span>` : ''}${s.error ? `<span class="err">${esc(s.error)}</span>` : ''}</span>
        <span class="d">${s.kind === 'step' ? fmtMs(s.duration_ms) : ''}<br><small>+${fmtMs(s.start_ms)}</small></span></li>`;
    }).join('')}</ol>`;
  }

  function evidenceHtml(t) {
    const arts = t.artifacts || [];
    const imgs = shots(t);
    const multiAttempt = (t.attempts || []).length > 1;
    const caption = (a) => `${esc(a.title)}${multiAttempt ? ` · attempt ${a.attempt}` : ''}`;
    let html = '';
    if (imgs.length) {
      html += `<div class="shots">${imgs.map((a, j) => `<button type="button" class="shot" data-gallery="${t._i}" data-idx="${j}" aria-label="Open ${esc(a.title)}">
        <img src="${artUrl(a.path)}" alt="${esc(a.title)}" loading="${state.print ? 'eager' : 'lazy'}"><span>${caption(a)}</span></button>`).join('')}</div>`;
    }
    arts.filter((a) => a.kind === 'video').forEach((a) => {
      html += `<div class="evidence-row"><div class="pathline">${I.file}<b>${caption(a)}</b><code>${esc(a.path)}</code><a href="${artUrl(a.path)}" target="_blank" rel="noopener">Open ${I.ext}</a></div>
        <video controls preload="none" src="${artUrl(a.path)}"></video></div>`;
    });
    arts.filter((a) => a.kind === 'trace').forEach((a) => {
      const cmd = `playwright show-trace "${(RUN.dir ? RUN.dir.replace(/\\/g, '/') + '/' : '')}${a.path}"`;
      html += `<div class="evidence-row"><div class="pathline">${I.file}<b>${caption(a)}</b><a href="${artUrl(a.path)}">${esc(a.path)}</a>
        <button type="button" class="btn btn-sm copy" data-copy="${esc(cmd)}">${I.copy}Copy show-trace command</button>
        <a href="https://trace.playwright.dev" target="_blank" rel="noopener">trace.playwright.dev ${I.ext}</a></div>
        <span style="font-size:12px;color:var(--ink-2)">Open with <code>${esc(cmd)}</code>, or drop the .zip on trace.playwright.dev (runs locally in your browser).</span></div>`;
    });
    arts.filter((a) => a.kind === 'attachment').forEach((a) => {
      html += `<div class="evidence-row"><div class="pathline">${I.file}<b>${caption(a)}</b><a href="${artUrl(a.path)}" target="_blank" rel="noopener">${esc(a.path)}</a><span class="tag">${esc(a.mime)}</span></div></div>`;
    });
    return html;
  }

  function codeBlock(text) {
    return `<div class="codeblock"><button type="button" class="btn btn-sm copy" data-copy="${esc(text)}">${I.copy}Copy</button><pre>${esc(text)}</pre></div>`;
  }

  function apiHtml(t) {
    const hdrs = (h) => Object.entries(h || {}).map(([k, v]) => `${k}: ${v}`).join('\n');
    return t.api_logs.map((a) => `<details class="api"><summary>
        <span class="method">${esc(a.method)}</span><span class="http ${httpClass(a)}">${a.failure ? 'FAILED' : esc(a.status)}</span>
        <span class="url" title="${esc(a.url)}">${esc(shortUrl(a.url))}</span>
        <span class="num">${a.duration_ms != null ? fmtMs(a.duration_ms) : '—'}</span><span class="num">+${fmtMs(a.at_ms)}</span></summary>
        <div class="io">
          <div><h5>Request</h5><div class="codeblock"><pre>${esc(a.method)} ${esc(a.url)}\n\n${esc(hdrs(a.request_headers))}${a.request_body ? '\n\n' + esc(a.request_body) : ''}</pre></div></div>
          <div><h5>Response${a.failure ? ' — transport failure' : ''}</h5><div class="codeblock"><pre>${a.failure ? esc(a.failure) : `HTTP ${esc(a.status)}\n${esc(hdrs(a.response_headers))}${a.response_body ? '\n\n' + esc(a.response_body) : ''}`}</pre></div></div>
        </div></details>`).join('');
  }

  function consoleHtml(t) {
    return `<ul class="console-list">${t.console.map((c) => `<li><span class="lvl ${esc(c.level)}">${c.level === 'pageerror' ? 'uncaught' : esc(c.level)}</span><span class="at">+${fmtMs(c.at_ms)}</span>
      <div><pre>${esc(c.text)}</pre>${c.location ? `<small>${esc(c.location)}</small>` : ''}</div></li>`).join('')}</ul>`;
  }

  function networkHtml(t) {
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Method</th><th>Result</th><th>URL</th><th>Type</th><th class="num">At</th></tr></thead><tbody>
      ${t.network_failures.map((n) => `<tr><td><span class="method">${esc(n.method)}</span></td>
        <td><span class="http ${n.status ? (n.status >= 500 ? 'c5' : 'c4') : 'err'}">${esc(n.status || n.failure)}</span></td>
        <td class="mono" style="overflow-wrap:anywhere">${esc(n.url)}</td><td>${esc(n.resource_type)}</td><td class="num">+${fmtMs(n.at_ms)}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function attemptsHtml(t) {
    return `<table class="data-table"><thead><tr><th>Attempt</th><th>Status</th><th class="num">Duration</th><th>Failure reason</th><th>Category</th></tr></thead><tbody>
      ${t.attempts.map((a) => `<tr><td>#${a.attempt}</td><td>${badge(a.status)}</td><td class="num">${fmtMs(a.duration_ms)}</td><td class="mono">${esc(a.failure_reason)}</td><td>${esc(a.failure_category)}</td></tr>`).join('')}</tbody></table>`;
  }

  // ------------------------------------------------------------------ failures panel
  function renderFailuresPanel() {
    const panel = $('#panel-failures');
    const bad = TESTS.filter((t) => t._bad);
    if (!bad.length) {
      panel.innerHTML = `<div class="empty">${I.check}<p>No failed or blocked tests in this run.</p></div>`;
      return;
    }
    const byCat = new Map();
    bad.forEach((t) => { const c = t.failure_category || 'Uncategorised'; byCat.set(c, (byCat.get(c) || []).concat(t)); });
    const cats = Array.from(byCat.entries()).sort((a, b) => b[1].length - a[1].length);
    const shown = state.failCat ? cats.filter(([c]) => c === state.failCat) : cats;
    const byModule = {};
    bad.forEach((t) => { byModule[t.module] = (byModule[t.module] || 0) + 1; });
    panel.innerHTML = `<h2 class="print-title">Failure summary</h2>
      <div class="fail-cats no-print"><button type="button" class="chip" data-failcat="" aria-pressed="${!state.failCat}">All <span class="count">${bad.length}</span></button>
        ${cats.map(([c, l]) => `<button type="button" class="chip" data-failcat="${esc(c)}" aria-pressed="${state.failCat === c}">${esc(c)} <span class="count">${l.length}</span></button>`).join('')}</div>
      <div class="callout">${bad.length} test(s) need attention: ${SUM.failed} failed, ${SUM.blocked} blocked. Most affected modules: ${Object.entries(byModule).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([m, n]) => `<b>${esc(m)}</b> (${n})`).join(', ')}.</div>
      ${shown.map(([cat, list]) => `<div class="fail-group"><h3>${esc(cat)} <span class="count">${list.length}</span></h3><div class="fail-cards">${list.map(failCard).join('')}</div></div>`).join('')}`;
  }
  function failCard(t) {
    const shot = shots(t)[0];
    return `<article class="fcard${shot ? '' : ' no-shot'}"><div style="min-width:0">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${badge(t.status)}<span class="tc-id">${esc(t.id)}</span>${t.retries ? `<span class="tag">↻ ${t.retries}</span>` : ''}</div>
        <h4>${esc(t.title)}</h4><div class="where">${esc(t.module)} › ${esc(t.feature)} · ${fmtMs(t.duration_ms)}</div>
        <div class="why">${esc(t.failure_reason || 'No reason captured')}</div>
        <button type="button" class="btn btn-sm no-print" data-goto="${t._i}">View full details →</button></div>
      ${shot ? `<button type="button" class="thumb" data-gallery="${t._i}" data-idx="0" aria-label="Open failure screenshot"><img src="${artUrl(shot.path)}" alt="Failure screenshot of ${esc(t.id)}" loading="${state.print ? 'eager' : 'lazy'}"></button>` : ''}
    </article>`;
  }

  // ------------------------------------------------------------------ retries panel
  function retryRows() {
    return TESTS.filter((t) => (t.retries || 0) > 0 || flips(TEST_HISTORY[t.nodeid]) >= 2);
  }
  function renderRetriesPanel() {
    const panel = $('#panel-retries');
    const rows = retryRows().sort((a, b) => (b.retries || 0) - (a.retries || 0) || flips(TEST_HISTORY[b.nodeid]) - flips(TEST_HISTORY[a.nodeid]));
    const retried = TESTS.filter((t) => t.retries > 0);
    const flaky = TESTS.filter((t) => t.flaky);
    const failedAfter = retried.filter((t) => t.status !== 'PASS');
    const unstable = TESTS.filter((t) => flips(TEST_HISTORY[t.nodeid]) >= 2);
    const tile = (label, v, hint) => `<div class="tile"><span class="label">${label}</span><span class="value">${v}</span><span class="hint">${hint}</span></div>`;
    panel.innerHTML = `<div class="kpis" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin-top:0">
        ${tile('Retried tests', retried.length, 'needed more than one attempt')}
        ${tile('Flaky', flaky.length, 'failed first, passed on retry')}
        ${tile('Failed after retries', failedAfter.length, 'consistent failures')}
        ${tile('Unstable across runs', unstable.length, `status changed 2+ times in last ${Math.max(...Object.values(TEST_HISTORY).map((h) => h.length), 0)} runs`)}
      </div>
      ${retried.length ? '' : `<div class="callout" style="margin-top:12px">No retries in this run. Enable them with <code>pytest --reruns 2</code> (pytest-rerunfailures) or per test with <code>@pytest.mark.flaky(reruns=2)</code>; every attempt is recorded with its own screenshot and reason.</div>`}
      ${rows.length ? `<div class="card" style="margin-top:12px"><div class="table-scroll"><table class="data-table"><thead><tr><th>Test</th><th>Final</th><th>Attempts</th><th class="num">Retries</th><th>Recent runs</th><th class="num">Status changes</th><th></th></tr></thead><tbody>
        ${rows.map((t) => `<tr><td><span class="tc-id">${esc(t.id)}</span><br>${esc(t.title)}</td><td>${badge(t.status)}${t.flaky ? ' <span class="tag flaky">flaky</span>' : ''}</td>
          <td>${(t.attempts || []).map((a) => `<span class="badge s-${ST[a.status].cls}" data-tip="Attempt ${a.attempt}: ${ST[a.status].label}${a.failure_reason ? '\n' + esc(trunc(a.failure_reason, 160)) : ''}">${ST[a.status].icon}${a.attempt}</span>`).join(' ')}</td>
          <td class="num">${t.retries || 0}</td><td>${histDots(t)}</td><td class="num">${flips(TEST_HISTORY[t.nodeid])}</td>
          <td><button type="button" class="btn btn-sm" data-goto="${t._i}">Details</button></td></tr>`).join('')}</tbody></table></div></div>` : ''}`;
  }

  // ------------------------------------------------------------------ modules panel
  function renderModulesPanel() {
    const panel = $('#panel-modules');
    const mods = SUM.modules || [];
    panel.innerHTML = `<div class="card"><div class="table-scroll"><table class="data-table"><thead><tr><th>Module</th><th class="num">Total</th><th class="num">Passed</th><th class="num">Failed</th><th class="num">Blocked</th><th class="num">Skipped</th><th>Pass rate</th><th class="num">Test time</th></tr></thead><tbody>
      ${mods.map((m) => {
        const executed = m.total - m.SKIPPED, rate = pctOf(m.PASS, executed);
        const meter = STATUSES.map((s) => (m[s] ? `<i style="width:${(m[s] * 100) / m.total}%;background:${ST[s].color}"></i>` : '')).join('');
        return `<tr><td><button type="button" class="btn btn-ghost btn-sm" data-filter-module="${esc(m.module)}">${esc(m.module)} →</button></td>
          <td class="num">${m.total}</td><td class="num">${m.PASS}</td><td class="num">${m.FAIL}</td><td class="num">${m.BLOCKED}</td><td class="num">${m.SKIPPED}</td>
          <td style="min-width:160px"><div style="display:flex;gap:8px;align-items:center"><div class="meter" style="flex:1">${meter}</div><span class="mono">${rate}%</span></div></td>
          <td class="num">${fmtMs(m.duration_ms)}</td></tr>`;
      }).join('')}</tbody></table></div></div>`;
  }

  // ------------------------------------------------------------------ run panel
  function renderRunPanel() {
    const panel = $('#panel-run');
    const kv = (rows) => `<dl class="kv">${rows.filter((r) => r[1]).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
    const ci = RUN.ci || {};
    panel.innerHTML = `<h2 class="print-title">Run details</h2><div class="info-grid">
      <div class="card"><div class="card-head"><h3>Execution</h3></div><div class="card-body">${kv([
        ['Run ID', `<span class="mono">${esc(RUN.id)}</span>`], ['Run name', esc(RUN.name)], ['Started', fmtDate(RUN.start)], ['Finished', fmtDate(RUN.end)],
        ['Duration', fmtMs(RUN.duration_ms)], ['Workers', esc(RUN.workers)], ['pytest exit status', esc(RUN.exit_status)],
        ['Marker filter', RUN.markexpr ? `<span class="mono">${esc(RUN.markexpr)}</span>` : ''], ['Command', `<span class="mono">${esc(RUN.command)}</span>`],
        ['Run folder', `<span class="mono">${esc(RUN.dir)}</span>`]])}</div></div>
      <div class="card"><div class="card-head"><h3>Environment</h3></div><div class="card-body">${kv([
        ['Environment', esc(RUN.environment)], ['Application URL', esc(RUN.base_url)], ['Browser', esc(RUN.browser)], ['Build / release', esc(RUN.build)],
        ['Executed by', esc(RUN.executed_by)], ['CI', ci.provider ? (ci.url ? `<a href="${esc(ci.url)}" target="_blank" rel="noopener">${esc(ci.provider)} ${I.ext}</a>` : esc(ci.provider)) : 'Local'],
        ['Host', esc(RUN.hostname)], ['Platform', esc(RUN.platform)], ['Python', esc(RUN.python)], ['pytest', esc(RUN.pytest)], ['Playwright', esc(RUN.playwright)]])}</div></div>
    </div>
    <div class="card no-print" style="margin-top:12px"><div class="card-head"><div><h3>Run history</h3><p>Every recorded execution (reports/history/history.json)</p></div><a class="btn btn-sm" href="${REPORTS_ROOT}index.html">All runs ${I.ext}</a></div>
      <div class="card-body table-scroll"><table class="data-table"><thead><tr><th>Run</th><th>Started</th><th>Env</th><th>Build</th><th class="num">Total</th><th class="num">Pass</th><th class="num">Fail</th><th class="num">Blocked</th><th class="num">Skip</th><th class="num">Pass rate</th></tr></thead><tbody>
      ${HISTORY.slice().reverse().map((h) => `<tr><td>${h.run_id === RUN.id ? `<b>${esc(h.name)}</b> <span class="tag">this run</span>` : `<a href="${REPORTS_ROOT}${esc(h.report)}">${esc(h.name)}</a>`}<br><small class="mono" style="color:var(--muted)">${esc(h.run_id)}</small></td>
        <td>${fmtDate(h.start, false)}</td><td>${esc(h.environment)}</td><td>${esc(h.build)}</td><td class="num">${h.total}</td><td class="num">${h.passed}</td><td class="num">${h.failed}</td><td class="num">${h.blocked || 0}</td><td class="num">${h.skipped}</td><td class="num">${h.pass_rate}%</td></tr>`).join('')}
      </tbody></table></div></div>`;
  }

  // ------------------------------------------------------------------ tooltip
  const tip = $('#tooltip');
  function showTip(text, e) {
    tip.textContent = text;
    tip.hidden = false;
    moveTip(e);
  }
  function moveTip(e) {
    if (tip.hidden || !e) return;
    const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + pad, y = e.clientY + pad;
    if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
    tip.style.left = `${Math.max(8, x)}px`;
    tip.style.top = `${Math.max(8, y)}px`;
  }
  function hideTip() { tip.hidden = true; }
  document.addEventListener('mouseover', (e) => {
    const el = e.target.closest && e.target.closest('[data-tip]');
    if (el) showTip(el.getAttribute('data-tip'), e);
  });
  document.addEventListener('mousemove', (e) => { if (!tip.hidden) moveTip(e); });
  document.addEventListener('mouseout', (e) => {
    const el = e.target.closest && e.target.closest('[data-tip]');
    if (el && !el.contains(e.relatedTarget)) hideTip();
  });

  // ------------------------------------------------------------------ modal gallery
  const modal = { list: [], idx: 0, last: null };
  function openGallery(testIndex, idx) {
    const t = TESTS[testIndex];
    modal.list = shots(t).map((a) => ({ src: artUrl(a.path), caption: `${t.id} · ${a.title}${(t.attempts || []).length > 1 ? ` · attempt ${a.attempt}` : ''}` }));
    if (!modal.list.length) return;
    modal.idx = Math.max(0, Math.min(idx, modal.list.length - 1));
    modal.last = document.activeElement;
    $('#modal').hidden = false;
    document.body.style.overflow = 'hidden';
    showModalImage();
    $('#modal [data-modal="close"].btn').focus();
  }
  function showModalImage() {
    const item = modal.list[modal.idx];
    $('#modal-img').src = item.src;
    $('#modal-img').alt = item.caption;
    $('#modal-open').href = item.src;
    $('#modal-caption').textContent = `${item.caption}  (${modal.idx + 1}/${modal.list.length})`;
    $$('#modal [data-modal="prev"], #modal [data-modal="next"]').forEach((b) => { b.hidden = modal.list.length < 2; });
  }
  function closeModal() {
    $('#modal').hidden = true;
    document.body.style.overflow = '';
    if (modal.last && modal.last.focus) modal.last.focus();
  }

  // ------------------------------------------------------------------ navigation helpers
  function selectTab(key) {
    state.tab = key;
    $$('.tab').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === key)));
    $$('.panel').forEach((p) => { p.hidden = p.id !== `panel-${key}`; });
  }
  function resetFilters() {
    Object.assign(state, { q: '', module: '', type: '', feature: '', category: '', statuses: new Set(STATUSES), limit: 150 });
    renderTestsPanel();
  }
  function filterTo(patch) {
    resetFilters();
    Object.assign(state, patch);
    selectTab('tests');
    renderTestsPanel();
    $('#panel-tests').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  function gotoTest(i) {
    const t = TESTS[i];
    if (!t) return;
    selectTab('tests');
    if (!matches(t)) resetFilters();
    state.collapsed.delete(t.module);
    const pos = visibleTests().indexOf(t);
    if (pos >= state.limit) state.limit = pos + 20;
    state.open.add(i);
    updateList();
    const el = document.getElementById(`tc-${i}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
    }
    try { history.replaceState(null, '', `#test=${encodeURIComponent(t.nodeid)}`); } catch (e) { /* file:// in some browsers */ }
  }

  // ------------------------------------------------------------------ exports
  function download(name, mime, text) {
    const blob = new Blob([text], { type: mime });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
  }
  const csvCell = (v) => { const s = v == null ? '' : String(v); return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  function exportCsv() {
    const cols = [['Test Case ID', (t) => t.id], ['Test Case Name', (t) => t.title], ['Module', (t) => t.module], ['Feature/Flow', (t) => t.feature],
      ['Type', (t) => (t.types || []).join(', ')], ['Preconditions', (t) => (t.preconditions || []).join('\n')],
      ['Test Data', (t) => Object.entries(t.test_data || {}).map(([k, v]) => `${k} = ${typeof v === 'string' ? v : JSON.stringify(v)}`).join('\n')],
      ['Steps', (t) => (t.steps || []).filter((s) => s.kind === 'step').map((s, i) => `${i + 1}. ${s.title}${s.status === 'failed' ? ' [FAILED]' : ''}`).join('\n')],
      ['Expected Result', (t) => t.expected], ['Actual Result', (t) => t.actual], ['Status', (t) => t.status],
      ['Failure Reason', (t) => t.failure_reason], ['Failure Category', (t) => t.failure_category], ['Error', (t) => trunc(t.error, 30000)],
      ['Screenshots', (t) => shots(t).map((a) => a.path.startsWith('data:') ? '(embedded)' : a.path).join('\n')],
      ['Video', (t) => (t.artifacts || []).filter((a) => a.kind === 'video').map((a) => a.path).join('\n')],
      ['Start', (t) => t.start], ['End', (t) => t.end], ['Duration (s)', (t) => ((t.duration_ms || 0) / 1000).toFixed(2)],
      ['Browser', (t) => t.browser || RUN.browser], ['Environment', () => RUN.environment], ['Executed By', () => RUN.executed_by], ['Build', () => RUN.build],
      ['API Calls', (t) => (t.api_logs || []).length], ['Console Errors', (t) => (t.console || []).length], ['Network Failures', (t) => (t.network_failures || []).length],
      ['Retries', (t) => t.retries || 0], ['Flaky', (t) => (t.flaky ? 'yes' : 'no')], ['Node ID', (t) => t.nodeid]];
    const rows = [cols.map((c) => c[0])].concat(visibleTests().map((t) => cols.map((c) => c[1](t))));
    download(`${RUN.id || 'report'}-filtered.csv`, 'text/csv;charset=utf-8', '﻿' + rows.map((r) => r.map(csvCell).join(',')).join('\r\n'));
  }
  function exportJson() {
    download(`${RUN.id || 'report'}.json`, 'application/json', JSON.stringify(DATA, (k, v) => (k.startsWith('_') ? undefined : v), 2));
  }
  function exportHtml() {
    const clone = document.documentElement.cloneNode(true);
    clone.removeAttribute('data-theme');
    const app = clone.querySelector('#app');
    if (app) { app.innerHTML = ''; app.setAttribute('aria-busy', 'true'); }
    ['#modal', '#tooltip'].forEach((s) => { const el = clone.querySelector(s); if (el) el.hidden = true; });
    download(`${RUN.id || 'report'}.html`, 'text/html;charset=utf-8', '<!doctype html>\n' + clone.outerHTML);
  }
  function printReport() {
    window.print();
  }

  // ------------------------------------------------------------------ theme
  const THEME_KEY = 'snxt-report-theme';
  function currentTheme() {
    return document.documentElement.getAttribute('data-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  }
  function paintThemeButton() {
    const btn = $('#theme-btn');
    if (btn) btn.innerHTML = `${currentTheme() === 'dark' ? I.sun : I.moon}<span class="label-text">${currentTheme() === 'dark' ? 'Light' : 'Dark'}</span>`;
  }
  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) { /* storage blocked */ }
    if (saved === 'dark' || saved === 'light') document.documentElement.setAttribute('data-theme', saved);
  }

  // ------------------------------------------------------------------ copy
  function copyText(text, btn) {
    const done = () => { if (!btn) return; const old = btn.innerHTML; btn.innerHTML = `${I.check}Copied`; setTimeout(() => { btn.innerHTML = old; }, 1200); };
    const fallback = () => {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { /* ignore */ }
      ta.remove();
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
    else fallback();
  }

  // ------------------------------------------------------------------ events
  function bindEvents() {
    document.addEventListener('click', (e) => {
      const el = e.target.closest('button, a, [data-filter-status], [data-filter-module], [data-filter-category], [data-modal]');
      if (!el) return;
      const d = el.dataset;
      const menu = $('#export-menu');
      if (el.id !== 'export-btn' && !el.closest('#export-menu') && !menu.hidden) { menu.hidden = true; $('#export-btn').setAttribute('aria-expanded', 'false'); }

      if (el.id === 'export-btn') { menu.hidden = !menu.hidden; el.setAttribute('aria-expanded', String(!menu.hidden)); return; }
      if (d.export) {
        menu.hidden = true;
        ({ pdf: () => (RUN.pdf ? window.open('report.pdf', '_blank') : printReport()), print: printReport, html: exportHtml, csv: exportCsv, json: exportJson }[d.export] || (() => {}))();
        return;
      }
      if (el.id === 'theme-btn') {
        const next = currentTheme() === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        try { localStorage.setItem(THEME_KEY, next); } catch (err) { /* storage blocked */ }
        paintThemeButton();
        renderTrendChart();
        return;
      }
      if (d.modal) {
        if (d.modal === 'close' && (e.target === el || el.tagName === 'BUTTON')) closeModal();
        if (d.modal === 'prev') { modal.idx = (modal.idx - 1 + modal.list.length) % modal.list.length; showModalImage(); }
        if (d.modal === 'next') { modal.idx = (modal.idx + 1) % modal.list.length; showModalImage(); }
        return;
      }
      if (d.tab) { selectTab(d.tab); return; }
      if (d.toggleTable) {
        const card = document.getElementById(`card-${d.toggleTable}`);
        const showTable = el.getAttribute('aria-pressed') !== 'true';
        el.setAttribute('aria-pressed', String(showTable));
        el.textContent = showTable ? 'Chart' : 'Table';
        $('.chart-view', card).hidden = showTable;
        $('.table-view', card).hidden = !showTable;
        return;
      }
      if (d.filterStatus) { filterTo({ statuses: new Set([d.filterStatus]) }); return; }
      if (d.filterModule) { filterTo({ module: d.filterModule }); return; }
      if (d.filterCategory) { filterTo({ category: d.filterCategory }); return; }
      if (d.chip) {
        const s = d.chip;
        if (e.altKey || e.metaKey || e.ctrlKey) state.statuses = new Set([s]);           // modifier-click: only this status
        else if (state.statuses.has(s)) state.statuses.delete(s); else state.statuses.add(s);
        if (!state.statuses.size) state.statuses = new Set(STATUSES);
        $$('[data-chip]').forEach((c) => c.setAttribute('aria-pressed', String(state.statuses.has(c.dataset.chip))));
        state.limit = 150; updateList(); return;
      }
      if (d.failcat !== undefined) { state.failCat = d.failcat; renderFailuresPanel(); return; }
      if (d.gallery !== undefined) { openGallery(+d.gallery, +d.idx || 0); return; }
      if (d.goto !== undefined) { gotoTest(+d.goto); return; }
      if (d.copy !== undefined) { copyText(d.copy, el); return; }
      if (d.subtab) {
        const body = el.closest('.tc-body');
        $$('.subtab', body).forEach((b) => b.setAttribute('aria-selected', String(b === el)));
        $$('.subpanel', body).forEach((p) => { p.hidden = p.dataset.subpanel !== d.subtab; });
        return;
      }
      switch (d.act) {
        case 'toggle': {
          const row = el.closest('.tc'), i = +row.dataset.i, body = $('.tc-body', row);
          const open = !state.open.has(i);
          if (open) { state.open.add(i); if (!body.innerHTML.trim()) body.innerHTML = detailsHtml(TESTS[i]); } else state.open.delete(i);
          body.hidden = !open; row.classList.toggle('open', open); el.setAttribute('aria-expanded', String(open));
          if (open) { try { history.replaceState(null, '', `#test=${encodeURIComponent(TESTS[i].nodeid)}`); } catch (err) { /* ignore */ } }
          break;
        }
        case 'group': {
          const g = el.closest('.group'), mod = g.dataset.module;
          const collapsed = g.dataset.collapsed !== 'true';
          g.dataset.collapsed = String(collapsed); el.setAttribute('aria-expanded', String(!collapsed));
          if (collapsed) state.collapsed.add(mod); else state.collapsed.delete(mod);
          break;
        }
        case 'more': state.limit += 150; updateList(); break;
        case 'reset': resetFilters(); break;
        case 'expand-all': visibleTests().slice(0, state.limit).forEach((t) => state.open.add(t._i)); state.collapsed.clear(); updateList(); break;
        case 'collapse-all': state.open.clear(); updateList(); break;
        default: break;
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.target.closest && e.target.closest('[data-filter-status][role="button"]') && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault(); filterTo({ statuses: new Set([e.target.closest('[data-filter-status]').dataset.filterStatus]) }); return;
      }
      if (!$('#modal').hidden) {
        if (e.key === 'Escape') closeModal();
        if (e.key === 'ArrowRight' && modal.list.length > 1) { modal.idx = (modal.idx + 1) % modal.list.length; showModalImage(); }
        if (e.key === 'ArrowLeft' && modal.list.length > 1) { modal.idx = (modal.idx - 1 + modal.list.length) % modal.list.length; showModalImage(); }
        return;
      }
      if (e.key === 'Escape') { const m = $('#export-menu'); if (!m.hidden) { m.hidden = true; $('#export-btn').focus(); } }
      if (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
        e.preventDefault(); selectTab('tests'); const q = $('#q'); if (q) q.focus();
      }
    });

    let qTimer = null;
    document.addEventListener('input', (e) => {
      if (e.target.id === 'q') {
        clearTimeout(qTimer);
        qTimer = setTimeout(() => { state.q = e.target.value.trim(); state.limit = 150; updateList(); }, 120);
      }
    });
    document.addEventListener('change', (e) => {
      const id = e.target.id;
      const map = { 'f-module': 'module', 'f-type': 'type', 'f-feature': 'feature', 'f-category': 'category', 'f-sort': 'sort' };
      if (map[id]) { state[map[id]] = e.target.value; state.limit = 150; updateList(); }
      if (id === 'f-group') { state.group = e.target.checked; updateList(); }
    });

    let rTimer = null;
    window.addEventListener('resize', () => { clearTimeout(rTimer); rTimer = setTimeout(renderTrendChart, 150); });
    window.addEventListener('beforeprint', () => { state.print = true; renderPanels(); });
    window.addEventListener('afterprint', () => { state.print = PRINT_QUERY; renderPanels(); selectTab(state.tab); });
    if (window.matchMedia) {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      const onChange = () => { paintThemeButton(); renderTrendChart(); };
      if (mq.addEventListener) mq.addEventListener('change', onChange);
    }
  }

  function renderPanels() {
    renderTestsPanel(); renderFailuresPanel(); renderRetriesPanel(); renderModulesPanel(); renderRunPanel();
  }

  // ------------------------------------------------------------------ boot
  function boot() {
    initTheme();
    renderShell();
    paintThemeButton();
    renderCharts();
    renderPanels();
    bindEvents();
    selectTab('tests');
    const m = /#test=(.+)$/.exec(location.hash);
    if (m) {
      const nodeid = decodeURIComponent(m[1]);
      const t = TESTS.find((x) => x.nodeid === nodeid);
      if (t) setTimeout(() => gotoTest(t._i), 50);
    }
    const images = $$('img').filter((img) => img.loading !== 'lazy' && !img.complete);
    Promise.all(images.map((img) => new Promise((r) => { img.onload = img.onerror = r; }))).then(() => { window.__reportReady = true; });
    setTimeout(() => { window.__reportReady = true; }, 20000);   // never block PDF generation forever
  }
  boot();
})();
