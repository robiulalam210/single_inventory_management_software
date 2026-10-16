/*
 * Sale List — /api/sales/ (তালিকা, প্রতি page এ ৩০টা) + /api/sales/summary/ (একই filter এ মোট হিসাব)।
 * filter গুলো URL এ থাকে (?q=&status=&from=&to=…) — refresh / back / link share করলেও একই তালিকা।
 */
function salesList(opts) {
  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const PAGE_SIZE = 30; // server এর সর্বোচ্চ

  const PRESETS = [
    { key: 'today', label: 'Today' },
    { key: '7d', label: 'Last 7 days' },
    { key: 'month', label: 'This month' },
    { key: 'all', label: 'All time' },
    { key: 'custom', label: 'Custom' },
  ];

  function rangeOf(key) {
    const t = today();
    if (key === 'today') return [iso(t), iso(t)];
    if (key === '7d') { const s = new Date(t); s.setDate(s.getDate() - 6); return [iso(s), iso(t)]; }
    if (key === 'month') return [iso(new Date(t.getFullYear(), t.getMonth(), 1)), iso(t)];
    return ['', ''];
  }

  return {
    presets: PRESETS,
    statuses: [
      { key: '', label: 'All' },
      { key: 'paid', label: 'Paid' },
      { key: 'partial', label: 'Partial' },
      { key: 'pending', label: 'Unpaid' },
      { key: 'due', label: 'Has due' },
    ],
    f: { q: '', status: '', customer: '', seller: '', preset: 'month', from: '', to: '' },
    page: 1,
    rows: [],
    meta: { count: 0, total_pages: 1 },
    sum: null,
    loading: true,
    error: null,
    sel: null,
    customers: [],
    sellers: [],
    canSeeUsers: !!opts.canSeeUsers,
    _req: 0,
    _t: null,

    init() {
      const p = new URLSearchParams(location.search);
      this.f.q = p.get('q') || '';
      this.f.status = p.get('status') || '';
      this.f.customer = p.get('customer') || '';
      this.f.seller = p.get('seller') || '';
      this.f.preset = p.get('period') || 'month';
      this.f.from = p.get('from') || '';
      this.f.to = p.get('to') || '';
      this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
      if (this.f.preset !== 'custom') [this.f.from, this.f.to] = rangeOf(this.f.preset);

      this.loadOptions();
      this.fetch();

      // নতুন sale save এর পর ?open=<id> দিয়ে আসে — সরাসরি invoice খুলে দেখাই (print এর জন্য)
      const openId = parseInt(p.get('open') || '', 10);
      // (এই endpoint টা wrapper ছাড়া সরাসরি sale ফেরত দেয়)
      if (openId) App.api(`/api/sales/${openId}/`).then(r => {
        const sale = r && r.data && r.data.id ? r.data : (r && r.id ? r : null);
        if (sale) this.open(sale);
      }).catch(() => {});

      this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 350); });
      ['f.status', 'f.customer', 'f.seller'].forEach(k => this.$watch(k, () => this.reset()));
    },

    async loadOptions() {
      App.api('/api/customers-active/').then(r => {
        const list = Array.isArray(r.data) ? r.data : (r.data && r.data.results) || [];
        this.customers = list.map(c => ({ value: String(c.id), label: c.name, sub: c.phone || c.client_no || '' }));
      }).catch(() => {});
      if (this.canSeeUsers) {
        App.api('/api/users/', { query: { status: 1 } }).then(r => {
          const list = Array.isArray(r.data) ? r.data : (r.data && r.data.results) || [];
          this.sellers = list.map(u => ({ value: String(u.id), label: u.full_name || u.username, sub: u.username }));
        }).catch(() => { this.canSeeUsers = false; });
      }
    },

    setPreset(key) {
      this.f.preset = key;
      if (key !== 'custom') { [this.f.from, this.f.to] = rangeOf(key); this.reset(); }
    },
    applyCustom() {
      if (this.f.from && this.f.to && this.f.from > this.f.to) [this.f.from, this.f.to] = [this.f.to, this.f.from];
      this.reset();
    },
    clearAll() {
      this.f = { q: '', status: '', customer: '', seller: '', preset: 'month', from: '', to: '' };
      [this.f.from, this.f.to] = rangeOf('month');
      this.reset();
    },
    get filtered() {
      return !!(this.f.q || this.f.status || this.f.customer || this.f.seller || this.f.preset !== 'month');
    },

    reset() { this.page = 1; this.fetch(); },
    go(p) {
      if (p < 1 || p > this.meta.total_pages || p === this.page) return;
      this.page = p;
      this.fetch();
      document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    query() {
      const q = {
        search: this.f.q.trim(),
        customer: this.f.customer,
        seller: this.f.seller,
        start_date: this.f.from,
        end_date: this.f.to,
      };
      if (this.f.status === 'due') q.due_only = 'true';
      else if (this.f.status) q.payment_status = this.f.status;
      return q;
    },

    syncUrl() {
      const p = new URLSearchParams();
      if (this.f.q) p.set('q', this.f.q);
      if (this.f.status) p.set('status', this.f.status);
      if (this.f.customer) p.set('customer', this.f.customer);
      if (this.f.seller) p.set('seller', this.f.seller);
      if (this.f.preset !== 'month') p.set('period', this.f.preset);
      if (this.f.preset === 'custom') { if (this.f.from) p.set('from', this.f.from); if (this.f.to) p.set('to', this.f.to); }
      if (this.page > 1) p.set('page', this.page);
      const s = p.toString();
      history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
    },

    async fetch() {
      const id = ++this._req; // পুরনো request দেরিতে ফিরলে নতুন ফলাফল মুছে দেবে না
      this.loading = true;
      this.error = null;
      this.syncUrl();
      const q = this.query();
      try {
        const [list, sum] = await Promise.all([
          App.api('/api/sales/', { query: Object.assign({ page: this.page, page_size: PAGE_SIZE }, q) }),
          App.api('/api/sales/summary/', { query: q }).catch(() => null),
        ]);
        if (id !== this._req) return;
        const d = list.data || {};
        this.rows = d.results || [];
        this.meta = { count: d.count || 0, total_pages: d.total_pages || 1 };
        this.sum = sum ? sum.data : null;
      } catch (e) {
        if (id !== this._req) return;
        this.error = e.message;
        this.rows = [];
      }
      this.loading = false;
    },

    // ───── display helpers ─────
    taka: (v) => App.taka(v),
    num: (v) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(Number(v || 0)),
    date(s) { return new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }); },
    time(s) { return new Date(s).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); },
    statusLabel(s) { return { paid: 'Paid', partial: 'Partial', pending: 'Unpaid', overdue: 'Overdue' }[s] || s || '—'; },
    // method আর account এর নাম একই হলে ("Cash, Cash") একবারই দেখাই
    payWith(r) {
      const parts = [r.payment_method, r.account_name].filter(Boolean);
      const uniq = parts.filter((v, i) => parts.findIndex(x => x.toLowerCase() === v.toLowerCase()) === i);
      return uniq.join(', ') || '—';
    },
    customerName(r) { return r.customer_name || 'Walk-in customer'; },
    get from() { return this.meta.count ? (this.page - 1) * PAGE_SIZE + 1 : 0; },
    get to() { return Math.min(this.page * PAGE_SIZE, this.meta.count); },
    get pages() {
      // ১ … ৪ ৫ [৬] ৭ ৮ … ২০
      const t = this.meta.total_pages, c = this.page, out = [];
      for (let i = 1; i <= t; i++) {
        if (i === 1 || i === t || Math.abs(i - c) <= 2) out.push(i);
        else if (out[out.length - 1] !== '…') out.push('…');
      }
      return out;
    },
    get periodText() {
      if (this.f.preset === 'all' || (!this.f.from && !this.f.to)) return 'All time';
      const fmt = (s) => new Date(s + 'T00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
      if (this.f.from === this.f.to) return fmt(this.f.from);
      return `${this.f.from ? fmt(this.f.from) : 'Start'} – ${this.f.to ? fmt(this.f.to) : 'today'}`;
    },

    // ───── invoice drawer ─────
    open(r) { this.sel = r; document.body.style.overflow = 'hidden'; },
    shut() {
      this.sel = null;
      document.body.style.overflow = '';
      if (new URLSearchParams(location.search).has('open')) this.syncUrl();
    },
    /*
     * backend এর Sale.calculate_totals() এর হুবহু একই হিসাব — percent হলে net total এর উপর,
     * না হলে সরাসরি টাকা। তাই invoice এর প্রতিটা লাইন app এর সাথে পয়সা পর্যন্ত মেলে।
     */
    lines(r) {
      const base = Number(r.net_total || r.gross_total || 0);
      const round2 = (v) => Math.round(v * 100) / 100;
      const charge = (amount, type) => {
        const a = Number(amount || 0);
        if (a <= 0) return 0;
        return type === 'percent' ? round2(base * a / 100) : a;
      };
      const tag = (amount, type) => (type === 'percent' && Number(amount) > 0 ? ` (${Number(amount)}%)` : '');
      const rows = [
        ['Subtotal', Number(r.gross_total || 0)],
        ['Discount' + tag(r.overall_discount, r.overall_discount_type), -charge(r.overall_discount, r.overall_discount_type)],
        ['VAT' + tag(r.overall_vat_amount, r.overall_vat_type), charge(r.overall_vat_amount, r.overall_vat_type)],
        ['Service charge' + tag(r.overall_service_charge, r.overall_service_type), charge(r.overall_service_charge, r.overall_service_type)],
        ['Delivery charge' + tag(r.overall_delivery_charge, r.overall_delivery_type), charge(r.overall_delivery_charge, r.overall_delivery_type)],
      ];
      return rows.filter(([, v], i) => i === 0 || v !== 0);
    },
    itemLine(it) {
      const d = Number(it.discount || 0);
      if (!d) return '';
      return it.discount_type === 'percent' ? `${d}% off` : `${App.taka(d)} off`;
    },
    print() { window.print(); },
  };
}
