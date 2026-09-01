'use strict';

/* ═══════════════════════════════════════════════════════════
   SF-Panel — i18n.js
   English (default) / فارسی
   ▸ I(key, ...args)      → رشته ترجمه؛ {0} {1} جایگزین می‌شوند
   ▸ applyI18n()          → اعمال روی همه [data-i18n] + dir/lang
   ▸ LangUI               → سوییچر (initLanguageUI به دکمه وصل می‌شود)
   ═══════════════════════════════════════════════════════════ */

const LANGS = { en: 'English', fa: 'فارسی' };

const I18N = {
  /* ---------- عمومی ---------- */
  'app.name':        { en: 'SF-Panel', fa: 'SF-Panel' },
  'app.tagline':     { en: 'Xray Management Panel', fa: 'پنل مدیریت Xray' },
  'common.loading':  { en: 'Loading…', fa: 'در حال بارگذاری…' },
  'common.copy':     { en: 'Copy', fa: 'کپی' },
  'common.copied':   { en: 'Copied ✓', fa: 'کپی شد ✓' },
  'common.copyFail': { en: 'Copy failed — select manually', fa: 'کپی ناموفق — دستی انتخاب کن' },
  'common.cancel':   { en: 'Cancel', fa: 'انصراف' },
  'common.save':     { en: 'Save & Apply', fa: 'ذخیره و اعمال' },
  'common.refresh':  { en: 'Refresh', fa: 'بروزرسانی' },
  'common.yes':      { en: 'Yes, do it', fa: 'بله، انجام بده' },
  'common.search':   { en: 'Search…', fa: 'جستجو…' },
  'common.empty':    { en: 'Nothing here yet', fa: 'هنوز چیزی اینجا نیست' },
  'common.error':    { en: 'Error', fa: 'خطا' },
  'common.ok':       { en: 'OK', fa: 'باشه' },
  'common.never':    { en: 'Never', fa: 'هرگز' },
  'common.unlimited':{ en: 'Unlimited', fa: 'نامحدود' },
  'common.active':   { en: 'Active', fa: 'فعال' },
  'common.disabled': { en: 'Disabled', fa: 'غیرفعال' },
  'common.enabled':  { en: 'Enabled', fa: 'فعال' },
  'common.confirm':  { en: 'Confirm', fa: 'تأیید' },
  'common.delete':   { en: 'Delete', fa: 'حذف' },
  'common.edit':     { en: 'Edit', fa: 'ویرایش' },
  'common.enabledBadge': { en: 'On', fa: 'روشن' },
  'common.disabledBadge': { en: 'Off', fa: 'خاموش' },
  'common.noData':   { en: 'No data', fa: 'داده‌ای نیست' },
  'common.auto':     { en: 'Auto', fa: 'خودکار' },

  /* ---------- ورود/نصب ---------- */
  'auth.checking':     { en: 'Checking status…', fa: 'در حال بررسی وضعیت…' },
  'auth.login':        { en: 'Log in', fa: 'ورود' },
  'auth.loginToPanel': { en: 'Sign in to your panel', fa: 'ورود به پنل' },
  'auth.setup':        { en: 'Initial setup', fa: 'نصب اولیه' },
  'auth.setupHint':    { en: 'Create your admin account', fa: 'حساب مدیر را بساز' },
  'auth.username':     { en: 'Username', fa: 'نام کاربری' },
  'auth.password':     { en: 'Password', fa: 'رمز عبور' },
  'auth.password2':    { en: 'Repeat password', fa: 'تکرار رمز عبور' },
  'auth.newPassword':  { en: 'New password (min 6)', fa: 'رمز جدید (حداقل ۶)' },
  'auth.currentPassword': { en: 'Current password', fa: 'رمز فعلی' },
  'auth.2faCode':      { en: '2FA code', fa: 'کد دومرحله‌ای' },
  'auth.2faHint':      { en: 'Enter the 6-digit code from your app.', fa: 'کد ۶ رقمی اپ را وارد کن.' },
  'auth.btnLogin':     { en: 'Sign in', fa: 'ورود به پنل' },
  'auth.btnInstall':   { en: 'Install panel', fa: 'نصب پنل' },
  'auth.welcome':      { en: 'Welcome back, {0} 👋', fa: 'خوش آمدی، {0} 👋' },
  'auth.installed':    { en: 'Installation complete 🎉', fa: 'نصب کامل شد 🎉' },
  'auth.sessionSetup': { en: 'Session expired — sign in again', fa: 'نشست منقضی شد — دوباره وارد شو' },
  'auth.pwMismatch':   { en: 'Passwords do not match.', fa: 'رمزها با هم یکسان نیستند.' },
  'auth.enter2fa':     { en: 'Enter your 2FA code.', fa: 'کد دومرحله‌ای را وارد کن.' },
  'auth.connError':    { en: 'Cannot reach the panel — make sure app.py is running.', fa: 'به پنل دسترسی ندارم — مطمئن شو app.py اجراست.' },
  'auth.errConnFail':  { en: 'Server unreachable', fa: 'اتصال به سرور ممکن نیست' },

  /* ---------- ناوبری ---------- */
  'nav.dashboard': { en: 'Dashboard', fa: 'داشبورد' },
  'nav.inbounds':  { en: 'Inbounds', fa: 'اینباند‌ها' },
  'nav.clients':   { en: 'Clients', fa: 'کاربران' },
  'nav.settings':  { en: 'Settings', fa: 'تنظیمات' },
  'nav.xray':      { en: 'Xray Core', fa: 'هسته Xray' },
  'nav.logs':      { en: 'Logs', fa: 'لاگ‌ها' },
  'nav.logout':    { en: 'Log out', fa: 'خروج' },
  'nav.xrayOn':    { en: 'Xray OK', fa: 'Xray سالم' },
  'nav.xrayOff':   { en: 'Xray down', fa: 'Xray خاموش' },
  'nav.paasMode':  { en: '☁ Cloud', fa: '☁ ابری' },
  'nav.vpsMode':   { en: '🖥 VPS', fa: '🖥 VPS' },

  'view.dashboard.sub': { en: 'System overview & live traffic', fa: 'نمای کلی سیستم و آمار زنده' },
  'view.inbounds.sub':  { en: 'Manage proxy inbounds', fa: 'مدیریت اینباند‌های پروکسی' },
  'view.clients.sub':   { en: 'Users, quotas & subscriptions', fa: 'کاربران، محدودیت‌ها و اشتراک' },
  'view.settings.sub':  { en: 'Panel, security, bot & backup', fa: 'پنل، امنیت، ربات و پشتیبان' },
  'view.xray.sub':      { en: 'Core status & tools', fa: 'وضعیت و ابزارهای هسته' },
  'view.logs.sub':      { en: 'Panel & core events', fa: 'رویدادهای پنل و هسته' },

  /* ---------- داشبورد ---------- */
  'dash.cpu':        { en: 'CPU', fa: 'پردازنده' },
  'dash.memory':     { en: 'Memory', fa: 'حافظه' },
  'dash.disk':       { en: 'Disk', fa: 'دیسک' },
  'dash.net':        { en: 'Network (live)', fa: 'شبکه (لحظه‌ای)' },
  'dash.ofTotal':    { en: '{0} of {1}', fa: '{0} از {1}' },
  'dash.todayUsage': { en: 'Usage today', fa: 'مصرف امروز' },
  'dash.totalUsage': { en: 'Total user traffic', fa: 'ترافیک کل کاربران' },
  'dash.clients':    { en: 'Clients (active/total)', fa: 'کاربران (فعال/کل)' },
  'dash.conns':      { en: 'Live connections', fa: 'اتصالات زنده' },
  'dash.trafficChart': { en: 'Live traffic', fa: 'ترافیک زنده' },
  'dash.upload':     { en: 'Upload', fa: 'آپلود' },
  'dash.download':   { en: 'Download', fa: 'دانلود' },
  'dash.xrayCore':   { en: 'Xray core', fa: 'هسته Xray' },
  'dash.version':    { en: 'Version', fa: 'نسخه' },
  'dash.uptime':     { en: 'Uptime', fa: 'آپتایم' },
  'dash.restarts':   { en: 'Restarts', fa: 'ری‌استارت‌ها' },
  'dash.btnRestart': { en: '🔄 Restart core', fa: '🔄 راه‌اندازی مجدد' },
  'dash.topUsers':   { en: 'Top consumers', fa: 'بیشترین مصرف' },
  'dash.recentEvents': { en: 'Recent events', fa: 'رویدادهای اخیر' },
  'dash.waiting':    { en: 'Waiting for data…', fa: 'در انتظار داده…' },
  'dash.userCol':    { en: 'Client', fa: 'کاربر' },
  'dash.usageCol':   { en: 'Usage', fa: 'مصرف' },
  'dash.statusCol':  { en: 'Status', fa: 'وضعیت' },
  'dash.running':    { en: 'Running', fa: 'در حال اجرا' },
  'dash.starting':   { en: 'Starting…', fa: 'در حال راه‌اندازی…' },
  'dash.stopped':    { en: 'Stopped', fa: 'خاموش' },

  /* ---------- اینباند‌ها ---------- */
  'ib.title':        { en: 'Inbounds', fa: 'اینباند‌ها' },
  'ib.new':          { en: '＋ New inbound', fa: '＋ اینباند جدید' },
  'ib.editTitle':    { en: '✏️ Edit inbound', fa: '✏️ ویرایش اینباند' },
  'ib.count':        { en: '{0} inbound(s)', fa: '{0} اینباند' },
  'ib.colStatus':    { en: 'Status', fa: 'وضعیت' },
  'ib.colRemark':    { en: 'Name', fa: 'نام' },
  'ib.colProtocol':  { en: 'Protocol', fa: 'پروتکل' },
  'ib.colDetail':    { en: 'Connection', fa: 'جزئیات اتصال' },
  'ib.colClients':   { en: 'Clients', fa: 'کاربران' },
  'ib.colTraffic':   { en: 'Traffic', fa: 'ترافیک' },
  'ib.colActions':   { en: 'Actions', fa: 'عملیات' },
  'ib.emptyTitle':   { en: 'No inbounds yet', fa: 'هنوز اینباندی نساختی' },
  'ib.emptyHint':    { en: 'Create your first inbound to start serving configs.', fa: 'اولین اینباند را بساز تا کانفیگ‌ها ساخته شوند.' },
  'ib.remark':       { en: 'Remark (name)', fa: 'نام (Remark)' },
  'ib.remarkPh':     { en: 'e.g. SF-Main', fa: 'مثلاً SF-Main' },
  'ib.protocol':     { en: 'Protocol', fa: 'پروتکل' },
  'ib.port':         { en: 'Port', fa: 'پورت' },
  'ib.transport':    { en: 'Transport', fa: 'ترنسپورت' },
  'ib.path':         { en: 'Path', fa: 'مسیر (Path)' },
  'ib.pathPh':       { en: '/sf-xxx', fa: '/sf-xxx' },
  'ib.grpcService':  { en: 'gRPC service name', fa: 'نام سرویس gRPC' },
  'ib.host':         { extoptional: true, en: 'Host header (optional)', fa: 'هدر Host (اختیاری)' },
  'ib.security':     { en: 'Security', fa: 'امنیت' },
  'ib.sec.none':     { en: 'None', fa: 'بدون رمزنگاری' },
  'ib.sec.tls':      { en: 'TLS (certificate)', fa: 'TLS (گواهی)' },
  'ib.sec.reality':  { en: 'Reality (no domain needed)', fa: 'Reality (بدون دامنه)' },
  'ib.sni':          { en: 'SNI (cert domain)', fa: 'SNI (دامنه گواهی)' },
  'ib.alpn':         { en: 'ALPN', fa: 'ALPN' },
  'ib.certFile':     { en: 'Certificate file (crt)', fa: 'فایل گواهی (crt)' },
  'ib.keyFile':      { en: 'Key file (key)', fa: 'فایل کلید (key)' },
  'ib.selfsigned':   { en: 'Client uses allowInsecure', fa: 'کلاینت allowInsecure بگیرد' },
  'ib.genCert':      { en: '📜 Generate self-signed cert', fa: '📜 گواهی خودامضا بساز' },
  'ib.rDest':        { en: 'dest (target site)', fa: 'dest (سایت هدف)' },
  'ib.rServerNames': { en: 'serverNames (comma-sep)', fa: 'serverNames (با کاما)' },
  'ib.rPrivateKey':  { en: 'privateKey', fa: 'privateKey' },
  'ib.rPublicKey':   { en: 'publicKey', fa: 'publicKey' },
  'ib.rShortIds':    { en: 'shortIds (hex, comma-sep)', fa: 'shortIds (hex، با کاما)' },
  'ib.genKeys':      { en: '🔑 Generate x25519 keys', fa: '🔑 تولید کلید x25519' },
  'ib.keysDone':     { en: 'Keys generated & filled ✅', fa: 'کلید تولید و پر شد ✅' },
  'ib.certDone':     { en: 'Certificate generated & filled ✅', fa: 'گواهی ساخته و پر شد ✅' },
  'ib.ssMethod':     { en: 'Encryption method', fa: 'روش رمزنگاری' },
  'ib.ssPassword':   { en: 'Password', fa: 'رمز' },
  'ib.paasHint':     { en: 'In cloud mode TLS is handled by the platform; clients connect with wss to this path.', fa: 'در حالت ابری TLS توسط پلتفرم انجام می‌شود؛ کلاینت‌ها با wss به همین مسیر وصل می‌شوند.' },
  'ib.tr.tcp':       { en: 'TCP (raw — fastest)', fa: 'TCP (خام — سریع‌ترین)' },
  'ib.tr.ws':        { en: 'WebSocket', fa: 'WebSocket' },
  'ib.tr.grpc':      { en: 'gRPC', fa: 'gRPC' },
  'ib.tr.httpupgrade': { en: 'HTTPUpgrade', fa: 'HTTPUpgrade' },
  'ib.delTitle':     { en: 'Delete inbound', fa: 'حذف اینباند' },
  'ib.delMsg':       { en: 'Delete inbound “{0}” and detach all its clients?', fa: 'اینباند «{0}» و اتصال همه کاربرانش به آن حذف شود؟' },
  'ib.deleted':      { en: 'Deleted', fa: 'حذف شد' },
  'ib.saved':        { en: 'Saved & applied to core ✅', fa: 'ذخیره و روی هسته اعمال شد ✅' },
  'ib.xrayWarn':     { en: 'Xray warning: {0}', fa: 'هشدار Xray: {0}' },
  'ib.needInboundFirst': { en: 'Create an inbound first', fa: 'اول یک اینباند بساز' },
  'ib.errTlsNeedCert': { en: 'TLS requires certificate files — use “Generate self-signed”.', fa: 'برای TLS فایل گواهی لازم است — «گواهی خودامضا» را بزن.' },

  /* ---------- کاربران ---------- */
  'cl.title':        { en: 'Clients', fa: 'کاربران' },
  'cl.new':          { en: '＋ New client', fa: '＋ کاربر جدید' },
  'cl.editTitle':    { en: '✏️ Edit client', fa: '✏️ ویرایش کاربر' },
  'cl.count':        { en: '{0} client(s)', fa: '{0} کاربر' },
  'cl.colStatus':    { en: 'Status', fa: 'وضعیت' },
  'cl.colClient':    { en: 'Client', fa: 'کاربر' },
  'cl.colInbounds':  { en: 'Inbounds', fa: 'اینباند‌ها' },
  'cl.colUsage':     { en: 'Usage', fa: 'مصرف' },
  'cl.colLimit':     { en: 'Data limit', fa: 'محدودیت حجم' },
  'cl.colExpiry':    { en: 'Expiry', fa: 'اعتبار' },
  'cl.colActions':   { en: 'Actions', fa: 'عملیات' },
  'cl.emptyTitle':   { en: 'No clients yet', fa: 'هنوز کاربری نساختی' },
  'cl.emptyHint':    { en: 'Create a client to generate config links.', fa: 'یک کاربر بساز تا لینک کانفیگ ساخته شود.' },
  'cl.email':        { en: 'Name / email', fa: 'نام کاربر (ایمیل)' },
  'cl.emailPh':      { en: 'e.g. ali', fa: 'مثلاً ali' },
  'cl.uuid':         { en: 'UUID', fa: 'UUID' },
  'cl.uuidPh':       { en: 'empty = auto', fa: 'خالی = خودکار' },
  'cl.password':     { en: 'Password (Trojan / SS)', fa: 'رمز (Trojan / SS)' },
  'cl.inbounds':     { en: 'Inbounds', fa: 'اینباند‌ها' },
  'cl.flow':         { en: 'VLESS flow', fa: 'فلوِ VLESS' },
  'cl.flowNone':     { en: '— no flow (recommended for ws) —', fa: '— بدون فلوِ (پیشنهادی برای ws) —' },
  'cl.flowHint':     { en: 'Only applies to VLESS + TCP + TLS/Reality.', fa: 'فقط روی VLESS + TCP + TLS/Reality اثر دارد.' },
  'cl.expiry':       { en: 'Expiry', fa: 'انقضا' },
  'cl.expNever':     { en: 'Never expires', fa: 'بدون انقضا' },
  'cl.expDate':      { en: 'Exact date', fa: 'تاریخ دقیق' },
  'cl.expDays':      { en: 'N days from now', fa: 'N روز از الان' },
  'cl.dataLimit':    { en: 'Data limit', fa: 'محدودیت حجم' },
  'cl.limOff':       { en: 'Unlimited', fa: 'نامحدود' },
  'cl.limGB':        { en: 'Gigabytes', fa: 'گیگابایت' },
  'cl.limMB':        { en: 'Megabytes', fa: 'مگابایت' },
  'cl.tgId':         { en: 'Telegram ID (optional)', fa: 'شناسه تلگرام (اختیاری)' },
  'cl.note':         { en: 'Note (optional)', fa: 'یادداشت (اختیاری)' },
  'cl.notePh':       { en: 'customer, price…', fa: 'مشتری، قیمت…' },
  'cl.active':       { en: 'Client is enabled', fa: 'کاربر فعال باشد' },
  'cl.tgConnected':  { en: '🤖 Telegram linked', fa: '🤖 متصل به تلگرام' },
  'cl.saved':        { en: 'Saved & applied to core ✅', fa: 'ذخیره و روی هسته اعمال شد ✅' },
  'cl.delTitle':     { en: 'Delete client', fa: 'حذف کاربر' },
  'cl.delMsg':       { en: 'Delete client “{0}” and its configs?', fa: 'کاربر «{0}» و کانفیگش حذف شود؟' },
  'cl.deleted':      { en: 'Deleted', fa: 'حذف شد' },
  'cl.resetTitle':   { en: 'Reset usage', fa: 'ریست آمار' },
  'cl.resetMsg':     { en: 'Reset usage counter of “{0}” to zero?', fa: 'مصرف «{0}» صفر شود؟' },
  'cl.resetDone':    { en: 'Usage reset', fa: 'آمار ریست شد' },
  'cl.toggleErr':    { en: 'Quota or expiry exhausted — increase or reset first.', fa: 'حجم یا اعتبار تمام است — ابتدا افزایش یا ریست کن.' },
  'cl.badgeExpired': { en: 'Expired', fa: 'منقضی' },
  'cl.daysLeft':     { en: '{0}d', fa: '{0} روز' },
  'cl.hoursLeft':    { en: '{0}h', fa: '{0} ساعت' },
  'cl.tgBound':      { en: '🤖 Telegram linked', fa: '🤖 متصل به تلگرام' },

  /* ---------- لینک‌ها / ساب ---------- */
  'ln.title':       { en: 'Links & subscription', fa: 'لینک‌ها و اشتراک' },
  'ln.titleOf':     { en: 'Links — {0}', fa: 'لینک‌ها — {0}' },
  'ln.status':      { en: 'Status', fa: 'وضعیت' },
  'ln.usage':       { en: 'Usage', fa: 'مصرف' },
  'ln.expiry':      { en: 'Expiry', fa: 'انقضا' },
  'ln.subSection':  { en: '📥 Subscription link (all configs in one URL)', fa: '📥 لینک اشتراک (همه‌ی کانفیگ‌ها با یک لینک)' },
  'ln.copySub':     { en: '📋 Copy subscription', fa: '📋 کپی لینک اشتراک' },
  'ln.qrSub':       { en: '🔍 Subscription QR', fa: '🔍 QR اشتراک' },
  'ln.bindSection': { en: '🤖 Telegram binding', fa: '🤖 اتصال به ربات تلگرام' },
  'ln.bindHint':    { en: 'Send this code to the bot: /bind <code>', fa: 'این کد را در ربات بفرست: <code>/bind کد</code>' },
  'ln.copyBind':    { en: '📋 Copy bind code', fa: '📋 کپی کد اتصال' },
  'ln.singleLinks': { en: '🔗 Individual links', fa: '🔗 لینک‌های تکی' },
  'ln.disabledCfg': { en: 'This subscription is disabled.', fa: 'این اشتراک غیرفعال است.' },

  /* ---------- مصرف روزانه ---------- */
  'dy.title':     { en: 'Daily usage — {0}', fa: 'مصرف روزانه — {0}' },
  'dy.day':       { en: 'Day (UTC)', fa: 'روز (UTC)' },
  'dy.up':        { en: 'Upload', fa: 'آپلود' },
  'dy.down':      { en: 'Download', fa: 'دانلود' },
  'dy.total':     { en: 'Total', fa: 'مجموع' },
  'dy.empty':     { en: 'No data recorded', fa: 'داده‌ای ثبت نشده' },

  /* ---------- تنظیمات ---------- */
  'st.general':     { en: '🌐 General', fa: '🌐 عمومی' },
  'st.domain':      { en: 'Public domain / address', fa: 'دامنه / آدرس عمومی' },
  'st.domainHint':  { en: 'Cloud mode: your Railway/Render domain. Empty = auto-detect from request.', fa: 'حالت ابری: دامنه پلتفرمت. خالی = خودکار.' },
  'st.subTitle':    { en: 'Subscription title', fa: 'عنوان اشتراک' },
  'st.security':    { en: '🔑 Password', fa: '🔑 رمز عبور' },
  'st.changePass':  { en: 'Change password', fa: 'تغییر رمز' },
  'st.passHint':    { en: 'After change, all sessions are invalidated and a new token is stored automatically.', fa: 'بعد از تغییر، نشست‌ها باطل می‌شوند و توکن جدید خودکار ذخیره می‌شود.' },
  'st.2fa':         { en: '🔐 Two-factor (TOTP)', fa: '🔐 ورود دومرحله‌ای (TOTP)' },
  'st.2faSetup':    { en: '🔑 Setup 2FA', fa: '🔑 راه‌اندازی 2FA' },
  'st.2faSecret':   { en: 'Enter this key in Google Authenticator / Aegis:', fa: 'این کلید را در Google Authenticator / Aegis وارد کن:' },
  'st.2faEnter':    { en: 'Enter the 6-digit code', fa: 'کد ۶ رقمی اپ' },
  'st.2faEnable':   { en: '✅ Enable', fa: '✅ فعال‌سازی' },
  'st.2faDisable':  { en: 'Disable 2FA', fa: 'غیرفعال‌سازی 2FA' },
  'st.2faPass':     { en: 'Password (to disable)', fa: 'رمز عبور (برای غیرفعال‌سازی)' },
  'st.2faOn':       { en: 'Enabled ✅', fa: 'فعال ✅' },
  'st.2faOff':      { en: 'Disabled', fa: 'غیرفعال' },
  'st.2faEnabled':  { en: '2FA enabled 🔐', fa: 'دومرحله‌ای فعال شد 🔐' },
  'st.2faDisabled': { en: '2FA disabled', fa: 'دومرحله‌ای غیرفعال شد' },
  'st.tg':          { en: '🤖 Telegram bot', fa: '🤖 ربات تلگرام' },
  'st.tgToken':     { en: 'Bot token (from @BotFather)', fa: 'توکن ربات (از @BotFather)' },
  'st.tgAdmins':    { en: 'Admin IDs (comma-sep)', fa: 'شناسه‌های ادمین (با کاما)' },
  'st.tgAdminsHint':{ en: 'Get your ID via /start in the bot.', fa: 'شناسه‌ات را از /start ربات بگیر.' },
  'st.tgNotify':    { en: 'Auto-notify quota/expiry to clients', fa: 'اعلان خودکار حجم/انقضا به کاربران' },
  'st.tgSave':      { en: '💾 Save', fa: '💾 ذخیره' },
  'st.tgTest':      { en: '🔌 Test connection', fa: '🔌 تست اتصال' },
  'st.tgOk':        { en: '✅ Connected — bot: {0}', fa: '✅ متصل — ربات: {0}' },
  'st.reset':       { en: '♻️ Periodic usage reset', fa: '♻️ ریست دوره‌ای مصرف' },
  'st.resetMode':   { en: 'Mode', fa: 'حالت' },
  'st.resetOff':    { en: 'Disabled', fa: 'غیرفعال' },
  'st.resetDaily':  { en: 'Daily (UTC)', fa: 'روزانه (UTC)' },
  'st.resetMonthly':{ en: 'Monthly', fa: 'ماهانه' },
  'st.resetDay':    { en: 'Monthly reset day (1–28)', fa: 'روز ریست ماهانه (۱ تا ۲۸)' },
  'st.resetHint':   { en: 'On the selected day, ALL clients’ usage resets to zero (limits stay).', fa: 'در روز انتخابی، مصرف همه کاربران صفر می‌شود (محدودیت‌ها می‌مانند).' },
  'st.backup':      { en: '📦 Backup', fa: '📦 پشتیبان‌گیری' },
  'st.backupDl':    { en: '⬇️ Download JSON backup', fa: '⬇️ دانلود پشتیبان JSON' },
  'st.restore':     { en: 'Restore from file', fa: 'بازیابی از فایل' },
  'st.restoreBtn':  { en: '⬆️ Restore', fa: '⬆️ بازیابی' },
  'st.restoreHint': { en: '⚠️ Restore REPLACES current inbounds & clients.', fa: '⚠️ بازیابی، اینباند/کاربران فعلی را جایگزین می‌کند.' },
  'st.restoreWarn': { en: 'Current inbounds & clients will be replaced by the backup. Continue?', fa: 'اینباند‌ها و کاربران فعلی با فایل پشتیبان جایگزین می‌شوند. ادامه؟' },
  'st.restored':    { en: 'Restored: {0} inbounds, {1} clients ✅', fa: 'بازیابی شد: {0} اینباند، {1} کاربر ✅' },
  'st.backupDone':  { en: 'Backup downloaded ✅', fa: 'پشتیبان دانلود شد ✅' },
  'st.saved':       { en: 'Saved ✅', fa: 'ذخیره شد ✅' },
  'st.testing':     { en: 'Testing…', fa: 'در حال تست…' },
  'st.passChanged': { en: 'Password changed; new session stored ✅', fa: 'رمز عوض شد؛ نشست تازه ذخیره شد ✅' },
  'st.pickFile':    { en: 'Select a file first', fa: 'اول فایل را انتخاب کن' },
  'st.tgFail':      { en: '❌ {0}', fa: '❌ {0}' },

  /* ---------- هسته Xray ---------- */
  'xr.title':        { en: '⚙️ Core status', fa: '⚙️ وضعیت هسته' },
  'xr.state':        { en: 'Core state', fa: 'وضعیت هسته' },
  'xr.version':      { en: 'Version', fa: 'نسخه' },
  'xr.uptime':       { en: 'Uptime', fa: 'آپتایم' },
  'xr.goroutines':   { en: 'Goroutines', fa: 'Goroutines' },
  'xr.alloc':        { en: 'Core memory', fa: 'حافظه هسته' },
  'xr.pinVersion':   { en: 'Pinned version (empty = latest)', fa: 'نسخه دلخواه (خالی = آخرین)' },
  'xr.pinPh':        { en: 'e.g. v25.1.1', fa: 'مثلاً v25.1.1' },
  'xr.saveVer':      { en: '💾 Save version', fa: '💾 ذخیره نسخه' },
  'xr.restart':      { en: '🔄 Restart core', fa: '🔄 راه‌اندازی مجدد' },
  'xr.update':       { en: '⬆️ Update core', fa: '⬆️ بروزرسانی هسته' },
  'xr.tools':        { en: '🧰 Security tools', fa: '🧰 ابزارهای امنیتی' },
  'xr.keysTool':     { en: 'Generate Reality keys (x25519)', fa: 'تولید کلید Reality (x25519)' },
  'xr.genKeys':      { en: '🔑 Generate keys', fa: '🔑 تولید کلید' },
  'xr.clickToCopy':  { en: 'Click the box to copy', fa: 'برای کپی روی کادر کلیک کن' },
  'xr.certTool':     { en: 'Self-signed certificate (TLS)', fa: 'گواهی خودامضا (TLS)' },
  'xr.certDomain':   { en: 'Domain — empty = auto', fa: 'دامنه — خالی = خودکار' },
  'xr.genCert':      { en: '📜 Generate 10-year cert', fa: '📜 ساخت گواهی ۱۰ ساله' },
  'xr.certDone':     { en: '✅ Generated for <b>{0}</b><br>Use these paths in the inbound TLS form.', fa: '✅ ساخته شد برای <b>{0}</b><br>در فرم اینباند TLS همین مسیرها را وارد کن.' },
  'xr.routes':       { en: '🔀 Router paths (cloud mode)', fa: '🔀 مسیرهای روتر (حالت ابری)' },
  'xr.colPath':      { en: 'Proxy path', fa: 'مسیر پروکسی' },
  'xr.colPort':      { en: 'Internal port', fa: 'پورت داخلی' },
  'xr.noRoutes':     { en: 'No routes', fa: 'مسیری نیست' },
  'xr.modeInfo':     { en: 'Runtime mode', fa: 'حالت اجرا' },
  'xr.modePaas':     { en: '<b>Cloud (PaaS)</b> — everything is served behind the L4 router on port <b>{0}</b>. Panel and proxy inbounds share this single port. Public address: <span class="mono">{1}</span>', fa: 'حالت <b>ابری (PaaS)</b> — همه‌چیز پشت روتر L4 روی پورت <b>{0}</b> است. پنل و اینباند‌های پروکسی هر دو از همین پورت سرو می‌شوند. آدرس عمومی: <span class="mono">{1}</span>' },
  'xr.modeVps':      { en: '<b>Server (VPS)</b> — panel on port <b>{0}</b>, inbounds on their real ports. Reality/TLS/gRPC fully supported. Address: <span class="mono">{1}</span>', fa: 'حالت <b>سرور (VPS)</b> — پنل روی پورت <b>{0}</b> و اینباند‌ها روی پورت‌های واقعی. Reality/TLS/gRPC کامل پشتیبانی می‌شود. آدرس: <span class="mono">{1}</span>' },
  'xr.restarted':    { en: 'Core restarted ✅', fa: 'هسته راه‌اندازی مجدد شد ✅' },
  'xr.updating':     { en: 'Downloading…', fa: 'در حال دانلود…' },
  'xr.updated':      { en: 'Updated: {0} ✅', fa: 'بروزرسانی شد: {0} ✅' },
  'xr.updateConfirm':{ en: 'Download & install the latest Xray-core? Takes a moment.', fa: 'آخرین نسخه Xray-core دانلود و نصب شود؟ چند لحظه طول می‌کشد.' },

  /* ---------- لاگ‌ها ---------- */
  'lg.panel':    { en: 'Panel', fa: 'پنل' },
  'lg.xray':     { en: 'Xray', fa: 'Xray' },
  'lg.empty':    { en: '— empty —', fa: '— خالی —' },

  /* ---------- عمومی فرم ---------- */
  'fm.generate':   { en: 'Generate', fa: 'تولید' },
  'fm.optional':   { en: 'optional', fa: 'اختیاری' },
  'fm.protocolNotCloud': { en: 'Not available in cloud mode', fa: 'در حالت ابری در دسترس نیست' },

  /* ---------- خطاها/توست‌ها ---------- */
  'er.sessionExpired': { en: 'Session expired', fa: 'نشست منقضی شد' },
  'er.request':        { en: 'Request failed', fa: 'درخواست ناموفق بود' },
  'er.showMore':       { en: 'Show error', fa: 'نمایش خطا' },
};

