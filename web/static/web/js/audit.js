/*
 * Audit Log — কে, কখন, কোন app/device থেকে, কোন record এ কী বদলেছে। শুধু দেখা।
 *   GET /api/sync/audit/       (page, page_size, model, user_id, action, source, date_from, date_to, q)
 *   GET /api/sync/audit/meta/  (একই filter; dropdown এর বিকল্প ও সংখ্যা, আর উপরের summary)
 * 
 */
(function () {
  'use strict';

  const pad = (x) => String(x).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const PAGE_SIZE = 30;
  const SOURCE = { web: 'Web app', desktop: 'Desktop app', desktop_offline: 'Desktop (offline)', mobile: 'Mobile app', mobile_offline: 'Mobile (offline)', api: 'API', system: 'System' };
  const cap = (s) => s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : '—';

  function rangeOf(key) {
    const t = today();
    if (key === 'today') return [iso(t), iso(t)];
    if (key === '7d') { const s = new Date(t); s.setDate(s.getDate() - 6); return [iso(s), iso(t)]; }
    if (key === 'month') return [iso(new Date(t.getFullYear(), t.getMonth(), 1)), iso(t)];
    return ['', ''];
  }
  function dt(s) {
    if (!s) return '—';
    const d = new Date(s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) + ', ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' });
  }
  function pagesOf(c, t) {
    const out = [];
    for (let i = 1; i <= t; i++) {
      if (i === 1 || i === t || Math.abs(i - c) <= 2) out.push(i);
      else if (out[out.length - 1] !== '…') out.push('…');
    }
    return out;
  }

  window.auditPage = function () {
    return {
      presets: [
        { key: 'today', label: 'Today' }, { key: '7d', label: 'Last 7 days' }, { key: 'month', label: 'This month' },
        { key: 'all', label: 'All time' }, { key: 'custom', label: 'Custom' },
      ],
      actions: [{ key: '', label: 'All' }, { key: 'create', label: 'Created' }, { key: 'update', label: 'Changed' }, { key: 'delete', label: 'Deleted' }],
      f: { q: '', action: '', model: '', user: '', source: '', preset: 'today', d1: '', d2: '' },
      meta: null, models: [], users: [], sources: [], isSuper: false,
      page: 1, rows: [], total: 0, pages_n: 1,
      loading: true, error: null, sel: null, _req: 0, _mreq: 0, _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        const f = this.f;
        f.q = p.get('q') || ''; f.action = p.get('action') || ''; f.model = p.get('model') || ''; f.user = p.get('user') || '';
        f.source = p.get('source') || '';
        f.preset = p.get('period') || 'today'; f.d1 = p.get('d1') || ''; f.d2 = p.get('d2') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        if (f.preset !== 'custom') [f.d1, f.d2] = rangeOf(f.preset);
        this.fetch();
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 350); });
        ['f.action', 'f.model', 'f.user', 'f.source'].forEach(k => this.$watch(k, () => this.reset()));
      },

      setPreset(key) { this.f.preset = key; if (key !== 'custom') { [this.f.d1, this.f.d2] = rangeOf(key); this.reset(); } },
      applyCustom() { if (this.f.d1 && this.f.d2 && this.f.d1 > this.f.d2) [this.f.d1, this.f.d2] = [this.f.d2, this.f.d1]; this.reset(); },
      clearAll() { this.f = { q: '', action: '', model: '', user: '', source: '', preset: 'today', d1: '', d2: '' }; [this.f.d1, this.f.d2] = rangeOf('today'); this.reset(); },
      get filtered() { const f = this.f; return !!(f.q || f.action || f.model || f.user || f.source || f.preset !== 'today'); },
      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.pages_n || p === this.page) return;
        this.page = p; this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },

      query() {
        const f = this.f;
        return { q: f.q.trim(), action: f.action, model: f.model, user_id: f.user, source: f.source, date_from: f.d1, date_to: f.d2 };
      },
      syncUrl() {
        const p = new URLSearchParams(), f = this.f;
        if (f.q) p.set('q', f.q); if (f.action) p.set('action', f.action); if (f.model) p.set('model', f.model);
        if (f.user) p.set('user', f.user); if (f.source) p.set('source', f.source);
        if (f.preset !== 'today') p.set('period', f.preset);
        if (f.preset === 'custom') { if (f.d1) p.set('d1', f.d1); if (f.d2) p.set('d2', f.d2); }
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },
      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null; this.syncUrl();
        const q = this.query();
        this.loadMeta(q);
        try {
          const r = await App.api('/api/sync/audit/', { query: Object.assign({ page: this.page, page_size: PAGE_SIZE }, q) });
          if (id !== this._req) return;
          const d = r.data || {};
          this.rows = d.results || []; this.total = d.count || 0; this.pages_n = d.total_pages || 1;
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = [];
        }
        this.loading = false;
      },
      // dropdown এর বিকল্প ও সংখ্যা — বাকি filter মেনে; ব্যর্থ হলেও তালিকা কাজ করে
      async loadMeta(q) {
        const id = ++this._mreq;
        try {
          const r = await App.api('/api/sync/audit/meta/', { query: q });
          if (id !== this._mreq) return;
          const m = r.data || {};
          this.meta = m.summary || null; this.isSuper = !!m.is_super_admin;
          this.models = (m.models || []).map(x => ({ value: x.model, label: this.modelName(x.model), sub: x.count + '' }));
          this.users = (m.users || []).map(x => ({ value: String(x.id), label: x.name || 'Unknown', sub: x.count + '' }));
          this.sources = (m.sources || []).map(x => ({ value: x.source, label: this.sourceName(x.source), sub: x.count + '' }));
        } catch (e) { /* meta ছাড়াও চলে */ }
      },

      // ───── display ─────
      num: (v) => new Intl.NumberFormat('en-US').format(Number(v || 0)),
      dt, cap,
      modelName(label) {
        const base = String(label || '').split('.').pop();
        return base.replace(/([a-z0-9])([A-Z])/g, '$1 $2') || '—';
      },
      sourceName: (s) => SOURCE[s] || cap(String(s || '').replace(/_/g, ' ')),
      actionName: (a) => ({ create: 'Created', update: 'Changed', delete: 'Deleted' }[a] || cap(a)),
      who: (r) => r.user || 'System (automatic)',
      summaryLine(r) {
        const n = (r.changes || []).length;
        if (r.action === 'create') return n ? n + ' fields set' : 'New record';
        if (r.action === 'delete') return 'Record removed';
        return n ? (n === 1 ? r.changes[0].field.replace(/_/g, ' ') : n + ' fields') : 'No field changes';
      },
      val(v) {
        if (v === null || v === undefined || v === '') return null;
        const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
        return s.length > 300 ? s.slice(0, 300) + '…' : s;
      },
      get from() { return this.total ? (this.page - 1) * PAGE_SIZE + 1 : 0; },
      get to() { return Math.min(this.page * PAGE_SIZE, this.total); },
      get pages() { return pagesOf(this.page, this.pages_n); },

      open(r) { this.sel = r; document.body.style.overflow = 'hidden'; },
      shut() { this.sel = null; document.body.style.overflow = ''; },
    };
  };
})();
