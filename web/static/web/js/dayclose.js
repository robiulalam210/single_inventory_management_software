/*
 * Day Close — /app/reports/day-close/
 * API: /api/day-close/summary/?date=  ·  POST /api/day-close/  ·  DELETE /api/day-close/<id>/  (dayclose/views.py)
 * Counted ঘর খালি রাখলে ওই account হিসাবে ধরা হয় না।
 */
(function () {
  'use strict';
  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const today = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };

  window.dayClose = function () {
    return {
      date: today(), data: null, closed: null, canClose: false, canReopen: false,
      counts: {}, note: '', loading: true, error: '', busy: false, formError: '', confirmReopen: false, history: [],

      init() { this.load(); this.loadHistory(); },

      async load() {
        this.loading = true; this.error = ''; this.formError = '';
        try {
          const r = await App.api('/api/day-close/summary/', { query: { date: this.date } });
          this.data = r.data.summary; this.closed = r.data.closed;
          this.canClose = r.data.can_close; this.canReopen = r.data.can_reopen;
          this.counts = {}; this.note = '';
        } catch (e) { this.error = e.message; this.data = null; }
        this.loading = false;
      },
      async loadHistory() {
        try { const r = await App.api('/api/day-close/', { query: { page_size: 14 } }); this.history = r.data.results || []; } catch (e) { /* ignore */ }
      },
      pick(d) { this.date = d; this.load(); },

      lines() { return this.closed ? this.closed.lines : (this.data ? this.data.accounts : []); },
      counted(a) { return this.closed ? a.counted : this.counts[a.account_id]; },
      diff(a) {
        if (this.closed) return a.difference;
        const c = this.counts[a.account_id];
        return (c === undefined || c === '' || c === null) ? null : n(c) - n(a.expected);
      },
      get totalDiff() {
        if (this.closed) return this.closed.difference;
        return (this.data ? this.data.accounts : []).reduce((s, a) => { const d = this.diff(a); return d === null ? s : s + d; }, 0);
      },
      get anyCounted() { return Object.values(this.counts).some(v => v !== '' && v !== null && v !== undefined); },
      fillExpected() { (this.data.accounts || []).forEach(a => { this.counts[a.account_id] = a.expected; }); },

      async close() {
        if (this.busy) return;
        this.busy = true; this.formError = '';
        try {
          await App.api('/api/day-close/', { method: 'POST', body: { date: this.date, counts: this.counts, note: this.note.trim() } });
          await this.load(); this.loadHistory();
        } catch (e) { this.formError = e.message; }
        this.busy = false;
      },
      async reopen() {
        if (this.busy || !this.closed) return;
        this.busy = true;
        try { await App.api('/api/day-close/' + this.closed.id + '/', { method: 'DELETE' }); this.confirmReopen = false; await this.load(); this.loadHistory(); }
        catch (e) { this.formError = e.message; }
        this.busy = false;
      },
      taka: (v) => App.taka(v),
      signed(v) { return (v > 0 ? '+' : '') + App.taka(v); },
    };
  };
})();
