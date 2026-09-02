'use strict';
/* SF-Panel — app.js (i18n · neon) — requires i18n.js */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

let TOKEN = localStorage.getItem('sf_token') || '';
let USER  = localStorage.getItem('sf_user') || '';
let PAAS = false, VIEW = 'dashboard', POLL = null, POLL_MS = 6000;
let inboundsCache = [], clientsCache = [], chartSeries = [];
let currentModal = null;

(function () {
    const c = document.createElement('style');
    c.textContent = [
        '.chk-list{display:flex;flex-direction:column;gap:8px;max-height:220px;overflow-y:auto;padding:4px;border:1px solid var(--bd);border-radius:12px}',
        '.chk-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:9px;cursor:pointer;font-size:.82rem}',
        '.chk-item:hover{background:rgba(0,255,157,.06)}',
        '.chk-item input{width:16px;height:16px;accent-color:#00ff9d;cursor:pointer}',
        '.chk-item.dis{opacity:.45;cursor:not-allowed}',
        '.exp-flex{display:flex;gap:10px}.exp-flex select{width:150px!important;flex-shrink:0}',
        '.qr-mini{margin-top:10px;text-align:center}.qr-mini svg{width:200px;height:200px;background:#fff;border-radius:12px;border:1px solid var(--bd);padding:8px}',
        '.btn-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}',
        '.tag-list{display:flex;flex-wrap:wrap;gap:5px}',
        '.modal-err{color:var(--bad);font-size:.8rem;min-height:18px;margin-top:8px}',
    ].join('\n');
    document.head.appendChild(c);
})();

/* ---------- toast / modal / copy ---------- */
function toast(msg, type = '') {
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    $('toastWrap').appendChild(el);
    setTimeout(() => { el.classList.add('out');
        setTimeout(() => el.remove(), 260); }, 3200);
}
function openModal(title, body, foot, wide) {
    currentModal = true;
    $('modalTitle').textContent = title;
    $('modalBody').innerHTML = body;
    $('modalFoot').innerHTML = foot || '';
    $('modalCard').classList.toggle('wide', !!wide);
    $('modalBack').classList.remove('hidden');
}
function closeModal() {
    $('modalBack').classList.add('hidden');
    $('modalBody').innerHTML = '';
    $('modalFoot').innerHTML = '';
    currentModal = null;
}
function confirmBox(title, msg, onYes) {
    openModal(title,
        `<div style="font-size:.9rem;line-height:2;color:var(--tx2)">${esc(msg)}</div>`,
        `<button class="btn btn-bad" id="cfYes">${esc(I('common.yes'))}</button>
         <button class="btn" id="cfNo">${esc(I('common.cancel'))}</button>`);
    $('cfYes').onclick = () => { closeModal(); onYes(); };
    $('cfNo').onclick = closeModal;
}
async function copyText(text) {
    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
        } else {
            const ta = document.createElement('textarea');
            ta.value = text; ta.style.cssText = 'position:fixed;opacity:0';
            document.body.appendChild(ta); ta.select();
            document.execCommand('copy'); ta.remove();
        }
        toast(I('common.copied'), 'ok');
    } catch (e) { toast(I('common.copyFail'), 'err'); }
}

/* ---------- فرمت‌ها ---------- */
function fmtBytes(n) {
    n = Number(n) || 0;
    const neg = n < 0; n = Math.abs(n);
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    for (const u of units) {
        if (n < 1024 || u === 'PB') {
            const s = (u === 'B') ? Math.round(n) + ' B'
                : n.toFixed(2).replace(/\.?0+$/, '') + ' ' + u;
            return (neg ? '-' : '') + s;
        }
        n /= 1024;
    }
    return '0 B';
}
function fmtExpiryHtml(ms) {
    if (!ms) return '<span class="badge b-def">∞</span>';
    const left = ms - Date.now();
    if (left <= 0) return `<span class="badge b-bad">${esc(I('cl.badgeExpired'))}</span>`;
    const d = Math.floor(left / 86400000);
    if (d > 0) return `<span class="badge ${d < 3 ? 'b-bad' : d < 7 ? 'b-warn' : 'b-ok'}">${esc(I('cl.daysLeft', d))}</span>`;
    const h = Math.floor(left / 3600000);
    return `<span class="badge ${h < 6 ? 'b-bad' : 'b-warn'}">${esc(I('cl.hoursLeft', h))}</span>`;
}
function newUuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}
function toLocalInput(ms) {
    if (!ms) return '';
    const d = new Date(ms), p = x => String(x).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/* ---------- API ---------- */
async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (opts.body !== undefined && !(opts.body instanceof FormData))
        headers['Content-Type'] = 'application/json';
    if (TOKEN) headers['Authorization'] = 'Bearer ' + TOKEN;
    const init = { method: opts.method || 'GET', headers };
    if (opts.body !== undefined)
        init.body = (opts.body instanceof FormData) ? opts.body
                    : JSON.stringify(opts.body);
    const res = await fetch(path, init);
    if (res.status === 401) { doLogout(); throw new Error(I('er.sessionExpired')); }
    let data = null;
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (!res.ok) throw new Error((data && data.error) || ('HTTP ' + res.status));
    return data;
}
async function fetchQrSvg(text) {
    try {
        const res = await fetch('/api/qr?text=' + encodeURIComponent(text),
            { headers: { 'Authorization': 'Bearer ' + TOKEN } });
        return res.ok ? await res.text() : '';
    } catch (e) { return ''; }
}
function btnLoad(btn, on = true) {
    if (!btn) return;
    btn.classList.toggle('loading', on);
    btn.disabled = on;
}
function setPill(el, cls, text) {
    if (!el) return;
    el.className = 'pill ' + (cls || '');
    el.innerHTML = `<span class="dot"></span> ${esc(text)}`;
}

/* ═══════════════ Auth ═══════════════ */
async function initAuth() {
    try {
        const st = await api('/api/status');
        $('authVer').textContent = st.version || '—';
        setPill($('authXrayState'), st.xray.running ? 'ok' : 'bad',
                'Xray ' + (st.xray.running ? '✓' : '✗'));
        if (st.setup_done) {
            $('authBrandSub').textContent = I('auth.loginToPanel');
            $('loginForm').classList.remove('hidden');
        } else {
            $('authBrandSub').textContent = I('auth.setup');
            $('setupForm').classList.remove('hidden');
        }
        if (TOKEN) {
            try {
                const me = await api('/api/me');
                USER = me.username; PAAS = !!me.paas;
                enterApp();
                return;
            } catch (e) { TOKEN = ''; localStorage.removeItem('sf_token'); }
        }
    } catch (e) {
        $('authBrandSub').textContent = I('auth.errConnFail');
        $('authErr').textContent = I('auth.connError');
    }
}
async function doLogin() {
    const btn = $('authBtn');
    $('authErr').textContent = '';
    btnLoad(btn, true);
    try {
        const body = {
            username: $('authUser').value.trim(),
            password: $('authPass').value,
        };
        if (!$('totpField').classList.contains('hidden'))
            body.code = $('authCode').value.trim();
        const r = await api('/api/login', { method: 'POST', body });
        TOKEN = r.token; USER = r.username;
        localStorage.setItem('sf_token', TOKEN);
        localStorage.setItem('sf_user', USER);
        toast(I('auth.welcome', USER), 'ok');
        const me = await api('/api/me');
        PAAS = !!me.paas;
        enterApp();
    } catch (e) {
        const m = e.message || '';
        if (m.includes('دومرحله') || m.includes('کد') || m.includes('2FA')) {
            $('totpField').classList.remove('hidden');
            $('authCode').focus();
            $('authErr').textContent = I('auth.enter2fa');
        } else $('authErr').textContent = m;
    } finally { btnLoad(btn, false); }
}
async function doSetup() {
    const btn = $('setupBtn');
    $('setupErr').textContent = '';
    if ($('setupPass').value !== $('setupPass2').value) {
        $('setupErr').textContent = I('auth.pwMismatch'); return;
    }
    btnLoad(btn, true);
    try {
        const r = await api('/api/setup', { method: 'POST', body: {
            username: $('setupUser').value.trim(),
            password: $('setupPass').value } });
        TOKEN = r.token; USER = r.username;
        localStorage.setItem('sf_token', TOKEN);
        localStorage.setItem('sf_user', USER);
        toast(I('auth.installed'), 'ok');
        const me = await api('/api/me');
        PAAS = !!me.paas;
        enterApp();
    } catch (e) { $('setupErr').textContent = e.message; }
    finally { btnLoad(btn, false); }
}
function doLogout() {
    TOKEN = ''; USER = '';
    localStorage.removeItem('sf_token');
    localStorage.removeItem('sf_user');
    if (POLL) { clearInterval(POLL); POLL = null; }
    location.reload();
}

