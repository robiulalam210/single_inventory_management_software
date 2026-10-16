/*
 * বিক্রি — "Sale" (পূর্ণ form) আর "POS Sale" (কাউন্টার) দুটোর একই হিসাব ও save।
 *
 * হিসাব backend এর হুবহু (Sale.calculate_totals + SaleItem.subtotal):
 *   লাইন    = qty × দাম − ছাড় (percent → লাইনের %, fixed → লাইনের বেশি নয়)
 *   চার্জ    = percent → মোটের %, fixed → সরাসরি (VAT, service, delivery, ছাড় — সব একই নিয়মে)
 *   total   = max(0, মোট + VAT + service + delivery − ছাড়)
 * টাকা: customer যত দিল (paid_amount) পাঠাই; বেশি দিলে backend ফেরত (change) হিসাব করে,
 *        কম দিলে বাকি — walk-in customer এর বাকি রাখা যায় না।
 */
(function () {
  'use strict';

  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const todayIso = () => iso(new Date());
  const n = (v) => { const x = Number(String(v == null ? '' : v).replace(/,/g, '')); return isFinite(x) ? x : 0; };
  const r2 = (v) => Math.round((n(v) + Number.EPSILON) * 100) / 100;
  const r3 = (v) => Math.round((n(v) + Number.EPSILON) * 1000) / 1000;
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const numFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 });
  const METHODS = [
    { value: 'Cash', label: 'Cash' },
    { value: 'Bank', label: 'Bank' },
    { value: 'Mobile banking', label: 'Mobile banking' },
  ];

  function lineTotal(qty, price, disc, type) {
    const gross = n(qty) * n(price);
    let off = 0;
    if (n(disc) > 0) off = type === 'percent' ? gross * n(disc) / 100 : Math.min(n(disc), gross);
    return r2(Math.max(0, gross - off));
  }
  const charge = (base, v, type) => (n(v) > 0 ? r2(type === 'percent' ? base * n(v) / 100 : n(v)) : 0);

  // ── সেল মোড (কেজি / গ্রাম / প্যাক) — backend এর ProductSaleMode.get_final_price এর সাথে মেলানো ──
  // দাম সবসময় "প্রতি সেল-মোড-ইউনিট": flat → flat_price; unit/tier → unit_price × factor।
  // স্টক base unit এ (যেমন গ্রাম); qty × factor = base পরিমাণ।
  const isWeightUnit = (u) => /^(g|gm|gram|grams|গ্রাম)$/i.test(String(u || '').trim());
  function modesOf(p, basePrice, unitLabel) {
    const out = [{ id: '', name: unitLabel || 'Unit', code: '', type: 'base', factor: 1, price: basePrice, flat: false, disc: 0, discType: 'fixed' }];
    (p.sale_modes || []).filter(m => m && m.is_active !== false).forEach(m => {
      const factor = n(m.conversion_factor) || 1;
      const flat = m.price_type === 'flat';
      const per = flat ? n(m.flat_price != null ? m.flat_price : m.effective_flat_price)
                       : r2((n(m.unit_price != null ? m.unit_price : m.effective_unit_price) || basePrice) * factor);
      if (!(per > 0)) return;
      // এই মোডের নিজের ছাড় (ProductSaleMode.discount_*) — অনলাইন শপ ও অ্যাপের মতোই এখানেও ধরা হয়
      const dv = n(m.discount_value);
      const dt = m.discount_type === 'percentage' || m.discount_type === 'percent' ? 'percent' : 'fixed';
      const disc = m.discount_type && dv > 0 ? dv : 0;
      out.push({ id: String(m.sale_mode_id), name: m.sale_mode_name, code: m.sale_mode_code || '', type: m.price_type,
                 factor, price: per, flat, disc, discType: dt });
    });
    // "গ্রাম" মতো factor=1 unit-মোড থাকলে আলাদা base-ইউনিট অপশন (একই জিনিস) বাদ
    if (out.length > 1 && out.slice(1).some(m => m.factor === 1 && !m.flat)) out.shift();
    return out;
  }
  // যে মোডে প্রথমে লাইন যোগ হবে: "kg" কোড থাকলে সেটা, নইলে সবচেয়ে ছোট প্যাক (factor > 1), নইলে base ইউনিট
  function defaultMode(modes) {
    const kg = modes.find(m => m.code === 'kg');
    if (kg) return kg;
    const packs = modes.filter(m => m.id && m.factor > 1).sort((a, b) => a.factor - b.factor);
    return packs[0] || modes[0];
  }

  // ছাড়ের পরের দাম (দেখানোর জন্য) — লাইনের আসল হিসাব lineTotal() করে
  function finalOf(m) {
    if (!(m.disc > 0)) return m.price;
    return r2(Math.max(0, m.discType === 'percent' ? m.price * (1 - m.disc / 100) : m.price - m.disc));
  }

  function product(p) {
    const dt = p.discount_type === 'percentage' || p.discount_type === 'percent' ? 'percent' : 'fixed';
    const unit = (p.unit_info && (p.unit_info.code || p.unit_info.name)) || '';
    const price = n(p.selling_price);
    const modes = modesOf(p, price, unit);
    modes.forEach(m => { m.final = finalOf(m); });
    const def = defaultMode(modes);
    return {
      id: p.id, name: p.name, sku: p.sku || '',
      stock: n(p.stock_qty), alert: n(p.alert_quantity),
      unit, weight: isWeightUnit(unit),
      price: def.price, basePrice: price, modes, def,
      disc: p.discount_applied ? n(p.discount_value) : 0, discType: dt,
      cat: (p.category_info && p.category_info.name) || 'Other',
      image: p.image || '',
    };
  }

  // যে error ই আসুক — nested ({items: [{quantity: [...]}]}) হলেও প্রথম বোধগম্য বার্তা
  function explain(e) {
    const dig = (v) => {
      if (v == null) return '';
      if (typeof v === 'string') return v;
      if (Array.isArray(v)) { for (const x of v) { const m = dig(x); if (m) return m; } return ''; }
      if (typeof v === 'object') { for (const x of Object.values(v)) { const m = dig(x); if (m) return m; } }
      return '';
    };
    const d = e.data && e.data.data;
    return dig(d) || e.message;
  }

  // getter গুলো ঠিক রেখে একাধিক অংশ জোড়া (Object.assign getter কে স্থির মান বানিয়ে ফেলে)
  function compose(...parts) {
    const out = {};
    parts.forEach(p => Object.defineProperties(out, Object.getOwnPropertyDescriptors(p)));
    return out;
  }

  // ─────────────────────────────── shared core ───────────────────────────────
  function core(init) {
    let seq = 0;
    return {
      init0() {
        App.api('/api/customers-active/').then(r => {
          const list = listOf(r).filter(c => c.is_active !== false);
          this.customerRows = Object.fromEntries(list.map(c => [String(c.id), c]));
          this.customers = list.map(c => ({ value: String(c.id), label: c.name,
            sub: [c.phone, n(c.total_due) > 0 ? 'Due ' + App.taka(c.total_due) : ''].filter(Boolean).join(' · ') }));
        }).catch(() => {});
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => {
          this.accountsAll = listOf(r).filter(a => a.is_active !== false);
          this.pickAccount();
        }).catch(() => {});
        if (this.canPickSeller) {
          App.api('/api/users/', { query: { status: 1 } }).then(r => {
            this.users = listOf(r).map(u => ({ value: String(u.id), label: u.full_name || u.username, sub: u.username }));
          }).catch(() => { this.canPickSeller = false; });
        }
        if (init.customer) { this.cust.mode = 'saved'; this.cust.id = String(init.customer); }
        this.$watch('pay.method', () => this.pickAccount());
        this.$watch('cust.mode', (m) => { if (m === 'walk_in') this.cust.id = ''; this.errors.customer = ''; });
        this.$watch('cust.id', () => { this.errors.customer = ''; });
      },

      me: init.me,
      company: init.company || {},
      canPickSeller: !!init.canPickSeller,
      canSeeList: !!init.canSeeList,
      methods: METHODS,
      customers: [], customerRows: {}, accountsAll: [], users: [],
      rows: [],
      cust: { mode: 'walk_in', id: '' },
      ch: { discount: '', discount_type: 'fixed', vat: '', vat_type: 'percent', service: '', service_type: 'fixed', delivery: '', delivery_type: 'fixed' },
      pay: { received: '', method: 'Cash', account: '', followTotal: true },
      seller: String(init.me.id),
      date: todayIso(),
      maxDate: todayIso(),
      remark: '',
      errors: {}, saving: false, serverError: '', done: null,

      // ───── cart ─────
      addProduct(p, qty, mode) {
        this.errors.items = '';
        const m = mode || p.def;
        const ex = this.rows.find(r => r.product_id === p.id && r.mode === m.id);
        if (ex) {
          ex.qty = String(r3(n(ex.qty) + (qty || 1)));
          ex.err = this.stockErr(ex);
          return ex;
        }
        const row = {
          key: ++seq, product_id: p.id, name: p.name, sku: p.sku, stock: p.stock, unit: p.unit, cat: p.cat,
          modes: p.modes, mode: m.id, modeName: m.name, factor: m.factor, flat: m.flat, weight: p.weight,
          qty: String(qty || 1), price: String(m.price), listPrice: m.price,
          pDisc: p.disc, pDiscType: p.discType,
          discount: m.disc ? String(m.disc) : (p.disc ? String(p.disc) : ''), discount_type: m.disc ? m.discType : p.discType,
          err: '', open: false,
        };
        row.err = this.stockErr(row);
        this.rows.push(row);
        return row;
      },
      // সারির সেল মোড বদলালে: দাম ওই মোডের দামে ফিরে যায়, পরিমাণ একই থাকে
      setMode(r, id) {
        const m = r.modes.find(x => x.id === String(id)) || r.modes[0];
        r.mode = m.id; r.modeName = m.name; r.factor = m.factor; r.flat = m.flat;
        r.price = String(m.price); r.listPrice = m.price;
        r.discount = m.disc ? String(m.disc) : (r.pDisc ? String(r.pDisc) : '');
        r.discount_type = m.disc ? m.discType : (r.pDiscType || 'fixed');
        r.err = this.stockErr(r);
      },
      step(r) { return r.weight && r.factor <= 1 ? 50 : 1; },      // গ্রামে ৫০ করে বাড়ে
      baseQty(r) { return n(r.qty) * (r.factor || 1); },
      availIn(r) { return r.stock / (r.factor || 1); },              // এই মোডের এককে কতটা আছে
      // কার্টে এই পণ্য মোট কত base ইউনিট (সব মোড মিলিয়ে)
      baseInCart(pid) { return this.rows.filter(x => x.product_id === pid).reduce((s, x) => s + this.baseQty(x), 0); },
      stockErr(r) {
        const q = n(r.qty);
        if (!(q > 0)) return 'Quantity must be above 0.';
        const used = this.baseInCart(r.product_id) - this.baseQty(r);       // একই পণ্যের অন্য সারি
        if (this.baseQty(r) + used > r.stock + 1e-9) {
          const left = Math.max(0, r.stock - used) / (r.factor || 1);
          return r.stock > 0 ? `Only ${numFmt.format(Math.floor(left * 1000) / 1000)} ${r.modeName} available.` : 'Out of stock.';
        }
        if (!(n(r.price) > 0)) return 'Enter the selling price.';
        return '';
      },
      bump(r, d) {
        const q = r3(n(r.qty) + d * this.step(r));
        if (q <= 0) { this.remove(r); return; }
        r.qty = String(q);
        r.err = this.stockErr(r);
      },
      remove(r) { this.rows = this.rows.filter(x => x.key !== r.key); },
      clearCart() { this.rows = []; },
      lineOf(r) { return lineTotal(r.qty, r.price, r.discount, r.discount_type); },
      get qtyTotal() { return r3(this.rows.reduce((s, r) => s + n(r.qty), 0)); },

      // ───── totals (backend এর হুবহু) ─────
      get t() {
        const sub = r2(this.rows.reduce((s, r) => s + this.lineOf(r), 0));
        const discount = charge(sub, this.ch.discount, this.ch.discount_type);
        const vat = charge(sub, this.ch.vat, this.ch.vat_type);
        const service = charge(sub, this.ch.service, this.ch.service_type);
        const delivery = charge(sub, this.ch.delivery, this.ch.delivery_type);
        const grand = r2(Math.max(0, sub + vat + service + delivery - discount));
        const itemOff = r2(this.rows.reduce((s, r) => s + (n(r.qty) * n(r.price) - this.lineOf(r)), 0));
        return { sub, discount, vat, service, delivery, grand, itemOff };
      },
      get receivedNum() { return r2(this.pay.received); },
      get change() { return r2(Math.max(0, this.receivedNum - this.t.grand)); },
      get due() { return r2(Math.max(0, this.t.grand - this.receivedNum)); },
      get customer() { return this.cust.mode === 'saved' ? this.customerRows[this.cust.id] || null : null; },

      // ───── accounts ─────
      get accounts() {
        return this.accountsAll.filter(a => same(a.ac_type, this.pay.method))
          .map(a => ({ value: String(a.id), label: a.name, sub: a.ac_number || a.bank_name || '' }));
      },
      pickAccount() {
        const list = this.accounts;
        if (!list.some(a => a.value === this.pay.account)) this.pay.account = list.length ? list[0].value : '';
      },
      get account() { return this.accountsAll.find(a => String(a.id) === String(this.pay.account)) || null; },

      // ───── save ─────
      validate() {
        const e = {};
        if (!this.rows.length) e.items = 'Add at least one product.';
        this.rows.forEach(r => { r.err = this.stockErr(r); if (r.err) e.items = e.items || 'Fix the highlighted products.'; });
        if (this.cust.mode === 'saved' && !this.cust.id) e.customer = 'Choose the customer, or switch to walk-in.';
        if (this.date > this.maxDate) e.date = 'The date cannot be in the future.';
        if (this.receivedNum > 0 && !this.pay.account) e.account = `There is no active ${this.pay.method} account.`;
        if (this.due > 0 && this.cust.mode === 'walk_in')
          e.received = `A walk-in customer must pay the full ${App.taka(this.t.grand)}. Choose a saved customer to give credit.`;
        this.errors = e;
        return !Object.keys(e).length;
      },
      payload() {
        const body = {
          customer_type: this.cust.mode === 'saved' ? 'saved_customer' : 'walk_in',
          sale_type: 'retail',
          sale_date: this.date,
          sale_by: Number(this.seller || this.me.id),
          items: this.rows.map(r => this.itemPayload(r)),
          overall_discount: r2(this.ch.discount).toFixed(2), overall_discount_type: this.ch.discount_type,
          vat: r2(this.ch.vat).toFixed(2), overall_vat_type: this.ch.vat_type,
          service_charge: r2(this.ch.service).toFixed(2), overall_service_type: this.ch.service_type,
          delivery_charge: r2(this.ch.delivery).toFixed(2), overall_delivery_type: this.ch.delivery_type,
          remark: this.remark.trim(),
          with_money_receipt: 'Yes',
          paid_amount: this.receivedNum.toFixed(2),
        };
        if (this.cust.mode === 'saved') body.customer_id = Number(this.cust.id);
        if (this.receivedNum > 0) { body.payment_method = this.pay.method; body.account_id = Number(this.pay.account); }
        return body;
      },
      // সেল মোড থাকলে: quantity = মোডের এককে (প্যাক সংখ্যা / গ্রাম / কেজি); backend নিজে base এ বদলায়।
      //   flat  → flat_price = প্রতি প্যাকের দাম (subtotal = flat_price × quantity)
      //   unit  → unit_price = প্রতি base ইউনিটের দাম (দাম ÷ factor)
      itemPayload(r) {
        const it = { product_id: r.product_id, quantity: r3(r.qty).toFixed(3),
          discount: r2(r.discount).toFixed(2), discount_type: r.discount_type };
        if (r.mode) {
          it.sale_mode_id = Number(r.mode);
          if (r.flat) { it.flat_price = r2(r.price).toFixed(2); it.unit_price = r2(r.price).toFixed(2); }
          else it.unit_price = r2(n(r.price) / (r.factor || 1)).toFixed(2);
        } else it.unit_price = r2(r.price).toFixed(2);
        return it;
      },
      async submit() {
        this.serverError = '';
        if (!this.validate() || this.saving) return false;
        this.saving = true;
        try {
          const r = await App.api('/api/sales/', { method: 'POST', body: this.payload() });
          this.done = r.data;
          return true;
        } catch (e) {
          this.serverError = explain(e);
          return false;
        } finally {
          this.saving = false;
        }
      },
      resetSale() {
        this.rows = [];
        this.cust = { mode: 'walk_in', id: '' };
        Object.assign(this.ch, { discount: '', vat: '', service: '', delivery: '' });
        Object.assign(this.pay, { received: '', followTotal: true });
        this.remark = ''; this.errors = {}; this.serverError = ''; this.done = null;
        this.date = todayIso();
      },

      // save হওয়া sale থেকে রসিদের লাইন (backend এর একই হিসাবে)
      saleLines(s) {
        const sub = n(s.gross_total);
        const tag = (v, type) => (type === 'percent' && n(v) > 0 ? ` (${n(v)}%)` : '');
        return [
          ['Subtotal', sub],
          ['Discount' + tag(s.overall_discount, s.overall_discount_type), -charge(sub, s.overall_discount, s.overall_discount_type)],
          ['VAT' + tag(s.overall_vat_amount, s.overall_vat_type), charge(sub, s.overall_vat_amount, s.overall_vat_type)],
          ['Service' + tag(s.overall_service_charge, s.overall_service_type), charge(sub, s.overall_service_charge, s.overall_service_type)],
          ['Delivery' + tag(s.overall_delivery_charge, s.overall_delivery_type), charge(sub, s.overall_delivery_charge, s.overall_delivery_type)],
        ].filter(([, v], i) => i === 0 || v !== 0);
      },
      taka: (v) => App.taka(v),
      num: (v) => numFmt.format(n(v)),
      words: (v) => App.takaWords(v),
      round2: r2,
      fmtDate(s) { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }); },
      fmtTime(s) { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); },
    };
  }

  // ─────────────────────────────── Sale (full form) ───────────────────────────────
  window.saleForm = function (init) {
    return compose(core(init), {
      pq: '', results: [], searching: false, showResults: false, hi: 0, _st: null, _sreq: 0, _enter: false,

      init() {
        this.init0();
        this.$watch('pq', (v) => {
          clearTimeout(this._st);
          if (!v.trim()) { this.results = []; this.searching = false; return; }
          this.searching = true;
          this._st = setTimeout(() => this.search(v.trim()), 200);
        });
        // টাকার ঘর মোটের সাথে চলে, যতক্ষণ না user নিজে বদলায়
        this.$watch('t.grand', (g) => { if (this.pay.followTotal) this.pay.received = g ? g.toFixed(2) : ''; });
        this.$nextTick(() => this.$refs.pq && this.$refs.pq.focus());
      },
      async search(q) {
        const id = ++this._sreq;
        try {
          const r = await App.api('/api/products/', { query: { search: q, is_active: 'true', page_size: 12 } });
          if (id !== this._sreq) return;
          this.results = listOf(r).map(product);
          this.hi = 0;
          this.showResults = true;
          if (this._enter) {
            this._enter = false;
            const exact = this.results.find(x => same(x.sku, q));
            if (exact) this.pick(exact); else if (this.results.length === 1) this.pick(this.results[0]);
          }
        } catch (e) { if (id === this._sreq) this.results = []; }
        if (id === this._sreq) this.searching = false;
      },
      searchEnter() {
        if (this.searching) { this._enter = true; return; }
        const exact = this.results.find(x => same(x.sku, this.pq.trim()));
        const p = exact || this.results[this.hi];
        if (p) this.pick(p);
      },
      move(d) {
        const len = this.results.length;
        if (!len) return;
        this.hi = (this.hi + d + len) % len;
        this.$nextTick(() => { const el = this.$refs.results && this.$refs.results.children[this.hi]; if (el) el.scrollIntoView({ block: 'nearest' }); });
      },
      pick(p) {
        if (p.stock <= 0) { this.errors.items = `${p.name} is out of stock.`; return; }
        const row = this.addProduct(p);
        this.pq = ''; this.results = []; this.showResults = false;
        this.$nextTick(() => { const el = document.querySelector(`[data-row="${row.key}"] .qty-in`); if (el) { el.focus(); el.select(); } });
      },
      backToSearch() { this.$refs.pq && this.$refs.pq.focus(); },
      quickCash() {
        const g = this.t.grand, out = [];
        if (!g) return out;
        [100, 500, 1000].forEach(step => { const v = Math.ceil(g / step) * step; if (v > g && !out.includes(v)) out.push(v); });
        return out.slice(0, 3);
      },
      setReceived(v) { this.pay.received = r2(v).toFixed(2); this.pay.followTotal = r2(v) === this.t.grand; this.errors.received = ''; },
      async save() {
        const ok = await this.submit();
        if (ok) window.scrollTo({ top: 0, behavior: 'smooth' });
        else this.$nextTick(() => { const el = this.$root.querySelector('.has-error, .row-err, .form-err'); if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); });
      },
      again() { this.resetSale(); this.$nextTick(() => this.backToSearch()); },
    });
  };

  // ─────────────────────────────── POS ───────────────────────────────
  // ─────────────── Short Sale: ক্যাটাগরি → পণ্য → সেল মোড → পরিমাণ → "Add", তারপর customer/পেমেন্ট ───────────────
  window.shortSale = function (init) {
    return compose(window.saleForm(init), {
      catalog: [], catLoading: true, catError: '',
      qCat: '', qProd: '', qMode: '', qQty: '1', qPrice: '', qErr: '',

      init() {
        this.init0();
        this.$watch('t.grand', (g) => { if (this.pay.followTotal) this.pay.received = g ? g.toFixed(2) : ''; });
        this.loadCatalog();
        this.$nextTick(() => this.$refs.qprod && this.$refs.qprod.focus());
      },
      async loadCatalog() {
        try {
          const r = await App.api('/api/products/', { query: { no_pagination: 'true', is_active: 'true' } });
          this.catalog = listOf(r).map(product).sort((a, b) => a.name.localeCompare(b.name));
          this.catError = '';
        } catch (e) { this.catError = e.message; }
        this.catLoading = false;
      },
      get qCats() { return [...new Set(this.catalog.map(p => p.cat))].sort((a, b) => a.localeCompare(b)); },
      get qProducts() { return this.catalog.filter(p => !this.qCat || p.cat === this.qCat); },
      get qP() { return this.catalog.find(p => String(p.id) === String(this.qProd)) || null; },
      get qM() { const p = this.qP; return p ? (p.modes.find(m => m.id === this.qMode) || p.def) : null; },
      get qAvail() { const p = this.qP, m = this.qM; return p ? Math.max(0, (p.stock - this.baseInCart(p.id)) / m.factor) : 0; },
      // লাইনের টোটাল (ছাড় সহ) — সারিতে যোগ হলে যা হবে ঠিক তাই
      get qTotal() {
        const m = this.qM; if (!m) return 0;
        return lineTotal(this.qQty, this.qPrice, m.disc || (this.qP && this.qP.disc) || 0, m.disc ? m.discType : (this.qP ? this.qP.discType : 'fixed'));
      },
      qPick() {
        const p = this.qP; this.qErr = '';
        if (!p) { this.qMode = ''; this.qPrice = ''; return; }
        this.qMode = p.def.id; this.qQty = '1'; this.qPrice = String(p.def.price);
      },
      qSetMode() { const m = this.qM; if (m) { this.qPrice = String(m.price); } this.qErr = ''; },
      qBump(d) { const m = this.qM; const st = this.qP && this.qP.weight && m && m.factor <= 1 ? 50 : 1; this.qQty = String(Math.max(0, r3(n(this.qQty) + d * st))); },
      quickAdd() {
        const p = this.qP, m = this.qM;
        if (!p) { this.qErr = 'Choose a product.'; return; }
        const q = n(this.qQty);
        if (!(q > 0)) { this.qErr = 'Quantity must be above 0.'; return; }
        if (!(n(this.qPrice) > 0)) { this.qErr = 'Enter the selling price.'; return; }
        if (q * m.factor > p.stock - this.baseInCart(p.id) + 1e-9) {
          this.qErr = `Only ${numFmt.format(Math.floor(this.qAvail * 1000) / 1000)} ${m.name} available.`; return;
        }
        const row = this.addProduct(p, q, m);
        if (r2(this.qPrice) !== r2(m.price)) { row.price = String(r2(this.qPrice)); row.err = this.stockErr(row); }
        this.qProd = ''; this.qMode = ''; this.qQty = '1'; this.qPrice = ''; this.qErr = '';
        this.$nextTick(() => this.$refs.qprod && this.$refs.qprod.focus());
      },
      backToSearch() { this.$refs.qprod && this.$refs.qprod.focus(); },
    });
  };

  window.posScreen = function (init) {
    return compose(core(init), {
      catalog: [], catLoading: true, catError: '',
      q: '', cat: '',
      payOpen: false, receiptOpen: false, chargesOpen: false,
      flashKey: 0, flashMsg: '',
      _scan: '', _scanAt: 0,

      init() {
        this.init0();
        this.loadCatalog();
        // barcode scanner: কোনো ঘরে না থাকলেও দ্রুত টাইপ + Enter = scan
        window.addEventListener('keydown', (e) => this.globalKey(e));
      },
      async loadCatalog() {
        try {
          const r = await App.api('/api/products/', { query: { no_pagination: 'true', is_active: 'true' } });
          this.catalog = listOf(r).map(product).sort((a, b) => a.name.localeCompare(b.name));
          this.catError = '';
          // cart এর stock নতুন করে
          this.rows.forEach(row => { const p = this.catalog.find(x => x.id === row.product_id); if (p) row.stock = p.stock; });
        } catch (e) { this.catError = e.message; }
        this.catLoading = false;
      },
      get cats() {
        const m = new Map();
        this.catalog.forEach(p => m.set(p.cat, (m.get(p.cat) || 0) + 1));
        return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([name, count]) => ({ name, count }));
      },
      get shown() {
        const q = this.q.trim().toLowerCase();
        return this.catalog.filter(p => (!this.cat || p.cat === this.cat) &&
          (!q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q))).slice(0, 120);
      },
      inCart(p) { return this.rows.filter(x => x.product_id === p.id).reduce((s, x) => s + n(x.qty), 0); },
      tap(p) {
        if (p.stock <= 0) { this.say(`${p.name} is out of stock`); return; }
        if (this.baseInCart(p.id) + p.def.factor > p.stock + 1e-9) { this.say(`Only ${numFmt.format(p.stock / p.def.factor)} ${p.def.name} of ${p.name} in stock`); return; }
        this.addProduct(p);
        this.say(`${p.name} added`);
      },
      searchEnter() {
        const q = this.q.trim();
        if (!q) return;
        const exact = this.catalog.find(p => same(p.sku, q));
        const list = this.shown;
        const p = exact || (list.length === 1 ? list[0] : null);
        if (p) { this.tap(p); this.q = ''; }
        else if (!list.length) this.say(`No product matches “${q}”`);
      },
      globalKey(e) {
        if (this.payOpen || this.receiptOpen) return;
        if (e.key === 'F9') { e.preventDefault(); this.openPay(); return; }
        if (e.key === 'F2') { e.preventDefault(); this.$refs.q && this.$refs.q.focus(); return; }
        const t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
        const now = Date.now();
        if (e.key === 'Enter') {
          if (this._scan.length >= 3 && now - this._scanAt < 80) {
            const code = this._scan; this._scan = '';
            const p = this.catalog.find(x => same(x.sku, code));
            if (p) this.tap(p); else this.say(`No product with code ${code}`);
          }
          this._scan = '';
          return;
        }
        if (e.key.length === 1) {
          if (now - this._scanAt > 80) this._scan = '';
          this._scan += e.key;
          this._scanAt = now;
        }
      },
      say(msg) { this.flashMsg = msg; this.flashKey++; const k = this.flashKey; setTimeout(() => { if (k === this.flashKey) this.flashMsg = ''; }, 1600); },

      // ───── payment ─────
      openPay() {
        if (!this.rows.length) { this.say('Add a product first'); return; }
        const bad = this.rows.find(r => (r.err = this.stockErr(r)));
        if (bad) { this.say(bad.name + ': ' + bad.err); bad.open = true; return; }
        if (this.cust.mode === 'saved' && !this.cust.id) { this.errors.customer = 'Choose the customer, or switch to walk-in.'; return; }
        this.pay.received = this.t.grand.toFixed(2);
        this.serverError = ''; this.errors.received = ''; this.errors.account = '';
        this.payOpen = true;
        this.$nextTick(() => { const el = this.$refs.recv; if (el) { el.focus(); el.select(); } });
      },
      quickCash() {
        const g = this.t.grand, out = [g];
        [50, 100, 500, 1000].forEach(step => { const v = Math.ceil(g / step) * step; if (v > g && !out.includes(v)) out.push(v); });
        return out.slice(0, 5);
      },
      async complete() {
        const ok = await this.submit();
        if (ok) {
          this.payOpen = false;
          this.receiptOpen = true;
          this.loadCatalog();
        } else if (this.errors.items) {
          this.payOpen = false;
          this.say(this.errors.items);
        }
      },
      printReceipt() { window.print(); },
      newSale() {
        this.receiptOpen = false;
        this.resetSale();
        this.$nextTick(() => this.$refs.q && this.$refs.q.focus());
      },
    });
  };
})();
