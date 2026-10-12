/*
 * Stocktake — গুনে সিস্টেমের সাথে মেলানো।
 *   stocktakeList  : /app/stocktake/      — গণনার তালিকা + নতুন গণনা শুরু
 *   stocktakeCount : /app/stocktake/<id>/ — গণনার স্ক্রিন
 * API: /api/stock/counts/ (stocktake/views.py)
 *
 * গণনার স্ক্রিন: সংখ্যা লিখলে ৬০০ms পর নিজে নিজে সেভ (একসাথে অনেক সারি), Enter এ পরের সারিতে যায়,
 * বারকোড স্ক্যান করলে সেই সারির ঘরে কার্সার যায়। Apply না করা পর্যন্ত স্টক বদলায় না।
 */
(function () {
  'use strict';

  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const fmtDateTime = (s) => {
    const d = new Date(s);
    return isNaN(d) ? '' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) + ', ' +
      d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  };

  // ─────────────────────────────── list ───────────────────────────────
  window.stocktakeList = function (opts) {
    return {
      canEdit: !!(opts && opts.canEdit),
      rows: [], categories: [], loading: true, error: '',
      status: '', statuses: [{ key: '', label: 'All' }, { key: 'draft', label: 'Counting' }, { key: 'applied', label: 'Applied' }, { key: 'cancelled', label: 'Cancelled' }],
      form: { title: '', category: '', note: '' }, starting: false, startError: '',

      init() {
        this.fetch();
        App.api('/api/categories/').then(r => { this.categories = listOf(r).filter(c => c.is_active !== false); }).catch(() => {});
      },
      async fetch() {
        this.loading = true; this.error = '';
        try { const r = await App.api('/api/stock/counts/', { query: { status: this.status } }); this.rows = r.data || []; }
        catch (e) { this.error = e.message; this.rows = []; }
        this.loading = false;
      },
      async start() {
        if (this.starting) return;
        this.starting = true; this.startError = '';
        try {
          const r = await App.api('/api/stock/counts/', { method: 'POST', body: {
            title: this.form.title.trim(), category_id: this.form.category ? Number(this.form.category) : null, note: this.form.note.trim() } });
          location.href = '/app/stocktake/' + r.data.id + '/';
        } catch (e) { this.startError = e.message; this.starting = false; }
      },
      taka: (v) => App.taka(v),
      dateTime: fmtDateTime,
    };
  };

  // ─────────────────────────────── count screen ───────────────────────────────
  window.stocktakeCount = function (opts) {
    return {
      id: opts.id, canEdit: !!opts.canEdit,
      c: null, error: '', q: '', view: 'all', limit: 150, hot: null, scanMsg: '',
      confirm: '', busy: false, modalError: '', toast: '',
      pending: {}, saving: false, savedAt: null, saveError: '',
      _timer: null, _toast: null, _hot: null,

      init() {
        this.load();
        window.addEventListener('beforeunload', (e) => { if (this.dirty) { e.preventDefault(); e.returnValue = ''; } });
      },

      async load() {
        this.error = '';
        try {
          const r = await App.api('/api/stock/counts/' + this.id + '/');
          const d = r.data;
          d.lines.forEach(l => { l.input = l.counted_qty === null ? '' : String(l.counted_qty); });
          this.c = d;
          this.$nextTick(() => this.$refs.scan && this.$refs.scan.focus());
        } catch (e) { this.error = e.message; }
      },

      // ───── derived ─────
      get sum() { return this.liveSummary(); },
      liveSummary() {
        const lines = (this.c && this.c.lines) || [];
        let counted = 0, differing = 0, sq = 0, oq = 0, sv = 0, ov = 0;
        lines.forEach(l => {
          const v = this.diffOf(l);
          if (v === null) return;
          counted++;
          if (v < 0) { differing++; sq += -v; sv += -v * l.unit_cost; }
          else if (v > 0) { differing++; oq += v; ov += v * l.unit_cost; }
        });
        return { total: lines.length, counted, uncounted: lines.length - counted, differing,
                 short_qty: sq, over_qty: oq, short_value: sv, over_value: ov };
      },
      get pct() { return this.sum.total ? Math.round((this.sum.counted / this.sum.total) * 100) : 0; },
      diffOf(l) {
        if (this.c && this.c.status === 'draft') return l.input === '' ? null : n(l.input) - l.system_qty;
        return l.counted_qty === null ? null : l.counted_qty - l.system_qty;
      },
      get views() {
        const L = (this.c && this.c.lines) || [];
        const un = L.filter(l => this.diffOf(l) === null).length;
        const df = L.filter(l => { const v = this.diffOf(l); return v !== null && v !== 0; }).length;
        return [
          { key: 'all', label: 'All', count: L.length },
          { key: 'uncounted', label: 'Not counted', count: un },
          { key: 'diff', label: 'Differences', count: df },
          { key: 'counted', label: 'Counted', count: L.length - un },
        ];
      },
      get filtered() {
        const q = this.q.trim().toLowerCase();
        return ((this.c && this.c.lines) || []).filter(l => {
          const v = this.diffOf(l);
          if (this.view === 'uncounted' && v !== null) return false;
          if (this.view === 'counted' && v === null) return false;
          if (this.view === 'diff' && (v === null || v === 0)) return false;
          return !q || l.name.toLowerCase().includes(q) || (l.sku || '').toLowerCase().includes(q);
        });
      },
      get shown() { return this.filtered.slice(0, this.limit); },

      // ───── scan / keyboard ─────
      scanEnter() {
        const q = this.q.trim();
        if (!q) return;
        const lines = this.c.lines;
        let hit = lines.find(l => same(l.sku, q));
        if (!hit) {
          const m = this.filtered;
          if (m.length === 1) hit = m[0];
          else if (m.length > 1) { this.scanMsg = m.length + ' products match — pick one from the list below, or type more of the name.'; return; }
        }
        if (!hit) { this.scanMsg = 'No product matches “' + q + '”.'; return; }
        this.scanMsg = '';
        this.focusLine(hit);
        this.q = '';
      },
      focusLine(l) {
        if (this.view !== 'all' && !this.filtered.includes(l)) this.view = 'all';
        const idx = this.filtered.indexOf(l);
        if (idx >= this.limit) this.limit = idx + 20;
        this.hot = l.id;
        clearTimeout(this._hot); this._hot = setTimeout(() => { this.hot = null; }, 2200);
        this.$nextTick(() => {
          const el = document.querySelector('[data-in="' + l.id + '"]');
          if (el) { el.scrollIntoView({ block: 'center' }); el.focus(); }
        });
      },
      next(l) {
        const list = this.shown;
        const i = list.indexOf(l);
        const nx = list[i + 1];
        if (nx) { const el = document.querySelector('[data-in="' + nx.id + '"]'); if (el) { el.focus(); return; } }
        this.$refs.scan && this.$refs.scan.focus();
      },
      match(l) { l.input = String(l.system_qty); this.edited(l); this.next(l); },

      // ───── autosave ─────
      edited(l) {
        this.pending[l.id] = l.input === '' ? null : n(l.input);
        this.saveError = '';
        clearTimeout(this._timer);
        this._timer = setTimeout(() => this.flush(), 600);
      },
      get dirty() { return Object.keys(this.pending).length > 0 || this.saving; },
      get saveText() {
        if (this.saveError) return this.saveError;
        if (this.dirty) return 'Saving…';
        return this.savedAt ? 'All saved' : '';
      },
      async flush() {
        if (this.saving) { clearTimeout(this._timer); this._timer = setTimeout(() => this.flush(), 300); return; }
        const batch = this.pending;
        const ids = Object.keys(batch);
        if (!ids.length) return;
        this.pending = {};
        this.saving = true;
        try {
          await App.api('/api/stock/counts/' + this.id + '/count/', { method: 'POST', body: {
            rows: ids.map(id => ({ line_id: Number(id), counted_qty: batch[id] })) } });
          this.savedAt = Date.now();
        } catch (e) {
          ids.forEach(id => { if (!(id in this.pending)) this.pending[id] = batch[id]; });   // আবার চেষ্টার জন্য ফেরত
          this.saveError = 'Not saved: ' + e.message;
        }
        this.saving = false;
        if (Object.keys(this.pending).length && !this.saveError) this._timer = setTimeout(() => this.flush(), 300);
      },

      // ───── apply / cancel ─────
      async askApply() {
        clearTimeout(this._timer);
        await this.flush();
        if (this.saveError) { this.say(this.saveError); return; }
        this.modalError = '';
        this.confirm = 'apply';
      },
      async apply() {
        this.busy = true; this.modalError = '';
        try {
          const r = await App.api('/api/stock/counts/' + this.id + '/apply/', { method: 'POST' });
          this.confirm = '';
          this.say(r.message || 'Applied');
          await this.load();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (e) { this.modalError = e.message; }
        this.busy = false;
      },
      async cancel() {
        this.busy = true; this.modalError = '';
        try {
          const r = await App.api('/api/stock/counts/' + this.id + '/cancel/', { method: 'POST' });
          this.confirm = '';
          this.say(r.message || 'Cancelled');
          await this.load();
        } catch (e) { this.modalError = e.message; }
        this.busy = false;
      },

      say(t) { this.toast = t; clearTimeout(this._toast); this._toast = setTimeout(() => { this.toast = ''; }, 3200); },
      taka: (v) => App.taka(v),
      dateTime: fmtDateTime,
    };
  };
})();