/* ═══════════════ Shell ═══════════════ */
const VIEW_META = {
    dashboard: ['nav.dashboard', 'view.dashboard.sub'],
    inbounds:  ['nav.inbounds',  'view.inbounds.sub'],
    clients:   ['nav.clients',   'view.clients.sub'],
    settings:  ['nav.settings',  'view.settings.sub'],
    xray:      ['nav.xray',      'view.xray.sub'],
    logs:      ['nav.logs',      'view.logs.sub'],
};
function refreshViewTitles() {
    const meta = VIEW_META[VIEW] || [VIEW, ''];
    $('viewTitle').textContent = I(meta[0]);
    $('viewSub').textContent = I(meta[1]);
}
function enterApp() {
    $('authWrap').classList.add('hidden');
    $('appWrap').classList.remove('hidden');
    $('verTag').textContent = $('authVer').textContent || '—';
    setPill($('modePill'), '', I(PAAS ? 'nav.paasMode' : 'nav.vpsMode'));
    setPill($('xrayPill'), 'warn', 'Xray …');
    switchView('dashboard');
    startPolling();
}
function switchView(name) {
    VIEW = name;
    document.querySelectorAll('.nav-item').forEach(n =>
        n.classList.toggle('active', n.dataset.view === name));
    document.querySelectorAll('.view').forEach(v =>
        v.classList.toggle('hidden', v.id !== 'view-' + name));
    refreshViewTitles();
    closeSidebar();
    if (name === 'dashboard') loadDashboard();
    if (name === 'inbounds')  loadInbounds();
    if (name === 'clients')   loadClients();
    if (name === 'settings')  loadSettings();
    if (name === 'xray')      loadXrayView();
    if (name === 'logs')      loadLogs();
}
function startPolling() {
    if (POLL) clearInterval(POLL);
    POLL = setInterval(async () => {
        try {
            const d = await api('/api/dashboard');
            POLL_MS = Math.max(3, d.interval || 6) * 1000;
            setPill($('xrayPill'), d.xray.running ? 'ok' : 'bad',
                    'Xray ' + (d.xray.running ? '✓' : '✗'));
            if (VIEW === 'dashboard') renderDashboard(d);
        } catch (e) { /* silent */ }
    }, POLL_MS);
}

/* ═══════════════ Dashboard ═══════════════ */
async function loadDashboard() {
    try {
        const d = await api('/api/dashboard');
        if (d.interval) {
            const want = Math.max(3, d.interval) * 1000;
            if (Math.abs(want - POLL_MS) > 500) { POLL_MS = want; startPolling(); }
        }
        renderDashboard(d);
    } catch (e) { toast(e.message, 'err'); }
}
function renderDashboard(d) {
    const s = d.sys;
    $('stCpu').textContent = s.cpu + '%';
    $('stCpuBar').style.width = Math.min(100, s.cpu) + '%';
    $('stCpuBar').className = s.cpu > 85 ? 'bad' : s.cpu > 60 ? 'warn' : '';
    $('stMem').textContent = s.mem.pct + '%';
    $('stMemBar').style.width = Math.min(100, s.mem.pct) + '%';
    $('stMemBar').className = s.mem.pct > 85 ? 'bad' : s.mem.pct > 65 ? 'warn' : '';
    $('stMemSub').textContent = I('dash.ofTotal', fmtBytes(s.mem.used), fmtBytes(s.mem.total));
    $('stDisk').textContent = s.disk.pct + '%';
    $('stDiskBar').style.width = Math.min(100, s.disk.pct) + '%';
    $('stDiskBar').className = s.disk.pct > 85 ? 'bad' : s.disk.pct > 65 ? 'warn' : '';
    $('stDiskSub').textContent = I('dash.ofTotal', fmtBytes(s.disk.used), fmtBytes(s.disk.total));
    $('stNet').textContent = fmtBytes(s.net.up + s.net.down) + '/s';
    $('stNetSub').textContent = '↑ ' + fmtBytes(s.net.up) + '   ↓ ' + fmtBytes(s.net.down);
    $('stToday').textContent = '↑ ' + fmtBytes(d.traffic.today_up) + '  ↓ ' + fmtBytes(d.traffic.today_down);
    $('stTotal').textContent = fmtBytes(d.traffic.up + d.traffic.down);
    $('stClients').textContent = `${d.counts.clients_active} / ${d.counts.clients}`;
    $('stConns').textContent = d.paas ? d.counts.conns : '—';

    setPill($('xrayState'), d.xray.running ? 'ok' : (d.xray.starting ? 'warn' : 'bad'),
        I(d.xray.running ? 'dash.running' : d.xray.starting ? 'dash.starting' : 'dash.stopped'));
    $('xrayVer').textContent = d.xray.version || '—';
    $('xrayUptime').textContent = fmtDur(d.xray.uptime);
    $('xrayRestarts').textContent = d.xray.restarts ?? '—';

    $('topUsers').innerHTML = (d.top || []).map(c => `
        <tr><td><b>${esc(c.email)}</b></td>
        <td>${fmtBytes(c.up + c.down)}</td>
        <td>${c.enable ? `<span class="badge b-ok">${esc(I('common.enabledBadge'))}</span>`
                       : `<span class="badge b-bad">${esc(I('common.disabledBadge'))}</span>`}</td></tr>`
    ).join('') || `<tr><td colspan="3" class="muted">${esc(I('common.noData'))}</td></tr>`;

    const lv = { ok: 'ok', err: 'err', warn: 'warn', info: 'info' };
    $('dashEvents').innerHTML = (d.events || []).map(e => `
        <li><span class="lv ${lv[e.level] || 'info'}"></span>${esc(e.msg)}
            <span class="ts">${fmtTs(e.ts)}</span></li>`).join('')
        || `<li class="muted">—</li>`;

    chartSeries = d.series || [];
    drawChart();
}
function drawChart() {
    const cv = $('chart');
    if (!cv) return;
    const ctx = cv.getContext('2d');
    const w = cv.parentElement.clientWidth || 600, h = 180;
    const dpr = window.devicePixelRatio || 1;
    cv.width = w * dpr; cv.height = h * dpr;
    cv.style.width = w + 'px'; cv.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const padL = 56, padR = 8, padT = 10, padB = 22;
    const iw = w - padL - padR, ih = h - padT - padB;
    const data = chartSeries;
    if (!data || data.length < 2) {
        ctx.fillStyle = '#5d7a6b';
        ctx.font = '12px Vazirmatn, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(I('dash.waiting'), w / 2, h / 2);
        return;
    }
    const max = Math.max(2048, ...data.map(p => Math.max(p.up || 0, p.d || 0))) * 1.18;
    for (let i = 0; i <= 4; i++) {
        const y = padT + ih - (ih * i / 4);
        ctx.strokeStyle = 'rgba(0,255,157,.08)';
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
        ctx.fillStyle = '#5d7a6b'; ctx.font = '9px Vazirmatn, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(fmtBytes(max * i / 4), 2, y + 3);
    }
    const step = iw / (data.length - 1);
    const drawSeries = (key, color) => {
        ctx.beginPath();
        data.forEach((p, i) => {
            const x = padL + i * step;
            const y = padT + ih - ((p[key] || 0) / max) * ih;
            i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        });
        ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
        ctx.lineTo(padL + iw, padT + ih); ctx.lineTo(padL, padT + ih);
        ctx.closePath(); ctx.fillStyle = color + '22'; ctx.fill();
    };
    drawSeries('up', '#00ffd1');
    drawSeries('d', '#39d0ff');
    ctx.fillStyle = '#5d7a6b'; ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    const every = Math.max(1, Math.floor(data.length / 6));
    for (let i = 0; i < data.length; i += every) {
        const x = Math.min(padL + i * step, w - padR - 16);
        const dt = new Date(data[i].t * 1000);
        ctx.fillText(String(dt.getHours()).padStart(2, '0') + ':' +
            String(dt.getMinutes()).padStart(2, '0'), x, h - 6);
    }
}

