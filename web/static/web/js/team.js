/*
 * Staff / User Permissions — কোম্পানির মানুষ আর তাদের অনুমতি।
 *   GET   /api/users/team/                     সবাই + actor কী করতে পারে
 *   POST  /api/users/                          নতুন মানুষ
 *   PATCH /api/users/<id>/                     নাম, role, চালু/বন্ধ
 *   POST  /api/users/<id>/set-password/
 *   POST  /api/user-permissions/update/        { user_id, permissions }
 *   POST  /api/user-permissions/reset/         { user_id }   role এর default এ ফেরত
 */
(function () {
  'use strict';

  const ROLES = {
    ADMIN: { label: 'Admin', note: 'Everything, including staff, permissions and setup.' },
    MANAGER: { label: 'Manager', note: 'All daily work and reports. Can see staff but not change them.' },
    STAFF: { label: 'Staff', note: 'Sells, takes payments, adds customers. Cannot delete or see setup.' },
    VIEWER: { label: 'Viewer', note: 'Can look at everything, change nothing.' },
  };
  // অনুমতির তালিকা — backend এর User.get_permissions() এর module/action এর সাথে মিল রেখে
  const MODULES = [
    { key: 'dashboard', label: 'Dashboard', note: 'Sales, profit and money summary', acts: ['view'] },
    { key: 'sales', label: 'Sales', note: 'Invoices and sale list', acts: ['view', 'create', 'edit', 'delete'], extra: [['create_pos', 'POS sale'], ['create_short', 'Quick sale']] },
    { key: 'money_receipt', label: 'Money receipts', note: 'Collecting customer dues', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'customers', label: 'Customers', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'products', label: 'Products & stock', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'purchases', label: 'Purchases', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'suppliers', label: 'Suppliers', note: 'Including supplier payments', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'accounts', label: 'Accounts', note: 'Cash, bank, transfers, income', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'expense', label: 'Expenses', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'return', label: 'Returns', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'reports', label: 'Reports', acts: ['view'], extra: [['export', 'Export']] },
    { key: 'users', label: 'Staff', note: 'Adding and changing people', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'administration', label: 'Setup', note: 'Units, categories, brands…', acts: ['view', 'create', 'edit', 'delete'] },
    { key: 'settings', label: 'Settings', acts: ['view', 'edit'] },
  ];
  const ACTS = [['view', 'View'], ['create', 'Add'], ['edit', 'Edit'], ['delete', 'Delete']];

  const fmtDate = (s) => {
    if (!s) return '—';
    const d = new Date(s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const ago = (s) => {
    if (!s) return 'Never signed in';
    const m = Math.round((Date.now() - new Date(s)) / 60000);
    if (m < 2) return 'Just now';
    if (m < 60) return `${m} min ago`;
    const h = Math.round(m / 60); if (h < 24) return `${h} h ago`;
    const d = Math.round(h / 24); if (d < 31) return `${d} day${d === 1 ? '' : 's'} ago`;
    return fmtDate(s);
  };
  const genPassword = () => {
    const a = 'abcdefghjkmnpqrstuvwxyz', A = 'ABCDEFGHJKLMNPQRSTUVWXYZ', d = '23456789', all = a + A + d;
    const b = new Uint32Array(10); crypto.getRandomValues(b);
    let p = A[b[0] % A.length] + a[b[1] % a.length] + d[b[2] % d.length];
    for (let i = 3; i < 10; i++) p += all[b[i] % all.length];
    return p;
  };
  const clone = (o) => JSON.parse(JSON.stringify(o || {}));
  const errsOf = (e) => { const d = e && e.data && e.data.data; return d && typeof d === 'object' && !Array.isArray(d) ? d : {}; };

  window.teamPage = function (init) {
    return {
      init0: init, roles: ROLES, modules: MODULES, acts: ACTS,
      people: [], limit: null, activeCount: 0, assignable: [], canPerms: false,
      loading: true, error: null,
      q: '', view: 'active',
      sel: null, tab: init.start === 'access' ? 'access' : 'details',
      draft: null, saved: null, pSaving: false, pError: '',
      formOpen: false, form: {}, fe: {}, formError: '', formSaving: false, done: null,
      pwOpen: false, pw: '', pwErr: '', pwSaving: false, pwDone: '',
      confirm: null, busy: false, toast: '', copied: false,

      init() {
        const p = new URLSearchParams(location.search);
        this.q = p.get('q') || '';
        this.load().then(() => {
          const id = Number(p.get('open'));
          const r = id && this.people.find(x => x.id === id);
          if (r) this.open(r, p.get('tab') || this.tab);
        });
      },
      async load() {
        this.loading = true; this.error = null;
        try {
          const r = await App.api('/api/users/team/');
          const d = r.data;
          this.people = d.results; this.limit = d.limit; this.activeCount = d.active;
          this.assignable = d.assignable; this.canPerms = d.can_manage_permissions;
          if (this.sel) { const f = this.people.find(x => x.id === this.sel.id); if (f) this.sel = f; }
        } catch (e) { this.error = e.message; }
        this.loading = false;
      },
      sync() {
        const p = new URLSearchParams();
        if (this.q) p.set('q', this.q);
        if (this.sel) { p.set('open', this.sel.id); if (this.tab !== 'details') p.set('tab', this.tab); }
        history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : ''));
      },

      // ───── list ─────
      get counts() {
        const on = this.people.filter(u => u.is_active).length;
        return { active: on, off: this.people.length - on, all: this.people.length };
      },
      get chips() {
        return [{ key: 'active', label: 'Active', n: this.counts.active }, { key: 'off', label: 'Turned off', n: this.counts.off }, { key: 'all', label: 'All', n: this.counts.all }];
      },
      get rows() {
        const q = this.q.trim().toLowerCase();
        return this.people.filter(u => {
          if (this.view === 'active' && !u.is_active) return false;
          if (this.view === 'off' && u.is_active) return false;
          return !q || [u.name, u.username, u.email, u.phone, this.roleLabel(u.role)].some(v => String(v || '').toLowerCase().includes(q));
        });
      },
      get atLimit() { return this.limit != null && this.activeCount >= this.limit; },
      get roleCounts() {
        return Object.keys(ROLES).map(k => ({ key: k, label: ROLES[k].label, n: this.people.filter(u => u.is_active && u.role === k).length })).filter(r => r.n);
      },
      roleLabel: (r) => (ROLES[r] || {}).label || r,
      initials(u) { const p = (u.name || u.username).split(/\s+/).filter(Boolean); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); },
      hue(u) { let h = 0; for (const c of u.username) h = (h * 31 + c.charCodeAt(0)) % 360; return h; },
      ago, date: fmtDate,
      // কতগুলো জায়গায় ঢুকতে পারে — "Access" কলামের জন্য
      reach(u) {
        if (u.role === 'ADMIN') return { n: MODULES.length, text: 'Everything' };
        const n = MODULES.filter(m => (u.permissions[m.key] || {}).view).length;
        return { n, text: n === MODULES.length ? 'Sees everything' : `${n} of ${MODULES.length} areas` };
      },
      sourceLabel(u) {
        if (u.role === 'ADMIN') return '';
        return u.permission_source === 'ROLE' ? 'Role defaults' : 'Customised';
      },

      // ───── drawer ─────
      open(u, tab) {
        if (this.dirty && !confirm('Discard the permission changes you have not saved?')) return;
        this.sel = u; this.tab = tab || this.tab;
        if (this.tab === 'access' && !this.canSeeAccess) this.tab = 'details';
        this.resetDraft();
        document.body.style.overflow = 'hidden';
        this.sync();
      },
      shut() {
        if (this.dirty && !confirm('Discard the permission changes you have not saved?')) return;
        this.sel = null; this.draft = null; document.body.style.overflow = ''; this.sync();
      },
      setTab(t) { this.tab = t; this.sync(); },
      get canSeeAccess() { return !!this.sel; },
      resetDraft() { this.saved = clone(this.sel && this.sel.permissions); this.draft = clone(this.saved); this.pError = ''; },

      // ───── permissions matrix ─────
      get permEditable() { return !!(this.sel && this.sel.can_edit_permissions); },
      has(m, a) { return !!(this.draft && this.draft[m.key] && this.draft[m.key][a]); },
      hasAct(m, a) { return m.acts.includes(a); },
      flip(m, a) {
        if (!this.permEditable) return;
        const row = this.draft[m.key] = this.draft[m.key] || {};
        const on = !row[a];
        row[a] = on;
        // দেখতে না পারলে তৈরি/বদল/মোছা অর্থহীন — তাই একসাথে রাখি
        if (a === 'view' && !on) Object.keys(row).forEach(k => { row[k] = false; });
        if (a !== 'view' && on) row.view = true;
      },
      rowAll(m) { const r = this.draft[m.key] || {}; return [...m.acts, ...(m.extra || []).map(x => x[0])].every(a => r[a]); },
      flipRow(m) {
        if (!this.permEditable) return;
        const on = !this.rowAll(m);
        const r = this.draft[m.key] = this.draft[m.key] || {};
        [...m.acts, ...(m.extra || []).map(x => x[0])].forEach(a => { r[a] = on; });
        if (m.key === 'reports') r.create = on;   // reports এর create আলাদা দেখাই না
      },
      preset(kind) {
        if (!this.permEditable) return;
        MODULES.forEach(m => {
          const r = this.draft[m.key] = this.draft[m.key] || {};
          Object.keys(r).forEach(k => { r[k] = kind === 'all'; });
          [...m.acts, ...(m.extra || []).map(x => x[0])].forEach(a => { r[a] = kind === 'all' || (kind === 'view' && a === 'view'); });
          if (m.key === 'reports' && kind === 'view') r.export = true;
        });
      },
      get dirty() { return !!(this.draft && this.saved && JSON.stringify(this.draft) !== JSON.stringify(this.saved)); },
      get changedCount() {
        if (!this.dirty) return 0;
        let n = 0;
        MODULES.forEach(m => Object.keys(this.draft[m.key] || {}).forEach(a => { if (!!this.draft[m.key][a] !== !!((this.saved[m.key] || {})[a])) n++; }));
        return n;
      },
      async savePerms() {
        if (!this.dirty || this.pSaving) return;
        this.pSaving = true; this.pError = '';
        const permissions = {};
        MODULES.forEach(m => { permissions[m.key] = { ...(this.draft[m.key] || {}) }; });
        try {
          await App.api('/api/user-permissions/update/', { method: 'POST', body: { user_id: this.sel.id, permissions } });
          this.flash(`Saved. ${this.sel.name} sees the change next time a page loads.`);
          this.saved = clone(this.draft);
          await this.load(); this.resetDraft();
        } catch (e) { this.pError = e.message; }
        this.pSaving = false;
      },
      askResetPerms() {
        this.confirm = { kind: 'reset', title: `Go back to ${this.roleLabel(this.sel.role)} defaults?`,
          text: `Every change made for ${this.sel.name} is undone and they get the standard ${this.roleLabel(this.sel.role).toLowerCase()} access.`, btn: 'Reset access', danger: false };
      },
      async resetPerms() {
        this.busy = true;
        try {
          await App.api('/api/user-permissions/reset/', { method: 'POST', body: { user_id: this.sel.id } });
          await this.load(); this.resetDraft(); this.flash('Access reset to the role defaults.');
        } catch (e) { this.flash(e.message); }
        this.busy = false; this.confirm = null;
      },

      // ───── add / edit person ─────
      openForm(u) {
        if (u ? !u.can_edit : !this.init0.perms.create) return;
        this.form = u
          ? { id: u.id, first_name: u.first_name, last_name: u.last_name, phone: u.phone, email: u.email, username: u.username, role: u.role, was: u.role, me: u.is_me }
          : { id: null, first_name: '', last_name: '', phone: '', email: '', username: '', role: this.assignable.includes('STAFF') ? 'STAFF' : this.assignable[this.assignable.length - 1], password: genPassword() };
        this.fe = {}; this.formError = ''; this.done = null; this.formOpen = true;
        this.$nextTick(() => this.$refs.fFirst && this.$refs.fFirst.focus());
      },
      get roleChoices() {
        const list = [...this.assignable];
        if (this.form.id && this.form.was && !list.includes(this.form.was)) list.unshift(this.form.was);
        return list;
      },
      suggest() {
        if (this.form.id || this.form.userTouched) return;
        const s = (this.form.first_name + (this.form.last_name ? '.' + this.form.last_name : '')).toLowerCase().replace(/[^a-z0-9.]+/g, '');
        this.form.username = s.slice(0, 30);
      },
      async saveForm() {
        if (this.formSaving) return;
        const f = this.form, fe = {};
        if (!f.first_name.trim()) fe.first_name = 'Enter their name.';
        if (!f.username.trim()) fe.username = 'Choose a username to sign in with.';
        else if (!/^[A-Za-z0-9._-]{3,150}$/.test(f.username.trim())) fe.username = 'Use 3+ letters, numbers, dot, dash or underscore — no spaces.';
        if (f.email && !/^\S+@\S+\.\S+$/.test(f.email)) fe.email = 'Enter a valid email address.';
        if (!f.id && (!f.password || f.password.length < 8)) fe.password = 'Use at least 8 characters.';
        this.fe = fe;
        if (Object.keys(fe).length) return;
        this.formSaving = true; this.formError = '';
        const body = { first_name: f.first_name.trim(), last_name: f.last_name.trim(), phone: f.phone.trim(), email: f.email.trim(), username: f.username.trim() };
        if (!f.me) body.role = f.role;
        if (!f.id) body.password = f.password;
        try {
          const r = f.id ? await App.api(`/api/users/${f.id}/`, { method: 'PATCH', body })
                         : await App.api('/api/users/', { method: 'POST', body });
          await this.load();
          if (f.id) { this.formOpen = false; this.flash(r.message || 'Saved.'); if (this.sel) this.resetDraft(); }
          else this.done = { user: r.data, password: f.password };
        } catch (e) { this.fe = errsOf(e); this.formError = Object.keys(this.fe).length ? '' : e.message; }
        this.formSaving = false;
      },
      openDone() { const u = this.people.find(x => x.id === this.done.user.id) || this.done.user; this.formOpen = false; this.open(u, 'access'); },
      get signInUrl() { return location.origin + '/app/login/'; },
      async copyCreds(user, pw) {
        const text = [`Sign in at: ${this.signInUrl}`, `Username: ${user}`, `Password: ${pw}`, 'Please change the password after your first sign-in.'].join('\n');
        try { await navigator.clipboard.writeText(text); } catch (e) { /* পুরনো browser — নিজে copy করবে */ }
        this.copied = true; clearTimeout(this._ct); this._ct = setTimeout(() => { this.copied = false; }, 1800);
      },
      genPw: genPassword,

      // ───── password / on-off ─────
      openPw() { this.pw = genPassword(); this.pwErr = ''; this.pwDone = ''; this.pwOpen = true; },
      async savePw() {
        if (this.pwSaving) return;
        if (!this.pw || this.pw.length < 8) { this.pwErr = 'Use at least 8 characters.'; return; }
        this.pwSaving = true; this.pwErr = '';
        try {
          await App.api(`/api/users/${this.sel.id}/set-password/`, { method: 'POST', body: { password: this.pw } });
          this.pwDone = this.pw;
        } catch (e) { this.pwErr = e.message; }
        this.pwSaving = false;
      },
      askToggle() {
        const u = this.sel;
        this.confirm = u.is_active
          ? { kind: 'toggle', title: `Turn off ${u.name}?`, text: `${u.username} can't sign in any more. Everything they recorded stays, with their name on it.`, btn: 'Turn off', danger: true }
          : { kind: 'toggle', title: `Turn ${u.name} back on?`, text: `${u.username} can sign in again with their current password.`, btn: 'Turn on', danger: false };
      },
      async toggle() {
        this.busy = true;
        try {
          const r = await App.api(`/api/users/${this.sel.id}/`, { method: 'PATCH', body: { is_active: !this.sel.is_active } });
          this.flash(r.message); await this.load();
        } catch (e) { this.flash(e.message); }
        this.busy = false; this.confirm = null;
      },
      doConfirm() {
        if (!this.confirm) return;
        if (this.confirm.kind === 'reset') this.resetPerms();
        else if (this.confirm.kind === 'toggle') this.toggle();
      },

      escape() {
        if (this.confirm) this.confirm = null;
        else if (this.pwOpen) this.pwOpen = false;
        else if (this.formOpen) { if (!this.formSaving) this.formOpen = false; }
        else if (this.sel) this.shut();
      },
      flash(msg) { this.toast = msg; clearTimeout(this._t); this._t = setTimeout(() => { this.toast = ''; }, 3800); },
    };
  };
})();
