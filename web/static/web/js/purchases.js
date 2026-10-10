/*
 * Purchase — তালিকা (purchaseList) আর নতুন কেনা (purchaseForm)।
 *   তালিকা: /api/purchases/ (প্রতি page এ ৩০) + /api/purchases/summary/ (একই filter এর মোট, বাতিল বাদে)
 *   নতুন:   POST /api/purchases/ — মোট হিসাব backend এর Purchase.update_totals() এর হুবহু একই নিয়মে আগেই দেখাই
 */
(function () {
  'use strict';

  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  // backend ROUND_HALF_UP এর মতো — 0.125 → 0.13
  const r2 = (v) => Math.round((n(v) + Number.EPSILON) * 100) / 100;
  const PAGE_SIZE = 30;
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const fmtDate = (s) => {
    if (!s) return '';
    const d = new Date(String(s).length === 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const fmtDateTime = (s) => {
    const d = new Date(s);
    return isNaN(d) ? '' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) + ', ' +
      d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  };
  const METHODS = [
    { value: 'Cash', label: 'Cash' },
    { value: 'Bank', label: 'Bank' },
    { value: 'Mobile banking', label: 'Mobile banking' },
  ];
  const STATUS = { paid: 'Paid', partial: 'Partial', pending: 'Unpaid', overdue: 'Overdue', cancelled: 'Cancelled' };

  function rangeOf(key) {
    const t = today();
    if (key === 'today') return [iso(t), iso(t)];
    if (key === '7d') { const s = new Date(t); s.setDate(s.getDate() - 6); return [iso(s), iso(t)]; }
    if (key === 'month') return [iso(new Date(t.getFullYear(), t.getMonth(), 1)), iso(t)];
    return ['', ''];
  }

  /*
   * Purchase.update_totals() এর হুবহু:
   *   item   = qty × price − ছাড় (percentage হলে লাইনের %, নইলে টাকা; লাইনের বেশি নয়)
   *   ছাড়   = percentage → subtotal এর %, fixed → subtotal এর বেশি নয়
   *   VAT / service / delivery = percentage → subtotal এর % (ছাড়ের আগের subtotal), fixed → সরাসরি
   *   total  = max(0, subtotal − ছাড়) + VAT + service + delivery
   */
  function lineTotal(qty, price, disc, type) {
    const gross = n(qty) * n(price);
    let off = type === 'percentage' ? gross * n(disc) / 100 : n(disc);
    off = Math.min(off, gross);
    return r2(Math.max(0, gross - off));
  }
  function charge(base, v, type) { return r2(type === 'percentage' ? base * n(v) / 100 : n(v)); }
  function totalsOf(subtotal, c) {
    const sub = r2(subtotal);
    const discount = c.discount_type === 'percentage' ? r2(sub * n(c.discount) / 100) : r2(Math.min(n(c.discount), sub));
    const vat = charge(sub, c.vat, c.vat_type);
    const service = charge(sub, c.service, c.service_type);
    const delivery = charge(sub, c.delivery, c.delivery_type);
    const grand = r2(Math.max(0, Math.max(0, sub - discount) + vat + service + delivery));
    return { sub, discount, vat, service, delivery, grand };
  }
  const pctTag = (v, type) => (type === 'percentage' && n(v) > 0 ? ` (${n(v)}%)` : '');

  // ─────────────────────────────── list ───────────────────────────────
  window.purchaseList = function (opts) {
    return {
      presets: [
        { key: 'today', label: 'Today' },
        { key: '7d', label: 'Last 7 days' },
        { key: 'month', label: 'This month' },
        { key: 'all', label: 'All time' },
        { key: 'custom', label: 'Custom' },
      ],
      statuses: [
        { key: '', label: 'All' },
        { key: 'paid', label: 'Paid' },
        { key: 'partial', label: 'Partial' },
        { key: 'pending', label: 'Unpaid' },
        { key: 'due', label: 'Has due' },
        { key: 'cancelled', label: 'Cancelled' },
      ],
      f: { q: '', status: '', supplier: '', preset: 'month', from: '', to: '' },
      page: 1,
      rows: [],
      meta: { count: 0, total_pages: 1 },
      sum: null,
      loading: true,
      error: null,
      sel: null,
      suppliers: [],
      canCancel: !!opts.canCancel,
      confirmCancel: false,
      cancelReason: '',
      cancelError: '',
      cancelling: false,
      toast: '',
      _req: 0,
      _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || '';
        this.f.status = p.get('status') || '';
        this.f.supplier = p.get('supplier') || '';
        this.f.preset = p.get('period') || 'month';
        this.f.from = p.get('from') || '';
        this.f.to = p.get('to') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        if (this.f.preset !== 'custom') [this.f.from, this.f.to] = rangeOf(this.f.preset);

        App.api('/api/suppliers-active/').then(r => {
          this.suppliers = listOf(r).map(s => ({ value: String(s.id), label: s.name, sub: s.phone || s.supplier_no || '' }));
        }).catch(() => {});
        this.fetch();

        const openId = parseInt(p.get('open') || '', 10);
        if (openId) App.api(`/api/purchases/${openId}/`).then(r => { if (r.data) this.open(r.data); }).catch(() => {});

        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 350); });
        ['f.status', 'f.supplier'].forEach(k => this.$watch(k, () => this.reset()));
      },

      setPreset(key) {
        this.f.preset = key;
        if (key !== 'custom') { [this.f.from, this.f.to] = rangeOf(key); this.reset(); }
      },
      applyCustom() {
        if (this.f.from && this.f.to && this.f.from > this.f.to) [this.f.from, this.f.to] = [this.f.to, this.f.from];
        this.reset();
      },
      clearAll() {
        this.f = { q: '', status: '', supplier: '', preset: 'month', from: '', to: '' };
        [this.f.from, this.f.to] = rangeOf('month');
        this.reset();
      },
      get filtered() { const f = this.f; return !!(f.q || f.status || f.supplier || f.preset !== 'month'); },

      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.meta.total_pages || p === this.page) return;
        this.page = p;
        this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },
      query() {
        const q = { search: this.f.q.trim(), supplier_id: this.f.supplier, start_date: this.f.from, end_date: this.f.to };
        if (this.f.status === 'due') q.due_only = 'true';
        else if (this.f.status) q.payment_status = this.f.status;
        return q;
      },
      syncUrl() {
        const p = new URLSearchParams();
        const f = this.f;
        if (f.q) p.set('q', f.q);
        if (f.status) p.set('status', f.status);
        if (f.supplier) p.set('supplier', f.supplier);
        if (f.preset !== 'month') p.set('period', f.preset);
        if (f.preset === 'custom') { if (f.from) p.set('from', f.from); if (f.to) p.set('to', f.to); }
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },
      async fetch() {
        const id = ++this._req;
        this.loading = true;
        this.error = null;
        this.syncUrl();
        const q = this.query();
        try {
          const [list, sum] = await Promise.all([
            App.api('/api/purchases/', { query: Object.assign({ page: this.page, page_size: PAGE_SIZE }, q) }),
            App.api('/api/purchases/summary/', { query: q }).catch(() => null),
          ]);
          if (id !== this._req) return;
          const d = list.data || {};
          this.rows = d.results || [];
          this.meta = { count: d.count || 0, total_pages: d.total_pages || 1 };
          this.sum = sum ? sum.data : null;
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message;
          this.rows = [];
        }
        this.loading = false;
      },

      // ───── display helpers ─────
      taka: (v) => App.taka(v),
      num: (v) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(n(v)),
      date: fmtDate,
      dateTime: fmtDateTime,
      statusLabel: (s) => STATUS[s] || s || '—',
      itemsText(r) {
        const c = n(r.item_count != null ? r.item_count : (r.items || []).length);
        const q = n(r.total_quantity);
        return `${c} ${c === 1 ? 'item' : 'items'}` + (q ? `, ${this.num(q)} pcs` : '');
      },
      payWith(r) {
        if (!n(r.paid_amount)) return 'Not paid yet';
        const parts = [r.payment_method, r.account_name].filter(Boolean);
        return parts.filter((v, i) => parts.findIndex(x => same(x, v)) === i).join(', ') || '—';
      },
      itemOff(it) {
        const d = n(it.discount);
        if (!d) return '';
        return it.discount_type === 'percentage' ? `${d}% off` : `${App.taka(d)} off`;
      },
      lines(r) {
        const sub = n(r.sub_total != null ? r.sub_total : r.total);
        const t = totalsOf(sub, {
          discount: r.overall_discount, discount_type: r.overall_discount_type,
          vat: r.vat, vat_type: r.vat_type,
          service: r.overall_service_charge, service_type: r.overall_service_charge_type,
          delivery: r.overall_delivery_charge, delivery_type: r.overall_delivery_charge_type,
        });
        return [
          ['Subtotal', t.sub],
          ['Discount' + pctTag(r.overall_discount, r.overall_discount_type), -t.discount],
          ['VAT' + pctTag(r.vat, r.vat_type), t.vat],
          ['Service charge' + pctTag(r.overall_service_charge, r.overall_service_charge_type), t.service],
          ['Delivery charge' + pctTag(r.overall_delivery_charge, r.overall_delivery_charge_type), t.delivery],
        ].filter(([, v], i) => i === 0 || v !== 0);
      },
      get from() { return this.meta.count ? (this.page - 1) * PAGE_SIZE + 1 : 0; },
      get to() { return Math.min(this.page * PAGE_SIZE, this.meta.count); },
      get pages() {
        const t = this.meta.total_pages, c = this.page, out = [];
        for (let i = 1; i <= t; i++) {
          if (i === 1 || i === t || Math.abs(i - c) <= 2) out.push(i);
          else if (out[out.length - 1] !== '…') out.push('…');
        }
        return out;
      },
      get periodText() {
        if (this.f.preset === 'all' || (!this.f.from && !this.f.to)) return 'All time';
        if (this.f.from === this.f.to) return fmtDate(this.f.from);
        return `${this.f.from ? fmtDate(this.f.from) : 'Start'} – ${this.f.to ? fmtDate(this.f.to) : 'today'}`;
      },

      // ───── drawer / cancel ─────
      open(r) { this.sel = r; document.body.style.overflow = 'hidden'; },
      shut() {
        this.sel = null;
        document.body.style.overflow = '';
        if (new URLSearchParams(location.search).has('open')) this.syncUrl();
      },
      print() { window.print(); },
      openCancel() { this.cancelReason = ''; this.cancelError = ''; this.confirmCancel = true; },
      async cancelPurchase() {
        if (!this.sel || this.cancelling) return;
        this.cancelling = true;
        this.cancelError = '';
        try {
          const r = await App.api(`/api/purchases/${this.sel.id}/cancel/`, {
            method: 'POST', body: { reason: this.cancelReason.trim() || 'Cancelled from web' },
          });
          this.confirmCancel = false;
          if (r.data) this.sel = r.data;
          this.flash(`${this.sel.invoice_no} cancelled. Stock and payment were reversed.`);
          this.fetch();
        } catch (e) {
          this.cancelError = e.message;
        }
        this.cancelling = false;
      },
      flash(msg) {
        this.toast = msg;
        clearTimeout(this._toast);
        this._toast = setTimeout(() => { this.toast = ''; }, 3500);
      },
    };
  };

  // ─────────────────────────────── new purchase ───────────────────────────────
  let rowSeq = 0;

  window.purchaseForm = function (init) {
    return {
      methods: METHODS,
      canSeeList: !!init.canSeeList,
      suppliers: [],
      supplierRows: {},
      accountsAll: [],
      form: {
        supplier: init.supplier ? String(init.supplier) : '',
        date: iso(today()),
        remark: '',
        discount: '', discount_type: 'fixed',
        vat: '', vat_type: 'percentage',
        service: '', service_type: 'fixed',
        delivery: '', delivery_type: 'fixed',
        payNow: false,
        paid: '',
        method: 'Cash',
        account: '',
      },
      maxDate: iso(today()),
      rows: [],
      // product search
      pq: '',
      results: [],
      searching: false,
      showResults: false,
      hi: 0,
      _st: null,
      _sreq: 0,
      errors: {},
      saving: false,
      serverError: '',
      done: null,

      init() {
        App.api('/api/suppliers-active/').then(r => {
          const list = listOf(r);
          this.supplierRows = Object.fromEntries(list.map(s => [String(s.id), s]));
          this.suppliers = list.map(s => ({
            value: String(s.id), label: s.name,
            sub: n(s.total_due) > 0 ? 'Due ' + App.taka(s.total_due) : (s.phone || ''),
          }));
        }).catch(() => {});
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => {
          this.accountsAll = listOf(r).filter(a => a.is_active !== false);
          this.pickAccount();
        }).catch(() => {});

        this.$watch('pq', (v) => {
          clearTimeout(this._st);
          if (!v.trim()) { this.results = []; this.searching = false; return; }
          this.searching = true;
          this._st = setTimeout(() => this.search(v.trim()), 220);
        });
        this.$watch('form.method', () => this.pickAccount());
        this.$watch('form.supplier', () => { this.errors.supplier = ''; });
        // "এখনই পরিশোধ" চালু করলে পুরো টাকাই বসাই; মোট বদলালে আর পুরোটা দেওয়ার ইচ্ছা থাকলে সাথে বদলাই
        this.$watch('form.payNow', (on) => { if (on && !n(this.form.paid)) this.form.paid = this.t.grand.toFixed(2); this.errors.paid = ''; });
        this.$watch('t.grand', (g, old) => { if (this.form.payNow && r2(this.form.paid) === r2(old)) this.form.paid = g.toFixed(2); });
      },

      // ───── product search ─────
      async search(q) {
        const id = ++this._sreq;
        try {
          const r = await App.api('/api/products/', { query: { search: q, is_active: 'true', page_size: 12 } });
          if (id !== this._sreq) return;
          this.results = listOf(r).map(p => ({
            id: p.id, name: p.name, sku: p.sku || '',
            stock: n(p.stock_qty), unit: (p.unit_info && (p.unit_info.code || p.unit_info.name)) || '',
            cost: n(p.purchase_price), sell: n(p.selling_price),
          }));
          this.hi = 0;
          this.showResults = true;
          // barcode scanner: হুবহু SKU মিললে আর একটাই ফল হলে সরাসরি যোগ
          if (this._enterPending) {
            this._enterPending = false;
            const exact = this.results.find(x => same(x.sku, q));
            if (exact) this.add(exact);
            else if (this.results.length === 1) this.add(this.results[0]);
          }
        } catch (e) {
          if (id === this._sreq) this.results = [];
        }
        if (id === this._sreq) this.searching = false;
      },
      searchEnter() {
        if (this.searching) { this._enterPending = true; return; }
        const exact = this.results.find(x => same(x.sku, this.pq.trim()));
        const pick = exact || this.results[this.hi];
        if (pick) this.add(pick);
      },
      move(d) {
        const len = this.results.length;
        if (!len) return;
        this.hi = (this.hi + d + len) % len;
        this.$nextTick(() => {
          const el = this.$refs.results && this.$refs.results.children[this.hi];
          if (el) el.scrollIntoView({ block: 'nearest' });
        });
      },
      add(p) {
        this.errors.items = '';
        const existing = this.rows.find(r => r.product_id === p.id);
        if (existing) {
          existing.qty = String(n(existing.qty) + 1);
          this.focusRow(existing.key);
        } else {
          const row = {
            key: ++rowSeq, product_id: p.id, name: p.name, sku: p.sku, stock: p.stock, unit: p.unit,
            // কেনার দাম — product এর purchase price; না থাকলে খালি (বিক্রির দাম বসালে লাভ ভুল দেখাত)
            qty: '1', price: p.cost > 0 ? String(p.cost) : '', lastCost: p.cost,
            discount: '', discount_type: 'fixed', err: '',
          };
          this.rows.push(row);
          this.focusRow(row.key);
        }
        this.pq = '';
        this.results = [];
        this.showResults = false;
      },
      focusRow(key) {
        this.$nextTick(() => {
          const el = document.querySelector(`[data-row="${key}"] .qty-in`);
          if (el) { el.focus(); el.select(); }
        });
      },
      remove(row) { this.rows = this.rows.filter(r => r.key !== row.key); },
      lineOf(row) { return lineTotal(row.qty, row.price, row.discount, row.discount_type); },
      backToSearch() { this.$refs.pq && this.$refs.pq.focus(); },

      // ───── totals ─────
      get t() {
        const sub = this.rows.reduce((s, r) => s + this.lineOf(r), 0);
        return totalsOf(sub, {
          discount: this.form.discount, discount_type: this.form.discount_type,
          vat: this.form.vat, vat_type: this.form.vat_type,
          service: this.form.service, service_type: this.form.service_type,
          delivery: this.form.delivery, delivery_type: this.form.delivery_type,
        });
      },
      get qtyTotal() { return this.rows.reduce((s, r) => s + n(r.qty), 0); },
      get paidNum() { return this.form.payNow ? r2(String(this.form.paid).replace(/,/g, '')) : 0; },
      get dueNum() { return r2(Math.max(0, this.t.grand - this.paidNum)); },
      get supplier() { return this.supplierRows[this.form.supplier] || null; },

      // ───── accounts ─────
      get accounts() {
        return this.accountsAll.filter(a => same(a.ac_type, this.form.method))
          .map(a => ({ value: String(a.id), label: a.name, sub: 'Balance ' + App.taka(a.balance) }));
      },
      get account() { return this.accountsAll.find(a => String(a.id) === String(this.form.account)) || null; },
      pickAccount() {
        const list = this.accounts;
        if (!list.some(a => a.value === this.form.account)) this.form.account = list.length ? list[0].value : '';
      },
      get shortBy() {
        const a = this.account;
        return a && this.paidNum > n(a.balance) ? r2(this.paidNum - n(a.balance)) : 0;
      },

      // ───── save ─────
      validate() {
        const e = {};
        if (!this.form.supplier) e.supplier = 'Choose the supplier you bought from.';
        if (!this.form.date) e.date = 'Pick the purchase date.';
        else if (this.form.date > this.maxDate) e.date = 'The date cannot be in the future.';
        if (!this.rows.length) e.items = 'Add at least one product.';
        this.rows.forEach(r => {
          const q = n(r.qty);
          if (!(q > 0) || !Number.isInteger(q)) r.err = 'Quantity must be a whole number above 0.';
          else if (!(n(r.price) > 0)) r.err = 'Enter the unit cost.';
          else if (r.discount_type === 'percentage' && n(r.discount) > 100) r.err = 'Discount cannot be more than 100%.';
          else r.err = '';
          if (r.err) e.items = e.items || 'Fix the highlighted rows.';
        });
        if (this.form.payNow) {
          if (!(this.paidNum > 0)) e.paid = 'Enter how much you are paying now.';
          else if (this.paidNum > this.t.grand) e.paid = 'You cannot pay more than the invoice total.';
          if (!this.form.account) e.account = this.accounts.length ? 'Choose the account the money comes from.'
            : `There is no active ${this.form.method} account.`;
          else if (this.shortBy > 0) e.account = `This account has only ${App.taka(this.account.balance)}.`;
        }
        this.errors = e;
        return !Object.keys(e).length;
      },
      payload() {
        const body = {
          supplier: Number(this.form.supplier),
          purchase_date: this.form.date,
          remark: this.form.remark.trim(),
          purchase_items: this.rows.map(r => ({
            product_id: r.product_id, qty: n(r.qty), price: r2(r.price).toFixed(2),
            discount: r2(r.discount).toFixed(2), discount_type: r.discount_type,
          })),
          overall_discount: r2(this.form.discount).toFixed(2), overall_discount_type: this.form.discount_type,
          vat: r2(this.form.vat).toFixed(2), vat_type: this.form.vat_type,
          overall_service_charge: r2(this.form.service).toFixed(2), overall_service_charge_type: this.form.service_type,
          overall_delivery_charge: r2(this.form.delivery).toFixed(2), overall_delivery_charge_type: this.form.delivery_type,
          instant_pay: this.form.payNow,
        };
        if (this.form.payNow) {
          body.paid_amount = this.paidNum.toFixed(2);
          body.payment_method = this.form.method;
          body.account_id = Number(this.form.account);
        }
        return body;
      },
      async save() {
        this.serverError = '';
        if (!this.validate() || this.saving) {
          this.$nextTick(() => {
            const el = this.$root.querySelector('.has-error, .row-err');
            if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
          });
          return;
        }
        this.saving = true;
        try {
          const r = await App.api('/api/purchases/', { method: 'POST', body: this.payload() });
          this.done = r.data;
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (e) {
          this.serverError = this.explain(e);
        }
        this.saving = false;
      },
      explain(e) {
        const d = e.data && e.data.data;
        if (d && typeof d === 'object') {
          const [k, v] = Object.entries(d)[0] || [];
          if (k) {
            let msg = Array.isArray(v) ? v[0] : v;
            if (msg && typeof msg === 'object') msg = Object.values(msg).flat()[0];
            const label = { paid_amount: 'Payment', purchase_items: 'Items', error: '', non_field_errors: '' }[k];
            return (label === undefined ? k.replace(/_/g, ' ') + ': ' : (label ? label + ': ' : '')) + msg;
          }
        }
        return e.message;
      },
      again() {
        this.done = null;
        this.rows = [];
        Object.assign(this.form, { supplier: '', remark: '', discount: '', vat: '', service: '', delivery: '', payNow: false, paid: '' });
        this.errors = {};
        this.$nextTick(() => this.backToSearch());
      },

      taka: (v) => App.taka(v),
      num: (v) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(n(v)),
      date: fmtDate,
    };
  };
})();