/* ═══════════════ Inbounds ═══════════════ */
async function loadInbounds() {
    try {
        inboundsCache = await api('/api/inbounds');
        renderInbounds();
    } catch (e) { toast(e.message, 'err'); }
}
function renderInbounds() {
    const q = ($('inboundSearch').value || '').trim().toLowerCase();
    const rows = inboundsCache.filter(r =>
        !q || (r.remark || '').toLowerCase().includes(q) || r.protocol.includes(q));
    $('inboundsCount').textContent = I('ib.count', rows.length);
    $('inboundsEmpty').classList.toggle('hidden', rows.length > 0);

    $('inboundsTbody').innerHTML = rows.map(r => {
        const g = r.config || {};
        let detail;
        if (PAAS) {
            detail = `<span class="mono">${esc(g.transport || 'ws')}</span> → <span class="mono">${esc(g.path || '')}</span>`;
        } else {
            detail = `Port <b>${esc(g.port)}</b> · <span class="mono">${esc(g.transport || 'tcp')}/${esc(g.security || 'none')}</span>`;
            if (g.path) detail += `<div class="cell-sub mono">${esc(g.path)}</div>`;
        }
        return `<tr>
            <td><label class="sw"><input type="checkbox" ${r.enable ? 'checked' : ''}
                data-tgl-ib="${r.id}"><span></span></label></td>
            <td><b>${esc(r.remark)}</b></td>
            <td><span class="badge b-${r.protocol}">${r.protocol.toUpperCase()}</span></td>
            <td>${detail}</td>
            <td>${r.clients}</td>
            <td>${fmtBytes(r.up + r.down)}</td>
            <td><div class="acts">
                <button class="btn-icon" title="${esc(I('common.edit'))}" data-edit-ib="${r.id}">✏️</button>
                <button class="btn-icon" title="${esc(I('common.delete'))}" data-del-ib="${r.id}">🗑</button>
            </div></td></tr>`;
    }).join('');

    const tb = $('inboundsTbody');
    tb.querySelectorAll('[data-tgl-ib]').forEach(el =>
        el.onchange = () => toggleInbound(el.dataset.tglIb));
    tb.querySelectorAll('[data-edit-ib]').forEach(el =>
        el.onclick = () => inboundForm(inboundsCache.find(x => x.id == el.dataset.editIb)));
    tb.querySelectorAll('[data-del-ib]').forEach(el =>
        el.onclick = () => deleteInbound(el.dataset.delIb));
}
async function toggleInbound(id) {
    try { await api(`/api/inbounds/${id}/toggle`, { method: 'POST' });
          await loadInbounds(); }
    catch (e) { toast(e.message, 'err'); loadInbounds(); }
}
function deleteInbound(id) {
    const r = inboundsCache.find(x => x.id == id);
    confirmBox(I('ib.delTitle'), I('ib.delMsg', r ? r.remark : id), async () => {
        try {
            const res = await api(`/api/inbounds/${id}`, { method: 'DELETE' });
            toast(I('ib.deleted'), 'ok');
            if (res.xray_error) toast(I('ib.xrayWarn', res.xray_error), 'err');
            loadInbounds();
        } catch (e) { toast(e.message, 'err'); }
    });
}

const SS_METHODS = ['aes-256-gcm', 'aes-128-gcm',
                    'chacha20-poly1305', 'xchacha20-poly1305'];

