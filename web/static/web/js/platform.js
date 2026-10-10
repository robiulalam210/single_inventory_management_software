/*
 * Platform → Companies (শুধু Super Admin)
 *   GET   /api/platform/companies/?q=&status=
 *   POST  /api/platform/companies/                   { company, admin, seed }
 *   GET   /api/platform/companies/<id>/
 *   PATCH /api/platform/companies/<id>/
 *   POST  /api/platform/companies/<id>/admins/
 *   POST  /api/platform/companies/<id>/users/<uid>/password/
 *   POST  /api/platform/companies/<id>/users/<uid>/toggle/
 */
(function () {
  'use strict';

  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const addMonths = (s, m) => {
    const base = s ? new Date(s + 'T00:00') : new Date();
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const from = base < today ? today : base;   // মেয়াদ পার হয়ে গেলে আজ থেকে গুনি
    const d = new Date(from); d.setMonth(d.getMonth() + m);
    return iso(d);
  };
  const fmtDate = (s) => {
    if (!s) return '—';
    const d = new Date(String(s).length === 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const ago = (s) => {
    if (!s) return 'Never signed in';
    const m = Math.round((Date.now() - new Date(s)) / 60000);
    if (m < 2) return 'Active just now';
    if (m < 60) return `Active ${m} min ago`;
    const h = Math.round(m / 60); if (h < 24) return `Active ${h} h ago`;
    const d = Math.round(h / 24); if (d < 31) return `Active ${d} day${d === 1 ? '' : 's'} ago`;
    return 'Last active ' + fmtDate(s);
  };
  const genPassword = () => {
    // দেখতে বিভ্রান্তিকর অক্ষর (0/O, 1/l/I) বাদ
    const a = 'abcdefghjkmnpqrstuvwxyz', A = 'ABCDEFGHJKLMNPQRSTUVWXYZ', d = '23456789';
    const all = a + A + d, buf = new Uint32Array(10);
    crypto.getRandomValues(buf);
    let p = A[buf[0] % A.length] + a[buf[1] % a.length] + d[buf[2] % d.length];
    for (let i = 3; i < 10; i++) p += all[buf[i] % all.length];
    return p.split('').sort(() => 0.5 - Math.random()).join('');
  };
  const slug = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 20);
  const errsOf = (e) => (e && e.data && e.data.data) || {};

  const STATES = {
    active: { label: 'Active', cls: 'st-paid' },
    expiring: { label: 'Expiring soon', cls: 'st-low' },
    expired: { label: 'Expired', cls: 'st-pending' },
    suspended: { label: 'Suspended', cls: 'st-off' },
  };

  const blankCompany = () => ({
    name: '', phone: '', email: '', address: '', trade_license: '', website: '',
    plan_type: 'basic', expiry_date: addMonths('', 12), max_users: 5, max_products: 1000, max_branches: 3,
  });
  const blankAdmin = () => ({ first_name: '', last_name: '', username: '', email: '', phone: '', password: genPassword() });

  window.platformCompanies = function (plans) {
    return {
      plans, states: STATES,
      rows: [], counts: {}, loading: true, error: null,
      f: { q: '', status: 'all' },
      sel: null, selLoading: false,
      // create / edit
      formOpen: false, mode: 'new', step: 1, c: blankCompany(), a: blankAdmin(), seed: true,
      fe: { company: {}, admin: {} }, formError: '', saving: false, done: null, userTouched: false, showPw: true,
      // admin / password
      adOpen: false, ad: blankAdmin(), adErr: {}, adError: '', adSaving: false, adDone: null,
      pwOpen: false, pwUser: null, pw: '', pwErr: '', pwSaving: false, pwDone: '',
      confirm: null, busy: false, toast: '', copied: '',
      _req: 0,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || ''; this.f.status = p.get('status') || 'all';
        this.load();
        this.$watch('f.q', () => { clearTimeout(this._qt); this._qt = setTimeout(() => this.load(), 250); });
        this.$watch('f.status', () => this.load());
        const open = p.get('open');
        if (open) this.open({ id: Number(open) });
      },
      sync() {
        const p = new URLSearchParams();
        if (this.f.q) p.set('q', this.f.q);
        if (this.f.status !== 'all') p.set('status', this.f.status);
        if (this.sel) p.set('open', this.sel.id);
        history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : ''));
      },
      async load() {
        const id = ++this._req;
        this.loading = true; this.error = null; this.sync();
        try {
          const r = await App.api('/api/platform/companies/', { query: { q: this.f.q, status: this.f.status } });
          if (id !== this._req) return;
          this.rows = r.data.results; this.counts = r.data.counts;
        } catch (e) { if (id === this._req) this.error = e.message; }
        if (id === this._req) this.loading = false;
      },
      get chips() {
        return [
          { key: 'all', label: 'All' }, { key: 'active', label: 'Active' }, { key: 'expiring', label: 'Expiring soon' },
          { key: 'expired', label: 'Expired' }, { key: 'suspended', label: 'Suspended' },
        ].map(c => ({ ...c, n: this.counts[c.key] || 0 }));
      },
      st(r) { return STATES[r.state] || STATES.active; },
      planLabel(v) { const p = this.plans.find(x => x.value === v); return p ? p.label : v; },
      date: fmtDate, ago, genPw: genPassword,
      left(r) {
        if (r.days_left == null) return 'No end date';
        if (r.days_left < 0) return `Ended ${-r.days_left} day${r.days_left === -1 ? '' : 's'} ago`;
        if (r.days_left === 0) return 'Ends today';
        return `${r.days_left} day${r.days_left === 1 ? '' : 's'} left`;
      },
      roleLabel: (r) => ({ ADMIN: 'Admin', MANAGER: 'Manager', STAFF: 'Staff', VIEWER: 'Viewer', SUPER_ADMIN: 'Super admin' }[r] || r),

      // ───── detail drawer ─────
      async open(r) {
        this.sel = { ...r, admins: r.admins || null };
        document.body.style.overflow = 'hidden';
        this.sync();
        await this.reloadSel();
      },
      async reloadSel() {
        if (!this.sel) return;
        this.selLoading = true;
        try { const r = await App.api(`/api/platform/companies/${this.sel.id}/`); this.sel = r.data; }
        catch (e) { this.flash(e.message); if (!this.sel.name) this.shut(); }
        this.selLoading = false;
      },
      shut() { this.sel = null; document.body.style.overflow = ''; this.sync(); },
      get users() { return (this.sel && this.sel.admins) || []; },

      async patch(body, ok) {
        if (this.busy) return;
        this.busy = true;
        try {
          const r = await App.api(`/api/platform/companies/${this.sel.id}/`, { method: 'PATCH', body });
          this.sel = r.data; this.flash(ok || r.message); this.load();
        } catch (e) {
          const ce = errsOf(e).company || {};
          this.flash(Object.values(ce)[0] || e.message);
        }
        this.busy = false; this.confirm = null;
      },
      extend(months) {
        const to = addMonths(this.sel.expiry_date, months);
        const body = { expiry_date: to };
        if (this.sel.state === 'expired') body.is_active = true;
        this.patch(body, `Subscription now ends on ${fmtDate(to)}.`);
      },
      askSuspend() {
        this.confirm = this.sel.is_active
          ? { kind: 'suspend', title: `Suspend ${this.sel.name}?`, text: 'Nobody from this company can sign in until you turn it back on. Their data stays safe.', btn: 'Suspend', danger: true }
          : { kind: 'resume', title: `Turn ${this.sel.name} back on?`, text: 'Its users can sign in again.', btn: 'Turn on', danger: false };
      },
      doConfirm() {
        const c = this.confirm; if (!c) return;
        if (c.kind === 'suspend') this.patch({ is_active: false });
        else if (c.kind === 'resume') this.patch({ is_active: true });
        else if (c.kind === 'user') this.toggleUser(c.user);
      },

      // ───── new / edit company ─────
      openNew() {
        this.mode = 'new'; this.step = 1; this.c = blankCompany(); this.a = blankAdmin(); this.seed = true;
        this.fe = { company: {}, admin: {} }; this.formError = ''; this.done = null; this.userTouched = false; this.showPw = true;
        this.formOpen = true;
        this.$nextTick(() => this.$refs.cName && this.$refs.cName.focus());
      },
      openEdit() {
        const s = this.sel;
        this.mode = 'edit'; this.step = 1; this.done = null;
        this.c = {
          name: s.name, phone: s.phone, email: s.email, address: s.address, trade_license: s.trade_license, website: s.website,
          plan_type: s.plan_type, expiry_date: s.expiry_date || '', max_users: s.max_users, max_products: s.max_products, max_branches: s.max_branches,
        };
        this.fe = { company: {}, admin: {} }; this.formError = ''; this.formOpen = true;
        this.$nextTick(() => this.$refs.cName && this.$refs.cName.focus());
      },
      nameChanged() {
        this.fe.company.name = '';
        // এডমিনের username নিজে না বদলালে কোম্পানির নাম থেকে প্রস্তাব
        if (this.mode === 'new' && !this.userTouched) this.a.username = slug(this.c.name) ? slug(this.c.name) + '_admin' : '';
      },
      setExpiry(m) { this.c.expiry_date = addMonths('', m); this.fe.company.expiry_date = ''; },
      checkCompany() {
        const e = {}, c = this.c;
        if (!c.name.trim()) e.name = 'Enter the company name.';
        if (!c.phone.trim()) e.phone = 'Enter a phone number to reach the shop.';
        if (c.email && !/^\S+@\S+\.\S+$/.test(c.email)) e.email = 'Enter a valid email address.';
        if (!c.expiry_date) e.expiry_date = 'Pick the date the subscription ends.';
        ['max_users', 'max_products', 'max_branches'].forEach(k => { if (!(Number(c[k]) >= 1)) e[k] = 'At least 1.'; });
        this.fe.company = e;
        return !Object.keys(e).length;
      },
      checkAdmin(a, into) {
        const e = {};
        if (!a.first_name.trim()) e.first_name = "Enter the admin's name.";
        if (!a.username.trim()) e.username = 'Choose a username to log in with.';
        else if (!/^[A-Za-z0-9._-]{3,150}$/.test(a.username.trim())) e.username = 'Use 3+ letters, numbers, dot, dash or underscore — no spaces.';
        if (a.email && !/^\S+@\S+\.\S+$/.test(a.email)) e.email = 'Enter a valid email address.';
        if (!a.password || a.password.length < 8) e.password = 'Use at least 8 characters.';
        Object.assign(into, e);
        return !Object.keys(e).length;
      },
      next() {
        if (!this.checkCompany()) return;
        this.step = 2;
        this.$nextTick(() => this.$refs.aFirst && this.$refs.aFirst.focus());
      },
      companyBody() {
        const c = this.c;
        return {
          name: c.name.trim(), phone: c.phone.trim(), email: c.email.trim(), address: c.address.trim(),
          trade_license: c.trade_license.trim(), website: c.website.trim(), plan_type: c.plan_type,
          expiry_date: c.expiry_date, max_users: Number(c.max_users), max_products: Number(c.max_products), max_branches: Number(c.max_branches),
        };
      },
      async save() {
        if (this.saving) return;
        if (this.mode === 'edit') {
          if (!this.checkCompany()) return;
          this.saving = true; this.formError = '';
          try {
            const r = await App.api(`/api/platform/companies/${this.sel.id}/`, { method: 'PATCH', body: this.companyBody() });
            this.sel = r.data; this.formOpen = false; this.flash('Company details saved.'); this.load();
          } catch (e) { this.fe.company = errsOf(e).company || {}; this.formError = Object.keys(this.fe.company).length ? '' : e.message; }
          this.saving = false; return;
        }
        if (!this.checkCompany()) { this.step = 1; return; }
        this.fe.admin = {};
        if (!this.checkAdmin(this.a, this.fe.admin)) return;
        this.saving = true; this.formError = '';
        const a = this.a;
        try {
          const r = await App.api('/api/platform/companies/', {
            method: 'POST',
            body: {
              company: this.companyBody(), seed: this.seed,
              admin: { first_name: a.first_name.trim(), last_name: a.last_name.trim(), username: a.username.trim(), email: a.email.trim(), phone: a.phone.trim(), password: a.password },
            },
          });
          this.done = { ...r.data, password: a.password };
          this.step = 3;
          this.load();
        } catch (e) {
          const d = errsOf(e);
          this.fe = { company: d.company || {}, admin: d.admin || {} };
          if (Object.keys(this.fe.company).length) this.step = 1;
          this.formError = (Object.keys(this.fe.company).length || Object.keys(this.fe.admin).length) ? '' : e.message;
        }
        this.saving = false;
      },
      get signInUrl() { return location.origin + '/app/login/'; },
      credText(company, user, password) {
        return [
          `${company} — sign-in details`,
          `Address: ${this.signInUrl}`,
          `Username: ${user}`,
          `Password: ${password}`,
          'Please change the password after your first sign-in.',
        ].join('\n');
      },
      async copy(text, key) {
        try { await navigator.clipboard.writeText(text); }
        catch (e) {
          const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select();
          try { document.execCommand('copy'); } catch (_) {} t.remove();
        }
        this.copied = key; clearTimeout(this._ct); this._ct = setTimeout(() => { this.copied = ''; }, 1800);
      },
      openDone() { const id = this.done.company.id; this.formOpen = false; this.open({ id }); },

      // ───── add admin ─────
      openAdmin() {
        this.ad = blankAdmin(); this.adErr = {}; this.adError = ''; this.adDone = null; this.adOpen = true;
        this.$nextTick(() => this.$refs.adFirst && this.$refs.adFirst.focus());
      },
      async saveAdmin() {
        if (this.adSaving) return;
        this.adErr = {};
        if (!this.checkAdmin(this.ad, this.adErr)) return;
        this.adSaving = true; this.adError = '';
        const a = this.ad;
        try {
          const r = await App.api(`/api/platform/companies/${this.sel.id}/admins/`, {
            method: 'POST',
            body: { first_name: a.first_name.trim(), last_name: a.last_name.trim(), username: a.username.trim(), email: a.email.trim(), phone: a.phone.trim(), password: a.password },
          });
          this.adDone = { user: r.data, password: a.password };
          this.reloadSel(); this.load();
        } catch (e) { this.adErr = errsOf(e).admin || {}; this.adError = Object.keys(this.adErr).length ? '' : e.message; }
        this.adSaving = false;
      },

      // ───── user password / on-off ─────
      openPw(u) { this.pwUser = u; this.pw = genPassword(); this.pwErr = ''; this.pwDone = ''; this.pwOpen = true; },
      newPw() { this.pw = genPassword(); this.pwErr = ''; },
      async savePw() {
        if (this.pwSaving) return;
        if (!this.pw || this.pw.length < 8) { this.pwErr = 'Use at least 8 characters.'; return; }
        this.pwSaving = true; this.pwErr = '';
        try {
          await App.api(`/api/platform/companies/${this.sel.id}/users/${this.pwUser.id}/password/`, { method: 'POST', body: { password: this.pw } });
          this.pwDone = this.pw;
        } catch (e) { this.pwErr = e.message; }
        this.pwSaving = false;
      },
      askUser(u) {
        this.confirm = u.is_active
          ? { kind: 'user', user: u, title: `Turn off ${u.name}?`, text: `${u.username} won't be able to sign in. Everything they recorded stays.`, btn: 'Turn off', danger: true }
          : { kind: 'user', user: u, title: `Turn ${u.name} back on?`, text: `${u.username} can sign in again with their current password.`, btn: 'Turn on', danger: false };
      },
      async toggleUser(u) {
        if (this.busy) return;
        this.busy = true;
        try {
          const r = await App.api(`/api/platform/companies/${this.sel.id}/users/${u.id}/toggle/`, { method: 'POST' });
          this.flash(r.message); await this.reloadSel(); this.load();
        } catch (e) { this.flash(e.message); }
        this.busy = false; this.confirm = null;
      },

      escape() {
        if (this.confirm) this.confirm = null;
        else if (this.pwOpen) this.pwOpen = false;
        else if (this.adOpen) this.adOpen = false;
        else if (this.formOpen) { if (!this.saving) this.formOpen = false; }
        else if (this.sel) this.shut();
      },
      flash(msg) {
        this.toast = msg;
        clearTimeout(this._toast);
        this._toast = setTimeout(() => { this.toast = ''; }, 3800);
      },
    };
  };
})();
