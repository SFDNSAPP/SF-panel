'use strict';

/* ═══════════════════════════════════════════════════════════
   SF-Panel — app.js  (SPA بدون هیچ کتابخانه خارجی)
   ═══════════════════════════════════════════════════════════ */

/* ---------- ابزارهای پایه ---------- */
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

/* استایل‌های دینامیک مخصوص فرم‌ها (به CSS اصلی اضافه می‌شود) */
(function injectExtraCss() {
    const css = `
    .chk-list{display:flex;flex-direction:column;gap:8px;max-height:220px;
      overflow-y:auto;padding:4px;border:1px solid var(--bd);border-radius:12px}
    .chk-item{display:flex;align-items:center;gap:10px;padding:9px 12px;
      border-radius:9px;cursor:pointer;transition:.15s;font-size:.82rem}
    .chk-item:hover{background:rgba(126,145,255,.07)}
    .chk-item input{width:16px;height:16px;accent-color:#6366f1;cursor:pointer}
    .chk-item.dis{opacity:.45;cursor:not-allowed}
    .exp-flex{display:flex;gap:10px}
    .exp-flex select{width:130px!important;flex-shrink:0}
    .qr-mini{margin-top:10px;text-align:center}
    .qr-mini svg{width:200px;height:200px;background:#fff;border-radius:12px;
      border:1px solid var(--bd);padding:8px}
    .btn-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
    .tag-list{display:flex;flex-wrap:wrap;gap:5px}
    .modal-err{color:var(--bad);font-size:.8rem;min-height:18px;margin-top:8px}
    .skel{display:inline-block;height:14px;border-radius:6px;
      background:rgba(126,145,255,.1);animation:skelP 1.2s infinite;
      width:90px;vertical-align:middle}
    @keyframes skelP{0%,100%{opacity:.4}50%{opacity:.9}}
    `;
    const tag = document.createElement('style');
    tag.textContent = css;
    document.head.appendChild(tag);
})();

/* ---------- Toast ---------- */
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

/* ---------- Modal ---------- */
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
function confirmBox(title, msg, onYes, yesLabel = 'بله، انجام بده') {
    openModal(title,
        `<div style="font-size:.9rem;line-height:2;color:var(--tx2)">${esc(msg)}</div>`,
        `<button class="btn btn-bad" id="cfYes">${esc(yesLabel)}</button>
         <button class="btn" id="cfNo">انصراف</button>`);
    $('cfYes').onclick = () => { closeModal(); onYes(); };
    $('cfNo').onclick = closeModal;
}

/* ---------- کپی ---------- */
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
        toast('کپی شد ✅', 'ok');
    } catch (e) {
        toast('کپی ناموفق — دستی انتخاب کن', 'err');
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
function fmtDur(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    if (sec < 60) return sec + ' ثانیه';
    const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600),
          m = Math.floor(sec % 3600 / 60);
    if (d) return `${d} روز ${h} ساعت`;
    if (h) return `${h} ساعت ${m} دقیقه`;
    return `${m} دقیقه`;
}
function fmtTs(ms) {
    if (!ms) return '—';
    const d = new Date(ms);
    return d.toLocaleDateString('fa-IR') + ' ' +
        d.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
}
function fmtExpiryHtml(ms) {
    if (!ms) return '<span class="badge b-def">∞</span>';
    const left = ms - Date.now();
    if (left <= 0) return '<span class="badge b-bad">منقضی</span>';
    const d = Math.floor(left / 86400000);
    if (d > 0) return `<span class="badge ${d < 3 ? 'b-bad' : d < 7 ? 'b-warn' : 'b-ok'}">${d} روز</span>`;
    const h = Math.floor(left / 3600000);
    return `<span class="badge ${h < 6 ? 'b-bad' : 'b-warn'}">${h} ساعت</span>`;
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
    if (res.status === 401) { doLogout(); throw new Error('نشست منقضی شد'); }
    let data = null;
    try { data = await res.json(); } catch (e) { /* بدون بدنه */ }
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

/* ═══════════════════ احراز هویت ═══════════════════ */

async function initAuth() {
    try {
        const st = await api('/api/status');
        $('authVer').textContent = st.version || '—';
        setPill($('authXrayState'), st.xray.running ? 'ok' : 'bad',
                'Xray ' + (st.xray.running ? 'فعال' : 'خاموش'));

        if (st.setup_done) {
            $('authBrandSub').textContent = 'ورود به پنل';
            $('loginForm').classList.remove('hidden');
        } else {
            $('authBrandSub').textContent = 'نصب اولیه پنل';
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
        $('authBrandSub').textContent = 'خطا در اتصال به سرور';
        $('authErr').textContent = 'به پنل دسترسی ندارم — مطمئن شو app.py اجراست.';
    }
}

function setPill(el, cls, text) {
    if (!el) return;
    el.className = 'pill ' + (cls || '');
    const dot = el.querySelector('.dot') || document.createElement('span');
    dot.className = 'dot';
    if (!el.contains(dot)) el.insertBefore(dot, el.firstChild);
    el.lastChild.textContent = '';
    el.append(' ' + text);
    // ساده‌تر: بازسازی کامل
    el.innerHTML = `<span class="dot"></span> ${esc(text)}`;
    el.className = 'pill ' + (cls || '');
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
        toast('خوش آمدی، ' + USER + ' 👋', 'ok');
        const me = await api('/api/me');
        PAAS = !!me.paas;
        enterApp();
    } catch (e) {
        if (e.message.includes('دومرحله')) {
            $('totpField').classList.remove('hidden');
            $('authCode').focus();
            $('authErr').textContent = 'کد دومرحله‌ای را وارد کن.';
        } else {
            $('authErr').textContent = e.message;
        }
    } finally { btnLoad(btn, false); }
}

async function doSetup() {
    const btn = $('setupBtn');
    $('setupErr').textContent = '';
    if ($('setupPass').value !== $('setupPass2').value) {
        $('setupErr').textContent = 'رمزها با هم یکسان نیستند.'; return;
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
        toast('نصب کامل شد 🎉', 'ok');
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

/* ═══════════════════ ورود به اپ ═══════════════════ */

const VIEW_META = {
    dashboard: ['داشبورد', 'نمای کلی سیستم و آمار زنده'],
    inbounds:  ['اینباند‌ها', 'مدیریت سرورهای ورودی پروکسی'],
    clients:   ['کاربران', 'مدیریت کاربران، حجم و اشتراک'],
    settings:  ['تنظیمات', 'پنل، امنیت، ربات و پشتیبان'],
    xray:      ['هسته Xray', 'وضعیت و ابزارهای هسته'],
    logs:      ['لاگ‌ها', 'رویدادهای پنل و هسته'],
};

function enterApp() {
    $('authWrap').classList.add('hidden');
    $('appWrap').classList.remove('hidden');
    $('verTag').textContent = '—';
    setPill($('modePill'), '', PAAS ? '☁️ ابری' : '🖥 VPS');
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
    const meta = VIEW_META[name] || [name, ''];
    $('viewTitle').textContent = meta[0];
    $('viewSub').textContent = meta[1];
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
        } catch (e) { /* ساکت — خطاها جای خودشان */ }
    }, POLL_MS);
}