function inboundForm(row) {
    const isNew = !row;
    const g = row ? (row.config || {}) : {};
    const proto = g.protocol || 'vless';

    const protoOpts = ['vless', 'vmess', 'trojan', 'shadowsocks']
        .map(p => `<option value="${p}" ${proto === p ? 'selected' : ''}
            ${PAAS && p === 'shadowsocks' ? 'disabled' : ''}>${p.toUpperCase()}</option>`).join('');
    const trKeys = PAAS ? ['ws', 'httpupgrade']
                         : ['tcp', 'ws', 'grpc', 'httpupgrade'];
    const trSel = g.transport || (PAAS ? 'ws' : 'tcp');
    const trOpts = trKeys.map(v =>
        `<option value="${v}" ${trSel === v ? 'selected' : ''}>${esc(I('ib.tr.' + v, v))}</option>`).join('');
    const secSel = g.security || 'none';
    const secOpts = [['none', I('ib.sec.none')], ['tls', I('ib.sec.tls')],
                     ['reality', I('ib.sec.reality')]]
        .map(([v, t]) => `<option value="${v}" ${secSel === v ? 'selected' : ''}>${esc(t)}</option>`).join('');
    const methodOpts = SS_METHODS.map(m =>
        `<option ${g.method === m ? 'selected' : ''}>${m}</option>`).join('');
    const r = g.reality || {};

    const paasFields = `
        <div class="form-grid">
            <div class="f"><label>${esc(I('ib.transport'))}</label>
                <select id="ibTransport">${trOpts}</select></div>
            <div class="f"><label>${esc(I('ib.path'))}</label>
                <input id="ibPath" class="ltr" value="${esc(g.path || '')}" placeholder="/sf-xxx"></div>
        </div>
        <div class="hint">${esc(I('ib.paasHint'))}</div>`;

    const vpsFields = `
        <div class="form-grid">
            <div class="f"><label>${esc(I('ib.port'))}</label>
                <input id="ibPort" type="number" min="1" max="65535" value="${esc(g.port || 443)}"></div>
            <div class="f"><label>${esc(I('ib.transport'))}</label>
                <select id="ibTransport">${trOpts}</select></div>
        </div>
        <div class="form-grid">
            <div class="f"><label id="ibPathLbl">${esc(I('ib.path'))}</label>
                <input id="ibPath" class="ltr" value="${esc(g.path || '')}" placeholder="/mypath"></div>
            <div class="f" id="ibHostRow"><label>${esc(I('ib.host'))}</label>
                <input id="ibHost" class="ltr" value="${esc(g.host || '')}"></div>
        </div>
        <div class="f"><label>${esc(I('ib.security'))}</label>
            <select id="ibSecurity">${secOpts}</select></div>
        <div id="ibTlsBox" class="hidden">
            <div class="form-grid">
                <div class="f"><label>${esc(I('ib.sni'))}</label>
                    <input id="ibSni" class="ltr" value="${esc(g.sni || '')}"></div>
                <div class="f"><label>${esc(I('ib.alpn'))}</label>
                    <input id="ibAlpn" class="ltr" value="${esc(g.alpn || 'http/1.1')}"></div>
            </div>
            <div class="form-grid">
                <div class="f"><label>${esc(I('ib.certFile'))}</label>
                    <input id="ibCert" class="ltr" value="${esc(g.certFile || '')}"></div>
                <div class="f"><label>${esc(I('ib.keyFile'))}</label>
                    <input id="ibKey" class="ltr" value="${esc(g.keyFile || '')}"></div>
            </div>
            <div class="btn-row">
                <button class="btn btn-sm" id="ibBtnCert" type="button">📜 ${esc(I('ib.genCert'))}</button>
                <label class="sw-row" style="margin-inline-start:8px">
                    <span class="sw"><input type="checkbox" id="ibSelfsg" ${g.selfsigned ? 'checked' : ''}><span></span></span>
                    <span>${esc(I('ib.selfsigned'))}</span></label>
            </div>
        </div>
        <div id="ibRealityBox" class="hidden">
            <div class="form-grid">
                <div class="f"><label>${esc(I('ib.rDest'))}</label>
                    <input id="ibRDest" class="ltr" value="${esc(r.dest || 'www.microsoft.com:443')}"></div>
                <div class="f"><label>${esc(I('ib.rServerNames'))}</label>
                    <input id="ibRNames" class="ltr" value="${esc((r.serverNames || []).join(','))}"></div>
            </div>
            <div class="form-grid">
                <div class="f"><label>${esc(I('ib.rPrivateKey'))}</label>
                    <input id="ibRPriv" class="ltr" value="${esc(r.privateKey || '')}"></div>
                <div class="f"><label>${esc(I('ib.rPublicKey'))}</label>
                    <input id="ibRPub" class="ltr" value="${esc(r.publicKey || '')}"></div>
            </div>
            <div class="f"><label>${esc(I('ib.rShortIds'))}</label>
                <input id="ibRSids" class="ltr" value="${esc((r.shortIds || []).join(','))}"></div>
            <button class="btn btn-sm" id="ibBtnKeys" type="button">🔑 ${esc(I('ib.genKeys'))}</button>
        </div>`;

    const ssBox = `
        <div id="ibSsBox" class="hidden">
            <div class="form-grid">
                <div class="f"><label>${esc(I('ib.ssMethod'))}</label>
                    <select id="ibMethod">${methodOpts}</select></div>
                <div class="f"><label>${esc(I('ib.ssPassword'))}</label>
                    <input id="ibPass" class="ltr" value="${esc(g.password || '')}"></div>
            </div>
        </div>`;

    openModal(isNew ? I('ib.new') : I('ib.editTitle'), `
        <div class="form-grid">
            <div class="f"><label>${esc(I('ib.remark'))}</label>
                <input id="ibRemark" value="${esc(row ? row.remark : '')}" placeholder="${esc(I('ib.remarkPh'))}"></div>
            <div class="f"><label>${esc(I('ib.protocol'))}</label>
                <select id="ibProto">${protoOpts}</select></div>
        </div>
        ${PAAS ? paasFields : vpsFields}
        ${ssBox}
        <div class="modal-err" id="ibErr"></div>
    `, `
        <button class="btn btn-pri" id="ibSave">${esc(I('common.save'))}</button>
        <button class="btn" id="ibCancel">${esc(I('common.cancel'))}</button>
    `, true);

    const $ib = (id) => $('modalBody').querySelector('#' + id);
    const vis = () => {
        const p = $ib('ibProto').value;
        const tr = $ib('ibTransport').value;
        const sec = PAAS ? 'none' : ($ib('ibSecurity') || {}).value;
        $ib('ibSsBox').classList.toggle('hidden', p !== 'shadowsocks');
        if (!PAAS) {
            $ib('ibPathLbl').textContent =
                tr === 'grpc' ? I('ib.grpcService') : I('ib.path');
            $ib('ibPath').placeholder = tr === 'grpc' ? 'myservice' : '/mypath';
            $ib('ibHostRow').style.display =
                ['ws', 'httpupgrade'].includes(tr) ? '' : 'none';
            $ib('ibTlsBox').classList.toggle('hidden', sec !== 'tls');
            $ib('ibRealityBox').classList.toggle('hidden', sec !== 'reality');
        }
    };
    $ib('ibProto').onchange = vis;
    $ib('ibTransport').onchange = vis;
    if (!PAAS) $ib('ibSecurity').onchange = vis;
    vis();

    if (!PAAS) {
        const kb = $ib('ibBtnKeys');
        if (kb) kb.onclick = async () => {
            btnLoad(kb, true);
            try {
                const k = await api('/api/xray/x25519', { method: 'POST' });
                $ib('ibRPriv').value = k.privateKey;
                $ib('ibRPub').value = k.publicKey;
                toast(I('ib.keysDone'), 'ok');
            } catch (e) { toast(e.message, 'err'); }
            finally { btnLoad(kb, false); }
        };
        const cb = $ib('ibBtnCert');
        if (cb) cb.onclick = async () => {
            btnLoad(cb, true);
            try {
                const domain = $ib('ibSni').value.trim() ||
                               ($('setDomain') || {}).value?.trim() || '';
                const c = await api('/api/xray/cert',
                                    { method: 'POST', body: { domain } });
                $ib('ibCert').value = c.certFile;
                $ib('ibKey').value = c.keyFile;
                if (!$ib('ibSni').value.trim()) $ib('ibSni').value = c.domain;
                $ib('ibSelfsg').checked = true;
                toast(I('ib.certDone'), 'ok');
            } catch (e) { toast(e.message, 'err'); }
            finally { btnLoad(cb, false); }
        };
    }

    $('ibCancel').onclick = closeModal;
    $('ibSave').onclick = async () => {
        const err = $ib('ibErr'); err.textContent = '';
        const cfg = { protocol: $ib('ibProto').value };
        if (PAAS) {
            cfg.transport = $ib('ibTransport').value;
            cfg.path = $ib('ibPath').value.trim();
        } else {
            cfg.port = parseInt($ib('ibPort').value, 10) || 0;
            cfg.transport = $ib('ibTransport').value;
            cfg.path = $ib('ibPath').value.trim();
            cfg.host = $ib('ibHost').value.trim();
            cfg.security = $ib('ibSecurity').value;
            if (cfg.security === 'tls') {
                cfg.sni = $ib('ibSni').value.trim();
                cfg.alpn = $ib('ibAlpn').value.trim();
                cfg.certFile = $ib('ibCert').value.trim();
                cfg.keyFile = $ib('ibKey').value.trim();
                cfg.selfsigned = $ib('ibSelfsg').checked;
            }
            if (cfg.security === 'reality') {
                cfg.reality = {
                    dest: $ib('ibRDest').value.trim(),
                    serverNames: $ib('ibRNames').value,
                    privateKey: $ib('ibRPriv').value.trim(),
                    publicKey: $ib('ibRPub').value.trim(),
                    shortIds: $ib('ibRSids').value,
                };
            }
        }
        if (cfg.protocol === 'shadowsocks') {
            cfg.method = $ib('ibMethod').value;
            cfg.password = $ib('ibPass').value.trim();
        }
        const payload = { remark: $ib('ibRemark').value.trim(), config: cfg };
        btnLoad($('ibSave'), true);
        try {
            if (isNew) await api('/api/inbounds', { method: 'POST', body: payload });
            else await api(`/api/inbounds/${row.id}`, { method: 'PUT', body: payload });
            toast(I('ib.saved'), 'ok');
            closeModal();
            loadInbounds();
        } catch (e) { err.textContent = e.message; }
        finally { btnLoad($('ibSave'), false); }
    };
}

