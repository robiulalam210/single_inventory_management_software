/*
 * Expiry Alerts — ব্যাচ/মেয়াদ অনুযায়ী মেয়াদ-পেরোনো ও শিগগিরই-পেরোবে এমন মাল।
 *   তালিকা:   GET  /api/reports/expiry-alerts/?status=all&days=   (reports/expiry_views.py)
 *   write-off: POST /api/reports/expiry-alerts/<id>/write-off/     — পেরোনো ব্যাচের বাকিটা স্টক থেকে বাদ + Bad Stock এ
 * সব ব্যাচ একবারে আনা হয়; "দেখাও" বাছাই আর search browser এই হয় (ছোট দোকানে ব্যাচ কম)।
 */
(function () {
  'use strict';

  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const fmtDate = (s) => {
    if (!s) return '—';
    const d = new Date(String(s).length === 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  window.expiryPage = function (opts) {
    return {
      canWriteOff: !!(opts && opts.canWriteOff),
      days: 30,
      f: { view: 'alerts', q: '' },
      data: null,
      loading: true,
      error: '',
      wo: null,
      reason: '',
      woError: '',
      busy: false,
      toast: '',
      _toast: null,

      init() {
        const p = new URLSearchParams(location.search);
        const d = parseInt(p.get('days') || '', 10);
        if (d >= 1 && d <= 365) this.days = d;
        if (['alerts', 'expired', 'expiring', 'ok', 'all'].includes(p.get('view'))) this.f.view = p.get('view');
        this.fetch();
      },

      async fetch() {
        this.loading = true;
        this.error = '';
        try {
          const r = await App.api('/api/reports/expiry-alerts/', { query: { status: 'all', days: this.days } });
          this.data = r.data;
        } catch (e) {
          this.error = e.message;
          this.data = null;
        }
        this.loading = false;
      },

      setDays(v) {
        v = Math.round(n(v));
        this.days = Math.max(1, Math.min(365, v || 30));
        this.sync();
        this.fetch();
      },
      setView(k) { this.f.view = k; this.sync(); },
      sync() {
        const p = new URLSearchParams();
        if (this.days !== 30) p.set('days', this.days);
        if (this.f.view !== 'alerts') p.set('view', this.f.view);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },

      get views() {
        const c = (this.data && this.data.counts) || { expired: 0, expiring: 0, ok: 0, total: 0 };
        return [
          { key: 'alerts', label: 'Needs attention', count: c.expired + c.expiring },
          { key: 'expired', label: 'Expired', count: c.expired },
          { key: 'expiring', label: 'Expiring soon', count: c.expiring },
          { key: 'ok', label: 'Fine for now', count: c.ok },
          { key: 'all', label: 'All', count: c.total },
        ];
      },
      get shown() {
        const rows = (this.data && this.data.batches) || [];
        const q = this.f.q.trim().toLowerCase();
        return rows.filter(b => {
          if (this.f.view === 'alerts' && b.status === 'ok') return false;
          if (['expired', 'expiring', 'ok'].includes(this.f.view) && b.status !== this.f.view) return false;
          if (!q) return true;
          return [b.product_name, b.sku, b.batch_no, b.supplier, b.purchase_invoice].some(v => String(v || '').toLowerCase().includes(q));
        });
      },
      get atRisk() { return this.data ? n(this.data.value.expired) + n(this.data.value.expiring) : 0; },

      label(b) {
        const d = n(b.days_left);
        if (d < 0) return 'Expired ' + Math.abs(d) + (Math.abs(d) === 1 ? ' day' : ' days') + ' ago';
        if (d === 0) return 'Expires today';
        return d + (d === 1 ? ' day left' : ' days left');
      },

      ask(b) { this.wo = b; this.reason = ''; this.woError = ''; },
      async writeOff() {
        if (!this.wo || this.busy) return;
        this.busy = true;
        this.woError = '';
        try {
          const r = await App.api('/api/reports/expiry-alerts/' + this.wo.id + '/write-off/', { method: 'POST', body: { reason: this.reason } });
          this.say(r.message || 'Written off');
          this.wo = null;
          await this.fetch();
        } catch (e) {
          this.woError = e.message;
        }
        this.busy = false;
      },
      say(t) { this.toast = t; clearTimeout(this._toast); this._toast = setTimeout(() => { this.toast = ''; }, 2600); },

      taka: (v) => App.taka(v),
      qty: (v) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(n(v)),
      fmtDate,
    };
  };
})();
