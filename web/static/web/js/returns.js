/*
 * Returns — Sales Return (salesReturnList, salesReturnForm)।
 *   তালিকা:  GET /api/sales-returns/ (page, page_size, search, start_date, end_date, status)
 *   কাজ:     POST /api/sales-returns/<id>/approve|reject|complete/  ·  DELETE /api/sales-returns/<id>/
 *   নতুন:    POST /api/sales-returns/ — invoice বাছলে /api/sale-invoice/ থেকে পণ্য আসে
 *   নিয়ম app এর হুবহু: pending → approved → completed; pending/rejected মোছা যায়।
 */
(function () {
  'use strict';

  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const n = (v) => Number(v || 0);
  const round2 = (v) => Math.round(v * 100) / 100;
  const PAGE_SIZE = 30;
  const fmtDate = (s) => s ? new Date(String(s).length <= 10 ? s + 'T00:00' : s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
  const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const cap = (s) => s ? s.charAt(0).toUpperCase() + s.slice(1) : '—';

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

  // ─────────────────────────────── list (sales + purchase) ───────────────────────────────
  const KINDS = {
    sales: {
      api: '/api/sales-returns/', partyApi: '/api/customers-active/', partyParam: 'customer_id',
      noKey: 'receipt_no', walkIn: 'Walk-in customer', hasDamage: true,
      approveBody: 'Approving puts the returned stock back and records the refund to the customer. Check the quantities first.',
    },
    purchase: {
      api: '/api/purchase-returns/', partyApi: '/api/suppliers-active/', partyParam: 'supplier_id',
      noKey: 'invoice_no', walkIn: 'Unknown supplier', hasDamage: false,
      approveBody: 'Approving takes the returned stock out and records the refund coming from the supplier. Check the quantities first.',
    },
  };

  window.returnList = function (opts) {
    const cfg = KINDS[opts.kind];
    return {
      cfg,
      presets: [
        { key: 'today', label: 'Today' }, { key: '7d', label: 'Last 7 days' },
        { key: 'month', label: 'This month' }, { key: 'all', label: 'All time' }, { key: 'custom', label: 'Custom' },
      ],
      statuses: [
        { key: '', label: 'All' }, { key: 'pending', label: 'Pending' }, { key: 'approved', label: 'Approved' },
        { key: 'completed', label: 'Completed' }, { key: 'rejected', label: 'Rejected' },
      ],
      f: { q: '', status: '', party: '', preset: 'all', from: '', to: '' },
      parties: [], partyNames: {},
      page: 1, rows: [], meta: { count: 0, total_pages: 1 },
      loading: true, error: null, sel: null,
      canUpdate: !!opts.canUpdate, canDelete: !!opts.canDelete,
      confirm: null, working: false, confirmError: '',
      toast: '', _req: 0, _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || '';
        this.f.status = p.get('status') || '';
        this.f.party = p.get('party') || '';
        this.f.preset = p.get('period') || 'all';
        this.f.from = p.get('from') || '';
        this.f.to = p.get('to') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        if (this.f.preset !== 'custom') [this.f.from, this.f.to] = rangeOf(this.f.preset);

        App.api(cfg.partyApi).then(r => {
          const list = listOf(r);
          this.partyNames = Object.fromEntries(list.map(c => [String(c.id), c.name]));
          this.parties = list.map(c => ({ value: String(c.id), label: c.name, sub: c.phone || '' }));
        }).catch(() => {});
        this.fetch();
        if (p.get('saved')) this.flash('Return saved.');
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 350); });
        ['f.status', 'f.party'].forEach(k => this.$watch(k, () => this.reset()));
      },

      setPreset(key) { this.f.preset = key; if (key !== 'custom') { [this.f.from, this.f.to] = rangeOf(key); this.reset(); } },
      applyCustom() { if (this.f.from && this.f.to && this.f.from > this.f.to) [this.f.from, this.f.to] = [this.f.to, this.f.from]; this.reset(); },
      clearAll() { this.f = { q: '', status: '', party: '', preset: 'all', from: '', to: '' }; this.reset(); },
      get filtered() { const f = this.f; return !!(f.q || f.status || f.party || f.preset !== 'all'); },
      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.meta.total_pages || p === this.page) return;
        this.page = p; this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },

      syncUrl() {
        const p = new URLSearchParams(), f = this.f;
        if (f.q) p.set('q', f.q);
        if (f.status) p.set('status', f.status);
        if (f.party) p.set('party', f.party);
        if (f.preset !== 'all') p.set('period', f.preset);
        if (f.preset === 'custom') { if (f.from) p.set('from', f.from); if (f.to) p.set('to', f.to); }
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },

      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null; this.syncUrl();
        const query = { page: this.page, page_size: PAGE_SIZE, search: this.f.q.trim(), status: this.f.status,
          start_date: this.f.from, end_date: this.f.to };
        query[cfg.partyParam] = this.f.party;
        try {
          const r = await App.api(cfg.api, { query });
          if (id !== this._req) return;
          const d = r.data || {};
          let rows = Array.isArray(d) ? d : (d.results || []);
          // server ও status filter করে; না করলেও এই page এ ভুল অবস্থার সারি দেখাই না
          if (this.f.status) rows = rows.filter(x => x.status === this.f.status);
          this.rows = rows;
          this.meta = { count: d.count != null ? d.count : rows.length, total_pages: d.total_pages || 1 };
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = [];
        }
        this.loading = false;
      },

      // ───── helpers ─────
      taka: (v) => App.taka(v),
      num: (v) => new Intl.NumberFormat('en-US').format(n(v)),
      date: fmtDate, cap,
      no: (r) => r[cfg.noKey] || ('#' + r.id),
      partyName(r) {
        if (opts.kind === 'sales') return r.customer_name || cfg.walkIn;
        const s = r.supplier_name || (r.supplier && typeof r.supplier === 'object' ? r.supplier.name : r.supplier);
        if (s != null && s !== '' && this.partyNames[String(s)]) return this.partyNames[String(s)];
        return (s != null && s !== '' && isNaN(Number(s)) ? s : '') || (r.supplier_id && this.partyNames[String(r.supplier_id)]) || cfg.walkIn;
      },
      itemCount: (r) => (r.items || []).length,
      accountOf: (r) => (r.account && r.account.name) || r.account_name || '',
      get from() { return this.meta.count ? (this.page - 1) * PAGE_SIZE + 1 : 0; },
      get to() { return Math.min(this.page * PAGE_SIZE, this.meta.count); },
      get pages() { return pagesOf(this.page, this.meta.total_pages); },
      canDeleteRow(r) { return this.canDelete && (r.status === 'pending' || r.status === 'rejected'); },

      // ───── detail drawer ─────
      async open(r) {
        this.sel = r; document.body.style.overflow = 'hidden';
        try { const d = await App.api(`${cfg.api}${r.id}/`); if (this.sel && this.sel.id === r.id && d.data) this.sel = d.data; } catch (e) { /* তালিকার data দিয়েই চলে */ }
      },
      shut() { this.sel = null; document.body.style.overflow = ''; },

      // ───── approve / reject / complete / delete ─────
      ask(kind, row) { this.confirm = { kind, row }; this.confirmError = ''; },
      get confirmText() {
        const c = this.confirm; if (!c) return null;
        const no = this.no(c.row);
        return {
          approve: { title: `Approve return ${no}?`, body: cfg.approveBody, btn: 'Approve', danger: false },
          reject: { title: `Reject return ${no}?`, body: 'The return is turned down. Nothing changes in stock or accounts. A rejected return can be deleted later.', btn: 'Reject', danger: true },
          complete: { title: `Mark return ${no} as completed?`, body: 'Use this once the whole return is settled.', btn: 'Mark completed', danger: false },
          delete: { title: `Delete return ${no}?`, body: 'Only pending or rejected returns can be deleted. This cannot be undone.', btn: 'Delete', danger: true },
        }[c.kind];
      },
      async runConfirm() {
        const c = this.confirm; if (!c || this.working) return;
        this.working = true; this.confirmError = '';
        const base = `${cfg.api}${c.row.id}/`;
        try {
          if (c.kind === 'delete') await App.api(base, { method: 'DELETE' });
          else await App.api(base + c.kind + '/', { method: 'POST', body: {} });
          const done = { approve: 'approved', reject: 'rejected', complete: 'marked completed', delete: 'deleted' }[c.kind];
          const no = this.no(c.row);
          this.confirm = null; this.shut();
          this.flash(`Return ${no} ${done}.`);
          this.fetch();
        } catch (e) { this.confirmError = e.message; }
        this.working = false;
      },
      flash(msg) { this.toast = msg; clearTimeout(this._toast); this._toast = setTimeout(() => { this.toast = ''; }, 3500); },
      print() { window.print(); },
    };
  };

  // ─────────────────────────────── new sales return ───────────────────────────────
  window.salesReturnForm = function (init) {
    return {
      invoicesAll: [],            // /api/sale-invoice/ — পণ্য সহ
      accountsAll: [],
      methods: [
        { value: 'cash', label: 'Cash' }, { value: 'bank', label: 'Bank' }, { value: 'mobile', label: 'Mobile' },
        { value: 'card', label: 'Card' }, { value: 'credit', label: 'Credit' },
      ],
      chargeTypes: [{ value: 'fixed', label: '৳ Fixed' }, { value: 'percentage', label: '% Percent' }],
      canSeeList: !!init.canSeeList,
      canApprove: !!init.canApprove,
      loading: true,
      form: { invoice: '', date: iso(today()), method: 'cash', account: '', charge: '', chargeType: 'fixed', reason: '', autoApprove: false },
      lines: [],                  // { productId, name, price, discount, discountType, max, qty, damage }
      maxDate: iso(today()),
      errors: {}, saving: false, serverError: '', done: null,

      init() {
        Promise.all([
          App.api('/api/sale-invoice/', { query: { no_pagination: 'true', page_size: 500 } }),
          App.api('/api/accounts/', { query: { no_pagination: 'true' } }),
        ]).then(([inv, acc]) => {
          this.invoicesAll = listOf(inv);
          this.accountsAll = listOf(acc).filter(a => a.is_active !== false);
          this.pickAccount();
          if (init.invoice) this.form.invoice = String(init.invoice);
          this.loading = false;
        }).catch(e => { this.serverError = 'Could not load invoices: ' + e.message; this.loading = false; });

        this.$watch('form.invoice', () => this.loadInvoice());
        this.$watch('form.method', () => this.pickAccount());
        this.$watch('form.chargeType', () => { this.errors.charge = ''; });
      },

      get invoiceOptions() {
        return this.invoicesAll.map(s => ({
          value: String(s.id), label: s.invoice_no || ('#' + s.id),
          sub: (s.customer_name || 'Walk-in') + (s.sale_date ? ', ' + fmtDate(s.sale_date) : ''),
        }));
      },
      get invoice() { return this.invoicesAll.find(s => String(s.id) === String(this.form.invoice)) || null; },
      get customerName() { return this.invoice ? (this.invoice.customer_name || 'Walk-in customer') : ''; },

      // account কে payment method এর সাথে মেলাই; না মিললে সব active account দেখাই (app এও সব দেখায়)
      get accounts() {
        const exact = this.accountsAll.filter(a => same(a.ac_type, this.form.method));
        return (exact.length ? exact : this.accountsAll).map(a => ({ value: String(a.id), label: a.name, sub: a.ac_number || a.bank_name || a.ac_type || '' }));
      },
      pickAccount() {
        const list = this.accounts;
        if (!list.some(a => a.value === this.form.account)) this.form.account = list.length ? list[0].value : '';
      },

      loadInvoice() {
        this.errors = {};
        const s = this.invoice;
        this.lines = s ? (s.items || []).map(it => ({
          productId: it.product_id || it.id, name: it.product_name || 'Unknown product',
          price: n(it.unit_price), discount: n(it.discount), discountType: it.discount_type || 'fixed',
          max: n(it.quantity), qty: n(it.quantity), damage: 0,
        })) : [];
      },

      lineTotal(l) {
        let t = l.price * l.qty;
        t = l.discountType === 'percentage' ? t - t * l.discount / 100 : t - l.discount;
        return round2(Math.max(0, t));
      },
      setQty(l, v) {
        v = Math.floor(n(v));
        l.qty = Math.min(Math.max(v, 0), l.max);
        if (l.damage > l.qty) l.damage = l.qty;
      },
      setDamage(l, v) { l.damage = Math.min(Math.max(Math.floor(n(v)), 0), l.qty); },
      remove(i) { this.lines.splice(i, 1); },

      get subtotal() { return round2(this.lines.reduce((s, l) => s + this.lineTotal(l), 0)); },
      get chargeAmount() {
        const c = n(String(this.form.charge).replace(/,/g, ''));
        return round2(this.form.chargeType === 'percentage' ? this.subtotal * c / 100 : c);
      },
      // app এর হিসাব: মোট = subtotal + return charge
      get total() { return round2(this.subtotal + this.chargeAmount); },

      validate() {
        const e = {};
        if (!this.form.invoice) e.invoice = 'Choose the invoice being returned.';
        if (this.invoice && !this.lines.length) e.items = 'Add at least one product to return.';
        else if (this.lines.length && this.lines.every(l => l.qty <= 0)) e.items = 'Set a return quantity above 0 for at least one product.';
        if (!this.form.date) e.date = 'Pick the return date.';
        else if (this.form.date > this.maxDate) e.date = 'The date cannot be in the future.';
        if (!this.form.account) e.account = 'Choose the account for this refund.';
        if (n(this.form.charge) < 0) e.charge = 'Return charge cannot be negative.';
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
        const items = this.lines.filter(l => l.qty > 0).map(l => ({
          product_id: l.productId, product_name: l.name, quantity: l.qty, damage_quantity: l.damage,
          unit_price: l.price, discount: l.discount, discount_type: l.discountType, total: this.lineTotal(l),
        }));
        const body = {
          receipt_no: this.invoice.invoice_no,
          customer_name: this.customerName,
          return_date: this.form.date,
          account_id: Number(this.form.account),
          payment_method: this.form.method,
          reason: this.form.reason.trim(),
          return_charge: n(this.form.charge),
          return_charge_type: this.form.chargeType,
          return_amount: this.total,
          auto_approve: this.canApprove && !!this.form.autoApprove,
          items,
        };
        try {
          const r = await App.api('/api/sales-returns/', { method: 'POST', body });
          this.done = Object.assign({ total: this.total }, r.data);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (e) { this.serverError = explain(e); }
        this.saving = false;
      },

      again() {
        const keep = { method: this.form.method, account: this.form.account };
        this.done = null;
        this.form = Object.assign(this.form, { invoice: '', date: iso(today()), charge: '', chargeType: 'fixed', reason: '', autoApprove: false }, keep);
        this.lines = []; this.errors = {};
      },

      taka: (v) => App.taka(v), words: (v) => App.takaWords(v), date: fmtDate, round2,
    };
  };

  // ─────────────────────────────── new purchase return ───────────────────────────────
  window.purchaseReturnForm = function (init) {
    return {
      suppliers: [], supplierRows: {},
      invoicesAll: [], invoicesLoading: false,
      accountsAll: [],
      methods: [{ value: 'Cash', label: 'Cash' }, { value: 'Bank', label: 'Bank' }, { value: 'Mobile banking', label: 'Mobile banking' }],
      chargeTypes: [{ value: 'fixed', label: '৳ Fixed' }, { value: 'percentage', label: '% Percent' }],
      canSeeList: !!init.canSeeList,
      form: { supplier: '', invoice: '', date: iso(today()), method: 'Cash', account: '', charge: '', chargeType: 'fixed', reason: '' },
      lines: [],
      maxDate: iso(today()),
      errors: {}, saving: false, serverError: '', done: null,

      init() {
        App.api('/api/suppliers-active/').then(r => {
          const list = listOf(r);
          this.supplierRows = Object.fromEntries(list.map(c => [String(c.id), c]));
          this.suppliers = list.map(c => ({ value: String(c.id), label: c.name, sub: c.phone || '' }));
        }).catch(e => { this.serverError = 'Could not load suppliers: ' + e.message; });
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => {
          this.accountsAll = listOf(r).filter(a => a.is_active !== false);
          this.pickAccount();
        }).catch(() => {});
        this.$watch('form.supplier', () => this.loadInvoices());
        this.$watch('form.invoice', () => this.loadLines());
        this.$watch('form.method', () => this.pickAccount());
      },

      async loadInvoices() {
        const id = this.form.supplier;
        this.form.invoice = ''; this.invoicesAll = []; this.lines = []; this.errors = {};
        if (!id) return;
        this.invoicesLoading = true;
        try {
          const r = await App.api(`/api/purchases-invoice/supplier/${id}/`);
          if (this.form.supplier !== id) return;
          this.invoicesAll = listOf(r).filter(p => p.payment_status !== 'cancelled');
        } catch (e) { this.serverError = 'Could not load invoices: ' + e.message; }
        this.invoicesLoading = false;
      },
      get invoiceOptions() {
        return this.invoicesAll.map(p => ({
          value: String(p.id), label: p.invoice_no || ('#' + p.id),
          sub: (p.purchase_date ? fmtDate(p.purchase_date) + ', ' : '') + App.taka(p.grand_total),
        }));
      },
      get invoice() { return this.invoicesAll.find(p => String(p.id) === String(this.form.invoice)) || null; },
      get supplier() { return this.supplierRows[this.form.supplier] || null; },

      loadLines() {
        this.errors = {};
        const p = this.invoice;
        this.lines = p ? (p.items || []).map(it => ({
          // product এর id: নতুন `product` field; পুরনো backend এ product_id, না থাকলে item id (app এর মতো)
          productId: it.product != null ? it.product : (it.product_id != null ? it.product_id : it.id),
          name: it.product_name || 'Unknown product',
          price: n(String(it.price).replace(/,/g, '')), discount: n(String(it.discount || 0).replace(/,/g, '')),
          discountType: it.discount_type || 'fixed',
          max: n(it.qty), qty: n(it.qty),
        })) : [];
      },

      get accounts() {
        return this.accountsAll
          .filter(a => same(a.ac_type, this.form.method) || (same(this.form.method, 'Mobile banking') && same(a.ac_type, 'mobile')))
          .map(a => ({ value: String(a.id), label: a.name, sub: a.ac_number || a.bank_name || '' }));
      },
      pickAccount() {
        const list = this.accounts;
        if (!list.some(a => a.value === this.form.account)) this.form.account = list.length ? list[0].value : '';
      },

      lineTotal(l) {
        let t = l.price * l.qty;
        t = l.discountType === 'percentage' ? t - t * l.discount / 100 : t - l.discount;
        return round2(Math.max(0, t));
      },
      setQty(l, v) { l.qty = Math.min(Math.max(Math.floor(n(v)), 0), l.max); },
      remove(i) { this.lines.splice(i, 1); },

      get subtotal() { return round2(this.lines.reduce((s, l) => s + this.lineTotal(l), 0)); },
      get chargeAmount() {
        const c = n(String(this.form.charge).replace(/,/g, ''));
        return round2(this.form.chargeType === 'percentage' ? this.subtotal * c / 100 : c);
      },
      // app এর হিসাব: supplier এর কাছ থেকে ফেরত = পণ্যের মোট − return charge
      get total() { return round2(Math.max(0, this.subtotal - this.chargeAmount)); },

      validate() {
        const e = {};
        if (!this.form.supplier) e.supplier = 'Choose the supplier.';
        else if (!this.form.invoice) e.invoice = this.invoicesAll.length ? 'Choose the purchase invoice.' : 'This supplier has no invoices to return against.';
        if (this.invoice && (!this.lines.length || this.lines.every(l => l.qty <= 0))) e.items = 'Set a return quantity above 0 for at least one product.';
        if (!this.form.date) e.date = 'Pick the return date.';
        else if (this.form.date > this.maxDate) e.date = 'The date cannot be in the future.';
        if (!this.form.account) e.account = this.accounts.length ? 'Choose the account the refund goes into.'
          : `There is no active ${this.form.method} account. Add one in Accounts first.`;
        if (this.chargeAmount > this.subtotal) e.charge = 'Return charge cannot be more than the goods total.';
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
          supplier_id: String(this.form.supplier),
          invoice_no: this.invoice.invoice_no,
          return_date: this.form.date,
          return_charge: String(n(this.form.charge)),
          return_charge_type: this.form.chargeType,
          return_amount: this.total.toFixed(2),
          account_id: Number(this.form.account),
          payment_method: this.form.method,
          reason: this.form.reason.trim(),
          items: this.lines.filter(l => l.qty > 0).map(l => ({
            product_id: l.productId, quantity: l.qty, unit_price: String(l.price),
            discount: String(l.discount), discount_type: l.discountType,
          })),
        };
        try {
          const r = await App.api('/api/purchase-returns/', { method: 'POST', body });
          this.done = Object.assign({ total: this.total, invoice_no: body.invoice_no }, r.data);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (e) { this.serverError = explain(e); }
        this.saving = false;
      },

      again() {
        const keep = { method: this.form.method, account: this.form.account };
        this.done = null;
        this.form = Object.assign(this.form, { supplier: '', invoice: '', date: iso(today()), charge: '', chargeType: 'fixed', reason: '' }, keep);
        this.lines = []; this.invoicesAll = []; this.errors = {};
      },

      taka: (v) => App.taka(v), date: fmtDate, round2,
    };
  };

  // ─────────────────────────────── bad stock ───────────────────────────────
  window.badStockList = function () {
    return {
      f: { q: '', from: '', to: '' },
      page: 1, rows: [], meta: { count: 0, total_pages: 1 },
      loading: true, error: null, sel: null, _req: 0, _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || ''; this.f.from = p.get('from') || ''; this.f.to = p.get('to') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        this.fetch();
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 350); });
      },
      applyDates() { if (this.f.from && this.f.to && this.f.from > this.f.to) [this.f.from, this.f.to] = [this.f.to, this.f.from]; this.reset(); },
      get filtered() { return !!(this.f.q || this.f.from || this.f.to); },
      clearAll() { this.f = { q: '', from: '', to: '' }; this.reset(); },
      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.meta.total_pages || p === this.page) return;
        this.page = p; this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },
      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null;
        const sp = new URLSearchParams();
        if (this.f.q) sp.set('q', this.f.q);
        if (this.f.from) sp.set('from', this.f.from);
        if (this.f.to) sp.set('to', this.f.to);
        if (this.page > 1) sp.set('page', this.page);
        history.replaceState(null, '', location.pathname + (sp.toString() ? '?' + sp : ''));
        try {
          const r = await App.api('/api/bad-stocks/', { query: { page: this.page, page_size: PAGE_SIZE, search: this.f.q.trim(), from: this.f.from, to: this.f.to } });
          if (id !== this._req) return;
          const d = r.data || {};
          const rows = Array.isArray(d) ? d : (d.results || []);
          this.rows = rows;
          this.meta = { count: d.count != null ? d.count : rows.length, total_pages: d.total_pages || 1 };
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = [];
        }
        this.loading = false;
      },
      num: (v) => new Intl.NumberFormat('en-US').format(n(v)),
      date: fmtDate,
      ref: (r) => r.reference_type ? cap(String(r.reference_type).replace(/_/g, ' ')) + (r.reference_id ? ' #' + r.reference_id : '') : '—',
      get totalQty() { return this.rows.reduce((s, r) => s + n(r.quantity), 0); },
      get from() { return this.meta.count ? (this.page - 1) * PAGE_SIZE + 1 : 0; },
      get to() { return Math.min(this.page * PAGE_SIZE, this.meta.count); },
      get pages() { return pagesOf(this.page, this.meta.total_pages); },
    };
  };
})();