/* ═══════════════ Clients ═══════════════ */
async function loadClients() {
    try {
        clientsCache = await api('/api/clients');
        if (!inboundsCache.length) inboundsCache = await api('/api/inbounds');
        renderClients();
    } catch (e) { toast(e.message, 'err'); }
}
function renderClients() {
    const q = ($('clientSearch').value || '').trim().toLowerCase();
    const rows = clientsCache.filter(c =>
        !q || c.email.toLowerCase().includes(q) ||
        (c.note || '').toLowerCase().includes(q));
    $('clientsCount').textContent = I('cl.count', rows.length);
    $('clientsEmpty').classList.toggle('hidden', rows.length > 0);

    $('clientsTbody').innerHTML = rows.map(c => {
        const pct = c.limit_bytes ? Math.min(100, c.used * 100 / c.limit_bytes) : 0;
        const barCls = pct >= 90 ? 'bad' : pct >= 70 ? 'warn' : '';
        return `<tr>
            <td><label class="sw"><input type="checkbox" ${c.enable ? 'checked' : ''}
                data-tgl-cl="${c.id}"><span></span></label></td>
            <td class="email-cell"><b>${esc(c.email)}</b>
                ${c.tg_id ? `<div class="cell-sub">${esc(I('cl.tgBound'))}</div>` : ''}
                ${c.note ? `<div class="cell-sub">📝 ${esc(c.note)}</div>` : ''}</td>
            <td><div class="tag-list">${(c.inbound_names || []).map(n =>
                `<span class="badge b-def">${esc(n)}</span>`).join('')}</div></td>
            <td>${fmtBytes(c.used)}
                ${c.limit_bytes ? `<div class="prog prog-sm"><i class="${barCls}" style="width:${pct}%"></i></div>
                <div class="cell-sub">${pct}%</div>` : ''}</td>
            <td>${c.limit_bytes ? fmtBytes(c.limit_bytes)
                    : `<span class="badge b-def">∞</span>`}</td>
            <td>${fmtExpiryHtml(c.expiry)}</td>
            <td><div class="acts">
                <button class="btn-icon" title="${esc(I('ln.title'))}" data-links="${c.id}">🔗</button>
                <button class="btn-icon" title="📅" data-days="${c.id}">📅</button>
                <button class="btn-icon" title="${esc(I('common.edit'))}" data-edit-cl="${c.id}">✏️</button>
                <button class="btn-icon" title="${esc(I('cl.resetTitle'))}" data-rst="${c.id}">↺</button>
                <button class="btn-icon" title="${esc(I('common.delete'))}" data-del-cl="${c.id}">🗑</button>
            </div></td></tr>`;
    }).join('');

    const tb = $('clientsTbody');
    tb.querySelectorAll('[data-tgl-cl]').forEach(el =>
        el.onchange = () => toggleClient(el.dataset.tglCl));
    tb.querySelectorAll('[data-links]').forEach(el =>
        el.onclick = () => showLinks(el.dataset.links));
    tb.querySelectorAll('[data-days]').forEach(el =>
        el.onclick = () => showDaily(el.dataset.days));
    tb.querySelectorAll('[data-edit-cl]').forEach(el =>
        el.onclick = () => clientForm(clientsCache.find(x => x.id == el.dataset.editCl)));
    tb.querySelectorAll('[data-rst]').forEach(el =>
        el.onclick = () => confirmBox(I('cl.resetTitle'),
            I('cl.resetMsg', clientName(el.dataset.rst)), async () => {
                try {
                    await api(`/api/clients/${el.dataset.rst}/reset`, { method: 'POST' });
                    toast(I('cl.resetDone'), 'ok'); loadClients();
                } catch (e) { toast(e.message, 'err'); }
            }));
    tb.querySelectorAll('[data-del-cl]').forEach(el =>
        el.onclick = () => confirmBox(I('cl.delTitle'),
            I('cl.delMsg', clientName(el.dataset.delCl)), async () => {
                try {
                    await api(`/api/clients/${el.dataset.delCl}`, { method: 'DELETE' });
                    toast(I('cl.deleted'), 'ok'); loadClients();
                } catch (e) { toast(e.message, 'err'); }
            }));
}
function clientName(id) {
    const c = clientsCache.find(x => x.id == id);
    return c ? c.email : id;
}
async function toggleClient(id) {
    try { await api(`/api/clients/${id}/toggle`, { method: 'POST' });
          await loadClients(); }
    catch (e) { toast(e.message, 'err'); loadClients(); }
}

