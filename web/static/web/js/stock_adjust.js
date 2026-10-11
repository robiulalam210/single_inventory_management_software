/*
 * Stock Adjustment — এক পণ্যের স্টক হাতে ঠিক করা + ইতিহাস।
 *   POST /api/stock/adjustments/   {product_id, new_qty | change, reason, note}
 *   GET  /api/stock/adjustments/   ?q=&reason=&page=
 * স্টক পুরো সংখ্যায় রাখা হয়, তাই দশমিক নেওয়া হয় না। "Set new quantity" = গুনে পাওয়া মোট; "Add / remove" = +/−।
 */
(function () {
  'use strict';

  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const fmtDateTime = (s) => {
    const d = new Date(s);
    return isNaN(d) ? '' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) + ', ' +
      d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  };
  // "Stock count" নিজে হাতে বাছা যায় না — সেটা শুধু Stocktake এর
  const MANUAL = [
    { key: 'damaged', label: 'Damaged' }, { key: 'expired', label: 'Expired' }, { key: 'lost', label: 'Lost / stolen' },
    { key: 'found', label: 'Found / extra' }, { key: 'correction', label: 'Entry mistake' },
    { key: 'opening', label: 'Opening stock' }, { key: 'other', label: 'Other' },
  ];

  window.stockAdjust = function (opts) {
    return {
      canEdit: !!(opts && opts.canEdit),
      // form
      pq: '', results: [], hi: 0, showResults: false, searching: false, _sreq: 0, _st: null, _enterPending: false,
      product: null, mode: 'set', qty: '', reason: '', note: '',
      errors: {}, serverError: '', saving: false,
      // history
      f: { q: '', reason: '' }, page: 1, hist: null, rows: [], loading: true, error: '', toast: '', _t: null, _toast: null,

      get reasonList() { return MANUAL; },
      get filterReasons() { return MANUAL.concat([{ key: 'count', label: 'Stock count' }]); },

      init() {
        this.fetch();
        this.$watch('pq', (v) => {
          clearTimeout(this._st);
          if (!v.trim()) { this.results = []; this.searching = false; return; }
          this.searching = true;
          this._st = setTimeout(() => this.search(v.trim()), 220);
        });
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => { this.page = 1; this.fetch(); }, 350); });
        this.$watch('f.reason', () => { this.page = 1; this.fetch(); });
      },

      // ───── product search (Purchase form এর মতোই) ─────
      async search(q) {
        const id = ++this._sreq;
        try {
          const r = await App.api('/api/products/', { query: { search: q, is_active: 'true', page_size: 12 } });
          if (id !== this._sreq) return;
          this.results = listOf(r).map(p => ({
            id: p.id, name: p.name, sku: p.sku || '', category: (p.category_info && p.category_info.name) || p.category_name || '',
            stock: n(p.stock_qty), cost: n(p.purchase_price),
          }));
          this.hi = 0;
          this.showResults = true;
          if (this._enterPending) {
            this._enterPending = false;
            const exact = this.results.find(x => same(x.sku, q));
            if (exact) this.pick(exact); else if (this.results.length === 1) this.pick(this.results[0]);
          }
        } catch (e) { if (id === this._sreq) this.results = []; }
        if (id === this._sreq) this.searching = false;
      },
      searchEnter() {
        if (this.searching) { this._enterPending = true; return; }
        const exact = this.results.find(x => same(x.sku, this.pq.trim()));
        const pick = exact || this.results[this.hi];
        if (pick) this.pick(pick);
      },
      move(d) {
        const len = this.results.length;
        if (!len) return;
        this.hi = (this.hi + d + len) % len;
        this.$nextTick(() => { const el = this.$refs.results && this.$refs.results.children[this.hi]; if (el) el.scrollIntoView({ block: 'nearest' }); });
      },
      pick(p) {
        this.product = p;
        this.errors = {};
        this.serverError = '';
        this.pq = ''; this.results = []; this.showResults = false;
        this.qty = this.mode === 'set' ? String(p.stock) : '';
        this.$nextTick(() => { const el = this.$refs.qty; if (el) { el.focus(); el.select(); } });
      },
      clearProduct() {
        this.product = null; this.qty = ''; this.errors = {}; this.serverError = '';
        this.$nextTick(() => this.$refs.pq && this.$refs.pq.focus());
      },
      setMode(m) {
        this.mode = m;
        this.qty = m === 'set' && this.product ? String(this.product.stock) : '';
        this.errors = {};
      },
      bump(d) { this.qty = String(n(this.qty) + d); this.errors.qty = ''; },

      // ───── preview ─────
      get change() {
        if (!this.product || this.qty === '' || this.qty === '-' || this.qty === '+') return null;
        const v = Math.trunc(n(this.qty));
        return this.mode === 'set' ? v - this.product.stock : v;
      },
      get after() { return this.change === null ? null : this.product.stock + this.change; },
      get diff() { return this.change; },

      // ───── save ─────
      validate() {
        const e = {};
        if (!this.product) e.product = 'Choose the product to adjust.';
        else if (this.change === null) e.qty = this.mode === 'set' ? 'Enter the quantity you counted.' : 'Enter how many to add or remove.';
        else if (this.change === 0) e.qty = 'That is the same as the current stock.';
        else if (this.after < 0) e.qty = 'Only ' + this.product.stock + ' in stock — you can\'t remove more than that.';
        if (!this.reason) e.reason = 'Pick the reason.';
        this.errors = e;
        return !Object.keys(e).length;
      },
      async save() {
        this.serverError = '';
        if (!this.validate() || this.saving) return;
        this.saving = true;
        try {
          const r = await App.api('/api/stock/adjustments/', {
            method: 'POST',
            body: { product_id: this.product.id, new_qty: this.mode === 'set' ? this.after : undefined,
                    change: this.mode === 'change' ? this.change : undefined, reason: this.reason, note: this.note.trim() },
          });
          this.say(r.message || 'Stock adjusted');
          this.product = null; this.qty = ''; this.reason = ''; this.note = '';
          this.page = 1;
          await this.fetch();
          this.$nextTick(() => this.$refs.pq && this.$refs.pq.focus());
        } catch (e) { this.serverError = e.message; }
        this.saving = false;
      },

      // ───── history ─────
      async fetch() {
        this.loading = true; this.error = '';
        try {
          const r = await App.api('/api/stock/adjustments/', { query: { q: this.f.q.trim(), reason: this.f.reason, page: this.page } });
          this.hist = r.data; this.rows = r.data.results || [];
        } catch (e) { this.error = e.message; this.rows = []; }
        this.loading = false;
      },
      go(p) { this.page = p; this.fetch(); },
      say(t) { this.toast = t; clearTimeout(this._toast); this._toast = setTimeout(() => { this.toast = ''; }, 2800); },

      taka: (v) => App.taka(v),
      num: (v) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(n(v)),
      dateTime: fmtDateTime,
    };
  };
})();