/* ═══════════════════ داشبورد ═══════════════════ */

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
    $('stMemSub').textContent = fmtBytes(s.mem.used) + ' از ' + fmtBytes(s.mem.total);

    $('stDisk').textContent = s.disk.pct + '%';
    $('stDiskBar').style.width = Math.min(100, s.disk.pct) + '%';
    $('stDiskBar').className = s.disk.pct > 85 ? 'bad' : s.disk.pct > 65 ? 'warn' : '';
    $('stDiskSub').textContent = fmtBytes(s.disk.used) + ' از ' + fmtBytes(s.disk.total);

    $('stNet').textContent = fmtBytes(s.net.up + s.net.down) + '/s';
    $('stNetSub').textContent = '↑ ' + fmtBytes(s.net.up) + '   ↓ ' + fmtBytes(s.net.down);

    $('stToday').textContent = '↑ ' + fmtBytes(d.traffic.today_up) + '  ↓ ' + fmtBytes(d.traffic.today_down);
    $('stTotal').textContent = fmtBytes(d.traffic.up + d.traffic.down);
    $('stClients').textContent = `${d.counts.clients_active} / ${d.counts.clients}`;
    $('stConns').textContent = d.paas ? d.counts.conns : '—';

    // هسته
    setPill($('xrayState'), d.xray.running ? 'ok' : (d.xray.starting ? 'warn' : 'bad'),
            d.xray.running ? 'در حال اجرا' : d.xray.starting ? 'در حال راه‌اندازی…' : 'خاموش');
    $('xrayVer').textContent = d.xray.version || '—';
    $('xrayUptime').textContent = fmtDur(d.xray.uptime);
    $('xrayRestarts').textContent = d.xray.restarts ?? '—';

    // کاربران برتر
    const top = (d.top || []).map(c => `
        <tr>
            <td><b>${esc(c.email)}</b></td>
            <td>${fmtBytes(c.up + c.down)}</td>
            <td>${c.enable
                ? '<span class="badge b-ok">فعال</span>'
                : '<span class="badge b-bad">غیرفعال</span>'}</td>
        </tr>`).join('');
    $('topUsers').innerHTML = top || '<tr><td colspan="3" class="muted">کاربری نیست</td></tr>';

    // رویدادها
    const lv = { ok: 'ok', err: 'err', warn: 'warn', info: 'info' };
    $('dashEvents').innerHTML = (d.events || []).map(e => `
        <li><span class="lv ${lv[e.level] || 'info'}"></span>
            ${esc(e.msg)}<span class="ts">${fmtTs(e.ts)}</span></li>`).join('')
        || '<li class="muted">— خالی —</li>';

    // نمودار
    chartSeries = d.series || [];
    drawChart();
}

/* ---------- نمودار Canvas ---------- */
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
        ctx.fillStyle = '#5d6784';
        ctx.font = '12px Vazirmatn, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('در انتظار داده‌ها…', w / 2, h / 2);
        return;
    }

    const max = Math.max(2048, ...data.map(p => Math.max(p.up || 0, p.d || 0))) * 1.18;

    // شبکه
    for (let i = 0; i <= 4; i++) {
        const y = padT + ih - (ih * i / 4);
        ctx.strokeStyle = 'rgba(126,145,255,.09)';
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
        ctx.fillStyle = '#5d6784';
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
        ctx.fillStyle = color + '20';
        ctx.fill();
    };
    drawSeries('up', '#818cf8');
    drawSeries('d',  '#22d3ee');

    // برچسب زمان
    ctx.fillStyle = '#5d6784';
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