/* ---------- موتور ---------- */

function detectLang() {
  try {
    const saved = localStorage.getItem('sfplang');
    if (saved && LANGS[saved]) return saved;
  } catch (e) { /* localStorage blocked */ }
  const nav = (navigator.language || 'en').toLowerCase();
  return nav.startsWith('fa') ? 'fa' : 'en';
}

let LANG = detectLang();

function I(key, ...args) {
  const item = I18N[key];
  let s = (item && (item[LANG] || item.en)) || key;
  args.forEach((a, i) => { s = s.replace('{' + i + '}', String(a)); });
  return s;
}

function applyI18n() {
  document.documentElement.lang = LANG;
  document.documentElement.dir = LANG === 'fa' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = I(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    el.placeholder = I(el.dataset.i18nPh);
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.title = I(el.dataset.i18nTitle);
  });
  const btn = document.getElementById('langBtn');
  if (btn) btn.textContent = LANG === 'fa' ? 'English' : 'فارسی';
}

function setLang(l) {
  if (!LANGS[l]) return;
  LANG = l;
  try { localStorage.setItem('sfplang', l); } catch (e) {}
  applyI18n();
}

function initLanguageUI() {
  const btn = document.getElementById('langBtn');
  if (btn) btn.onclick = () => setLang(LANG === 'fa' ? 'en' : 'fa');
  applyI18n();
}

/* ---------- فرمت‌ها ---------- */

function fmtNum(n) {
  try { return Number(n).toLocaleString(LANG === 'fa' ? 'fa-IR' : 'en-US'); }
  catch (e) { return String(n); }
}

function fmtDur(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  if (sec < 60) return (LANG === 'fa' ? '' : '') + sec + (LANG === 'fa' ? ' ثانیه' : 's');
  const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600),
        m = Math.floor(sec % 3600 / 60);
  if (d) return LANG === 'fa' ? `${d} روز ${h} ساعت` : `${d}d ${h}h`;
  if (h) return LANG === 'fa' ? `${h} ساعت ${m} دقیقه` : `${h}h ${m}m`;
  return LANG === 'fa' ? `${m} دقیقه` : `${m}m`;
}

function fmtTs(ms) {
  if (!ms) return '—';
  const d = new Date(ms);
  try {
    return d.toLocaleString(LANG === 'fa' ? 'fa-IR' : 'en-GB', {
      hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short'
    });
  } catch (e) {
    return d.toLocaleString();
  }
   }