function clientForm(c) {
    const isNew = !c;
    const inbs = inboundsCache;

    openModal(isNew ? I('cl.new') : I('cl.editTitle'), `
        <div class="form-grid">
            <div class="f"><label>${esc(I('cl.email'))}</label>
                <input id="clEmail" value="${esc(c ? c.email : '')}" placeholder="${esc(I('cl.emailPh'))}"></div>
            <div class="f"><label>${esc(I('cl.uuid'))}</label>
                <div class="exp-flex">
                    <input id="clUuid" class="ltr" value="${esc(c ? c.uuid : '')}" placeholder="${esc(I('cl.uuidPh'))}">
                    <button class="btn-icon" id="clUuidBtn" type="button" title="${esc(I('fm.generate'))}">🎲</button>
                </div></div>
        </div>
        <div class="f"><label>${esc(I('cl.password'))}</label>
            <div class="exp-flex">
                <input id="clPass" class="ltr" value="${esc(c ? c.password : '')}" placeholder="${esc(I('cl.uuidPh'))}">
                <button class="btn-icon" id="clPassBtn" type="button" title="${esc(I('fm.generate'))}">🎲</button>
            </div></div>
        <div class="f"><label>${esc(I('cl.inbounds'))}</label>
            <div class="chk-list">${inbs.map(ib => `
                <label class="chk-item ${ib.enable ? '' : 'dis'}">
                    <input type="checkbox" class="cl-inb" value="${ib.id}"
                        ${c && (c.inbounds || []).includes(ib.id) ? 'checked' : ''}
                        ${ib.enable ? '' : 'disabled'}>
                    <span>${esc(ib.remark)}</span>
                    <span class="badge b-${ib.protocol}">${ib.protocol.toUpperCase()}</span>
                </label>`).join('') ||
                `<div class="muted" style="padding:10px">${esc(I('ib.needInboundFirst'))}</div>`}
            </div></div>
        <div class="f hidden" id="clFlowRow"><label>${esc(I('cl.flow'))}</label>
            <select id="clFlow">
                <option value="">${esc(I('cl.flowNone'))}</option>
                <option value="xtls-rprx-vision" ${c && c.flow === 'xtls-rprx-vision' ? 'selected' : ''}>xtls-rprx-vision</option>
            </select>
            <div class="hint">${esc(I('cl.flowHint'))}</div></div>
        <div class="form-grid">
            <div class="f"><label>${esc(I('cl.expiry'))}</label>
                <div class="exp-flex">
                    <select id="clExpMode">
                        <option value="never" ${!c || !c.expiry ? 'selected' : ''}>${esc(I('cl.expNever'))}</option>
                        <option value="date" ${c && c.expiry ? 'selected' : ''}>${esc(I('cl.expDate'))}</option>
                        <option value="days">${esc(I('cl.expDays'))}</option>
                    </select>
                    <input id="clExpVal" class="ltr" type="datetime-local"
                        value="${c && c.expiry ? toLocalInput(c.expiry) : ''}"
                        ${(!c || !c.expiry) ? 'style="visibility:hidden"' : ''}>
                </div></div>
            <div class="f"><label>${esc(I('cl.dataLimit'))}</label>
                <div class="exp-flex">
                    <select id="clLimMode">
                        <option value="off" ${!c || !c.limit_bytes ? 'selected' : ''}>${esc(I('cl.limOff'))}</option>
                        <option value="gb" ${c && c.limit_bytes >= 1073741824 ? 'selected' : ''}>${esc(I('cl.limGB'))}</option>
                        <option value="mb" ${c && c.limit_bytes && c.limit_bytes < 1073741824 ? 'selected' : ''}>${esc(I('cl.limMB'))}</option>
                    </select>
                    <input id="clLimVal" type="number" min="0" step="any" placeholder="0"
                        value="${c && c.limit_bytes ? Math.round(c.limit_bytes / (c.limit_bytes >= 1073741824 ? 1073741824 : 1048576) * 100) / 100 : ''}"
                        ${(!c || !c.limit_bytes) ? 'style="visibility:hidden"' : ''}>
                </div></div>
        </div>
        <div class="form-grid">
            <div class="f"><label>${esc(I('cl.tgId'))}</label>
                <input id="clTg" class="ltr" value="${esc(c ? c.tg_id : '')}" placeholder="123456789"></div>
            <div class="f"><label>${esc(I('cl.note'))}</label>
                <input id="clNote" value="${esc(c ? c.note : '')}" placeholder="${esc(I('cl.notePh'))}"></div>
        </div>
        <div class="f sw-row">
            <span class="sw"><input type="checkbox" id="clEnable" ${isNew || (c && c.enable) ? 'checked' : ''}><span></span></span>
            <span>${esc(I('cl.active'))}</span>
        </div>
        <div class="modal-err" id="clErr"></div>
    `, `
        <button class="btn btn-pri" id="clSave">${esc(I('common.save'))}</button>
        <button class="btn" id="clCancel">${esc(I('common.cancel'))}</button>
    `, true);

    const $cl = (id) => $('modalBody').querySelector('#' + id);
    $cl('clUuidBtn').onclick = () => $cl('clUuid').value = newUuid();
    $cl('clPassBtn').onclick = () => $cl('clPass').value =
        Array.from(crypto.getRandomValues(new Uint8Array(12)))
            .map(b => b.toString(16).padStart(2, '0')).join('');

    const updateFlowVis = () => {
        const sel = [...$('modalBody').querySelectorAll('.cl-inb:checked')]
            .map(el => inboundsCache.find(x => x.id == el.value));
        $cl('clFlowRow').classList.toggle('hidden',
            PAAS || !sel.some(x => x && x.protocol === 'vless'));
    };
    $('modalBody').querySelectorAll('.cl-inb').forEach(el =>
        el.onchange = updateFlowVis);
    updateFlowVis();

    $cl('clExpMode').onchange = () => {
        const mode = $cl('clExpMode').value;
        const el = $cl('clExpVal');
        if (mode === 'days') {
            el.type = 'number'; el.placeholder = '30'; el.value = '30';
            el.style.visibility = '';
        } else if (mode === 'date') {
            el.type = 'datetime-local';
            el.value = toLocalInput(Date.now() + 30 * 86400000);
            el.style.visibility = '';
        } else el.style.visibility = 'hidden';
    };
    $cl('clLimMode').onchange = () => {
        $cl('clLimVal').style.visibility =
            $cl('clLimMode').value === 'off' ? 'hidden' : '';
    };

    $('clCancel').onclick = closeModal;
    $('clSave').onclick = async () => {
        const err = $cl('clErr'); err.textContent = '';
        let expiry = 0;
        const expMode = $cl('clExpMode').value;
        if (expMode === 'date') {
            const v = $cl('clExpVal').value;
            expiry = v ? new Date(v).getTime() : 0;
        } else if (expMode === 'days') {
            const d = parseFloat($cl('clExpVal').value) || 0;
            expiry = d > 0 ? Date.now() + d * 86400000 : 0;
        }
        let limit = 0;
        const limMode = $cl('clLimMode').value;
        if (limMode !== 'off') {
            const n = parseFloat($cl('clLimVal').value) || 0;
            limit = Math.round(n * (limMode === 'gb' ? 1073741824 : 1048576));
        }
        const body = {
            email: $cl('clEmail').value.trim(),
            uuid: $cl('clUuid').value.trim(),
            password: $cl('clPass').value.trim(),
            flow: $cl('clFlowRow').classList.contains('hidden') ? '' : $cl('clFlow').value,
            inbounds: [...$('modalBody').querySelectorAll('.cl-inb:checked')]
                        .map(el => +el.value),
            expiry, limit_bytes: limit,
            tg_id: $cl('clTg').value.trim(),
            note: $cl('clNote').value.trim(),
            enable: $cl('clEnable').checked,
        };
        btnLoad($('clSave'), true);
        try {
            if (isNew) await api('/api/clients', { method: 'POST', body });
            else await api(`/api/clients/${c.id}`, { method: 'PUT', body });
            toast(I('cl.saved'), 'ok');
            closeModal();
            loadClients();
        } catch (e) { err.textContent = e.message; }
        finally { btnLoad($('clSave'), false); }
    };
}