/* ═══════════════════ اینباند‌ها ═══════════════════ */

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
    $('inboundsCount').textContent = `${rows.length} اینباند`;
    $('inboundsEmpty').classList.toggle('hidden', rows.length > 0);

    $('inboundsTbody').innerHTML = rows.map(r => {
        const g = r.config || {};
        let detail;
        if (PAAS) {
            detail = `<span class="mono">${esc(g.transport || 'ws')}</span> → <span class="mono">${esc(g.path || '')}</span>`;
        } else {
            detail = `پورت <b>${esc(g.port)}</b> • <span class="mono">${esc(g.transport || 'tcp')}/${esc(g.security || 'none')}</span>`;
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
                <button class="btn-icon" title="ویرایش" data-edit-ib="${r.id}">✏️</button>
                <button class="btn-icon" title="حذف" data-del-ib="${r.id}">🗑</button>
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
    confirmBox('حذف اینباند',
        `اینباند «${r ? r.remark : id}» و اتصال همه کاربرانش به آن حذف شود؟`,
        async () => {
            try {
                const res = await api(`/api/inbounds/${id}`, { method: 'DELETE' });
                toast('حذف شد', 'ok');
                if (res.xray_error) toast('هشدار Xray: ' + res.xray_error, 'err');
                loadInbounds();
            } catch (e) { toast(e.message, 'err'); }
        });
}

/* ---------- فرم اینباند (دینامیک) ---------- */

const SS_METHODS = ['aes-256-gcm', 'aes-128-gcm', 'chacha20-poly1305', 'xchacha20-poly1305'];

function inboundForm(row) {
    const isNew = !row;
    const g = row ? (row.config || {}) : {};
    const proto = g.protocol || 'vless';

    const protoOpts = ['vless', 'vmess', 'trojan', 'shadowsocks']
        .map(p => `<option value="${p}" ${proto === p ? 'selected' : ''}
                   ${PAAS && p === 'shadowsocks' ? 'disabled' : ''}>${p.toUpperCase()}</option>`).join('');

    const transports = PAAS
        ? [['ws', 'WebSocket'], ['httpupgrade', 'HTTPUpgrade']]
        : [['tcp', 'TCP (خام — سریع‌ترین)'],
           ['ws', 'WebSocket'], ['grpc', 'gRPC'], ['httpupgrade', 'HTTPUpgrade']];
    const trOpts = transports.map(([v, t]) =>
        `<option value="${v}" ${(g.transport || (PAAS ? 'ws' : 'tcp')) === v ? 'selected' : ''}>${t}</option>`).join('');

    const secOpts = [['none', 'بدون رمزنگاری'], ['tls', 'TLS (گواهی)'], ['reality', 'Reality (بدون دامنه)']]
        .map(([v, t]) => `<option value="${v}" ${(g.security || 'none') === v ? 'selected' : ''}>${t}</option>`).join('');

    const methodOpts = SS_METHODS.map(m =>
        `<option ${g.method === m ? 'selected' : ''}>${m}</option>`).join('');

    const r = g.reality || {};

    openModal(isNew ? '➕ اینباند جدید' : '✏️ ویرایش اینباند', `
        <div class="form-grid">
            <div class="f"><label>نام (Remark)</label>
                <input id="ibRemark" value="${esc(row ? row.remark : '')}" placeholder="مثلاً SF-Main"></div>
            <div class="f"><label>پروتکل</label>
                <select id="ibProto">${protoOpts}</select></div>
        </div>

        ${PAAS ? `
        <div class="form-grid">
            <div class="f"><label>ترنسپورت</label>
                <select id="ibTransport">${trOpts}</select></div>
            <div class="f"><label>مسیر (Path)</label>
                <input id="ibPath" class="ltr" value="${esc(g.path || '')}" placeholder="/sf-xxx"></div>
        </div>
        <div class="hint">در حالت ابری، TLS توسط خود پلتفرم انجام می‌شود؛
        کلاینت‌ها با <b>wss</b> به همین مسیر وصل می‌شوند.</div>
        ` : `
        <div class="form-grid">
            <div class="f"><label>پورت</label>
                <input id="ibPort" type="number" min="1" max="65535" value="${esc(g.port || 443)}"></div>
            <div class="f"><label>ترنسپورت</label>
                <select id="ibTransport">${trOpts}</select></div>
        </div>
        <div class="form-grid">
            <div class="f"><label id="ibPathLbl">مسیر (Path)</label>
                <input id="ibPath" class="ltr" value="${esc(g.path || '')}" placeholder="/mypath"></div>
            <div class="f" id="ibHostRow"><label>هدر Host</label>
                <input id="ibHost" class="ltr" value="${esc(g.host || '')}" placeholder="اختیاری"></div>
        </div>
        <div class="f"><label>امنیت</label>
            <select id="ibSecurity">${secOpts}</select></div>

        <div id="ibTlsBox" class="hidden">
            <div class="form-grid">
                <div class="f"><label>SNI (دامنه گواهی)</label>
                    <input id="ibSni" class="ltr" value="${esc(g.sni || '')}" placeholder="example.com"></div>
                <div class="f"><label>ALPN</label>
                    <input id="ibAlpn" class="ltr" value="${esc(g.alpn || 'http/1.1')}"></div>
            </div>
            <div class="form-grid">
                <div class="f"><label>فایل گواهی (crt)</label>
                    <input id="ibCert" class="ltr" value="${esc(g.certFile || '')}" placeholder="/مسیر/fullchain.crt"></div>
                <div class="f"><label>فایل کلید (key)</label>
                    <input id="ibKey" class="ltr" value="${esc(g.keyFile || '')}" placeholder="/مسیر/priv.key"></div>
            </div>
            <div class="btn-row">
                <button class="btn btn-sm" id="ibBtnCert" type="button">📜 گواهی خودامضا بساز</button>
                <label class="sw-row" style="margin-inline-start:8px">
                    <span class="sw"><input type="checkbox" id="ibSelfsg" ${g.selfsigned ? 'checked' : ''}><span></span></span>
                    <span>کلاینت allowInsecure بگیرد</span>
                </label>
            </div>
        </div>

        <div id="ibRealityBox" class="hidden">
            <div class="form-grid">
                <div class="f"><label>dest (目标 سایت)</label>
                    <input id="ibRDest" class="ltr" value="${esc(r.dest || 'www.microsoft.com:443')}"></div>
                <div class="f"><label>serverNames (با کاما)</label>
                    <input id="ibRNames" class="ltr" value="${esc((r.serverNames || []).join(','))}" placeholder="www.microsoft.com"></div>
            </div>
            <div class="form-grid">
                <div class="f"><label>privateKey</label>
                    <input id="ibRPriv" class="ltr" value="${esc(r.privateKey || '')}"></div>
                <div class="f"><label>publicKey</label>
                    <input id="ibRPub" class="ltr" value="${esc(r.publicKey || '')}"></div>
            </div>
            <div class="f"><label>shortIds (hex، با کاما)</label>
                <input id="ibRSids" class="ltr" value="${esc((r.shortIds || []).join(','))}" placeholder="auto"></div>
            <button class="btn btn-sm" id="ibBtnKeys" type="button">🔑 تولید کلید x25519</button>
        </div>
        `}

        <div id="ibSsBox" class="hidden">
            <div class="form-grid">
                <div class="f"><label>روش رمزنگاری</label>
                    <select id="ibMethod">${methodOpts}</select></div>
                <div class="f"><label>رمز</label>
                    <input id="ibPass" class="ltr" value="${esc(g.password || '')}" placeholder="خالی = خودکار"></div>
            </div>
        </div>

        <div class="modal-err" id="ibErr"></div>
    `, `
        <button class="btn btn-pri" id="ibSave">💾 ذخیره و اعمال</button>
        <button class="btn" id="ibCancel">انصراف</button>
    `, true);

    /* --- رفتار فرم --- */
    const $ib = (id) => $('modalBody').querySelector('#' + id);
    const vis = () => {
        const proto = $ib('ibProto').value;
        const tr = $ib('ibTransport').value;
        const sec = PAAS ? 'none' : ($ib('ibSecurity') || {}).value;
        $ib('ibSsBox').classList.toggle('hidden', proto !== 'shadowsocks');
        if (!PAAS) {
            $ib('ibPathLbl').textContent = tr === 'grpc' ? 'نام سرویس gRPC' : 'مسیر (Path)';
            $ib('ibPath').placeholder = tr === 'grpc' ? 'myservice' : '/mypath';
            $ib('ibHostRow').style.display = ['ws', 'httpupgrade'].includes(tr) ? '' : 'none';
            $ib('ibTlsBox').classList.toggle('hidden', sec !== 'tls');
            $ib('ibRealityBox').classList.toggle('hidden', sec !== 'reality');
        }
    };
    $ib('ibProto').onchange = vis;
    $ib('ibTransport').onchange = vis;
    if (!PAAS) $ib('ibSecurity').onchange = vis;
    vis();

    if (!PAAS) {
        const keysBtn = $ib('ibBtnKeys');
        if (keysBtn) keysBtn.onclick = async () => {
            btnLoad(keysBtn, true);
            try {
                const k = await api('/api/xray/x25519', { method: 'POST' });
                $ib('ibRPriv').value = k.privateKey;
                $ib('ibRPub').value = k.publicKey;
                toast('کلید تولید و پر شد ✅', 'ok');
            } catch (e) { toast(e.message, 'err'); }
            finally { btnLoad(keysBtn, false); }
        };
        const certBtn = $ib('ibBtnCert');
        if (certBtn) certBtn.onclick = async () => {
            btnLoad(certBtn, true);
            try {
                const domain = $ib('ibSni').value.trim() || $('setDomain').value.trim();
                const c = await api('/api/xray/cert', { method: 'POST', body: { domain } });
                $ib('ibCert').value = c.certFile;
                $ib('ibKey').value = c.keyFile;
                if (!$ib('ibSni').value.trim()) $ib('ibSni').value = c.domain;
                $ib('ibSelfsg').checked = true;
                toast('گواهی ساخته و پر شد ✅', 'ok');
            } catch (e) { toast(e.message, 'err'); }
            finally { btnLoad(certBtn, false); }
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
            toast('ذخیره و روی هسته اعمال شد ✅', 'ok');
            closeModal();
            loadInbounds();
        } catch (e) { err.textContent = e.message; }
        finally { btnLoad($('ibSave'), false); }
    };
}

/* ═══════════════════ کاربران ═══════════════════ */

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
    $('clientsCount').textContent = `${rows.length} کاربر`;
    $('clientsEmpty').classList.toggle('hidden', rows.length > 0);

    $('clientsTbody').innerHTML = rows.map(c => {
        const pct = c.limit_bytes ? Math.min(100, c.used * 100 / c.limit_bytes) : 0;
        const barCls = pct >= 90 ? 'bad' : pct >= 70 ? 'warn' : '';
        return `
        <tr>
            <td><label class="sw"><input type="checkbox" ${c.enable ? 'checked' : ''}
                data-tgl-cl="${c.id}"><span></span></label></td>
            <td class="email-cell"><b>${esc(c.email)}</b>
                ${c.tg_id ? '<div class="cell-sub">🤖 متصل به تلگرام</div>' : ''}
                ${c.note ? `<div class="cell-sub">📝 ${esc(c.note)}</div>` : ''}</td>
            <td><div class="tag-list">${(c.inbound_names || []).map(n =>
                `<span class="badge b-def">${esc(n)}</span>`).join('')}</div></td>
            <td>${fmtBytes(c.used)}
                ${c.limit_bytes ? `<div class="prog prog-sm"><i class="${barCls}" style="width:${pct}%"></i></div>
                <div class="cell-sub">${pct}%</div>` : ''}</td>
            <td>${c.limit_bytes ? fmtBytes(c.limit_bytes) : '<span class="badge b-def">∞</span>'}</td>
            <td>${fmtExpiryHtml(c.expiry)}</td>
            <td><div class="acts">
                <button class="btn-icon" title="لینک‌ها و QR" data-links="${c.id}">🔗</button>
                <button class="btn-icon" title="مصرف روزانه" data-days="${c.id}">📅</button>
                <button class="btn-icon" title="ویرایش" data-edit-cl="${c.id}">✏️</button>
                <button class="btn-icon" title="ریست آمار" data-rst="${c.id}">↺</button>
                <button class="btn-icon" title="حذف" data-del-cl="${c.id}">🗑</button>
            </div></td>
        </tr>`;
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
        el.onclick = () => confirmBox('ریست آمار',
            `مصرف «${clientName(el.dataset.rst)}» صفر شود؟`,
            async () => {
                try {
                    await api(`/api/clients/${el.dataset.rst}/reset`, { method: 'POST' });
                    toast('آمار ریست شد', 'ok'); loadClients();
                } catch (e) { toast(e.message, 'err'); }
            }));
    tb.querySelectorAll('[data-del-cl]').forEach(el =>
        el.onclick = () => confirmBox('حذف کاربر',
            `کاربر «${clientName(el.dataset.delCl)}» و کانفیگش حذف شود؟`,
            async () => {
                try {
                    await api(`/api/clients/${el.dataset.delCl}`, { method: 'DELETE' });
                    toast('حذف شد', 'ok'); loadClients();
                } catch (e) { toast(e.message, 'err'); }
            }));
}

function clientName(id) {
    const c = clientsCache.find(x => x.id == id);
    return c ? c.email : id;
}

async function toggleClient(id) {
    try {
        await api(`/api/clients/${id}/toggle`, { method: 'POST' });
        await loadClients();
    } catch (e) { toast(e.message, 'err'); loadClients(); }
}

/* ---------- فرم کاربر ---------- */

function clientForm(c) {
    const isNew = !c;
    const inbs = inboundsCache;

    openModal(isNew ? '➕ کاربر جدید' : '✏️ ویرایش کاربر', `
        <div class="form-grid">
            <div class="f"><label>نام کاربر (ایمیل)</label>
                <input id="clEmail" value="${esc(c ? c.email : '')}" placeholder="ali"></div>
            <div class="f"><label>UUID</label>
                <div class="exp-flex">
                    <input id="clUuid" class="ltr" value="${esc(c ? c.uuid : '')}" placeholder="خالی = خودکار">
                    <button class="btn-icon" id="clUuidBtn" title="تولید" type="button">🎲</button>
                </div></div>
        </div>

        <div class="f"><label>رمز (برای Trojan / SS)</label>
            <div class="exp-flex">
                <input id="clPass" class="ltr" value="${esc(c ? c.password : '')}" placeholder="خالی = خودکار">
                <button class="btn-icon" id="clPassBtn" title="تولید" type="button">🎲</button>
            </div></div>

        <div class="f"><label>اینباند‌ها</label>
            <div class="chk-list">${inbs.map(ib => `
                <label class="chk-item ${ib.enable ? '' : 'dis'}">
                    <input type="checkbox" class="cl-inb" value="${ib.id}"
                        ${c && (c.inbounds || []).includes(ib.id) ? 'checked' : ''}
                        ${ib.enable ? '' : 'disabled'}>
                    <span>${esc(ib.remark)}</span>
                    <span class="badge b-${ib.protocol}">${ib.protocol.toUpperCase()}</span>
                </label>`).join('') || '<div class="muted" style="padding:10px">اول یک اینباند بساز</div>'}
            </div></div>

        <div class="f hidden" id="clFlowRow"><label>فلوِ VLESS</label>
            <select id="clFlow">
                <option value="">— بدون فلوِ (پیشنهادی برای ws) —</option>
                <option value="xtls-rprx-vision" ${c && c.flow === 'xtls-rprx-vision' ? 'selected' : ''}>xtls-rprx-vision</option>
            </select>
            <div class="hint">فقط روی VLESS + TCP + TLS/Reality اثر دارد.</div></div>

        <div class="form-grid">
            <div class="f"><label>انقضا</label>
                <div class="exp-flex">
                    <select id="clExpMode">
                        <option value="never" ${!c || !c.expiry ? 'selected' : ''}>بدون انقضا</option>
                        <option value="date" ${c && c.expiry ? 'selected' : ''}>تاریخ دقیق</option>
                        <option value="days">N روز از الان</option>
                    </select>
                    <input id="clExpVal" class="ltr" type="datetime-local"
                        value="${c && c.expiry ? toLocalInput(c.expiry) : ''}"
                        ${(!c || !c.expiry) ? 'style="visibility:hidden"' : ''}>
                </div></div>
            <div class="f"><label>محدودیت حجم</label>
                <div class="exp-flex">
                    <select id="clLimMode">
                        <option value="off" ${!c || !c.limit_bytes ? 'selected' : ''}>نامحدود</option>
                        <option value="gb" ${c && c.limit_bytes >= 1073741824 ? 'selected' : ''}>گیگابایت</option>
                        <option value="mb" ${c && c.limit_bytes && c.limit_bytes < 1073741824 ? 'selected' : ''}>مگابایت</option>
                    </select>
                    <input id="clLimVal" type="number" min="0" step="any" placeholder="0"
                        value="${c && c.limit_bytes
                            ? Math.round(c.limit_bytes / (c.limit_bytes >= 1073741824 ? 1073741824 : 1048576) * 100) / 100
                            : ''}"
                        ${(!c || !c.limit_bytes) ? 'style="visibility:hidden"' : ''}>
                </div></div>
        </div>

        <div class="form-grid">
            <div class="f"><label>شناسه تلگرام (اختیاری)</label>
                <input id="clTg" class="ltr" value="${esc(c ? c.tg_id : '')}" placeholder="123456789"></div>
            <div class="f"><label>یادداشت (اختیاری)</label>
                <input id="clNote" value="${esc(c ? c.note : '')}" placeholder="مشتری، قیمت، …"></div>
        </div>

        <div class="f sw-row">
            <span class="sw"><input type="checkbox" id="clEnable" ${isNew || (c && c.enable) ? 'checked' : ''}><span></span></span>
            <span>کاربر فعال باشد</span>
        </div>

        <div class="modal-err" id="clErr"></div>
    `, `
        <button class="btn btn-pri" id="clSave">💾 ذخیره و اعمال</button>
        <button class="btn" id="clCancel">انصراف</button>
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
        const el = $cl('clExpVal');
        if ($cl('clExpMode').value === 'days') {
            el.type = 'number'; el.placeholder = '30';
            el.value = el.dataset.daysVal || '30';
            el.style.visibility = '';
        } else if ($cl('clExpMode').value === 'date') {
            el.type = 'datetime-local';
            el.value = el.dataset.dateVal || toLocalInput(Date.now() + 30 * 86400000);
            el.style.visibility = '';
        } else el.style.visibility = 'hidden';
    };
    $cl('clExpVal').dataset.dateVal = c && c.expiry ? toLocalInput(c.expiry) : '';

    $cl('clLimMode').onchange = () => {
        const el = $cl('clLimVal');
        el.style.visibility = $cl('clLimMode').value === 'off' ? 'hidden' : '';
    };

    $('clCancel').onclick = closeModal;
    $('clSave').onclick = async () => {
        const err = $cl('clErr'); err.textContent = '';

        // محاسبه انقضا
        let expiry = 0;
        const expMode = $cl('clExpMode').value;
        if (expMode === 'date') {
            const v = $cl('clExpVal').value;
            expiry = v ? new Date(v).getTime() : 0;
        } else if (expMode === 'days') {
            const d = parseFloat($cl('clExpVal').value) || 0;
            expiry = d > 0 ? Date.now() + d * 86400000 : 0;
        }

        // محاسبه حجم
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
            inbounds: [...$('modalBody').querySelectorAll('.cl-inb:checked')].map(el => +el.value),
            expiry, limit_bytes: limit,
            tg_id: $cl('clTg').value.trim(),
            note: $cl('clNote').value.trim(),
            enable: $cl('clEnable').checked,
        };

        btnLoad($('clSave'), true);
        try {
            if (isNew) await api('/api/clients', { method: 'POST', body });
            else await api(`/api/clients/${c.id}`, { method: 'PUT', body });
            toast('ذخیره و روی هسته اعمال شد ✅', 'ok');
            closeModal();
            loadClients();
        } catch (e) { err.textContent = e.message; }
        finally { btnLoad($('clSave'), false); }
    };
}

/* ---------- لینک‌ها + QR ---------- */

async function showLinks(id) {
    openModal('🔗 لینک‌ها و اشتراک', '<div class="muted">در حال دریافت…</div>', '', true);
    try {
        const d = await api(`/api/clients/${id}/links`);
        const body = [];

        body.push(`
            <div class="kv"><span>وضعیت</span>
                <b>${d.enabled ? '<span class="badge b-ok">فعال</span>'
                               : '<span class="badge b-bad">غیرفعال</span>'}</b></div>
            <div class="kv"><span>مصرف</span><b>${fmtBytes(d.used)}${d.total ? ' از ' + fmtBytes(d.total) : ''}</b></div>
            <div class="kv"><span>انقضا</span><b>${d.expire ? fmtTs(d.expire * 1000) : '∞'}</b></div>
            <div class="lbl2" style="margin-top:16px">📥 لینک اشتراک (همه‌ی کانفیگ‌ها با یک لینک)</div>
            <div class="copybox mono" id="lnSub">${esc(d.sub_url)}</div>
            <div class="btn-row">
                <button class="btn btn-sm" id="lnSubCopy">📋 کپی لینک اشتراک</button>
                <button class="btn btn-sm" id="lnSubQr">🔍 QR اشتراک</button>
            </div>
            <div class="qr-mini" id="lnSubQrBox"></div>

            <div class="lbl2" style="margin-top:18px">🤖 اتصال به ربات تلگرام</div>
            <div class="hint">این کد را در ربات بفرست: <code>/bind کد</code></div>
            <div class="copybox mono" id="lnBind">${esc(d.bind_code)}</div>
            <button class="btn btn-sm" id="lnBindCopy">📋 کپی کد اتصال</button>

            <div class="lbl2" style="margin-top:18px">🔗 لینک‌های تکی</div>
        `);

        (d.links || []).forEach((l, i) => {
            body.push(`
                <div class="link-item">
                    <div class="ln-name">
                        <span class="badge b-${l.protocol}">${l.protocol.toUpperCase()}</span>
                        ${esc(l.name)}
                    </div>
                    <div class="ln-code">${esc(l.link)}</div>
                    <div class="ln-acts">
                        <button class="btn btn-sm" data-copy="${i}">📋 کپی</button>
                        <button class="btn btn-sm" data-qr="${i}">🔍 QR</button>
                    </div>
                    <div class="qr-mini hidden" id="qrbox-${i}"></div>
                </div>`);
        });

        openModal(`🔗 لینک‌های «${esc(d.email)}»`, body.join(''), '', true);

        $('lnSubCopy').onclick = () => copyText(d.sub_url);
        $('lnBindCopy').onclick = () => copyText(d.bind_code);
        $('lnSubQr').onclick = async () => {
            const box = $('lnSubQrBox');
            if (box.innerHTML) { box.innerHTML = ''; return; }
            box.innerHTML = '<span class="muted">…</span>';
            box.innerHTML = await fetchQrSvg(d.sub_url) || 'خطا در ساخت QR';
        };
        $('modalBody').querySelectorAll('[data-copy]').forEach(el =>
            el.onclick = () => copyText(d.links[+el.dataset.copy].link));
        $('modalBody').querySelectorAll('[data-qr]').forEach(el =>
            el.onclick = async () => {
                const i = +el.dataset.qr;
                const box = $('qrbox-' + i);
                if (box.innerHTML) { box.innerHTML = ''; return; }
                box.classList.remove('hidden');
                box.innerHTML = '<span class="muted">…</span>';
                box.innerHTML = await fetchQrSvg(d.links[i].link) || 'خطا';
            });
    } catch (e) {
        openModal('خطا', `<div class="err">${esc(e.message)}</div>`, '');
    }
}

/* ---------- مصرف روزانه ---------- */

async function showDaily(id) {
    openModal('📅 مصرف روزانه', '<div class="muted">…</div>', '', true);
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
                    <div class="cell-sub">${fmtBytes(total)}</div></td>
            </tr>`;
        }).join('');
        openModal(`📅 مصرف روزانه — ${esc(d.email)}`,
            days.length ? `
            <div class="tbl-wrap"><table>
                <thead><tr><th>روز (UTC)</th><th>آپلود</th><th>دانلود</th><th>مجموع</th></tr></thead>
                <tbody>${rows}</tbody>
            </table></div>` : '<div class="empty"><div class="big">📭</div>داده‌ای ثبت نشده</div>',
            '', true);
    } catch (e) {
        openModal('خطا', `<div class="err">${esc(e.message)}</div>`, '');
    }
}

