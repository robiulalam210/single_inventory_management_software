/*
 * Supplier — তালিকা (supplierList), payment তালিকা (supplierPaymentList), নতুন payment (supplierPayForm)।
 *   /api/suppliers/ (প্রতি page এ ৩০), /api/suppliers-active/ (মোট হিসাবের জন্য সব)
 *   /api/supplier-payments/ + /summary/ + /<id>/cancel/
 */
(function () {
  'use strict';

  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const r2 = (v) => Math.round((n(v) + Number.EPSILON) * 100) / 100;
  const PAGE_SIZE = 30;
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const fmtDate = (s) => {
    if (!s) return '';
    const d = new Date(String(s).length === 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const numFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
  // supplier payment এর method code (model এর choice) ↔ account এর ধরন (ac_type)
  const METHODS = [
    { value: 'cash', label: 'Cash', ac: 'cash' },
    { value: 'bank', label: 'Bank', ac: 'bank' },
    { value: 'mobile', label: 'Mobile banking', ac: 'mobile banking' },
  ];
  const METHOD_LABEL = { cash: 'Cash', bank: 'Bank', cheque: 'Cheque', mobile: 'Mobile banking' };
  const TYPE_LABEL = { specific: 'Invoice payment', overall: 'Toward dues', advance: 'Advance' };
  const PRESETS = [
    { key: 'today', label: 'Today' }, { key: '7d', label: 'Last 7 days' }, { key: 'month', label: 'This month' },
    { key: 'all', label: 'All time' }, { key: 'custom', label: 'Custom' },
  ];
  function rangeOf(key) {
    const t = today();
    if (key === 'today') return [iso(t), iso(t)];
    if (key === '7d') { const s = new Date(t); s.setDate(s.getDate() - 6); return [iso(s), iso(t)]; }
    if (key === 'month') return [iso(new Date(t.getFullYear(), t.getMonth(), 1)), iso(t)];
    return ['', ''];
  }
  function pagesOf(t, c) {
    const out = [];
    for (let i = 1; i <= t; i++) {
      if (i === 1 || i === t || Math.abs(i - c) <= 2) out.push(i);
      else if (out[out.length - 1] !== '…') out.push('…');
    }
    return out;
  }
  function explain(e) {
    const d = e.data && e.data.data;
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const [k, v] = Object.entries(d)[0] || [];
      if (k) {
        let msg = Array.isArray(v) ? v[0] : v;
        if (msg && typeof msg === 'object') msg = Object.values(msg).flat()[0];
        if (k === 'non_field_errors' || k === 'error' || k === 'debug_info') return String(msg);
        return k.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()) + ': ' + msg;
      }
    }
    return e.message;
  }
  function flashMixin() {
    return {
      toast: '',
      flash(msg) {
        this.toast = msg;
        clearTimeout(this._toast);
        this._toast = setTimeout(() => { this.toast = ''; }, 3500);
      },
    };
  }

  // ─────────────────────────────── supplier list ───────────────────────────────
  window.supplierList = function (perms) {
    return Object.assign({
      perms,
      sorts: [
        { key: '-total_due', label: 'Most owed' },
        { key: 'name', label: 'Name' },
        { key: '-total_purchases', label: 'Most bought' },
      ],
      views: [
        { key: 'active', label: 'Active' },
        { key: 'due', label: 'You owe' },
        { key: 'advance', label: 'Advance given' },
        { key: 'inactive', label: 'Inactive' },
        { key: 'all', label: 'All' },
      ],
      f: { q: '', view: 'active', sort: '-total_due' },
      page: 1, rows: [], meta: { count: 0, total_pages: 1 },
      tot: null, loading: true, error: null,
      sel: null, recentPo: null, recentPay: null,
      formOpen: false, form: {}, fe: {}, formError: '', formSaving: false,
      confirmDel: false, delError: '', deleting: false,
      _req: 0, _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || '';
        this.f.view = p.get('view') || 'active';
        this.f.sort = p.get('sort') || '-total_due';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        this.fetch();
        this.loadTotals();
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 300); });
        ['f.view', 'f.sort'].forEach(k => this.$watch(k, () => this.reset()));
      },
      get filtered() { return !!(this.f.q || this.f.view !== 'active' || this.f.sort !== '-total_due'); },
      clearAll() { this.f = { q: '', view: 'active', sort: '-total_due' }; this.reset(); },
      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.meta.total_pages || p === this.page) return;
        this.page = p; this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },
      query() {
        const q = { search: this.f.q.trim(), order_by: this.f.sort, page: this.page, page_size: PAGE_SIZE };
        if (this.f.view === 'active' || this.f.view === 'due' || this.f.view === 'advance') q.status = 'active';
        if (this.f.view === 'inactive') q.status = 'inactive';
        if (this.f.view === 'due') q.balance = 'due';
        if (this.f.view === 'advance') q.balance = 'advance';
        return q;
      },
      syncUrl() {
        const p = new URLSearchParams();
        if (this.f.q) p.set('q', this.f.q);
        if (this.f.view !== 'active') p.set('view', this.f.view);
        if (this.f.sort !== '-total_due') p.set('sort', this.f.sort);
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },
      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null; this.syncUrl();
        try {
          const r = await App.api('/api/suppliers/', { query: this.query() });
          if (id !== this._req) return;
          const d = r.data || {};
          this.rows = d.results || [];
          this.meta = { count: d.count || 0, total_pages: d.total_pages || 1 };
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = [];
        }
        this.loading = false;
      },
      async loadTotals() {
        try {
          const all = listOf(await App.api('/api/suppliers-active/'));
          const t = { active: 0, bought: 0, paid: 0, due: 0, advance: 0, owing: 0 };
          all.forEach(s => {
            if (s.is_active) t.active++;
            t.bought += n(s.total_purchases); t.paid += n(s.total_paid);
            t.due += n(s.total_due); t.advance += n(s.advance_balance);
            if (n(s.total_due) > 0) t.owing++;
          });
          this.tot = t;
        } catch (e) { this.tot = null; }
      },

      taka: (v) => App.taka(v),
      num: (v) => numFmt.format(n(v)),
      date: fmtDate,
      badge(r) {
        if (!r.is_active) return { label: 'Inactive', cls: 'st-cancelled' };
        if (n(r.total_due) > 0) return { label: 'You owe', cls: 'st-pending' };
        if (n(r.advance_balance) > 0) return { label: 'Advance', cls: 'st-partial' };
        return { label: 'Settled', cls: 'st-paid' };
      },
      payType(p) {
        if (p.payment_type === 'specific') return p.purchase_invoice_no ? 'for ' + p.purchase_invoice_no : 'one invoice';
        return (TYPE_LABEL[p.payment_type] || '').toLowerCase();
      },
      get from() { return this.meta.count ? (this.page - 1) * PAGE_SIZE + 1 : 0; },
      get to() { return Math.min(this.page * PAGE_SIZE, this.meta.count); },
      get pages() { return pagesOf(this.meta.total_pages, this.page); },

      // ───── drawer ─────
      open(r) {
        this.sel = r; this.recentPo = null; this.recentPay = null;
        document.body.style.overflow = 'hidden';
        const id = r.id;
        if (perms.purchases) {
          App.api('/api/purchases/', { query: { supplier_id: id, page_size: 5 } })
            .then(x => { if (this.sel && this.sel.id === id) this.recentPo = listOf(x); })
            .catch(() => { this.recentPo = []; });
        }
        App.api('/api/supplier-payments/', { query: { supplier_id: id, page_size: 5 } })
          .then(x => { if (this.sel && this.sel.id === id) this.recentPay = listOf(x); })
          .catch(() => { this.recentPay = []; });
      },
      shut() { this.sel = null; document.body.style.overflow = ''; },

      // ───── add / edit ─────
      openForm(r) {
        this.form = r
          ? { id: r.id, name: r.name || '', shop_name: r.shop_name || '', phone: r.phone || '', email: r.email || '',
              address: r.address || '', product_name: r.product_name || '', is_active: !!r.is_active }
          : { id: null, name: '', shop_name: '', phone: '', email: '', address: '', product_name: '', is_active: true };
        this.fe = {}; this.formError = ''; this.formOpen = true;
        this.$nextTick(() => this.$refs.sfName && this.$refs.sfName.focus());
      },
      async saveForm() {
        const f = this.form, fe = {};
        if (!f.name.trim()) fe.name = 'Enter the supplier name.';
        const phone = f.phone.replace(/[\s-]/g, '');
        if (!phone && !f.email.trim()) fe.phone = 'Add a phone number or an email.';
        else if (phone && phone.replace(/\D/g, '').length < 10) fe.phone = 'Phone number needs at least 10 digits.';
        if (f.email.trim() && !/^\S+@\S+\.\S+$/.test(f.email.trim())) fe.email = 'This email does not look right.';
        this.fe = fe;
        if (Object.keys(fe).length || this.formSaving) return;
        this.formSaving = true; this.formError = '';
        const body = {
          name: f.name.trim(), shop_name: f.shop_name.trim() || null, phone: phone || null,
          email: f.email.trim() || null, address: f.address.trim(), product_name: f.product_name.trim() || null,
          is_active: f.is_active,
        };
        try {
          const r = f.id
            ? await App.api(`/api/suppliers/${f.id}/`, { method: 'PATCH', body })
            : await App.api('/api/suppliers/', { method: 'POST', body });
          this.formOpen = false;
          this.flash(f.id ? 'Supplier updated.' : `${body.name} added.`);
          if (this.sel && r.data && this.sel.id === r.data.id) this.sel = Object.assign({}, this.sel, r.data);
          this.fetch(); this.loadTotals();
        } catch (e) {
          this.formError = explain(e);
        }
        this.formSaving = false;
      },

      // ───── delete ─────
      askDelete() { this.delError = ''; this.confirmDel = true; },
      async remove() {
        if (!this.sel || this.deleting) return;
        this.deleting = true; this.delError = '';
        try {
          const r = await App.api(`/api/suppliers/${this.sel.id}/`, { method: 'DELETE' });
          this.confirmDel = false;
          this.flash(r.message || 'Done.');
          this.shut(); this.fetch(); this.loadTotals();
        } catch (e) { this.delError = e.message; }
        this.deleting = false;
      },
    }, flashMixin());
  };

  // ─────────────────────────────── payment list ───────────────────────────────
  window.supplierPaymentList = function (opts) {
    return Object.assign({
      presets: PRESETS,
      types: [
        { key: '', label: 'All' }, { key: 'specific', label: 'Invoice payment' }, { key: 'overall', label: 'Toward dues' },
        { key: 'advance', label: 'Advance' }, { key: 'cancelled', label: 'Cancelled' },
      ],
      methods: METHODS.map(m => ({ value: m.value, label: m.label })),
      f: { q: '', type: '', supplier: '', method: '', preset: 'month', from: '', to: '' },
      page: 1, rows: [], meta: { count: 0, total_pages: 1 }, sum: null, loading: true, error: null,
      sel: null, suppliers: [], canCancel: !!opts.canCancel,
      confirmCancel: false, cancelReason: '', cancelError: '', cancelling: false,
      _req: 0, _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        ['q', 'type', 'supplier', 'method'].forEach(k => { this.f[k] = p.get(k) || ''; });
        this.f.preset = p.get('period') || 'month';
        this.f.from = p.get('from') || ''; this.f.to = p.get('to') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        if (this.f.preset !== 'custom') [this.f.from, this.f.to] = rangeOf(this.f.preset);
        App.api('/api/suppliers-active/').then(r => {
          this.suppliers = listOf(r).map(s => ({ value: String(s.id), label: s.name, sub: s.phone || s.supplier_no || '' }));
        }).catch(() => {});
        this.fetch();
        const openId = parseInt(p.get('open') || '', 10);
        if (openId) App.api(`/api/supplier-payments/${openId}/`).then(r => { if (r.data) this.open(r.data); }).catch(() => {});
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 350); });
        ['f.type', 'f.supplier', 'f.method'].forEach(k => this.$watch(k, () => this.reset()));
      },
      setPreset(key) { this.f.preset = key; if (key !== 'custom') { [this.f.from, this.f.to] = rangeOf(key); this.reset(); } },
      applyCustom() {
        if (this.f.from && this.f.to && this.f.from > this.f.to) [this.f.from, this.f.to] = [this.f.to, this.f.from];
        this.reset();
      },
      clearAll() {
        this.f = { q: '', type: '', supplier: '', method: '', preset: 'month', from: '', to: '' };
        [this.f.from, this.f.to] = rangeOf('month'); this.reset();
      },
      get filtered() { const f = this.f; return !!(f.q || f.type || f.supplier || f.method || f.preset !== 'month'); },
      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.meta.total_pages || p === this.page) return;
        this.page = p; this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },
      query() {
        const q = { search: this.f.q.trim(), supplier_id: this.f.supplier, payment_method: this.f.method,
          start_date: this.f.from, end_date: this.f.to };
        if (this.f.type === 'cancelled') q.status = 'cancelled';
        else if (this.f.type) { q.payment_type = this.f.type; q.status = 'completed'; }
        return q;
      },
      syncUrl() {
        const p = new URLSearchParams(), f = this.f;
        ['q', 'type', 'supplier', 'method'].forEach(k => { if (f[k]) p.set(k, f[k]); });
        if (f.preset !== 'month') p.set('period', f.preset);
        if (f.preset === 'custom') { if (f.from) p.set('from', f.from); if (f.to) p.set('to', f.to); }
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },
      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null; this.syncUrl();
        const q = this.query();
        try {
          const [list, sum] = await Promise.all([
            App.api('/api/supplier-payments/', { query: Object.assign({ page: this.page, page_size: PAGE_SIZE }, q) }),
            App.api('/api/supplier-payments/summary/', { query: q }).catch(() => null),
          ]);
          if (id !== this._req) return;
          const d = list.data || {};
          this.rows = d.results || [];
          this.meta = { count: d.count || 0, total_pages: d.total_pages || 1 };
          this.sum = sum ? sum.data : null;
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = [];
        }
        this.loading = false;
      },
      taka: (v) => App.taka(v),
      words: (v) => App.takaWords(v),
      num: (v) => numFmt.format(n(v)),
      date: fmtDate,
      methodLabel: (m) => METHOD_LABEL[m] || m || '—',
      paidFrom(r) {
        const m = METHOD_LABEL[r.payment_method] || r.payment_method || '';
        return [m, r.account_name].filter((v, i, a) => v && a.findIndex(x => same(x, v)) === i).join(', ') || '—';
      },
      typeLabel: (t) => TYPE_LABEL[t] || t || '—',
      appliedTo(r) {
        if (r.payment_type === 'specific') return r.purchase_invoice_no ? 'Invoice ' + r.purchase_invoice_no : 'One invoice';
        return TYPE_LABEL[r.payment_type] || '—';
      },
      get from() { return this.meta.count ? (this.page - 1) * PAGE_SIZE + 1 : 0; },
      get to() { return Math.min(this.page * PAGE_SIZE, this.meta.count); },
      get pages() { return pagesOf(this.meta.total_pages, this.page); },
      get periodText() {
        if (this.f.preset === 'all' || (!this.f.from && !this.f.to)) return 'All time';
        if (this.f.from === this.f.to) return fmtDate(this.f.from);
        return `${this.f.from ? fmtDate(this.f.from) : 'Start'} – ${this.f.to ? fmtDate(this.f.to) : 'today'}`;
      },
      open(r) { this.sel = r; document.body.style.overflow = 'hidden'; },
      shut() {
        this.sel = null; document.body.style.overflow = '';
        if (new URLSearchParams(location.search).has('open')) this.syncUrl();
      },
      print() { window.print(); },
      openCancel() { this.cancelReason = ''; this.cancelError = ''; this.confirmCancel = true; },
      async cancelPayment() {
        if (!this.sel || this.cancelling) return;
        this.cancelling = true; this.cancelError = '';
        try {
          const r = await App.api(`/api/supplier-payments/${this.sel.id}/cancel/`, {
            method: 'POST', body: { reason: this.cancelReason.trim() || 'Cancelled from web' } });
          this.confirmCancel = false;
          if (r.data) this.sel = r.data;
          this.flash(`${this.sel.sp_no} cancelled. Money and invoices were reversed.`);
          this.fetch();
        } catch (e) { this.cancelError = e.message; }
        this.cancelling = false;
      },
    }, flashMixin());
  };

  // ─────────────────────────────── pay supplier ───────────────────────────────
  window.supplierPayForm = function (init) {
    return {
      methods: METHODS,
      canSeeList: !!init.canSeeList,
      suppliers: [], supplierRows: {}, accountsAll: [],
      dues: [], duesLoading: false,
      form: {
        supplier: init.supplier ? String(init.supplier) : '',
        mode: init.purchase ? 'specific' : 'overall',
        purchase: init.purchase ? String(init.purchase) : '',
        amount: '', date: iso(today()), method: 'cash', account: '',
        useAdvance: false, reference: '', note: '',
      },
      maxDate: iso(today()),
      errors: {}, saving: false, serverError: '', done: null,

      init() {
        App.api('/api/suppliers-active/', { query: { status: 'active' } }).then(r => {
          const list = listOf(r);
          this.supplierRows = Object.fromEntries(list.map(s => [String(s.id), s]));
          this.suppliers = list.map(s => ({ value: String(s.id), label: s.name,
            sub: n(s.total_due) > 0 ? 'Owe ' + App.taka(s.total_due) : (s.phone || '') }));
        }).catch(() => {});
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => {
          this.accountsAll = listOf(r).filter(a => a.is_active !== false);
          this.pickAccount();
        }).catch(() => {});
        if (this.form.supplier) this.loadDues(true);

        this.$watch('form.supplier', () => {
          this.form.purchase = ''; this.form.amount = ''; this.form.useAdvance = false; this.errors = {};
          if (this.form.mode === 'specific') this.form.mode = 'overall';
          this.loadDues(false);
        });
        this.$watch('form.method', () => this.pickAccount());
        this.$watch('form.purchase', (v) => {
          const p = this.dues.find(d => String(d.id) === String(v));
          if (p) this.form.amount = n(p.due_amount).toFixed(2);
          this.errors.purchase = '';
        });
        this.$watch('form.mode', (m) => { if (m !== 'specific') this.form.purchase = ''; if (m === 'advance') this.form.useAdvance = false; });
      },

      async loadDues(keep) {
        const id = this.form.supplier;
        this.dues = [];
        if (!id) return;
        this.duesLoading = true;
        try {
          const r = await App.api('/api/purchase-due/', { query: { supplier_id: id, due: 'true' } });
          if (this.form.supplier !== id) return;
          this.dues = listOf(r).filter(p => n(p.due_amount) > 0 && p.payment_status !== 'cancelled');
          if (keep && init.purchase) {
            const p = this.dues.find(d => String(d.id) === String(init.purchase));
            if (p) { this.form.mode = 'specific'; this.form.purchase = String(p.id); this.form.amount = n(p.due_amount).toFixed(2); }
          }
        } catch (e) { this.dues = []; }
        this.duesLoading = false;
      },

      get supplier() { return this.supplierRows[this.form.supplier] || null; },
      get totalDue() { return r2(this.dues.reduce((s, d) => s + n(d.due_amount), 0)); },
      get invoiceOptions() {
        return this.dues.map(d => ({ value: String(d.id), label: d.invoice_no, sub: 'Due ' + App.taka(d.due_amount) + ', ' + fmtDate(d.purchase_date) }));
      },
      get selected() { return this.dues.find(d => String(d.id) === String(this.form.purchase)) || null; },
      get amountNum() { return r2(String(this.form.amount).replace(/,/g, '')); },
      get advAvail() { return n(this.supplier && this.supplier.advance_balance); },
      // backend: advance আগে, শুধু যতটুকু বাকি আছে ততটুকুই
      get advPart() {
        if (!this.form.useAdvance || this.form.mode === 'advance') return 0;
        const cap = this.form.mode === 'specific' ? n(this.selected && this.selected.due_amount) : this.totalDue;
        return r2(Math.max(0, Math.min(this.advAvail, this.amountNum, cap)));
      },
      get cashPart() { return r2(Math.max(0, this.amountNum - this.advPart)); },

      /* MoneyReceipt এর মতোই, backend এর SupplierPayment._process_* এর হুবহু:
       *   overall  → পুরনো বিল থেকে শুরু, বাড়তি নগদ supplier এর advance
       *   specific → ওই বিলেই (বাকির বেশি নয়)
       *   advance  → পুরোটা advance */
      get plan() {
        const amt = this.amountNum, lines = [];
        if (amt <= 0) return { lines, advance: 0 };
        if (this.form.mode === 'advance') return { lines, advance: amt };
        const targets = this.form.mode === 'specific' ? (this.selected ? [this.selected] : []) : this.dues;
        let left = amt;
        for (const p of targets) {
          if (left <= 0) break;
          const due = n(p.due_amount), take = r2(Math.min(left, due));
          if (take <= 0) continue;
          lines.push({ id: p.id, invoice: p.invoice_no, due, take, clears: take >= due });
          left = r2(left - take);
        }
        return { lines, advance: this.form.mode === 'specific' ? 0 : left };
      },

      get accounts() {
        const m = METHODS.find(x => x.value === this.form.method);
        return this.accountsAll.filter(a => same(a.ac_type, m ? m.ac : this.form.method))
          .map(a => ({ value: String(a.id), label: a.name, sub: 'Balance ' + App.taka(a.balance) }));
      },
      get account() { return this.accountsAll.find(a => String(a.id) === String(this.form.account)) || null; },
      pickAccount() {
        const list = this.accounts;
        if (!list.some(a => a.value === this.form.account)) this.form.account = list.length ? list[0].value : '';
      },
      get shortBy() { const a = this.account; return a && this.cashPart > n(a.balance) ? r2(this.cashPart - n(a.balance)) : 0; },

      fill(v) { this.form.amount = n(v).toFixed(2); this.errors.amount = ''; },
      validate() {
        const e = {};
        if (!this.form.supplier) e.supplier = 'Choose who you are paying.';
        if (this.form.mode === 'specific' && !this.form.purchase) e.purchase = 'Choose the invoice you are paying.';
        if (!(this.amountNum > 0)) e.amount = 'Enter an amount greater than 0.';
        else if (this.form.mode === 'specific' && this.selected && this.amountNum > n(this.selected.due_amount))
          e.amount = `This invoice has only ${App.taka(this.selected.due_amount)} due.`;
        if (!this.form.date) e.date = 'Pick the payment date.';
        else if (this.form.date > this.maxDate) e.date = 'The date cannot be in the future.';
        if (!this.form.account) e.account = this.accounts.length ? 'Choose the account the money comes from.'
          : 'There is no active account for this payment method.';
        else if (this.shortBy > 0) e.account = `This account has only ${App.taka(this.account.balance)}.`;
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
          supplier: Number(this.form.supplier),
          account: Number(this.form.account),
          amount: this.amountNum.toFixed(2),
          payment_method: this.form.method,
          payment_date: this.form.date,
          payment_type: this.form.mode,
          reference_no: this.form.reference.trim() || null,
          description: this.form.note.trim() || null,
          use_advance: this.advPart > 0,
          advance_amount_used: this.advPart.toFixed(2),
        };
        if (this.form.mode === 'specific') body.purchase = Number(this.form.purchase);
        try {
          const r = await App.api('/api/supplier-payments/', { method: 'POST', body });
          this.done = r.data;
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (e) { this.serverError = e.message || explain(e); }
        this.saving = false;
      },
      again() {
        this.done = null;
        Object.assign(this.form, { supplier: '', purchase: '', amount: '', mode: 'overall', useAdvance: false, reference: '', note: '', date: iso(today()) });
        this.dues = []; this.errors = {};
        // account balance বদলেছে — নতুন করে আনি
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => { this.accountsAll = listOf(r).filter(a => a.is_active !== false); }).catch(() => {});
      },
      cashOf: (p) => n(p.amount) - n(p.advance_amount_used),
      taka: (v) => App.taka(v),
      words: (v) => App.takaWords(v),
      round2: r2,
    };
  };
})();
