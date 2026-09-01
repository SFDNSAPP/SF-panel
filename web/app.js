'use strict';

/* ═══════════════════════════════════════════════════════════
   SF-Panel — app.js  (i18n-aware · neon theme)
   Depends: i18n.js  (I / applyI18n / setLang / fmtDur / fmtTs)
   ═══════════════════════════════════════════════════════════ */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

let TOKEN = localStorage.getItem('sf_token') || '';
let USER  = localStorage.getItem('sf_user') || '';
let PAAS  = false;
let VIEW  = 'dashboard';
let POLL  = null;
let POLL_MS = 6000;
let inboundsCache = [];
let clientsCache  = [];
let chartSeries = [];
let currentModal = null;

/* ---------- استایل دینامیک فرم‌ها (هماهنگ تم نئون) ---------- */
(function injectExtraCss() {
    const css = `
    .chk-list{display:flex;flex-direction:column;gap:8px;max-height:220px;
      overflow-y:auto;padding:4px;border:1px solid var(--bd);border-radius:12px}
    .chk-item{display:flex;align-items:center;gap:10px;padding:9px 12px;
      border-radius:9px;cursor:pointer;transition:.15s;font-size:.82rem}
    .chk-item:hover{background:rgba(0,255,157,.06)}
    .chk-item input{width:16px;height:16px;accent-color:#00ff9d;cursor:pointer}
    .chk-item.dis{opacity:.45;cursor:not-allowed}
    .exp-flex{display:flex;gap:10px}
    .exp-flex select{width:140px!important;flex-shrink:0}
    .qr-mini{margin-top:10px;text-align:center}
    .qr-mini svg{width:200px;height:200px;background:#fff;border-radius:12px;
      border:1px solid var(--bd);padding:8px}
    .btn-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
    .tag-list{display:flex;flex-wrap:wrap;gap:5px}
    .modal-err{color:var(--bad);font-size:.8rem;min-height:18px;margin-top:8px}
    `;
    const tag = document.createElement('style');
    tag.textContent = css;
    document.head.appendChild(tag);
})();

/* ---------- Toast / Modal / Copy ---------- */

function toast(msg, type = '') {
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    $('toastWrap').appendChild(el);
    setTimeout(() => {
        el.classList.add('out');
        setTimeout(() => el.remove(), 260);
    }, 3200);
}