/* ═══════════════════ تنظیمات ═══════════════════ */

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

        // TOTP
        const on = !!s.totp_enabled;
        setPill($('totpStatus'), on ? 'ok' : 'bad', on ? 'فعال ✅' : 'غیرفعال');
        $('totpSetupBox').classList.add('hidden');
        $('totpDisableBox').classList.toggle('hidden', !on);
        $('btnTotpSetup').classList.toggle('hidden', on);
    } catch (e) { toast(e.message, 'err'); }
}

async function saveSettings(body, btn) {
    btnLoad(btn, true);
    try {
        await api('/api/settings', { method: 'PUT', body });
        toast('ذخیره شد ✅', 'ok');
    } catch (e) { toast(e.message, 'err'); }
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
        $('tgTestResult').textContent = 'در حال تست…';
        btnLoad(e.target, true);
        try {
            const r = await api('/api/settings/tg-test', { method: 'POST' });
            $('tgTestResult').textContent = '✅ متصل — ربات: ' + r.bot;
            toast('تلگرام متصل است ✅', 'ok');
        } catch (err) { $('tgTestResult').textContent = '❌ ' + err.message; }
        finally { btnLoad(e.target, false); }
    };

    $('btnChangePass').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            const r = await api('/api/settings/password', { method: 'POST', body: {
                old: $('passOld').value, new: $('passNew').value }});
            TOKEN = r.token;
            localStorage.setItem('sf_token', TOKEN);
            $('passOld').value = ''; $('passNew').value = '';
            toast('رمز عوض شد؛ نشست تازه ذخیره شد ✅', 'ok');
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };

    /* TOTP */
    $('btnTotpSetup').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            const r = await api('/api/settings/totp/setup', { method: 'POST' });
            $('totpSetupBox').classList.remove('hidden');
            $('totpSecret').textContent = r.secret;
            const qr = await fetchQrSvg(r.uri);
            $('totpQr').innerHTML = qr || '<div class="hint">کلید را دستی در اپ وارد کن.</div>';
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };
    $('btnTotpEnable').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            await api('/api/settings/totp/enable', { method: 'POST',
                body: { code: $('totpCode').value.trim() }});
            toast('دومرحله‌ای فعال شد 🔐', 'ok');
            loadSettings();
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };
    $('btnTotpDisable').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            await api('/api/settings/totp/disable', { method: 'POST',
                body: { password: $('totpDisablePass').value }});
            toast('دومرحله‌ای غیرفعال شد', 'ok');
            loadSettings();
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };

    /* پشتیبان */
    $('btnBackup').onclick = async () => {
        try {
            const res = await fetch('/api/backup',
                { headers: { 'Authorization': 'Bearer ' + TOKEN } });
            if (!res.ok) throw new Error('خطا در تهیه پشتیبان');
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'sf-panel-backup-' +
                new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-') + '.json';
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 4000);
            toast('پشتیبان دانلود شد ✅', 'ok');
        } catch (err) { toast(err.message, 'err'); }
    };
    $('btnRestore').onclick = () => {
        const f = $('restoreFile').files[0];
        if (!f) { toast('اول فایل را انتخاب کن', 'err'); return; }
        confirmBox('بازیابی پشتیبان',
            '⚠️ اینباند‌ها و کاربران فعلی با فایل پشتیبان جایگزین می‌شوند. ادامه؟',
            async () => {
                try {
                    const data = JSON.parse(await f.text());
                    const r = await api('/api/restore', { method: 'POST', body: data });
                    toast(`بازیابی شد: ${r.inbounds} اینباند، ${r.clients} کاربر ✅`, 'ok');
                    if (r.xray_error) toast('هشدار Xray: ' + r.xray_error, 'err');
                    loadSettings(); loadInbounds(); loadClients();
                } catch (err) { toast(err.message, 'err'); }
            });
    };
}

