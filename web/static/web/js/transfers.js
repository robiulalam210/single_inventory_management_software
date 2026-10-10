/*
 * Transfer Balance — নতুন transfer (transferForm), Transfer List (transferList), Transactions (txnList)।
 *   POST /api/transfers/                    — pending transfer তৈরি
 *   POST /api/transfers/quick_transfer/     — তৈরি আর সাথে সাথে execute
 *   POST /api/transfers/<id>/execute|reverse|cancel/
 *   GET  /api/transfers/   ·   GET /api/transactions/ (শুধু দেখা)
 *   নিয়ম app এর হুবহু: pending → execute / cancel;  completed → reverse (reversal নিজে আবার reverse হয় না)
 */
(function () {
  'use strict';

  const pad = (x) => String(x).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const n = (v) => { const x = Number(String(v == null ? '' : v).replace(/,/g, '')); return isFinite(x) ? x : 0; };
  const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;
  const PAGE_SIZE = 25;
  const listOf = (r) => (Array.isArray(r && r.data) ? r.data : (r && r.data && r.data.results) || []);
  const cap = (s) => s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : '—';
  const fmtDate = (s) => {
    if (!s) return '—';
    const d = new Date(String(s).length <= 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const fmtDateTime = (s) => {
    if (!s) return '—';
    const d = new Date(s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) + ', ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  };
  function rangeOf(key) {
    const t = today();
    if (key === 'today') return [iso(t), iso(t)];
    if (key === '7d') { const s = new Date(t); s.setDate(s.getDate() - 6); return [iso(s), iso(t)]; }
    if (key === 'month') return [iso(new Date(t.getFullYear(), t.getMonth(), 1)), iso(t)];
    return ['', ''];
  }
  function pagesOf(c, t) {
    const out = [];
    for (let i = 1; i <= t; i++) {
      if (i === 1 || i === t || Math.abs(i - c) <= 2) out.push(i);
      else if (out[out.length - 1] !== '…') out.push('…');
    }
    return out;
  }
  function explain(e) {
    const d = e.data && e.data.data;
    if (d && typeof d === 'object') {
      const first = Object.entries(d)[0];
      if (first) {
        const [k, v] = first;
        const msg = Array.isArray(v) ? v[0] : (typeof v === 'string' ? v : JSON.stringify(v));
        return (k === 'non_field_errors' ? '' : k.replace(/_id$/, '').replace(/_/g, ' ') + ': ') + msg;
      }
    }
    return e.message;
  }
  const PRESETS = [
    { key: 'today', label: 'Today' }, { key: '7d', label: 'Last 7 days' },
    { key: 'month', label: 'This month' }, { key: 'all', label: 'All time' }, { key: 'custom', label: 'Custom' },
  ];
  // তালিকার সব কাজ একই: page, URL, reset
  const pager = {
    go(p) {
      if (p < 1 || p > this.meta.total_pages || p === this.page) return;
      this.page = p; this.fetch();
      document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    get from() { return this.meta.count ? (this.page - 1) * PAGE_SIZE + 1 : 0; },
    get to() { return Math.min(this.page * PAGE_SIZE, this.meta.count); },
    get pages() { return pagesOf(this.page, this.meta.total_pages); },
    num: (v) => new Intl.NumberFormat('en-US').format(n(v)),
    taka: (v) => App.taka(v),
    date: fmtDate, dateTime: fmtDateTime, cap,
  };
  // Object.assign getter গুলো চালিয়ে ফেলে; এটা getter সহ মেশায়
  const mix = (a, b) => Object.defineProperties({}, Object.assign({}, Object.getOwnPropertyDescriptors(a), Object.getOwnPropertyDescriptors(b)));
  function metaOf(d, rows) {
    return { count: d && d.count != null ? d.count : rows.length, total_pages: (d && d.total_pages) || 1 };
  }

  // ─────────────────────────────── new transfer ───────────────────────────────
  window.transferForm = function (init) {
    return {
      accountsAll: [],
      types: [{ value: 'internal', label: 'Internal' }, { value: 'external', label: 'External' }, { value: 'adjustment', label: 'Adjustment' }],
      canSeeList: !!init.canSeeList,
      loading: true,
      form: { from: '', to: '', amount: '', type: 'internal', date: iso(today()), ref: '', description: '', remarks: '', quick: true },
      maxDate: iso(today()),
      errors: {}, saving: false, serverError: '', done: null,

      init() {
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => {
          this.accountsAll = listOf(r).filter(a => a.is_active !== false);
          this.loading = false;
        }).catch(e => { this.serverError = 'Could not load accounts: ' + e.message; this.loading = false; });
        this.$watch('form.from', () => { if (this.form.to === this.form.from) this.form.to = ''; this.errors.from = ''; });
        this.$watch('form.to', () => { this.errors.to = ''; });
      },
      opts(excludeId) {
        return this.accountsAll.filter(a => String(a.id) !== String(excludeId))
          .map(a => ({ value: String(a.id), label: a.name, sub: (a.ac_type || '') + ' · ' + App.taka(a.balance) }));
      },
      get fromOptions() { return this.opts(this.form.to); },
      get toOptions() { return this.opts(this.form.from); },
      get fromAcc() { return this.accountsAll.find(a => String(a.id) === String(this.form.from)) || null; },
      get toAcc() { return this.accountsAll.find(a => String(a.id) === String(this.form.to)) || null; },
      get amountNum() { return round2(n(this.form.amount)); },
      get short() { return !!(this.fromAcc && this.amountNum > n(this.fromAcc.balance)); },
      get afterFrom() { return this.fromAcc ? round2(n(this.fromAcc.balance) - this.amountNum) : 0; },
      get afterTo() { return this.toAcc ? round2(n(this.toAcc.balance) + this.amountNum) : 0; },
      fill(v) { this.form.amount = String(round2(v)); this.errors.amount = ''; },

      validate() {
        const e = {};
        if (!this.form.from) e.from = 'Choose the account the money leaves.';
        if (!this.form.to) e.to = 'Choose the account the money goes to.';
        else if (this.form.to === this.form.from) e.to = 'Cannot transfer to the same account.';
        if (!(this.amountNum > 0)) e.amount = 'Enter an amount greater than 0.';
        else if (this.short) e.amount = `Not enough balance. Available ${App.taka(this.fromAcc.balance)}.`;
        if (!this.form.date) e.date = 'Pick the transfer date.';
        else if (this.form.date > this.maxDate) e.date = 'The date cannot be in the future.';
        this.errors = e;
        return !Object.keys(e).length;
      },

      async save() {
        this.serverError = '';
        if (!this.validate() || this.saving) {
          this.$nextTick(() => { const el = this.$root.querySelector('.has-error'); if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); });
          return;
        }
        this.saving = true;
        const body = {
          from_account_id: String(this.form.from), to_account_id: String(this.form.to),
          amount: this.amountNum.toFixed(2), description: this.form.description.trim(),
          transfer_type: this.form.type, reference_no: this.form.ref.trim(),
          remarks: this.form.remarks.trim(), transfer_date: this.form.date,
        };
        const quick = this.form.quick;
        try {
          const r = await App.api(quick ? '/api/transfers/quick_transfer/' : '/api/transfers/', { method: 'POST', body });
          this.done = { quick, amount: this.amountNum, from: this.fromAcc && this.fromAcc.name, to: this.toAcc && this.toAcc.name,
            no: r.data && (r.data.transfer_no || (r.data.transfer && r.data.transfer.transfer_no)) || '', status: r.data && r.data.status };
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (e) { this.serverError = explain(e); }
        this.saving = false;
      },

      again() {
        this.done = null;
        this.form = Object.assign(this.form, { from: '', to: '', amount: '', ref: '', description: '', remarks: '', date: iso(today()) });
        this.errors = {};
        // balance নতুন করে আনি — transfer এর পরে বদলেছে
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => { this.accountsAll = listOf(r).filter(a => a.is_active !== false); }).catch(() => {});
      },
      taka: (v) => App.taka(v), words: (v) => App.takaWords(v),
    };
  };

  // ─────────────────────────────── transfer list ───────────────────────────────
  window.transferList = function (opts) {
    return mix(pager, {
      presets: PRESETS,
      statuses: [{ key: '', label: 'All' }, { key: 'pending', label: 'Pending' }, { key: 'completed', label: 'Completed' }, { key: 'failed', label: 'Failed' }, { key: 'cancelled', label: 'Cancelled' }],
      typeOpts: [{ value: 'internal', label: 'Internal' }, { value: 'external', label: 'External' }, { value: 'adjustment', label: 'Adjustment' }],
      f: { q: '', status: '', type: '', from: '', to: '', reversal: false, preset: 'all', d1: '', d2: '' },
      accounts: [],
      page: 1, rows: [], meta: { count: 0, total_pages: 1 },
      loading: true, error: null, sel: null,
      canEdit: !!opts.canEdit, me: opts.me,
      confirm: null, reason: '', working: false, confirmError: '',
      toast: '', _req: 0, _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || ''; this.f.status = p.get('status') || ''; this.f.type = p.get('type') || '';
        this.f.from = p.get('from') || ''; this.f.to = p.get('to') || ''; this.f.reversal = p.get('reversal') === '1';
        this.f.preset = p.get('period') || 'all'; this.f.d1 = p.get('d1') || ''; this.f.d2 = p.get('d2') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        if (this.f.preset !== 'custom') [this.f.d1, this.f.d2] = rangeOf(this.f.preset);
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => {
          this.accounts = listOf(r).map(a => ({ value: String(a.id), label: a.name, sub: a.ac_type || '' }));
        }).catch(() => {});
        this.fetch();
        if (p.get('saved')) this.flash('Transfer saved.');
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 350); });
        ['f.status', 'f.type', 'f.from', 'f.to', 'f.reversal'].forEach(k => this.$watch(k, () => this.reset()));
      },
      setPreset(key) { this.f.preset = key; if (key !== 'custom') { [this.f.d1, this.f.d2] = rangeOf(key); this.reset(); } },
      applyCustom() { if (this.f.d1 && this.f.d2 && this.f.d1 > this.f.d2) [this.f.d1, this.f.d2] = [this.f.d2, this.f.d1]; this.reset(); },
      clearAll() { this.f = { q: '', status: '', type: '', from: '', to: '', reversal: false, preset: 'all', d1: '', d2: '' }; this.reset(); },
      get filtered() { const f = this.f; return !!(f.q || f.status || f.type || f.from || f.to || f.reversal || f.preset !== 'all'); },
      reset() { this.page = 1; this.fetch(); },
      syncUrl() {
        const p = new URLSearchParams(), f = this.f;
        if (f.q) p.set('q', f.q); if (f.status) p.set('status', f.status); if (f.type) p.set('type', f.type);
        if (f.from) p.set('from', f.from); if (f.to) p.set('to', f.to); if (f.reversal) p.set('reversal', '1');
        if (f.preset !== 'all') p.set('period', f.preset);
        if (f.preset === 'custom') { if (f.d1) p.set('d1', f.d1); if (f.d2) p.set('d2', f.d2); }
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },
      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null; this.syncUrl();
        const f = this.f;
        try {
          const r = await App.api('/api/transfers/', { query: {
            page: this.page, page_size: PAGE_SIZE, search: f.q.trim(), status: f.status, transfer_type: f.type,
            from_account_id: f.from, to_account_id: f.to, is_reversal: f.reversal ? 'true' : '',
            start_date: f.d1, end_date: f.d2,
          } });
          if (id !== this._req) return;
          const d = r.data || {};
          let rows = Array.isArray(d) ? d : (d.results || []);
          if (f.status) rows = rows.filter(x => String(x.status).toLowerCase() === f.status);
          this.rows = rows; this.meta = metaOf(d, rows);
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = [];
        }
        this.loading = false;
      },

      status: (t) => String(t.status || '').toLowerCase(),
      canExecute(t) { return this.canEdit && this.status(t) === 'pending' && !t.is_reversal; },
      canReverse(t) { return this.canEdit && this.status(t) === 'completed' && !t.is_reversal; },
      canCancel(t) { return this.canEdit && this.status(t) === 'pending'; },
      acc: (a) => (a && a.name) || '—',

      open(t) { this.sel = t; document.body.style.overflow = 'hidden'; },
      shut() { this.sel = null; document.body.style.overflow = ''; },

      ask(kind, row) { this.confirm = { kind, row }; this.reason = ''; this.confirmError = ''; },
      get confirmText() {
        const c = this.confirm; if (!c) return null;
        const no = c.row.transfer_no || ('#' + c.row.id), amt = App.taka(c.row.amount);
        return {
          execute: { title: `Execute ${no}?`, body: `${amt} moves from ${this.acc(c.row.from_account)} to ${this.acc(c.row.to_account)} now.`, btn: 'Execute', danger: false, reason: false },
          reverse: { title: `Reverse ${no}?`, body: `A new transfer moves ${amt} back from ${this.acc(c.row.to_account)} to ${this.acc(c.row.from_account)}. The original stays on record.`, btn: 'Reverse', danger: true, reason: true },
          cancel: { title: `Cancel ${no}?`, body: 'This transfer has not moved any money yet. Cancelling stops it for good.', btn: 'Cancel transfer', danger: true, reason: true },
        }[c.kind];
      },
      async runConfirm() {
        const c = this.confirm; if (!c || this.working) return;
        this.working = true; this.confirmError = '';
        const body = c.kind === 'execute' ? { user_id: this.me && this.me.id } : (this.reason.trim() ? { reason: this.reason.trim() } : {});
        try {
          await App.api(`/api/transfers/${c.row.id}/${c.kind}/`, { method: 'POST', body });
          const done = { execute: 'executed', reverse: 'reversed', cancel: 'cancelled' }[c.kind];
          const no = c.row.transfer_no || ('#' + c.row.id);
          this.confirm = null; this.shut(); this.flash(`Transfer ${no} ${done}.`); this.fetch();
        } catch (e) { this.confirmError = e.message; }
        this.working = false;
      },
      flash(msg) { this.toast = msg; clearTimeout(this._toast); this._toast = setTimeout(() => { this.toast = ''; }, 3500); },
    });
  };

  // ─────────────────────────────── transactions (read-only) ───────────────────────────────
  window.txnList = function () {
    return mix(pager, {
      presets: PRESETS,
      types: [{ key: '', label: 'All' }, { key: 'credit', label: 'Credit' }, { key: 'debit', label: 'Debit' }],
      statuses: [{ key: '', label: 'Any status' }, { key: 'completed', label: 'Completed' }, { key: 'pending', label: 'Pending' }, { key: 'failed', label: 'Failed' }],
      f: { q: '', type: '', status: '', account: '', preset: 'month', d1: '', d2: '' },
      accounts: [], page: 1, rows: [], meta: { count: 0, total_pages: 1 },
      loading: true, error: null, sel: null, _req: 0, _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || ''; this.f.type = p.get('type') || ''; this.f.status = p.get('status') || '';
        this.f.account = p.get('account') || ''; this.f.preset = p.get('period') || 'month';
        this.f.d1 = p.get('d1') || ''; this.f.d2 = p.get('d2') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        if (this.f.preset !== 'custom') [this.f.d1, this.f.d2] = rangeOf(this.f.preset);
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => {
          this.accounts = listOf(r).map(a => ({ value: String(a.id), label: a.name, sub: a.ac_type || '' }));
        }).catch(() => {});
        this.fetch();
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 350); });
        ['f.type', 'f.status', 'f.account'].forEach(k => this.$watch(k, () => this.reset()));
      },
      setPreset(key) { this.f.preset = key; if (key !== 'custom') { [this.f.d1, this.f.d2] = rangeOf(key); this.reset(); } },
      applyCustom() { if (this.f.d1 && this.f.d2 && this.f.d1 > this.f.d2) [this.f.d1, this.f.d2] = [this.f.d2, this.f.d1]; this.reset(); },
      clearAll() { this.f = { q: '', type: '', status: '', account: '', preset: 'month', d1: '', d2: '' }; [this.f.d1, this.f.d2] = rangeOf('month'); this.reset(); },
      get filtered() { const f = this.f; return !!(f.q || f.type || f.status || f.account || f.preset !== 'month'); },
      reset() { this.page = 1; this.fetch(); },
      syncUrl() {
        const p = new URLSearchParams(), f = this.f;
        if (f.q) p.set('q', f.q); if (f.type) p.set('type', f.type); if (f.status) p.set('status', f.status);
        if (f.account) p.set('account', f.account); if (f.preset !== 'month') p.set('period', f.preset);
        if (f.preset === 'custom') { if (f.d1) p.set('d1', f.d1); if (f.d2) p.set('d2', f.d2); }
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },
      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null; this.syncUrl();
        const f = this.f;
        try {
          const r = await App.api('/api/transactions/', { query: {
            page: this.page, page_size: PAGE_SIZE, search: f.q.trim(), transaction_type: f.type, status: f.status,
            account_id: f.account, start_date: f.d1, end_date: f.d2,
          } });
          if (id !== this._req) return;
          const d = r.data || {};
          const rows = Array.isArray(d) ? d : (d.results || []);
          this.rows = rows; this.meta = metaOf(d, rows);
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = [];
        }
        this.loading = false;
      },
      get credit() { return round2(this.rows.filter(r => r.transaction_type === 'credit').reduce((s, r) => s + n(r.amount), 0)); },
      get debit() { return round2(this.rows.filter(r => r.transaction_type === 'debit').reduce((s, r) => s + n(r.amount), 0)); },
      head: (r) => (r.expense_head && typeof r.expense_head === 'object' ? r.expense_head.name : r.expense_head) || '—',
      // লেনদেন কোথা থেকে এল — Sale, Money receipt, Purchase …
      source(r) {
        if (r.sale_invoice_no) return 'Sale ' + r.sale_invoice_no;
        if (r.money_receipt_no) return 'Receipt ' + r.money_receipt_no;
        if (r.purchase_invoice_no) return 'Purchase ' + r.purchase_invoice_no;
        if (r.expense_invoice_number) return 'Expense ' + r.expense_invoice_number;
        if (r.supplier_payment_reference) return 'Supplier payment ' + r.supplier_payment_reference;
        return '';
      },
    });
  };
})();
