/*
 * My Dashboard — desktop app এর dashboard এর একই data, একই API থেকে।
 *  • /api/reports/dashboard/?dateFilter=  → বিক্রি, কেনা, খরচ, লাভ, টাকার প্রবাহ, stock সতর্কতা, সাম্প্রতিক কাজ
 *  • /api/accounts/                       → account balance (Accounts দেখার অনুমতি থাকলে)
 *  • /api/reports/top-products/ , low-stock-alert/ → (Reports দেখার অনুমতি থাকলে)
 *  • /api/reports/dashboard-trends/?days=   → চার্ট: শেষ ৭/৩০ দিনের বিক্রি-কেনা-খরচ + খরচের head ভাগ
 *  • /api/reports/dashboard-charts/?months=&days= → চার্ট: মাসভিত্তিক লাভ, দৈনিক লাভ-ক্ষতি, category অনুযায়ী স্টক মূল্য
 *  • account balance ভাগের চার্ট /api/accounts/ এর data থেকেই আঁকা হয়
 *  • /api/reports/expiry-alerts/            → মেয়াদ শেষ হওয়ার সতর্কতা কার্ড (Reports দেখার অনুমতি থাকলে)
 * একটা অংশ ব্যর্থ হলে বাকিগুলো ঠিকই দেখায়।
 */

/* ───────── চার্ট helper (Chart.js, vendor/chart-*.umd.js) ─────────
 * Chart instance Alpine এর বাইরে রাখা হয়েছে — Alpine এর reactive proxy এর ভেতরে Chart.js ঠিক চলে না।
 * রং CSS variable থেকে পড়া হয়, তাই light/dark দুই theme এই মানায়।
 */
