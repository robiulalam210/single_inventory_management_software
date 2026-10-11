/*
 * Barcode Labels — অনেক পণ্যের লেবেল একসাথে সাজিয়ে প্রিন্ট।
 * পণ্য খোঁজা: GET /api/products/?search=  (Purchase/Adjust পেজের মতোই)।
 * ?ids=1,2,3 দিলে সেই পণ্যগুলো আগে থেকেই তালিকায় আসে।
 */
(function () {
  'use strict';

  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const MAX_EACH = 500, MAX_TOTAL = 2000;
  const KEY = 'lp-opts';

  const toRow = (p) => ({
    id: p.id, name: p.name, sku: p.sku || '', stock: n(p.stock_qty),
    price: p.discount_applied ? n(p.final_price) : n(p.selling_price),
    count: 1,
  });

  window.labelPrint = function () {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { /* ঠিক আছে */ }
    return {
      pq: '', results: [], hi: 0, showResults: false, searching: false, _sreq: 0, _st: null, _enterPending: false,
      rows: [],
      cols: [2, 3, 4, 5, 6].includes(saved.cols) ? saved.cols : 4,
      showName: saved.showName !== false, showPrice: saved.showPrice !== false,

      get total() { return this.rows.reduce((s, r) => s + this.clamp(r.count), 0); },
      get labels() {
        const out = [];
        for (const r of this.rows) {
          const c = this.clamp(r.count), price = App.taka(r.price);
          for (let i = 0; i < c && out.length < MAX_TOTAL; i++) out.push({ name: r.name, sku: r.sku, price });
        }
        return out;
      },
      clamp(v) { return Math.min(MAX_EACH, Math.max(0, parseInt(v, 10) || 0)); },
      fix(r) { r.count = Math.max(1, this.clamp(r.count)); },

      init() {
        this.$watch('pq', (v) => {
          clearTimeout(this._st);
          if (!v.trim()) { this.results = []; this.searching = false; return; }
          this.searching = true;
          this._st = setTimeout(() => this.search(v.trim()), 220);
        });
        // বাছাই মনে রাখা — শুধু এই ব্রাউজারের সুবিধা
        this.$watch('cols', () => this.remember());
        this.$watch('showName', () => this.remember());
        this.$watch('showPrice', () => this.remember());
        // বার্কোড আঁকা — তালিকা/অপশন বদলালেই
        this.$watch('labels', () => this.$nextTick(() => this.draw()));
        this.$watch('cols', () => this.$nextTick(() => this.draw()));
        this.prefill();
      },
      remember() {
        try { localStorage.setItem(KEY, JSON.stringify({ cols: this.cols, showName: this.showName, showPrice: this.showPrice })); } catch (e) { /* ঠিক আছে */ }
      },
      async prefill() {
        const ids = (new URLSearchParams(location.search).get('ids') || '').split(',').map(s => parseInt(s, 10)).filter(Boolean).slice(0, 50);
        for (const id of ids) {
          try { const r = await App.api('/api/products/' + id + '/'); if (r && r.data && r.data.id) this.add(toRow(r.data), true); } catch (e) { /* বাদ */ }
        }
      },
      draw() {
        const box = this.$root.querySelector('.ls-sheet');
        if (!box || typeof JsBarcode !== 'function') return;
        const h = Math.max(24, 44 - this.cols * 3);
        box.querySelectorAll('svg.lbl-bc').forEach(svg => {
          const code = svg.getAttribute('data-code');
          if (!code) return;
          try { JsBarcode(svg, code, { format: 'CODE128', height: h, width: this.cols > 4 ? 1.1 : 1.4, margin: 0, fontSize: 11, displayValue: true, background: 'transparent' }); }
          catch (e) { /* এমন অক্ষর থাকলে বার্কোড হয় না */ }
        });
      },

      async search(q) {
        const id = ++this._sreq;
        try {
          const r = await App.api('/api/products/', { query: { search: q, is_active: 'true', page_size: 12 } });
          if (id !== this._sreq) return;
          this.results = listOf(r).map(toRow);
          this.hi = 0; this.showResults = true;
          if (this._enterPending) {
            this._enterPending = false;
            const exact = this.results.find(x => same(x.sku, q));
            if (exact) this.add(exact); else if (this.results.length === 1) this.add(this.results[0]);
          }
        } catch (e) { if (id === this._sreq) this.results = []; }
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
        this.$nextTick(() => { const el = this.$refs.results && this.$refs.results.children[this.hi]; if (el) el.scrollIntoView({ block: 'nearest' }); });
      },
      add(p, quiet) {
        const have = this.rows.find(r => r.id === p.id);
        if (have) have.count = Math.min(MAX_EACH, this.clamp(have.count) + 1);
        else this.rows.push(Object.assign({}, p, { count: 1 }));
        if (!quiet) { this.pq = ''; this.results = []; this.showResults = false; const el = document.getElementById('lp-q'); if (el) el.focus(); }
      },
      remove(i) { this.rows.splice(i, 1); },
      print() { if (this.total) window.print(); },
    };
  };
})();
