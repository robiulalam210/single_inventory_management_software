/*
 * My Dashboard — desktop app এর dashboard এর একই data, একই API থেকে।
 *  • /api/reports/dashboard/?dateFilter=  → বিক্রি, কেনা, খরচ, লাভ, টাকার প্রবাহ, stock সতর্কতা, সাম্প্রতিক কাজ
 *  • /api/accounts/                       → account balance (Accounts দেখার অনুমতি থাকলে)
 *  • /api/reports/top-products/ , low-stock/ → (Reports দেখার অনুমতি থাকলে)
 * একটা অংশ ব্যর্থ হলে বাকিগুলো ঠিকই দেখায়।
 */
function dashboard(perms) {
  const n = (v) => Number(v || 0);
  const qty = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });

  return {
    perms,
    period: 'current_day',
    periods: [
      { key: 'current_day', label: 'Today' },
      { key: 'this_month', label: 'This month' },
      { key: 'lifeTime', label: 'All time' },
    ],
    loading: true,
    error: null,
    d: null,
    accounts: null,
    top: null,
    low: null,
    tab: 'sales',
    loadedAt: null,

    init() {
      this.load();
      // tab এ ফিরে এলে নতুন data (৫ মিনিটের বেশি পুরনো হলে)
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden && this.loadedAt && Date.now() - this.loadedAt > 5 * 60 * 1000) this.load();
      });
    },

    setPeriod(key) {
      if (this.period === key) return;
      this.period = key;
      this.load();
    },

    async load() {
      this.loading = true;
      this.error = null;
      try {
        const res = await App.api('/api/reports/dashboard/', { query: { dateFilter: this.period } });
        this.d = res.data;
      } catch (e) {
        this.error = e.message;
        this.loading = false;
        return;
      }
      const range = this.d.date_filter_info || {};
      const jobs = [];
      if (perms.accounts) {
        jobs.push(App.api('/api/accounts/', { query: { no_pagination: 'true' } })
          .then(r => { this.accounts = ((r.data && r.data.results) || r.data || []).filter(a => a.is_active !== false); })
          .catch(() => { this.accounts = []; }));
      }
      if (perms.reports) {
        jobs.push(App.api('/api/reports/top-products/', { query: { start: range.start_date, end: range.end_date } })
          .then(r => { this.top = ((r.data && r.data.report) || []).slice(0, 5); })
          .catch(() => { this.top = []; }));
        jobs.push(App.api('/api/reports/low-stock/')
          .then(r => { this.low = ((r.data && r.data.report) || []).slice(0, 6); })
          .catch(() => { this.low = []; }));
      }
      await Promise.allSettled(jobs);
      this.loading = false;
      this.loadedAt = Date.now();
    },

    // ───── helpers for the template ─────
    taka: (v) => App.taka(v),
    qty: (v) => qty.format(n(v)),
    get m() { return (this.d && this.d.today_metrics) || {}; },
    get pl() { return (this.d && this.d.profit_loss) || {}; },
    get periodLabel() { return (this.periods.find(p => p.key === this.period) || {}).label; },
    get periodNoun() {
      return { current_day: 'today', this_month: 'this month', lifeTime: 'so far' }[this.period];
    },

    get cash() {
      const c = (this.d && this.d.financial_summary && this.d.financial_summary.cash_components) || {};
      const rows = [
        { label: 'Money in', hint: 'Sales collected and other income', value: n(c.cash_in), dir: 'in' },
        { label: 'Purchases paid', hint: 'Paid to suppliers', value: n(c.cash_out_purchases), dir: 'out' },
        { label: 'Expenses', hint: 'Shop expenses', value: n(c.cash_out_expenses), dir: 'out' },
      ];
      const max = Math.max(1, ...rows.map(r => r.value));
      rows.forEach(r => { r.pct = Math.max(r.value > 0 ? 2 : 0, (r.value / max) * 100); });
      return rows;
    },
    get netCash() {
      const fs = (this.d && this.d.financial_summary) || {};
      return n(fs.operating_cash_flow);
    },

    get recent() {
      const ra = (this.d && this.d.recent_activities) || {};
      return {
        sales: (ra.sales || []).map(s => ({ title: s.invoice_no, sub: s.customer, amount: s.amount, due: s.due_amount, date: s.date })),
        purchases: (ra.purchases || []).map(p => ({ title: p.invoice_no, sub: p.supplier, amount: p.amount, due: p.due_amount, date: p.date })),
        expenses: (ra.expenses || []).map(x => ({ title: x.head || 'Expense', sub: x.note || x.account || x.invoice_no, amount: x.amount, due: 0, date: x.expense_date })),
      }[this.tab] || [];
    },
    get tabs() {
      const t = [];
      if (perms.sales) t.push({ key: 'sales', label: 'Sales' });
      if (perms.purchases) t.push({ key: 'purchases', label: 'Purchases' });
      if (perms.expense) t.push({ key: 'expenses', label: 'Expenses' });
      if (t.length && !t.some(x => x.key === this.tab)) this.tab = t[0].key;
      return t;
    },
    get totalBalance() { return (this.accounts || []).reduce((s, a) => s + n(a.balance), 0); },

    date(s) {
      if (!s) return '';
      const d = new Date(s);
      if (isNaN(d)) return s;
      return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    },
  };
}
