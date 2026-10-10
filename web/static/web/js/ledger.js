/*
 * Expense List / Income List — একই রকম দুটো page, একটাই component (cfg দিয়ে আলাদা)।
 *   খরচ: /api/expenses/expenses/  (server এ page), /api/expenses/expenses/summary/
 *   আয়:  /api/income/incomes/      (সব একসাথে আসে, এখানে page করি), /api/income/incomes/summary/
 * টাকা কোন account থেকে গেল/এল — payment method আলাদা করে জিজ্ঞেস করি না, account এর ধরন থেকে বসাই।
 */
(function () {
  'use strict';

  const pad = (x) => String(x).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const r2 = (v) => Math.round((n(v) + Number.EPSILON) * 100) / 100;
  const listOf = (r) => (Array.isArray(r && r.data) ? r.data : (r && r.data && r.data.results) || []);
  const fmtDate = (s) => {
    if (!s) return '';
    const d = new Date(String(s).length === 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const METHOD = { 'Cash': 'cash', 'Bank': 'bank', 'Mobile banking': 'mobile', 'Other': 'other' };
  const PAGE = 25;
  const errsOf = (e) => {
    const d = e && e.data && e.data.data, out = {};
    if (d && typeof d === 'object' && !Array.isArray(d)) Object.entries(d).forEach(([k, v]) => { out[k] = Array.isArray(v) ? v[0] : String(v); });
    return out;
  };

  window.ledgerPage = function (cfg) {
    const isExp = cfg.kind === 'expense';
    const dateKey = isExp ? 'expense_date' : 'income_date';
    return {
      cfg, isExp, perms: cfg.perms,
      presets: [
        { key: 'month', label: 'This month' }, { key: 'last', label: 'Last month' }, { key: '30d', label: 'Last 30 days' },
        { key: 'year', label: 'This year' }, { key: 'all', label: 'All time' }, { key: 'custom', label: 'Custom' },
      ],
      f: { preset: 'month', from: '', to: '', q: '', head: '', account: '' },
      rows: [], count: 0, page: 1, sum: null, loading: true, error: null,
      heads: [], subheads: [], accounts: [],
      sel: null,
      formOpen: false, form: {}, fe: {}, formError: '', saving: false, done: null,
      confirmDel: false, deleting: false, delError: '',
      toast: '', _req: 0, _all: [],

      init() {
        const p = new URLSearchParams(location.search);
        this.f.preset = p.get('period') || 'month';
        this.f.from = p.get('from') || ''; this.f.to = p.get('to') || '';
        this.f.q = p.get('q') || ''; this.f.head = p.get('head') || ''; this.f.account = p.get('account') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        this.setRange(this.f.preset, true);
        this.loadRefs();
        this.load();
        this.$watch('f.q', () => { clearTimeout(this._qt); this._qt = setTimeout(() => { this.page = 1; this.load(); }, 300); });
        const open = Number(p.get('open'));
        if (open) this.openId(open);
        if (p.get('new') && (this.perms.create)) this.$nextTick(() => this.openForm(null));
      },
      async loadRefs() {
        const tasks = [App.api(cfg.heads_api).then(r => { this.heads = listOf(r); }),
          App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => { this.accounts = listOf(r).filter(a => a.is_active !== false); })];
        if (isExp) tasks.push(App.api(cfg.subheads_api).then(r => { this.subheads = listOf(r); }));
        await Promise.all(tasks.map(t => t.catch(() => {})));
      },
      setRange(key, silent) {
        this.f.preset = key;
        const t = new Date(); t.setHours(0, 0, 0, 0);
        if (key === 'month') { this.f.from = iso(new Date(t.getFullYear(), t.getMonth(), 1)); this.f.to = iso(t); }
        else if (key === 'last') { this.f.from = iso(new Date(t.getFullYear(), t.getMonth() - 1, 1)); this.f.to = iso(new Date(t.getFullYear(), t.getMonth(), 0)); }
        else if (key === '30d') { const s = new Date(t); s.setDate(s.getDate() - 29); this.f.from = iso(s); this.f.to = iso(t); }
        else if (key === 'year') { this.f.from = iso(new Date(t.getFullYear(), 0, 1)); this.f.to = iso(t); }
        else if (key === 'all') { this.f.from = ''; this.f.to = ''; }
        else { if (!this.f.from) this.f.from = iso(new Date(t.getFullYear(), t.getMonth(), 1)); if (!this.f.to) this.f.to = iso(t); }
        if (!silent) { this.page = 1; this.load(); }
      },
      setHead(id) { this.f.head = this.f.head === String(id) ? '' : String(id); this.page = 1; this.load(); },
      setAccount(v) { this.f.account = v; this.page = 1; this.load(); },
      clearAll() { this.f.q = ''; this.f.head = ''; this.f.account = ''; this.setRange('month'); },
      get filtered() { return !!(this.f.q || this.f.head || this.f.account || this.f.preset !== 'month'); },
      query() {
        if (this.f.from && this.f.to && this.f.from > this.f.to) [this.f.from, this.f.to] = [this.f.to, this.f.from];
        const q = {};
        if (this.f.from) q.start_date = this.f.from;
        if (this.f.to) q.end_date = this.f.to;
        if (this.f.q) q.search = this.f.q;
        if (this.f.head) q.head_id = this.f.head;
        if (this.f.account) q.account_id = this.f.account;
        return q;
      },
      sync() {
        const p = new URLSearchParams();
        if (this.f.preset !== 'month') p.set('period', this.f.preset);
        if (this.f.preset === 'custom') { p.set('from', this.f.from); p.set('to', this.f.to); }
        if (this.f.q) p.set('q', this.f.q);
        if (this.f.head) p.set('head', this.f.head);
        if (this.f.account) p.set('account', this.f.account);
        if (this.page > 1) p.set('page', this.page);
        if (this.sel) p.set('open', this.sel.id);
        history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : ''));
      },
      async load() {
        const id = ++this._req, q = this.query();
        this.loading = true; this.error = null; this.sync();
        try {
          const [list, sum] = await Promise.all([
            isExp ? App.api(cfg.api, { query: { ...q, page: this.page, page_size: PAGE, sort_by: 'expense_date', sort_order: 'desc' } })
                  : App.api(cfg.api, { query: q }),
            App.api(cfg.summary_api, { query: q }),
          ]);
          if (id !== this._req) return;
          if (isExp) { this.rows = list.data.results; this.count = list.data.count; }
          else { this._all = listOf(list); this.count = this._all.length; this.rows = this._all.slice((this.page - 1) * PAGE, this.page * PAGE); }
          this.sum = sum.data;
          if (!this.rows.length && this.page > 1) { this.page = 1; return this.load(); }
        } catch (e) { if (id === this._req) this.error = e.message; }
        if (id === this._req) this.loading = false;
      },
      go(p) { if (p < 1 || p > this.pages) return; this.page = p; if (isExp) this.load(); else { this.rows = this._all.slice((p - 1) * PAGE, p * PAGE); this.sync(); } },
      get pages() { return Math.max(1, Math.ceil(this.count / PAGE)); },
      get fromRow() { return this.count ? (this.page - 1) * PAGE + 1 : 0; },
      get toRow() { return Math.min(this.count, this.page * PAGE); },
      get rangeText() {
        if (this.f.preset === 'all') return 'All time';
        if (this.f.from === this.f.to) return fmtDate(this.f.from);
        return fmtDate(this.f.from) + ' – ' + fmtDate(this.f.to);
      },
      get headBars() {
        if (!this.sum || !this.sum.by_head) return [];
        const top = this.sum.by_head.slice(0, 5), max = Math.max(1, ...top.map(h => n(h.total)));
        return top.map(h => ({ ...h, pct: Math.max(3, n(h.total) / max * 100), share: n(this.sum.total) ? Math.round(n(h.total) / n(this.sum.total) * 100) : 0 }));
      },
      get daysInRange() {
        if (!this.f.from || !this.f.to) return 0;
        return Math.round((new Date(this.f.to) - new Date(this.f.from)) / 864e5) + 1;
      },
      get perDay() { const d = this.daysInRange; return d && this.sum ? r2(n(this.sum.total) / d) : null; },
      taka: (v) => App.taka(v), date: fmtDate,
      headName(r) { return r.head_name || 'No head'; },
      sub(r) { return isExp && r.subhead_name ? r.subhead_name : ''; },

      // ───── detail ─────
      async openId(id) {
        try { const r = await App.api(`${cfg.api}${id}/`); this.open(r.data); } catch (e) { this.flash(e.message); }
      },
      open(r) { this.sel = r; this.confirmDel = false; document.body.style.overflow = 'hidden'; this.sync(); this.refreshSel(); },
      async refreshSel() {
        if (!this.sel) return;
        try { const r = await App.api(`${cfg.api}${this.sel.id}/`); if (this.sel && this.sel.id === r.data.id) this.sel = r.data; } catch (e) { /* list row is enough */ }
      },
      shut() { this.sel = null; document.body.style.overflow = ''; this.sync(); },
      print() { window.print(); },
      get selDate() { return this.sel ? this.sel[dateKey] : ''; },

      // ───── form ─────
      get activeHeads() { return this.heads.filter(h => h.is_active !== false || (this.form.head && String(h.id) === this.form.head)); },
      get subsForHead() { return this.subheads.filter(s => String(s.head) === String(this.form.head) && (s.is_active !== false || String(s.id) === this.form.subhead)); },
      get acct() { return this.accounts.find(a => String(a.id) === String(this.form.account)); },
      get overBalance() {
        if (!isExp || !this.acct) return false;
        let avail = n(this.acct.balance);
        if (this.form.id && String(this.form.was_account) === String(this.form.account)) avail += n(this.form.was_amount);
        return n(this.form.amount) > avail + 0.0001;
      },
      get available() {
        if (!this.acct) return 0;
        let avail = n(this.acct.balance);
        if (isExp && this.form.id && String(this.form.was_account) === String(this.form.account)) avail += n(this.form.was_amount);
        return r2(avail);
      },
      openForm(r) {
        if (r ? !this.perms.edit : !this.perms.create) return;
        const cash = this.accounts.find(a => a.ac_type === 'Cash') || this.accounts[0];
        this.form = r ? {
          id: r.id, head: r.head ? String(r.head) : '', subhead: r.subhead ? String(r.subhead) : '', amount: String(n(r.amount)),
          account: r.account ? String(r.account) : '', date: r[dateKey], note: r.note || '', was_account: r.account, was_amount: n(r.amount), ref: r.invoice_number,
        } : { id: null, head: this.f.head || '', subhead: '', amount: '', account: cash ? String(cash.id) : '', date: iso(new Date()), note: '', newHead: '' };
        this.fe = {}; this.formError = ''; this.done = null; this.formOpen = true;
        this.$nextTick(() => this.$refs.lgAmount && this.$refs.lgAmount.focus());
      },
      headChanged() { this.fe.head = ''; if (!this.subsForHead.some(s => String(s.id) === this.form.subhead)) this.form.subhead = ''; },
      async addHead() {
        const name = (this.form.newHead || '').trim();
        if (!name) return;
        try {
          const r = await App.api(cfg.heads_api, { method: 'POST', body: { name } });
          this.heads = [...this.heads, r.data].sort((a, b) => a.name.localeCompare(b.name));
          this.form.head = String(r.data.id); this.form.newHead = ''; this.form.addingHead = false; this.headChanged();
        } catch (e) { this.fe.head = (errsOf(e).name) || e.message; }
      },
      async save(again) {
        if (this.saving) return;
        const f = this.form, fe = {};
        if (!f.head) fe.head = `Pick what the ${isExp ? 'expense' : 'income'} was for.`;
        if (!(n(f.amount) > 0)) fe.amount = 'Enter an amount.';
        if (!f.account) fe.account = isExp ? 'Pick where the money was paid from.' : 'Pick where the money went in.';
        else if (this.overBalance) fe.amount = `${this.acct.name} only has ${this.taka(this.available)}.`;
        if (!f.date) fe.date = 'Pick the date.';
        this.fe = fe;
        if (Object.keys(fe).length) return;
        this.saving = true; this.formError = '';
        const body = { head: Number(f.head), amount: r2(f.amount).toFixed(2), account: Number(f.account),
          payment_method: METHOD[(this.acct || {}).ac_type] || 'other', note: f.note.trim() || null, [dateKey]: f.date };
        if (isExp) body.subhead = f.subhead ? Number(f.subhead) : null;
        try {
          const r = f.id ? await App.api(`${cfg.api}${f.id}/`, { method: 'PATCH', body })
                         : await App.api(cfg.api, { method: 'POST', body });
          this.loadRefs();
          await this.load();
          if (f.id) { this.formOpen = false; this.flash('Saved. The account balance was adjusted.'); if (this.sel) this.open(r.data); }
          else if (again) { this.flash(`${r.data.invoice_number} saved.`); this.form = { ...this.form, amount: '', note: '', subhead: '' }; this.$nextTick(() => this.$refs.lgAmount && this.$refs.lgAmount.focus()); }
          else { this.formOpen = false; this.flash(`${r.data.invoice_number} saved — ${this.taka(body.amount)} ${isExp ? 'paid from' : 'added to'} ${(this.acct || {}).name || 'the account'}.`); }
        } catch (e) {
          this.fe = errsOf(e);
          if (this.fe[dateKey]) this.fe.date = this.fe[dateKey];
          this.formError = Object.keys(this.fe).length ? '' : e.message;
        }
        this.saving = false;
      },

      // ───── delete ─────
      async remove() {
        if (!this.sel || this.deleting) return;
        this.deleting = true; this.delError = '';
        try {
          const r = await App.api(`${cfg.api}${this.sel.id}/`, { method: 'DELETE' });
          this.flash((r && r.message) || 'Deleted.');
          this.confirmDel = false; this.shut(); this.loadRefs(); await this.load();
        } catch (e) { this.delError = e.message; }
        this.deleting = false;
      },
      escape() {
        if (this.formOpen) { if (!this.saving) this.formOpen = false; }
        else if (this.confirmDel) this.confirmDel = false;
        else if (this.sel) this.shut();
      },
      flash(m) { this.toast = m; clearTimeout(this._t); this._t = setTimeout(() => { this.toast = ''; }, 4000); },
    };
  };
})();