async function showLinks(id) {
    openModal(I('ln.title'), `<div class="muted">${esc(I('common.loading'))}</div>`, '', true);
    try {
        const d = await api(`/api/clients/${id}/links`);
        const body = [];
        body.push(`
            <div class="kv"><span>${esc(I('ln.status'))}</span>
                <b>${d.enabled ? `<span class="badge b-ok">${esc(I('common.active'))}</span>`
                               : `<span class="badge b-bad">${esc(I('common.disabled'))}</span>`}</b></div>
            <div class="kv"><span>${esc(I('ln.usage'))}</span>
                <b>${fmtBytes(d.used)}${d.total ? ' / ' + fmtBytes(d.total) : ''}</b></div>
            <div class="kv"><span>${esc(I('ln.expiry'))}</span>
                <b>${d.expire ? fmtTs(d.expire * 1000) : '∞'}</b></div>
            <div class="lbl2" style="margin-top:16px">${esc(I('ln.subSection'))}</div>
            <div class="copybox mono" id="lnSub">${esc(d.sub_url)}</div>
            <div class="btn-row">
                <button class="btn btn-sm" id="lnSubCopy">${esc(I('ln.copySub'))}</button>
                <button class="btn btn-sm" id="lnSubQr">${esc(I('ln.qrSub'))}</button>
            </div>
            <div class="qr-mini hidden" id="lnSubQrBox"></div>
            <div class="lbl2" style="margin-top:18px">${esc(I('ln.bindSection'))}</div>
            <div class="hint">${I('ln.bindHint')}</div>
            <div class="copybox mono" id="lnBind">${esc(d.bind_code)}</div>
            <button class="btn btn-sm" id="lnBindCopy">${esc(I('ln.copyBind'))}</button>
            <div class="lbl2" style="margin-top:18px">${esc(I('ln.singleLinks'))}</div>`);
        (d.links || []).forEach((l, i) => {
            body.push(`
                <div class="link-item">
                    <div class="ln-name">
                        <span class="badge b-${l.protocol}">${l.protocol.toUpperCase()}</span>
                        ${esc(l.name)}</div>
                    <div class="ln-code">${esc(l.link)}</div>
                    <div class="ln-acts">
                        <button class="btn btn-sm" data-copy="${i}">${esc(I('common.copy'))}</button>
                        <button class="btn btn-sm" data-qr="${i}">QR</button></div>
                    <div class="qr-mini hidden" id="qrbox-${i}"></div>
                </div>`);
        });
        openModal(I('ln.titleOf', d.email), body.join(''), '', true);

        $('lnSubCopy').onclick = () => copyText(d.sub_url);
        $('lnBindCopy').onclick = () => copyText(d.bind_code);
        $('lnSubQr').onclick = async () => {
            const box = $('lnSubQrBox');
            box.classList.toggle('hidden');
            if (!box.classList.contains('hidden')) {
                box.innerHTML = '<span class="muted">…</span>';
                box.innerHTML = await fetchQrSvg(d.sub_url) || '';
            }
        };
        $('modalBody').querySelectorAll('[data-copy]').forEach(el =>
            el.onclick = () => copyText(d.links[+el.dataset.copy].link));
        $('modalBody').querySelectorAll('[data-qr]').forEach(el =>
            el.onclick = async () => {
                const i = +el.dataset.qr;
                const box = $('qrbox-' + i);
                box.classList.toggle('hidden');
                if (!box.classList.contains('hidden')) {
                    box.innerHTML = '<span class="muted">…</span>';
                    box.innerHTML = await fetchQrSvg(d.links[i].link) || '';
                }
            });
    } catch (e) {
        openModal(I('common.error'), `<div class="err">${esc(e.message)}</div>`, '');
    }
}

async function showDaily(id) {
    openModal('📅', `<div class="muted">${esc(I('common.loading'))}</div>`, '', true);
    try {
        const d = await api(`/api/clients/${id}/traffic`);
        const days = d.days || [];
        const max = Math.max(1, ...days.map(x => x.up + x.down));
        const rows = days.slice().reverse().map(x => {
            const total = x.up + x.down;
            const pct = Math.round(total * 100 / max);
            return `<tr>
                <td class="mono">${esc(x.day)}</td>
                <td>${fmtBytes(x.up)}</td>
                <td>${fmtBytes(x.down)}</td>
                <td style="min-width:140px">
                    <div class="prog prog-sm"><i style="width:${pct}%"></i></div>
                    <div class="cell-sub">${fmtBytes(total)}</div></td></tr>`;
        }).join('');
        openModal(I('dy.title', d.email),
            days.length ? `
            <div class="tbl-wrap"><table>
                <thead><tr><th>${esc(I('dy.day'))}</th><th>${esc(I('dy.up'))}</th>
                <th>${esc(I('dy.down'))}</th><th>${esc(I('dy.total'))}</th></tr></thead>
                <tbody>${rows}</tbody></table></div>`
            : `<div class="empty"><div class="big">📭</div>${esc(I('dy.empty'))}</div>`,
            '', true);
    } catch (e) {
        openModal(I('common.error'), `<div class="err">${esc(e.message)}</div>`, '');
    }
}

/* ═══════════════ Settings ═══════════════ */
async function loadSettings() {
    try {
        const s = await api('/api/settings');
        $('setDomain').value = s.public_domain || '';
        $('setSubTitle').value = s.sub_title || '';
        $('setTgToken').value = s.tg_token || '';
        $('setTgAdmins').value = s.tg_admins || '';
        $('setTgNotify').checked = !!s.tg_notify;
        $('setResetMode').value = s.reset_mode || 'off';
        $('setResetDay').value = s.reset_day || 1;
        $('setXrayVersion').value = s.xray_version || '';
        const on = !!s.totp_enabled;
        setPill($('totpStatus'), on ? 'ok' : 'bad', I(on ? 'st.2faOn' : 'st.2faOff'));
        $('totpSetupBox').classList.add('hidden');
        $('totpDisableBox').classList.toggle('hidden', !on);
        $('btnTotpSetup').classList.toggle('hidden', on);
    } catch (e) { toast(e.message, 'err'); }
}
async function saveSettings(body, btn) {
    btnLoad(btn, true);
    try { await api('/api/settings', { method: 'PUT', body });
          toast(I('st.saved'), 'ok'); }
    catch (e) { toast(e.message, 'err'); }
    finally { btnLoad(btn, false); }
}
function bindSettingsEvents() {
    $('btnSaveGeneral').onclick = (e) => saveSettings({
        public_domain: $('setDomain').value.trim(),
        sub_title: $('setSubTitle').value.trim(),
    }, e.target);
    $('btnSaveTg').onclick = (e) => saveSettings({
        tg_token: $('setTgToken').value.trim(),
        tg_admins: $('setTgAdmins').value.trim(),
        tg_notify: $('setTgNotify').checked,
    }, e.target);
    $('btnSaveReset').onclick = (e) => saveSettings({
        reset_mode: $('setResetMode').value,
        reset_day: parseInt($('setResetDay').value, 10) || 1,
    }, e.target);
    $('btnSaveXrayVer').onclick = (e) => saveSettings({
        xray_version: $('setXrayVersion').value.trim(),
    }, e.target);
    $('btnTgTest').onclick = async (e) => {
        $('tgTestResult').textContent = I('st.testing');
        btnLoad(e.target, true);
        try {
            const r = await api('/api/settings/tg-test', { method: 'POST' });
            $('tgTestResult').textContent = I('st.tgOk', r.bot);
            toast(I('st.tgOk', r.bot), 'ok');
        } catch (err) {
            $('tgTestResult').textContent = I('st.tgFail', err.message);
        } finally { btnLoad(e.target, false); }
    };
    $('btnChangePass').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            const r = await api('/api/settings/password', { method: 'POST', body: {
                old: $('passOld').value, new: $('passNew').value } });
            TOKEN = r.token;
            localStorage.setItem('sf_token', TOKEN);
            $('passOld').value = ''; $('passNew').value = '';
            toast(I('st.passChanged'), 'ok');
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };
    $('btnTotpSetup').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            const r = await api('/api/settings/totp/setup', { method: 'POST' });
            $('totpSetupBox').classList.remove('hidden');
            $('totpSecret').textContent = r.secret;
            $('totpQr').innerHTML = await fetchQrSvg(r.uri) ||
                `<div class="hint">${esc(I('st.2faSecret'))}</div>`;
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };
    $('btnTotpEnable').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            await api('/api/settings/totp/enable', { method: 'POST',
                body: { code: $('totpCode').value.trim() } });
            toast(I('st.2faEnabled'), 'ok');
            loadSettings();
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };
    $('btnTotpDisable').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            await api('/api/settings/totp/disable', { method: 'POST',
                body: { password: $('totpDisablePass').value } });
            toast(I('st.2faDisabled'), 'ok');
            loadSettings();
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };
    $('btnBackup').onclick = async () => {
        try {
            const res = await fetch('/api/backup',
                { headers: { 'Authorization': 'Bearer ' + TOKEN } });
            if (!res.ok) throw new Error(I('er.request'));
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'sf-panel-backup-' +
                new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-') + '.json';
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 4000);
            toast(I('st.backupDone'), 'ok');
        } catch (err) { toast(err.message, 'err'); }
    };
    $('btnRestore').onclick = () => {
        const f = $('restoreFile').files[0];
        if (!f) { toast(I('st.pickFile'), 'err'); return; }
        confirmBox(I('st.restoreBtn'), I('st.restoreWarn'), async () => {
            try {
                const data = JSON.parse(await f.text());
                const r = await api('/api/restore', { method: 'POST', body: data });
                toast(I('st.restored', r.inbounds, r.clients), 'ok');
                if (r.xray_error) toast(I('ib.xrayWarn', r.xray_error), 'err');
                loadSettings(); loadInbounds(); loadClients();
            } catch (err) { toast(err.message, 'err'); }
        });
    };
}