/* ═══════════════════ نمای Xray ═══════════════════ */

async function loadXrayView() {
    try {
        const [info, dash] = await Promise.all([api('/api/info'), api('/api/dashboard')]);
        const x = dash.xray;

        setPill($('xray2State'), x.running ? 'ok' : 'warn', x.running ? 'در حال اجرا' : 'خاموش');
        $('xray2Ver').textContent = x.version || '—';
        $('xray2Uptime').textContent = fmtDur(x.uptime);
        $('xray2Goro').textContent = x.goroutines ?? '—';
        $('xray2Alloc').textContent = fmtBytes(x.alloc);

        const errBox = $('xray2ErrBox');
        if (x.error && !x.running) {
            errBox.classList.remove('hidden');
            $('xray2ErrText').textContent = x.error;
        } else errBox.classList.add('hidden');

        // مسیرهای روتر
        $('routesCard').classList.toggle('hidden', !PAAS);
        if (PAAS) {
            $('xrayRoutes').innerHTML = (info.routes || []).map(r => `
                <tr><td class="mono">${esc(r.path)}</td>
                    <td class="mono">${esc(r.internal_port)}</td></tr>`).join('')
                || '<tr><td colspan="2" class="muted">مسیری نیست</td></tr>';
        }

        $('modeInfo').innerHTML = PAAS
            ? `حالت <b>ابری (PaaS)</b> — همه‌چیز پشت روتر L4 روی پورت
               <b>${esc(info.public_port)}</b> است. پنل و اینباند‌های پروکسی (WebSocket)
               هر دو از همین پورت سرو می‌شوند. آدرس عمومی: <span class="mono">${esc(info.host)}</span>`
            : `حالت <b>سرور (VPS)</b> — پنل روی پورت <b>${esc(info.public_port)}</b> و
               اینباند‌ها روی پورت‌های واقعی خودشان. Reality/TLS/gRPC کامل پشتیبانی می‌شود.
               آدرس: <span class="mono">${esc(info.host)}</span>`;
    } catch (e) { toast(e.message, 'err'); }
}