function openModal(title, bodyHtml, footHtml, wide = false) {
    currentModal = true;
    $('modalTitle').textContent = title;
    $('modalBody').innerHTML = bodyHtml;
    $('modalFoot').innerHTML = footHtml || '';
    $('modalCard').classList.toggle('wide', wide);
    $('modalBack').classList.remove('hidden');
}
function closeModal() {
    $('modalBack').classList.add('hidden');
    $('modalBody').innerHTML = '';
    $('modalFoot').innerHTML = '';
    currentModal = null;
}
function confirmBox(title, msg, onYes, yesLabel) {
    openModal(title,
        `<div style="font-size:.9rem;line-height:2;color:var(--tx2)">${esc(msg)}</div>`,
        `<button class="btn btn-bad" id="cfYes">${esc(yesLabel || I('common.yes'))}</button>
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
            ta.value = text;
            ta.style.cssText = 'position:fixed;opacity:0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
        }
        toast(I('common.copied'), 'ok');
    } catch (e) {
        toast(I('common.copyFail'), 'err');
    }
}

/* ---------- فرمت‌ها ---------- */

function fmtBytes(n) {
    n = Number(n) || 0;
    const neg = n < 0; n = Math.abs(n);
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    for (const u of units) {
        if (n < 1024 || u === 'PB') {
            const s = (u === 'B') ? `${Math.round(n)} B`
                : (n.toFixed(2).replace(/\.?0+$/, '') + ' ' + u);
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
    const d = new Date(ms);
    const p = (x) => String(x).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/* ---------- API ---------- */

async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (opts.body !== undefined && !(opts.body instanceof FormData))
        headers['Content-Type'] = 'application/json';
    if (TOKEN) headers['Authorization'] = 'Bearer ' + TOKEN;
    const init = { method: opts.method || 'GET', headers };
    if (opts.body !== undefined)
        init.body = (opts.body instanceof FormData) ? opts.body : JSON.stringify(opts.body);
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
        if (!res.ok) return '';
        return await res.text();
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

/* ═══════════════════ Auth ═══════════════════ */

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
        if (m.includes('دومرحله') || m.toLowerCase().includes('2fa')
                || m.includes('کد')) {
            $('totpField').classList.remove('hidden');
            $('authCode').focus();
            $('authErr').textContent = I('auth.enter2fa');
        } else {
            $('authErr').textContent = m;
        }
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
            password: $('setupPass').value,
        }});
        TOKEN = r.token; USER = r.username;
        localStorage.setItem('sf_token', TOKEN);
        localStorage.setItem('sf_user', USER);
        toast(I('auth.installed'), 'ok');
        const me = await api('/api/me');
        PAAS = !!me.paas;
        enterApp();
    } catch (e) {
        $('setupErr').textContent = e.message;
    } finally { btnLoad(btn, false); }
}

function doLogout() {
    TOKEN = ''; USER = '';
    localStorage.removeItem('sf_token');
    localStorage.removeItem('sf_user');
    if (POLL) { clearInterval(POLL); POLL = null; }
    location.reload();
}

/* ═══════════════════ Shell ═══════════════════ */

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
    applyI18n();
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

/* ═══════════════════ Dashboard ═══════════════════ */

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

    const top = (d.top || []).map(c => `
        <tr>
            <td><b>${esc(c.email)}</b></td>
            <td>${fmtBytes(c.up + c.down)}</td>
            <td>${c.enable
                ? `<span class="badge b-ok">${esc(I('common.enabledBadge'))}</span>`
                : `<span class="badge b-bad">${esc(I('common.disabledBadge'))}</span>`}</td>
        </tr>`).join('');
    $('topUsers').innerHTML = top || `<tr><td colspan="3" class="muted">${esc(I('common.noData'))}</td></tr>`;

    const lv = { ok: 'ok', err: 'err', warn: 'warn', info: 'info' };
    $('dashEvents').innerHTML = (d.events || []).map(e => `
        <li><span class="lv ${lv[e.level] || 'info'}"></span>
            ${esc(e.msg)}<span class="ts">${fmtTs(e.ts)}</span></li>`).join('')
        || `<li class="muted">— ${esc(I('lg.empty'))} —</li>`;

    chartSeries = d.series || [];
    drawChart();
}

/* ---------- Chart (neon) ---------- */

function drawChart() {
    const cv = $('chart');
    if (!cv) return;
    const ctx = cv.getContext('2d');
    const w = cv.parentElement.clientWidth || 600;
    const h = 180;
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
        ctx.fillStyle = '#5d7a6b';
        ctx.font = '9px Vazirmatn, sans-serif';
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
        ctx.lineTo(padL + iw, padT + ih);
        ctx.lineTo(padL, padT + ih);
        ctx.closePath();
        ctx.fillStyle = color + '22';
        ctx.fill();
    };
    drawSeries('up', '#00ffd1');
    drawSeries('d',  '#39d0ff');

    ctx.fillStyle = '#5d7a6b';
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    const every = Math.max(1, Math.floor(data.length / 6));
    for (let i = 0; i < data.length; i += every) {
        const x = Math.min(padL + i * step, w - padR - 16);
        const dt = new Date(data[i].t * 1000);
        const hh = String(dt.getHours()).padStart(2, '0');
        const mm = String(dt.getMinutes()).padStart(2, '0');
        ctx.fillText(hh + ':' + mm, x, h - 6);
    }
}

/* ═══════════════════ Inbounds ═══════════════════ */

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
            detail = `: <b>${esc(g.port)}</b> · <span class="mono">${esc(g.transport || 'tcp')}/${esc(g.security || 'none')}</span>`;
            if (g.path) detail += `<div class="cell-sub mono">${esc(g.path)}</div>`;
        }
        return `
        <tr>
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
            </div></td>
        </tr>`;
    }).join('');

    $('inboundsTbody').querySelectorAll('[data-tgl-ib]').forEach(el =>
        el.onchange = () => toggleInbound(el.dataset.tglIb));
    $('inboundsTbody').querySelectorAll('[data-edit-ib]').forEach(el =>
        el.onclick = () => inboundForm(inboundsCache.find(x => x.id == el.dataset.editIb)));
    $('inboundsTbody').querySelectorAll('[data-del-ib]').forEach(el =>
        el.onclick = () => deleteInbound(el.dataset.delIb));
}

async function toggleInbound(id) {
    try {
        await api(`/api/inbounds/${id}/toggle`, { method: 'POST' });
        await loadInbounds();
    } catch (e) { toast(e.message, 'err'); loadInbounds(); }
}

function deleteInbound(id) {
    const r = inboundsCache.find(x => x.id == id);
    confirmBox(I('ib.delTitle'),
        I('ib.delMsg', r ? r.remark : id),
        async () => {
            try {
                const res = await api(`/api/inbounds/${id}`, { method: 'DELETE' });
                toast(I('ib.deleted'), 'ok');
                if (res.xray_error) toast(I('ib.xrayWarn', res.xray_error), 'err');
                loadInbounds();
            } catch (e) { toast(e.message, 'err'); }
        });
}

/* ---------- Inbound form ---------- */

const SS_METHODS = ['aes-256-gcm', 'aes-128-gcm', 'chacha20-poly1305', 'xchacha20-poly1305'];

function transportLabel(v) {
    return I('ib.tr.' + v, v);
}

function inboundForm(row) {
    const isNew = !row;
    const g = row ? (row.config || {}) : {};
    const proto = g.protocol || 'vless';

    const protoOpts = ['vless', 'vmess', 'trojan', 'shadowsocks']
        .map(p => `<option value="${p}" ${proto === p ? 'selected' : ''}
                   ${PAAS && p === 'shadowsocks' ? 'disabled' : ''}>${p.toUpperCase()}</option>`).join('');

    const trKeys = PAAS ? ['ws', 'httpupgrade']