/* ═══════════════ Xray view ═══════════════ */
async function loadXrayView() {
    try {
        const [info, dash] = await Promise.all([api('/api/info'), api('/api/dashboard')]);
        const x = dash.xray;
        setPill($('xray2State'), x.running ? 'ok' : 'warn',
                I(x.running ? 'dash.running' : 'dash.stopped'));
        $('xray2Ver').textContent = x.version || '—';
        $('xray2Uptime').textContent = fmtDur(x.uptime);
        $('xray2Goro').textContent = x.goroutines ?? '—';
        $('xray2Alloc').textContent = fmtBytes(x.alloc);
        const errBox = $('xray2ErrBox');
        if (x.error && !x.running) {
            errBox.classList.remove('hidden');
            $('xray2ErrText').textContent = x.error;
        } else errBox.classList.add('hidden');
        $('routesCard').classList.toggle('hidden', !PAAS);
        if (PAAS) {
            $('xrayRoutes').innerHTML = (info.routes || []).map(r => `
                <tr><td class="mono">${esc(r.path)}</td>
                    <td class="mono">${esc(r.internal_port)}</td></tr>`).join('')
                || `<tr><td colspan="2" class="muted">${esc(I('xr.noRoutes'))}</td></tr>`;
        }
        $('modeInfo').innerHTML = I(PAAS ? 'xr.modePaas' : 'xr.modeVps',
                                    info.public_port, info.host);
    } catch (e) { toast(e.message, 'err'); }
}
function bindXrayEvents() {
    const restart = async (btn) => {
        btnLoad(btn, true);
        try {
            await api('/api/xray/restart', { method: 'POST' });
            toast(I('xr.restarted'), 'ok');
            loadXrayView(); loadDashboard();
        } catch (e) { toast(e.message, 'err'); }
        finally { btnLoad(btn, false); }
    };
    $('btnXrayRestart').onclick = (e) => restart(e.target);
    $('btnXrayRestart2').onclick = (e) => restart(e.target);
    $('btnXrayUpdate').onclick = () => confirmBox(I('xr.update'),
        I('xr.updateConfirm'), async () => {
            toast(I('xr.updating'));
            try {
                const r = await api('/api/xray/update', { method: 'POST' });
                toast(I('xr.updated', r.version || '?'), 'ok');
                loadXrayView();
            } catch (err) { toast(err.message, 'err'); }
        });
    $('btnXrayKeys').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            const k = await api('/api/xray/x25519', { method: 'POST' });
            const box = $('x25519Box');
            box.classList.remove('hidden');
            box.textContent = `Private: ${k.privateKey}\nPublic:  ${k.publicKey}`;
            box.onclick = () => copyText(k.privateKey);
            toast(I('xr.clickToCopy'), 'ok');
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };
    $('btnGenCert').onclick = async (e) => {
        btnLoad(e.target, true);
        $('certResult').textContent = I('st.testing');
        try {
            const c = await api('/api/xray/cert', { method: 'POST',
                body: { domain: $('certDomain').value.trim() } });
            $('certResult').innerHTML = I('xr.certDone', esc(c.domain)) +
                `<br><span class="mono" style="font-size:.7rem">cert: ${esc(c.certFile)}<br>` +
                `key: ${esc(c.keyFile)}</span>`;
        } catch (err) { $('certResult').textContent = '❌ ' + err.message; }
        finally { btnLoad(e.target, false); }
    };
}

/* ═══════════════ Logs ═══════════════ */
let LOG_TYPE = 'panel';
async function loadLogs() {
    try {
        const r = await api('/api/logs?type=' + LOG_TYPE);
        $('logBox').textContent = r.lines || '—';
        $('logBox').scrollTop = 0;
    } catch (e) { toast(e.message, 'err'); }
}
function bindLogEvents() {
    const setSeg = (a) => {
        $('logTypePanel').classList.toggle('active', a === 'panel');
        $('logTypeXray').classList.toggle('active', a === 'xray');
    };
    $('logTypePanel').onclick = () => { LOG_TYPE = 'panel'; setSeg('panel'); loadLogs(); };
    $('logTypeXray').onclick = () => { LOG_TYPE = 'xray'; setSeg('xray'); loadLogs(); };
    $('btnRefreshLogs').onclick = loadLogs;
}

/* ═══════════════ Sidebar / Lang / Init ═══════════════ */
function closeSidebar() {
    $('sidebar').classList.remove('open');
    document.querySelectorAll('.side-back').forEach(el => el.remove());
}
function openSidebar() {
    $('sidebar').classList.add('open');
    if (!document.querySelector('.side-back')) {
        const bk = document.createElement('div');
        bk.className = 'side-back';
        bk.onclick = closeSidebar;
        document.body.appendChild(bk);
    }
}
function toggleLang() {
    setLang(LANG === 'fa' ? 'en' : 'fa');
    refreshViewTitles();
    switchView(VIEW);
}

function bindGlobalEvents() {
    $('authBtn').onclick = doLogin;
    $('setupBtn').onclick = doSetup;
    $('authPass').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
    $('authCode').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
    $('setupPass2').addEventListener('keydown', e => { if (e.key === 'Enter') doSetup(); });

    document.querySelectorAll('.nav-item').forEach(n =>
        n.onclick = () => switchView(n.dataset.view));

    $('logoutBtn').onclick = () => confirmBox(I('nav.logout'), '', doLogout);
    $('mobileMenu').onclick = () =>
        $('sidebar').classList.contains('open') ? closeSidebar() : openSidebar();
    $('langBtn').onclick = toggleLang;
    $('langBtnAuth').onclick = toggleLang;

    $('btnAddInbound').onclick = () => inboundForm(null);
    $('btnAddClient').onclick = () => {
        if (!inboundsCache.length) { toast(I('ib.needInboundFirst'), 'err'); return; }
        clientForm(null);
    };
    $('inboundSearch').oninput = renderInbounds;
    $('clientSearch').oninput = renderClients;

    $('modalClose').onclick = closeModal;
    $('modalBack').addEventListener('click', e => {
        if (e.target === $('modalBack')) closeModal();
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && currentModal) closeModal();
    });

    bindSettingsEvents();
    bindXrayEvents();
    bindLogEvents();

    let rz;
    window.addEventListener('resize', () => {
        clearTimeout(rz);
        rz = setTimeout(() => { if (VIEW === 'dashboard') drawChart(); }, 150);
    });
}

applyI18n();
bindGlobalEvents();
initAuth();