const _charts = {};
const _compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });
const _css = (name, fallback) => (getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback);
const _isDark = () => {
  const t = document.documentElement.getAttribute('data-theme');
  if (t) return t === 'dark';
  return !!(window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
};
const _reduceMotion = () => !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
const _shortDate = (iso) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
};
const _monthLabel = (ym) => {
  const [y, m] = ym.split('-').map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
};
const _longDate = (iso) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
};
function _draw(id, config) {
  const el = document.getElementById(id);
  if (!el || typeof Chart === 'undefined') return;
  let c = _charts[id];
  if (c && c.canvas !== el) { c.destroy(); c = _charts[id] = null; }
  if (c) { c.data = config.data; c.options = config.options; c.update(); }
  else _charts[id] = new Chart(el, config);
}
function _destroyAll() {
  Object.keys(_charts).forEach(k => { _charts[k].destroy(); delete _charts[k]; });
}

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
    trendDays: 7,
    trend: null,
    trendLoading: false,
    trendError: null,
    // নতুন চার্ট: মাসভিত্তিক লাভ / দৈনিক লাভ-ক্ষতি / স্টক মূল্য
    charts: null,
    chartsLoading: false,
    chartsError: null,
    months: 6,
    profitDays: 30,
    // মেয়াদ শেষ হওয়ার সতর্কতা
    expiry: null,

    init() {
      this.load();
      // theme বদলালে (toggle বা সিস্টেম) চার্টের রং নতুন করে আঁকা
      const redraw = () => this.drawCharts();
      new MutationObserver(redraw).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
      if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redraw);
      window.addEventListener('pagehide', _destroyAll);
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
        jobs.push(App.api('/api/reports/low-stock-alert/')
          .then(r => { this.low = ((r.data && r.data.report) || []).slice(0, 6); })
          .catch(() => { this.low = []; }));
      }
      jobs.push(this.loadTrend());
      jobs.push(this.loadCharts());
      if (perms.reports) {
        jobs.push(App.api('/api/reports/expiry-alerts/', { query: { days: 30, limit: 6 } })
          .then(r => { this.expiry = r.data || null; })
          .catch(() => { this.expiry = null; }));
      }
      await Promise.allSettled(jobs);
      this.loading = false;
      this.loadedAt = Date.now();
      this.$nextTick(() => this.drawCharts());
    },

    // ───── charts ─────
    setTrendDays(days) {
      if (this.trendDays === days) return;
      this.trendDays = days;
      this.loadTrend();
    },

    async loadTrend() {
      this.trendLoading = true;
      this.trendError = null;
      try {
        const res = await App.api('/api/reports/dashboard-trends/', { query: { days: this.trendDays } });
        this.trend = res.data;
      } catch (e) {
        this.trendError = e.message;
      }
      this.trendLoading = false;
      this.$nextTick(() => this.drawCharts());
    },

    setMonths(m) {
      if (this.months === m) return;
      this.months = m;
      this.loadCharts();
    },
    setProfitDays(d) {
      if (this.profitDays === d) return;
      this.profitDays = d;
      this.loadCharts();
    },
    async loadCharts() {
      this.chartsLoading = true;
      this.chartsError = null;
      try {
        const res = await App.api('/api/reports/dashboard-charts/', { query: { months: this.months, days: this.profitDays } });
        this.charts = res.data;
      } catch (e) {
        this.chartsError = e.message;
      }
      this.chartsLoading = false;
      this.$nextTick(() => this.drawCharts());
    },

    drawCharts() {
      if (typeof Chart === 'undefined') return;
      if (this.trend) this.drawTrendCharts();
      this.drawNewCharts();
    },

    drawNewCharts() {
      const dark = _isDark();
      const th = {
        text: _css('--ink-2', '#334155'),
        muted: _css('--muted', '#64748b'),
        grid: _css('--line', '#e2e8f0'),
        surface: _css('--surface', '#ffffff'),
      };
      const animation = _reduceMotion() ? false : { duration: 450 };
      const taka = (v) => App.taka(v);
      const good = dark ? '#4ade80' : '#16a34a';
      const bad = dark ? '#f87171' : '#dc2626';
      const blue = dark ? '#60a5fa' : '#2563eb';
      const palette = dark
        ? ['#60a5fa', '#c4a1ff', '#fb923c', '#4ade80', '#fbbf24', '#22d3ee', '#f472b6']
        : ['#2563eb', '#7c3aed', '#c2410c', '#16a34a', '#d97706', '#0891b2', '#db2777'];
      const legend = { position: 'bottom', labels: { color: th.text, usePointStyle: true, boxWidth: 8, boxHeight: 8, padding: 12 } };
      const yAxis = { border: { display: false }, grid: { color: th.grid }, ticks: { color: th.muted, maxTicksLimit: 6, callback: (v) => _compact.format(v) } };
      const xAxis = { grid: { display: false }, ticks: { color: th.muted, maxRotation: 0, autoSkip: true } };

      const c = this.charts && JSON.parse(JSON.stringify(this.charts));

      // ③ মাসভিত্তিক লাভ (bar: মোট লাভ ও নিট লাভ)
      if (c && c.monthly) {
        const mo = c.monthly;
        _draw('chart-monthly', {
          type: 'bar',
          data: {
            labels: mo.labels.map(_monthLabel),
            datasets: [
              { label: 'Gross profit', data: mo.gross_profit, backgroundColor: blue, borderRadius: 4, maxBarThickness: 28 },
              {
                label: 'Net profit', data: mo.net_profit, borderRadius: 4, maxBarThickness: 28,
                backgroundColor: (ctx) => (ctx.raw < 0 ? bad : good),
              },
            ],
          },
          options: {
            responsive: true, maintainAspectRatio: false, animation,
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend,
              tooltip: { callbacks: { label: (x) => ' ' + x.dataset.label + ': ' + taka(x.parsed.y) + (x.dataset.label === 'Net profit' && x.parsed.y < 0 ? ' (loss)' : '') } },
            },
            scales: { x: xAxis, y: yAxis },
          },
        });

        // ⑥ লাভ-ক্ষতির ট্রেন্ড (দৈনিক নিট লাভ; শূন্যের নিচে = ক্ষতি)
        const pt = c.profit_trend;
        const val = pt.net_profit;
        _draw('chart-pl', {
          type: 'line',
          data: {
            labels: pt.labels.map(_shortDate),
            datasets: [{
              label: 'Net profit / loss', data: val,
              borderColor: good, borderWidth: 2, cubicInterpolationMode: 'monotone',
              pointRadius: pt.days > 7 ? 0 : 3, pointHoverRadius: 5,
              pointBackgroundColor: (ctx) => (ctx.raw < 0 ? bad : good),
              segment: { borderColor: (ctx) => (ctx.p0.parsed.y < 0 || ctx.p1.parsed.y < 0 ? bad : good) },
              fill: { target: 'origin', above: good + '22', below: bad + '22' },
            }],
          },
          options: {
            responsive: true, maintainAspectRatio: false, animation,
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  title: (items) => _longDate(pt.labels[items[0].dataIndex]),
                  label: (x) => ' ' + (x.parsed.y < 0 ? 'Loss: ' : 'Profit: ') + taka(Math.abs(x.parsed.y)),
                },
              },
            },
            scales: {
              x: { grid: { display: false }, ticks: { color: th.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: pt.days > 7 ? 8 : 7 } },
              y: yAxis,
            },
          },
        });

        // ⑤ পণ্যের স্টক মূল্য (category অনুযায়ী, কেনা দামে)
        const cats = (c.stock_value && c.stock_value.by_category) || [];
        _draw('chart-stock', {
          type: 'bar',
          data: {
            labels: cats.map(x => x.name),
            datasets: [{
              label: 'Stock value (at cost)', data: cats.map(x => x.cost_value),
              backgroundColor: cats.map((x, i) => (x.name === 'Other' ? (dark ? '#64748b' : '#94a3b8') : palette[i % palette.length])),
              borderRadius: 4, maxBarThickness: 22,
            }],
          },
          options: {
            indexAxis: 'y',
            responsive: true, maintainAspectRatio: false, animation,
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  label: (x) => {
                    const k = cats[x.dataIndex];
                    return [' At cost: ' + taka(k.cost_value), ' At selling price: ' + taka(k.retail_value), ' ' + k.qty + ' pcs, ' + k.products + (k.products === 1 ? ' product' : ' products')];
                  },
                },
              },
            },
            scales: {
              x: { beginAtZero: true, border: { display: false }, grid: { color: th.grid }, ticks: { color: th.muted, maxTicksLimit: 5, callback: (v) => _compact.format(v) } },
              y: { grid: { display: false }, ticks: { color: th.text } },
            },
          },
        });
      }

      // ④ account balance ভাগ (doughnut — শুধু ধনাত্মক balance)
      const accs = this.accountSlices;
      if (accs.length) {
        const sum = accs.reduce((t, a) => t + a.value, 0);
        _draw('chart-accounts', {
          type: 'doughnut',
          data: {
            labels: accs.map(a => a.name),
            datasets: [{
              data: accs.map(a => a.value),
              backgroundColor: accs.map((a, i) => palette[i % palette.length]),
              borderColor: th.surface, borderWidth: 2, hoverOffset: 6,
            }],
          },
          options: {
            responsive: true, maintainAspectRatio: false, animation, cutout: '62%',
            plugins: {
              legend,
              tooltip: { callbacks: { label: (x) => ' ' + x.label + ': ' + taka(x.parsed) + (sum > 0 ? ' (' + ((x.parsed / sum) * 100).toFixed(1) + '%)' : '') } },
            },
          },
        });
      } else if (_charts['chart-accounts']) {
        _charts['chart-accounts'].destroy();
        delete _charts['chart-accounts'];
      }
    },

    drawTrendCharts() {
      const dark = _isDark();
      const th = {
        text: _css('--ink-2', '#334155'),
        muted: _css('--muted', '#64748b'),
        grid: _css('--line', '#e2e8f0'),
        surface: _css('--surface', '#ffffff'),
      };
      const animation = _reduceMotion() ? false : { duration: 450 };
      const t = JSON.parse(JSON.stringify(this.trend)); // Alpine proxy ছাড়া সাধারণ copy — Chart.js এর জন্য নিরাপদ
      const taka = (v) => App.taka(v);

      // ① শেষ ৭/৩০ দিনের বিক্রি–কেনা–খরচ (line)
      const col = dark
        ? { sales: '#60a5fa', purchases: '#c4a1ff', expenses: '#fb923c' }
        : { sales: '#2563eb', purchases: '#7c3aed', expenses: '#c2410c' };
      const line = (label, data, color, fill) => ({
        label, data, borderColor: color, backgroundColor: color + '22', fill,
        cubicInterpolationMode: 'monotone', borderWidth: 2, pointRadius: t.days > 7 ? 0 : 3, pointHoverRadius: 5,
        pointBackgroundColor: color,
      });
      _draw('chart-trend', {
        type: 'line',
        data: {
          labels: t.labels.map(_shortDate),
          datasets: [
            line('Sales', t.sales, col.sales, true),
            line('Purchases', t.purchases, col.purchases, false),
            line('Expenses', t.expenses, col.expenses, false),
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { position: 'bottom', labels: { color: th.text, usePointStyle: true, boxWidth: 8, boxHeight: 8, padding: 16 } },
            tooltip: {
              callbacks: {
                title: (items) => _longDate(t.labels[items[0].dataIndex]),
                label: (c) => ' ' + c.dataset.label + ': ' + taka(c.parsed.y),
              },
            },
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: th.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: t.days > 7 ? 8 : 7 } },
            y: { beginAtZero: true, border: { display: false }, grid: { color: th.grid }, ticks: { color: th.muted, maxTicksLimit: 5, callback: (v) => _compact.format(v) } },
          },
        },
      });

      // ② খরচ কোন head এ গেছে (doughnut)
      const heads = t.expense_by_head || [];
      const palette = dark
        ? ['#60a5fa', '#c4a1ff', '#fb923c', '#4ade80', '#fbbf24', '#22d3ee']
        : ['#2563eb', '#7c3aed', '#c2410c', '#16a34a', '#d97706', '#0891b2'];
      const total = heads.reduce((s, h) => s + n(h.total), 0);
      _draw('chart-expense', {
        type: 'doughnut',
        data: {
          labels: heads.map(h => h.name),
          datasets: [{
            data: heads.map(h => h.total),
            backgroundColor: heads.map((h, i) => h.name === 'Other' ? (dark ? '#64748b' : '#94a3b8') : palette[i % palette.length]),
            borderColor: th.surface, borderWidth: 2, hoverOffset: 6,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation, cutout: '62%',
          plugins: {
            legend: { position: 'bottom', labels: { color: th.text, usePointStyle: true, boxWidth: 8, boxHeight: 8, padding: 12 } },
            tooltip: {
              callbacks: {
                label: (c) => ' ' + c.label + ': ' + taka(c.parsed) + (total > 0 ? ' (' + ((c.parsed / total) * 100).toFixed(1) + '%)' : ''),
              },
            },
          },
        },
      });
    },

    // ───── নতুন চার্টের helper ─────
    get accountSlices() {
      return (this.accounts || []).filter(a => n(a.balance) > 0).map(a => ({ name: a.name, value: n(a.balance) }));
    },
    get accountOverdrawn() { return (this.accounts || []).filter(a => n(a.balance) < 0); },
    get accountsHaveData() { return this.accountSlices.length > 0; },
    get monthlyHasData() {
      const m = this.charts && this.charts.monthly;
      return !!m && [m.gross_profit, m.net_profit, m.sales].some(a => (a || []).some(v => n(v) !== 0));
    },
    get plHasData() {
      const t = this.charts && this.charts.profit_trend;
      return !!t && (t.net_profit || []).some(v => n(v) !== 0);
    },
    get plTotals() {
      const t = (this.charts && this.charts.profit_trend && this.charts.profit_trend.net_profit) || [];
      const sum = t.reduce((a, v) => a + n(v), 0);
      return { sum, profitDays: t.filter(v => n(v) > 0).length, lossDays: t.filter(v => n(v) < 0).length };
    },
    get stock() { return (this.charts && this.charts.stock_value) || { total_cost: 0, total_retail: 0, expected_margin: 0, product_count: 0, by_category: [] }; },
    get stockHasData() { return this.stock.by_category.length > 0; },
    get monthlySummary() {
      const m = this.charts && this.charts.monthly;
      if (!m) return '';
      return 'Monthly profit, last ' + m.months + ' months. ' + m.labels.map((l, i) => _monthLabel(l) + ': net ' + App.taka(m.net_profit[i])).join('; ') + '.';
    },
    get plSummary() {
      const t = this.plTotals;
      return 'Daily profit and loss, last ' + this.profitDays + ' days. Net ' + App.taka(t.sum) + ', ' + t.profitDays + ' profit days and ' + t.lossDays + ' loss days.';
    },
    get stockSummary() {
      return 'Stock value by category at cost: ' + this.stock.by_category.map(x => x.name + ' ' + App.taka(x.cost_value)).join(', ') + '.';
    },
    get accountsSummary() {
      return 'Account balance share: ' + this.accountSlices.map(a => a.name + ' ' + App.taka(a.value)).join(', ') + '.';
    },

    // ───── মেয়াদ শেষ হওয়ার সতর্কতা ─────
    get expiryHas() { return !!this.expiry && (n(this.expiry.counts && this.expiry.counts.expired) + n(this.expiry.counts && this.expiry.counts.expiring)) > 0; },
    expiryLabel(b) {
      const d = n(b.days_left);
      if (d < 0) return 'Expired ' + Math.abs(d) + (Math.abs(d) === 1 ? ' day' : ' days') + ' ago';
      if (d === 0) return 'Expires today';
      return d + (d === 1 ? ' day left' : ' days left');
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
    get trendHasData() {
      const t = this.trend;
      return !!t && [t.sales, t.purchases, t.expenses].some(a => (a || []).some(v => n(v) > 0));
    },
    get expenseHasData() { return !!this.trend && (this.trend.expense_by_head || []).length > 0; },
    get trendSummary() {
      const t = this.trend;
      if (!t) return '';
      const sum = (a) => (a || []).reduce((x, y) => x + n(y), 0);
      return 'Last ' + t.days + ' days. Sales ' + App.taka(sum(t.sales)) + ', purchases ' + App.taka(sum(t.purchases)) + ', expenses ' + App.taka(sum(t.expenses)) + '.';
    },
    get expenseSummary() {
      const h = (this.trend && this.trend.expense_by_head) || [];
      return h.length ? 'Expenses by head: ' + h.map(x => x.name + ' ' + App.taka(x.total)).join(', ') + '.' : 'No expenses recorded.';
    },
    // Best sellers এর পাশের ছোট বার: সবচেয়ে বেশি বিক্রির তুলনায় শতাংশ
    topPct(p) {
      const max = Math.max(1, ...(this.top || []).map(x => n(x.total_sold_price)));
      return Math.max(n(p.total_sold_price) > 0 ? 3 : 0, (n(p.total_sold_price) / max) * 100);
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