function bindXrayEvents() {
    const restart = async (btn) => {
        btnLoad(btn, true);
        try {
            await api('/api/xray/restart', { method: 'POST' });
            toast('هسته راه‌اندازی مجدد شد ✅', 'ok');
            loadXrayView(); loadDashboard();
        } catch (e) { toast(e.message, 'err'); }
        finally { btnLoad(btn, false); }
    };
    $('btnXrayRestart').onclick = (e) => restart(e.target);
    $('btnXrayRestart2').onclick = (e) => restart(e.target);

    $('btnXrayUpdate').onclick = (e) => {
        confirmBox('بروزرسانی هسته',
            'آخرین نسخه Xray-core دانلود و نصب شود؟ چند لحظه طول می‌کشد.',
            async () => {
                toast('در حال دانلود…');
                try {
                    const r = await api('/api/xray/update', { method: 'POST' });
                    toast('بروزرسانی شد: ' + (r.version || '?') + ' ✅', 'ok');
                    loadXrayView();
                } catch (err) { toast(err.message, 'err'); }
            });
    };

    $('btnXrayKeys').onclick = async (e) => {
        btnLoad(e.target, true);
        try {
            const k = await api('/api/xray/x25519', { method: 'POST' });
            const box = $('x25519Box');
            box.classList.remove('hidden');
            box.textContent = `Private: ${k.privateKey}\nPublic:  ${k.publicKey}`;
            box.onclick = () => copyText(k.privateKey);
            toast('برای کپی روی کادر کلیک کن', 'ok');
        } catch (err) { toast(err.message, 'err'); }
        finally { btnLoad(e.target, false); }
    };

    $('btnGenCert').onclick = async (e) => {
        btnLoad(e.target, true);
        $('certResult').textContent = 'در حال ساخت…';
        try {
            const c = await api('/api/xray/cert', { method: 'POST',
                body: { domain: $('certDomain').value.trim() }});
            $('certResult').innerHTML =
                `✅ ساخته شد برای <b>${esc(c.domain)}</b><br>
                 <span class="mono" style="font-size:.7rem">
                 cert: ${esc(c.certFile)}<br>key: ${esc(c.keyFile)}</span><br>
                 در فرم اینباند TLS همین مسیرها را وارد کن.`;
        } catch (err) { $('certResult').textContent = '❌ ' + err.message; }
        finally { btnLoad(e.target, false); }
    };
}

