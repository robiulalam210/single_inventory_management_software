/*
 * Customers — তালিকা, যোগ/সম্পাদনা, আর একজনের পুরো হিসাব।
 *   /api/customers/ (প্রতি page এ ৩০, net_due_amount দিয়ে সাজানো যায়)
 *   /api/customers-active/ (মোট হিসাবের জন্য সব)
 *   /api/reports/customer-ledger/ (statement — তারিখের ক্রমে, চলমান বাকি)
 */
(function () {
  'use strict';

  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const PAGE_SIZE = 30;
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const numFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
  const fmtDate = (s) => {
    if (!s) return '';
    const d = new Date(String(s).length === 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  function explain(e) {
    const d = e.data && e.data.data;
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const [k, v] = Object.entries(d)[0] || [];
      if (k) return (Array.isArray(v) ? v[0] : String(v));
    }
    return e.message;
  }

  window.customerList = function (perms, company) {
    return {
      perms, company,
      sorts: [
        { key: '-net_due_amount', label: 'Most owed' },
        { key: 'name', label: 'Name' },
        { key: '-date_created', label: 'Newest' },
      ],
      views: [
        { key: 'active', label: 'Active' },
        { key: 'due', label: 'Owe you' },
        { key: 'advance', label: 'Advance' },
        { key: 'special', label: 'Special' },
        { key: 'inactive', label: 'Inactive' },
        { key: 'all', label: 'All' },
      ],
      f: { q: '', view: 'active', sort: '-net_due_amount' },
      page: 1, rows: [], meta: { count: 0, total_pages: 1 }, tot: null, loading: true, error: null,
      sel: null, tab: 'overview', recentSales: null, recentPay: null,
      stPresets: [
        { key: 'month', label: 'This month' }, { key: '3m', label: 'Last 3 months' },
        { key: 'year', label: 'This year' }, { key: 'all', label: 'All time' }, { key: 'custom', label: 'Custom' },
      ],
      st: { preset: '3m', from: '', to: '', rows: null, summary: null, loading: false, error: '' },
      formOpen: false, form: {}, fe: {}, formError: '', formSaving: false,
      confirmDel: false, delError: '', deleting: false,
      toast: '', _req: 0, _t: null, _sreq: 0,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || '';
        this.f.view = p.get('view') || 'active';
        this.f.sort = p.get('sort') || '-net_due_amount';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        this.fetch();
        this.loadTotals();
        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 300); });
        ['f.view', 'f.sort'].forEach(k => this.$watch(k, () => this.reset()));
      },
      get filtered() { return !!(this.f.q || this.f.view !== 'active' || this.f.sort !== '-net_due_amount'); },
      clearAll() { this.f = { q: '', view: 'active', sort: '-net_due_amount' }; this.reset(); },
      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.meta.total_pages || p === this.page) return;
        this.page = p; this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },
      query() {
        const q = { search: this.f.q.trim(), ordering: this.f.sort, page: this.page, page_size: PAGE_SIZE };
        const v = this.f.view;
        if (v === 'inactive') q.is_active = 'false';
        else if (v !== 'all') q.is_active = 'true';
        if (v === 'due') q.amount_type = 'due';
        if (v === 'advance') q.amount_type = 'advance';
        if (v === 'special') q.special_customer = 'true';
        return q;
      },
      syncUrl() {
        const p = new URLSearchParams();
        if (this.f.q) p.set('q', this.f.q);
        if (this.f.view !== 'active') p.set('view', this.f.view);
        if (this.f.sort !== '-net_due_amount') p.set('sort', this.f.sort);
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },
      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null; this.syncUrl();
        try {
          const r = await App.api('/api/customers/', { query: this.query() });
          if (id !== this._req) return;
          const d = r.data || {};
          this.rows = d.results || [];
          this.meta = { count: d.count || 0, total_pages: d.total_pages || 1 };
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = [];
        }
        this.loading = false;
      },
      async loadTotals() {
        try {
          const all = listOf(await App.api('/api/customers-active/'));
          const t = { active: 0, sold: 0, paid: 0, due: 0, advance: 0, owing: 0 };
          all.forEach(c => {
            if (c.is_active) t.active++;
            t.sold += n(c.total_bought); t.paid += n(c.total_paid);
            t.due += n(c.total_due); t.advance += n(c.advance_balance);
            if (n(c.total_due) > 0) t.owing++;
          });
          this.tot = t;
        } catch (e) { this.tot = null; }
      },

      taka: (v) => App.taka(v),
      num: (v) => numFmt.format(n(v)),
      date: fmtDate,
      bought: (r) => n(r.total_bought),
      badge(r) {
        if (!r.is_active) return { label: 'Inactive', cls: 'st-cancelled' };
        if (n(r.total_due) > 0) return { label: 'Owes you', cls: 'st-pending' };
        if (n(r.advance_balance) > 0) return { label: 'Advance', cls: 'st-partial' };
        return { label: 'Settled', cls: 'st-paid' };
      },
      payFor(p) {
        if (p.payment_type === 'specific') return p.sale_invoice_no ? 'for ' + p.sale_invoice_no : 'one invoice';
        return p.payment_type === 'advance' ? 'advance' : 'toward dues';
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

      // ───── drawer ─────
      open(r) {
        this.sel = r; this.tab = 'overview'; this.recentSales = null; this.recentPay = null;
        this.st.rows = null; this.st.summary = null; this.st.error = '';
        document.body.style.overflow = 'hidden';
        const id = r.id;
        if (perms.sales) {
          App.api('/api/sales/', { query: { customer: id, page_size: 5 } })
            .then(x => { if (this.sel && this.sel.id === id) this.recentSales = listOf(x); })
            .catch(() => { this.recentSales = []; });
        }
        if (perms.receipts) {
          App.api('/api/money-receipts/', { query: { customer_id: id, page_size: 5 } })
            .then(x => { if (this.sel && this.sel.id === id) this.recentPay = listOf(x); })
            .catch(() => { this.recentPay = []; });
        }
      },
      shut() { this.sel = null; document.body.style.overflow = ''; },
      print() { window.print(); },

      // ───── statement ─────
      openStatement() {
        this.tab = 'statement';
        if (!this.st.rows) this.setStPreset(this.st.preset);
      },
      setStPreset(key) {
        this.st.preset = key;
        const t = new Date(); t.setHours(0, 0, 0, 0);
        if (key === 'month') { this.st.from = iso(new Date(t.getFullYear(), t.getMonth(), 1)); this.st.to = iso(t); }
        else if (key === '3m') { const s = new Date(t); s.setMonth(s.getMonth() - 3); this.st.from = iso(s); this.st.to = iso(t); }
        else if (key === 'year') { this.st.from = iso(new Date(t.getFullYear(), 0, 1)); this.st.to = iso(t); }
        else if (key === 'all') { this.st.from = '2000-01-01'; this.st.to = iso(t); }
        else { if (!this.st.from) this.st.from = iso(new Date(t.getFullYear(), t.getMonth(), 1)); if (!this.st.to) this.st.to = iso(t); }
        this.loadStatement();
      },
      async loadStatement() {
        if (!this.sel) return;
        if (this.st.from && this.st.to && this.st.from > this.st.to) [this.st.from, this.st.to] = [this.st.to, this.st.from];
        const id = ++this._sreq;
        this.st.loading = true; this.st.error = '';
        try {
          const r = await App.api('/api/reports/customer-ledger/', {
            query: { customer: this.sel.id, start: this.st.from, end: this.st.to, page_size: 1000 } });
          if (id !== this._sreq) return;
          const rep = r.data && r.data.report;
          this.st.rows = Array.isArray(rep) ? rep : ((rep && rep.results) || []);
          this.st.summary = r.data && r.data.summary;
        } catch (e) {
          if (id !== this._sreq) return;
          this.st.error = e.message; this.st.rows = []; this.st.summary = null;
        }
        this.st.loading = false;
      },
      get stRangeText() {
        if (this.st.preset === 'all') return 'All time, up to ' + fmtDate(this.st.to);
        return fmtDate(this.st.from) + ' – ' + fmtDate(this.st.to);
      },
      balanceText(v) { return n(v) < 0 ? App.taka(-n(v)) + ' Adv' : App.taka(v); },

      // ───── add / edit ─────
      openForm(r) {
        this.form = r
          ? { id: r.id, name: r.name || '', phone: r.phone || '', email: r.email || '', address: r.address || '',
              special_customer: !!r.special_customer, is_active: !!r.is_active }
          : { id: null, name: '', phone: '', email: '', address: '', special_customer: false, is_active: true };
        this.fe = {}; this.formError = ''; this.formOpen = true;
        this.$nextTick(() => this.$refs.cfName && this.$refs.cfName.focus());
      },
      async saveForm() {
        const f = this.form, fe = {};
        if (!f.name.trim()) fe.name = 'Enter the customer name.';
        const phone = f.phone.replace(/[\s-]/g, '');
        if (phone && phone.replace(/\D/g, '').length < 10) fe.phone = 'Phone number needs at least 10 digits.';
        if (f.email.trim() && !/^\S+@\S+\.\S+$/.test(f.email.trim())) fe.email = 'This email does not look right.';
        this.fe = fe;
        if (Object.keys(fe).length || this.formSaving) return;
        this.formSaving = true; this.formError = '';
        const body = {
          name: f.name.trim(), phone: phone || null, email: f.email.trim() || null, address: f.address.trim(),
          special_customer: f.special_customer, is_active: f.is_active,
        };
        try {
          const r = f.id
            ? await App.api(`/api/customers/${f.id}/`, { method: 'PATCH', body })
            : await App.api('/api/customers/', { method: 'POST', body });
          this.formOpen = false;
          this.flash(f.id ? 'Customer updated.' : `${body.name} added.`);
          if (this.sel && r.data && this.sel.id === r.data.id) this.sel = Object.assign({}, this.sel, r.data);
          this.fetch(); this.loadTotals();
        } catch (e) {
          this.formError = /unique|already exists/i.test(explain(e)) ? 'Another customer already has this phone number.' : explain(e);
        }
        this.formSaving = false;
      },
      askDelete() { this.delError = ''; this.confirmDel = true; },
      async remove() {
        if (!this.sel || this.deleting) return;
        this.deleting = true; this.delError = '';
        try {
          const r = await App.api(`/api/customers/${this.sel.id}/`, { method: 'DELETE' });
          this.confirmDel = false;
          this.flash(r.message || 'Done.');
          this.shut(); this.fetch(); this.loadTotals();
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
