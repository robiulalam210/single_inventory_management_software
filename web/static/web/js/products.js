/*
 * Products — তালিকা, যোগ/সম্পাদনা (ছবি সহ), barcode label।
 *   /api/products/ (প্রতি page এ ৩০; stock=in|low|out filter)
 *   /api/categories/ , /api/units/ , /api/brands/
 *   /api/reports/stock/ → মোট stock ও তার দাম (Reports অনুমতি থাকলে)
 */
(function () {
  'use strict';

  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const r2 = (v) => Math.round((n(v) + Number.EPSILON) * 100) / 100;
  const PAGE_SIZE = 30;
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const numFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function explain(e) {
    const d = e.data && e.data.data;
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const [k, v] = Object.entries(d)[0] || [];
      if (k) return (Array.isArray(v) ? v[0] : String(v));
    }
    return e.message;
  }

  window.productList = function (perms) {
    return {
      perms,
      sorts: [
        { key: 'name', label: 'Name' },
        { key: 'stock_qty', label: 'Lowest stock' },
        { key: '-created_at', label: 'Newest' },
        { key: '-selling_price', label: 'Price' },
      ],
      views: [
        { key: 'active', label: 'Active' },
        { key: 'low', label: 'Running low' },
        { key: 'out', label: 'Out of stock' },
        { key: 'inactive', label: 'Inactive' },
      ],
      f: { q: '', view: 'active', sort: 'name', category: '' },
      page: 1, rows: [], meta: { count: 0, total_pages: 1, from: 0, to: 0 },
      counts: {}, stockSum: null, loading: true, error: null,
      categories: [], units: [], brands: [],
      sel: null,
      formOpen: false, form: {}, fe: {}, formError: '', formSaving: false,
      qa: { open: false, kind: 'category', name: '', error: '', saving: false },
      labelOpen: false, label: { product: null, count: 12, price: true },
      confirmDel: false, delError: '', deleting: false,
      toast: '', _req: 0, _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || '';
        this.f.view = p.get('view') || 'active';
        this.f.sort = p.get('sort') || 'name';
        this.f.category = p.get('category') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        this.loadLookups();
        this.fetch();
        this.loadCounts();
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 300); });
        ['f.view', 'f.sort', 'f.category'].forEach(k => this.$watch(k, () => this.reset()));
      },
      loadLookups() {
        App.api('/api/categories/').then(r => { this.categories = listOf(r).filter(c => c.is_active !== false); }).catch(() => {});
        App.api('/api/units/').then(r => { this.units = listOf(r).filter(u => u.is_active !== false); }).catch(() => {});
        App.api('/api/brands/').then(r => { this.brands = listOf(r).filter(b => b.is_active !== false); }).catch(() => {});
      },
      get categoryOptions() { return this.categories.map(c => ({ value: String(c.id), label: c.name })); },
      get unitOptions() { return this.units.map(u => ({ value: String(u.id), label: u.name, sub: u.code || '' })); },
      get brandOptions() { return this.brands.map(b => ({ value: String(b.id), label: b.name })); },

      get filtered() { const f = this.f; return !!(f.q || f.view !== 'active' || f.sort !== 'name' || f.category); },
      clearAll() { this.f = { q: '', view: 'active', sort: 'name', category: '' }; this.reset(); },
      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.meta.total_pages || p === this.page) return;
        this.page = p; this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },
      query() {
        const q = { search: this.f.q.trim(), ordering: this.f.sort, page: this.page, page_size: PAGE_SIZE, category_id: this.f.category };
        if (this.f.view === 'inactive') q.is_active = 'false';
        else q.is_active = 'true';
        if (this.f.view === 'low' || this.f.view === 'out') q.stock = this.f.view;
        return q;
      },
      syncUrl() {
        const p = new URLSearchParams();
        if (this.f.q) p.set('q', this.f.q);
        if (this.f.view !== 'active') p.set('view', this.f.view);
        if (this.f.sort !== 'name') p.set('sort', this.f.sort);
        if (this.f.category) p.set('category', this.f.category);
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },
      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null; this.syncUrl();
        try {
          const r = await App.api('/api/products/', { query: this.query() });
          if (id !== this._req) return;
          const d = r.data || {};
          const pg = d.pagination || {};
          this.rows = d.results || [];
          this.meta = { count: pg.count || 0, total_pages: pg.total_pages || 1, from: pg.from || 0, to: pg.to || 0 };
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = [];
        }
        this.loading = false;
      },
      // প্রতিটা chip এর সংখ্যা — page_size=1 দিয়ে শুধু count আনা
      loadCounts() {
        const count = (q) => App.api('/api/products/', { query: Object.assign({ page_size: 1 }, q) })
          .then(r => n(r.data && r.data.pagination && r.data.pagination.count)).catch(() => null);
        Promise.all([
          count({ is_active: 'true' }), count({ is_active: 'true', stock: 'low' }),
          count({ is_active: 'true', stock: 'out' }), count({ is_active: 'false' }),
        ]).then(([active, low, out, inactive]) => { this.counts = { active, low, out, inactive }; });
        if (perms.reports) {
          App.api('/api/reports/stock/').then(r => { this.stockSum = r.data && r.data.summary; }).catch(() => {});
        }
      },

      get pages() {
        const t = this.meta.total_pages, c = this.page, out = [];
        for (let i = 1; i <= t; i++) {
          if (i === 1 || i === t || Math.abs(i - c) <= 2) out.push(i);
          else if (out[out.length - 1] !== '…') out.push('…');
        }
        return out;
      },
      taka: (v) => App.taka(v),
      num: (v) => numFmt.format(n(v)),
      hue: (r) => ((String((r.category_info && r.category_info.name) || r.name).charCodeAt(0) * 37) % 360),
      unitOf: (r) => (r.unit_info && (r.unit_info.code || r.unit_info.name)) || '',
      stockState(r) {
        const s = n(r.stock_qty);
        if (s <= 0) return 'out';
        if (s <= n(r.alert_quantity)) return 'low';
        return 'in';
      },
      stockCls(r) { return { out: 'txt-due', low: 'txt-warn', in: '' }[this.stockState(r)]; },
      badge(r) {
        if (!r.is_active) return { label: 'Inactive', cls: 'st-cancelled' };
        return { out: { label: 'Out of stock', cls: 'st-pending' }, low: { label: 'Running low', cls: 'st-low' },
          in: { label: 'In stock', cls: 'st-paid' } }[this.stockState(r)];
      },
      margin(r) {
        const price = n(r.discount_applied ? r.final_price : r.selling_price), cost = n(r.purchase_price);
        const amount = r2(price - cost);
        return { amount, pct: price > 0 ? (amount / price * 100).toFixed(1) : '0.0' };
      },

      // ───── drawer ─────
      open(r) {
        this.sel = r;
        document.body.style.overflow = 'hidden';
        this.$nextTick(() => this.drawBarcode(this.$refs.barcode, r.sku));
      },
      shut() { this.sel = null; document.body.style.overflow = ''; },
      drawBarcode(el, code, opts) {
        if (!el || !code || typeof JsBarcode !== 'function') return;
        try {
          JsBarcode(el, code, Object.assign({ format: 'CODE128', height: 48, width: 1.6, margin: 0, fontSize: 13,
            font: 'monospace', textMargin: 4, background: 'transparent' }, opts || {}));
        } catch (e) { /* SKU তে এমন অক্ষর থাকলে barcode হয় না — label ছাড়াই চলবে */ }
      },

      // ───── labels ─────
      openLabels(r) {
        this.label.product = r;
        this.label.count = Math.min(200, Math.max(1, n(r.stock_qty) > 0 && n(r.stock_qty) <= 60 ? n(r.stock_qty) : 12));
        this.labelOpen = true;
        this.$nextTick(() => this.renderLabels());
      },
      renderLabels() {
        const box = this.$refs.labels, p = this.label.product;
        if (!box || !p) return;
        const count = Math.min(200, Math.max(1, parseInt(this.label.count, 10) || 1));
        const price = p.discount_applied ? p.final_price : p.selling_price;
        box.innerHTML = Array.from({ length: count }, () =>
          `<div class="lbl"><b>${esc(p.name)}</b><svg class="lbl-bc"></svg>${this.label.price ? `<span>${esc(App.taka(price))}</span>` : ''}</div>`).join('');
        box.querySelectorAll('svg.lbl-bc').forEach(svg => this.drawBarcode(svg, p.sku, { height: 34, width: 1.3, fontSize: 11 }));
      },
      print() { window.print(); },

      // ───── add / edit ─────
      openForm(r) {
        this.form = r ? {
          id: r.id, sku: r.sku, name: r.name || '',
          category: r.category ? String(r.category) : '', unit: r.unit ? String(r.unit) : '', brand: r.brand ? String(r.brand) : '',
          purchase_price: String(n(r.purchase_price) || ''), selling_price: String(n(r.selling_price) || ''),
          opening_stock: '', alert_quantity: String(n(r.alert_quantity)),
          discount_on: !!r.discount_applied_on, discount_type: r.discount_type === 'percentage' ? 'percentage' : 'fixed',
          discount_value: r.discount_applied_on ? String(n(r.discount_value)) : '',
          description: r.description || '', is_active: !!r.is_active, file: null, preview: r.image || '',
        } : {
          id: null, sku: '', name: '', category: this.f.category || '', unit: this.defaultUnit(), brand: '',
          purchase_price: '', selling_price: '', opening_stock: '', alert_quantity: '5',
          discount_on: false, discount_type: 'percentage', discount_value: '',
          description: '', is_active: true, file: null, preview: '',
        };
        this.fe = {}; this.formError = ''; this.formOpen = true;
        this.$nextTick(() => this.$refs.pfName && this.$refs.pfName.focus());
      },
      defaultUnit() {
        const pcs = this.units.find(u => /^(pcs|pc|piece|pics)$/i.test(u.code || '') || /^(pcs|pieces?|pics)$/i.test(u.name));
        return pcs ? String(pcs.id) : (this.units[0] ? String(this.units[0].id) : '');
      },
      get formMargin() {
        const s = n(this.form.selling_price), c = n(this.form.purchase_price);
        return s > 0 ? ((s - c) / s * 100).toFixed(1) : '0.0';
      },
      get formFinal() {
        const s = n(this.form.selling_price), d = n(this.form.discount_value);
        if (!this.form.discount_on || !d) return s;
        return r2(Math.max(0, this.form.discount_type === 'percentage' ? s - s * d / 100 : s - d));
      },
      pickImage(ev) {
        const f = ev.target.files && ev.target.files[0];
        if (!f) return;
        if (f.size > 3 * 1024 * 1024) { this.formError = 'The photo is too large. Use one under 3 MB.'; return; }
        this.form.file = f;
        this.form.preview = URL.createObjectURL(f);
      },
      async saveForm() {
        const f = this.form, fe = {};
        if (!f.name.trim()) fe.name = 'Enter the product name.';
        if (!f.unit) fe.unit = 'Choose how it is counted (pcs, kg …).';
        if (!(n(f.selling_price) > 0)) fe.price = 'Enter the selling price.';
        else if (n(f.selling_price) < n(f.purchase_price)) fe.price = 'Selling price is lower than the cost. You would lose money on each sale.';
        if (f.discount_on) {
          if (!(n(f.discount_value) > 0)) fe.discount = 'Enter the discount.';
          else if (f.discount_type === 'percentage' && n(f.discount_value) > 100) fe.discount = 'A discount cannot be more than 100%.';
          else if (f.discount_type === 'fixed' && n(f.discount_value) >= n(f.selling_price)) fe.discount = 'The discount must be less than the price.';
        }
        this.fe = fe;
        if (Object.keys(fe).length || this.formSaving) return;
        this.formSaving = true; this.formError = '';

        const fields = {
          name: f.name.trim(), category: f.category || '', unit: f.unit, brand: f.brand || '',
          purchase_price: r2(f.purchase_price).toFixed(2), selling_price: r2(f.selling_price).toFixed(2),
          alert_quantity: String(parseInt(f.alert_quantity, 10) || 0),
          description: f.description.trim(), is_active: f.is_active ? 'true' : 'false',
          discount_applied_on: f.discount_on ? 'true' : 'false',
        };
        if (f.discount_on) { fields.discount_type = f.discount_type; fields.discount_value = r2(f.discount_value).toFixed(2); }
        if (!f.id) fields.opening_stock = String(parseInt(f.opening_stock, 10) || 0);

        // ছবি থাকলে multipart (FormData), নইলে JSON
        let body;
        if (f.file) {
          body = new FormData();
          Object.entries(fields).forEach(([k, v]) => { if (v !== '') body.append(k, v); });
          body.append('image', f.file);
        } else {
          body = Object.assign({}, fields, {
            category: fields.category ? Number(fields.category) : null,
            brand: fields.brand ? Number(fields.brand) : null,
            unit: Number(fields.unit),
            is_active: f.is_active, discount_applied_on: f.discount_on,
          });
          if (body.category === null && f.id) delete body.category; // update এ category খালি রাখা যায় না
        }
        try {
          const r = f.id
            ? await App.api(`/api/products/${f.id}/`, { method: 'PATCH', body })
            : await App.api('/api/products/', { method: 'POST', body });
          this.formOpen = false;
          this.flash(f.id ? 'Product updated.' : `${fields.name} added${r.data && r.data.sku ? ' as ' + r.data.sku : ''}.`);
          if (this.sel && r.data && this.sel.id === r.data.id) { this.sel = r.data; this.$nextTick(() => this.drawBarcode(this.$refs.barcode, r.data.sku)); }
          this.fetch(); this.loadCounts();
        } catch (e) {
          this.formError = explain(e);
        }
        this.formSaving = false;
      },

      // ───── quick add category / brand ─────
      quickAdd(kind) {
        this.qa = { open: true, kind, name: '', error: '', saving: false };
        this.$nextTick(() => this.$refs.qaName && this.$refs.qaName.focus());
      },
      async saveQuickAdd() {
        const name = this.qa.name.trim();
        if (!name || this.qa.saving) return;
        this.qa.saving = true; this.qa.error = '';
        const url = this.qa.kind === 'brand' ? '/api/brands/' : '/api/categories/';
        try {
          const r = await App.api(url, { method: 'POST', body: { name } });
          const item = r.data;
          if (this.qa.kind === 'brand') { this.brands.push(item); this.form.brand = String(item.id); }
          else { this.categories.push(item); this.form.category = String(item.id); }
          this.qa.open = false;
        } catch (e) { this.qa.error = explain(e); }
        this.qa.saving = false;
      },

      // ───── delete ─────
      askDelete() { this.delError = ''; this.confirmDel = true; },
      async remove() {
        if (!this.sel || this.deleting) return;
        this.deleting = true; this.delError = '';
        try {
          const r = await App.api(`/api/products/${this.sel.id}/`, { method: 'DELETE' });
          this.confirmDel = false;
          this.flash(r.message || 'Done.');
          this.shut(); this.fetch(); this.loadCounts();
        } catch (e) { this.delError = e.message; }
        this.deleting = false;
      },
      flash(msg) {
        this.toast = msg;
        clearTimeout(this._toast);
        this._toast = setTimeout(() => { this.toast = ''; }, 3500);
      },
    };
  };
})();