/* ═══════════════════ لاگ‌ها ═══════════════════ */

let LOG_TYPE = 'panel';

async function loadLogs() {
    try {
        const r = await api('/api/logs?type=' + LOG_TYPE);
        $('logBox').textContent = r.lines || '— خالی —';
        $('logBox').scrollTop = 0;
    } catch (e) { toast(e.message, 'err'); }
}

function bindLogEvents() {
    const setSeg = (active) => {
        $('logTypePanel').classList.toggle('active', active === 'panel');
        $('logTypeXray').classList.toggle('active', active === 'xray');
    };
    $('logTypePanel').onclick = () => { LOG_TYPE = 'panel'; setSeg('panel'); loadLogs(); };
    $('logTypeXray').onclick = () => { LOG_TYPE = 'xray'; setSeg('xray'); loadLogs(); };
    $('btnRefreshLogs').onclick = loadLogs;
}

/* ═══════════════════ سایدبار موبایل ═══════════════════ */

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

/* ═══════════════════ راه‌اندازی ═══════════════════ */

function bindGlobalEvents() {
    // Auth
    $('authBtn').onclick = doLogin;
    $('setupBtn').onclick = doSetup;
    $('authPass').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
    $('authCode').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
    $('setupPass2').addEventListener('keydown', e => { if (e.key === 'Enter') doSetup(); });

    // Nav
    document.querySelectorAll('.nav-item').forEach(n =>
        n.onclick = () => switchView(n.dataset.view));

    // Topbar
    $('logoutBtn').onclick = () => confirmBox('خروج',
        'از پنل خارج می‌شوی؟', doLogout, 'خروج');
    $('mobileMenu').onclick = () =>
        $('sidebar').classList.contains('open') ? closeSidebar() : openSidebar();

    // تولبارها
    $('btnAddInbound').onclick = () => inboundForm(null);
    $('btnAddClient').onclick = () => {
        if (!inboundsCache.length) { toast('اول یک اینباند بساز', 'err'); return; }
        clientForm(null);
    };
    $('inboundSearch').oninput = renderInbounds;
    $('clientSearch').oninput = renderClients;

    // مودال
    $('modalClose').onclick = closeModal;
    $('modalBack').addEventListener('click', e => {
        if (e.target === $('modalBack')) closeModal();
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && currentModal) closeModal();
    });

    // بخش‌ها
    bindSettingsEvents();
    bindXrayEvents();
    bindLogEvents();

    // نمودار در تغییر اندازه
    let rz;
    window.addEventListener('resize', () => {
        clearTimeout(rz);
        rz = setTimeout(() => { if (VIEW === 'dashboard') drawChart(); }, 150);
    });
}

bindGlobalEvents();
initAuth();