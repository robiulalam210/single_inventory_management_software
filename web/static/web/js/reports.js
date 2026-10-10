/*
 * Reports — ১১টা report, একটাই কাঠামো (reportPage)। প্রতিটা report এর পার্থক্য শুধু REPORTS এ:
 *   কোন API, কোন filter, উপরে কোন মোট, table এ কোন column।
 *   API: /api/reports/<name>/  — সবার উত্তর { report, summary }; তারিখ আসে `start` / `end` নামে।
 *   Print: browser এর print (A4); CSV: সব সারি এনে Excel এ খোলার মতো।
 */
(function () {
  'use strict';

  const pad = (x) => String(x).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const n = (v) => { const x = Number(String(v == null ? '' : v).replace(/,/g, '')); return isFinite(x) ? x : 0; };
  const PAGE = 100;
  const listOf = (r) => (Array.isArray(r && r.data) ? r.data : (r && r.data && r.data.results) || []);
  const fmtDate = (s) => {
    if (!s) return '—';
    const d = new Date(String(s).length <= 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const cap = (s) => s ? String(s).charAt(0).toUpperCase() + String(s).slice(1).replace(/_/g, ' ') : '—';
  const int = (v) => new Intl.NumberFormat('en-US').format(n(v));

  function rangeOf(key) {
    const t = today();
    if (key === 'today') return [iso(t), iso(t)];
    if (key === '7d') { const s = new Date(t); s.setDate(s.getDate() - 6); return [iso(s), iso(t)]; }
    if (key === 'month') return [iso(new Date(t.getFullYear(), t.getMonth(), 1)), iso(t)];
    if (key === 'last') return [iso(new Date(t.getFullYear(), t.getMonth() - 1, 1)), iso(new Date(t.getFullYear(), t.getMonth(), 0))];
    if (key === 'year') return [iso(new Date(t.getFullYear(), 0, 1)), iso(t)];
    if (key === 'all') return ['2000-01-01', iso(t)];
    return ['', ''];
  }
  const PRESETS = [
    { key: 'today', label: 'Today' }, { key: '7d', label: 'Last 7 days' }, { key: 'month', label: 'This month' },
    { key: 'last', label: 'Last month' }, { key: 'year', label: 'This year' }, { key: 'all', label: 'All time' }, { key: 'custom', label: 'Custom' },
  ];
  const ALL = [['', 'All']];

  // column: { k: field, t: label, f: 'money'|'int'|'date'|'text'|'cap'|'pct', num: true (right aligned), hide: 'md', fn: (row) => text }
  const CUSTOMERS = { key: 'customer', type: 'combo', param: 'customer', label: 'Customer', source: '/api/customers-active/', icon: 'users' };
  const SUPPLIERS = { key: 'supplier', type: 'combo', param: 'supplier', label: 'Supplier', source: '/api/suppliers-active/', icon: 'store' };
  const CATEGORIES = { key: 'category', type: 'combo', param: 'category', label: 'Category', source: '/api/categories/active/', icon: 'box' };

  const REPORTS = {
    sales: {
      title: 'Sales Report', api: '/api/reports/sales/', dates: true, paged: true, period: 'month',
      note: 'Every sale in the period with what it cost and what is left to collect.',
      filters: [CUSTOMERS, { key: 'q', type: 'search', param: 'invoice_no', placeholder: 'Invoice number' }],
      cards: [
        { l: 'Sales', k: 'total_sales', f: 'money' }, { l: 'Cost', k: 'total_cost', f: 'money' },
        { l: 'Profit', k: 'total_profit', f: 'money', tone: 'sign' }, { l: 'Margin', k: 'average_profit_margin', f: 'pct' },
        { l: 'Collected', k: 'total_collected', f: 'money', tone: 'ok' }, { l: 'Due', k: 'total_due', f: 'money', tone: 'due' },
        { l: 'Invoices', k: 'total_transactions', f: 'int' },
      ],
      cols: [
        { k: 'invoice_no', t: 'Invoice', f: 'text', bold: true }, { k: 'sale_date', t: 'Date', f: 'date' },
        { k: 'customer_name', t: 'Customer', f: 'text' }, { k: 'sales_by', t: 'Sold by', f: 'text', hide: 'md' },
        { k: 'sales_price', t: 'Sales', f: 'money', num: true }, { k: 'cost_price', t: 'Cost', f: 'money', num: true, hide: 'md' },
        { k: 'profit', t: 'Profit', f: 'money', num: true, tone: 'sign' },
        { k: 'collect_amount', t: 'Collected', f: 'money', num: true, hide: 'md' }, { k: 'due_amount', t: 'Due', f: 'money', num: true, tone: 'due' },
      ],
    },
    purchases: {
      title: 'Purchase Report', api: '/api/reports/purchases/', dates: true, paged: true, period: 'month',
      note: 'Every purchase in the period, what was paid and what is still owed.',
      filters: [SUPPLIERS, { key: 'q', type: 'search', param: 'invoice_no', placeholder: 'Invoice number' }],
      cards: [
        { l: 'Purchases', k: 'total_purchases', f: 'money' }, { l: 'Paid', k: 'total_paid', f: 'money', tone: 'ok' },
        { l: 'Due', k: 'total_due', f: 'money', tone: 'due' }, { l: 'Invoices', k: 'total_transactions', f: 'int' },
      ],
      cols: [
        { k: 'invoice_no', t: 'Invoice', f: 'text', bold: true }, { k: 'purchase_date', t: 'Date', f: 'date' },
        { k: 'supplier', t: 'Supplier', f: 'text' }, { k: 'payment_status', t: 'Payment', f: 'cap', hide: 'md' },
        { k: 'net_total', t: 'Total', f: 'money', num: true }, { k: 'paid_total', t: 'Paid', f: 'money', num: true },
        { k: 'due_total', t: 'Due', f: 'money', num: true, tone: 'due' },
      ],
    },
    'profit-loss': {
      title: 'Profit / Loss', api: '/api/reports/profit-loss/', dates: true, kind: 'statement', period: 'month',
      note: 'Sales less purchases gives gross profit; expenses and returns then give net profit.',
      filters: [],
    },
    'top-products': {
      title: 'Top Selling Products', api: '/api/reports/top-products/', dates: true, paged: false, period: 'month',
      note: 'Best sellers by quantity sold in the period.',
      filters: [CATEGORIES, { key: 'limit', type: 'chips', param: 'limit', def: '10', options: [['10', 'Top 10'], ['20', 'Top 20'], ['50', 'Top 50'], ['100', 'Top 100']] }],
      cards: [
        { l: 'Products', k: 'total_products', f: 'int' }, { l: 'Units sold', k: 'total_quantity_sold', f: 'int' },
        { l: 'Sales', k: 'total_sales_amount', f: 'money' }, { l: 'Profit', k: 'total_profit', f: 'money', tone: 'sign' },
      ],
      cols: [
        { k: 'product_name', t: 'Product', f: 'text', bold: true }, { k: 'selling_price', t: 'Price', f: 'money', num: true, hide: 'md' },
        { k: 'total_sold_quantity', t: 'Sold', f: 'int', num: true }, { k: 'total_sold_price', t: 'Sales', f: 'money', num: true },
        { k: 'total_profit', t: 'Profit', f: 'money', num: true, tone: 'sign' }, { k: 'current_stock', t: 'In stock', f: 'int', num: true, hide: 'md' },
      ],
    },
    'low-stock': {
      title: 'Low Stock', api: '/api/reports/low-stock/', dates: false, paged: false,
      note: 'Products at or below the stock level you choose, so you can reorder before they run out.',
      filters: [CATEGORIES, { key: 'threshold', type: 'number', param: 'threshold', def: '10', label: 'Stock at or below' }],
      cards: [
        { l: 'Low-stock items', k: 'total_low_stock_items', f: 'int', tone: 'due' }, { l: 'Out of stock', k: 'critical_items', f: 'int', tone: 'due' },
        { l: 'Level used', k: 'threshold', f: 'int' },
      ],
      rowClass: (r) => (n(r.total_stock_quantity) <= 0 ? 'is-out' : ''),
      cols: [
        { k: 'product_name', t: 'Product', f: 'text', bold: true }, { k: 'category', t: 'Category', f: 'text', hide: 'md' },
        { k: 'brand', t: 'Brand', f: 'text', hide: 'md' }, { k: 'selling_price', t: 'Price', f: 'money', num: true },
        { k: 'alert_quantity', t: 'Alert at', f: 'int', num: true, hide: 'md' },
        { k: 'total_stock_quantity', t: 'In stock', f: 'int', num: true, tone: 'due' }, { k: 'total_sold_quantity', t: 'Sold', f: 'int', num: true, hide: 'md' },
      ],
    },
    stock: {
      title: 'Stock Report', api: '/api/reports/stock/', dates: false, paged: true,
      note: 'What is on the shelf now and what it is worth at cost.',
      filters: [CATEGORIES, { key: 'min_stock', type: 'number', param: 'min_stock', def: '', label: 'Stock from' }, { key: 'max_stock', type: 'number', param: 'max_stock', def: '', label: 'to' }],
      cards: [
        { l: 'Products', k: 'total_products', f: 'int' }, { l: 'Units in stock', k: 'total_stock_quantity', f: 'int' },
        { l: 'Stock value', k: 'total_stock_value', f: 'money' },
      ],
      cols: [
        { k: 'product_no', t: 'No.', f: 'text', hide: 'md' }, { k: 'product_name', t: 'Product', f: 'text', bold: true },
        { k: 'category', t: 'Category', f: 'text', hide: 'md' }, { k: 'brand', t: 'Brand', f: 'text', hide: 'md' },
        { k: 'avg_purchase_price', t: 'Avg cost', f: 'money', num: true }, { k: 'selling_price', t: 'Price', f: 'money', num: true, hide: 'md' },
        { k: 'current_stock', t: 'In stock', f: 'int', num: true }, { k: 'value', t: 'Value', f: 'money', num: true },
      ],
    },
    'customer-ledger': {
      title: 'Customer Ledger', api: '/api/reports/customer-ledger/', dates: true, paged: true, period: 'all', require: 'customer',
      note: 'Choose a customer to see every sale, payment and return with the running balance.',
      requireText: 'Choose a customer to see their ledger.',
      filters: [Object.assign({}, CUSTOMERS, { required: true }), { key: 'type', type: 'chips', param: 'transaction_type', def: 'all', options: [['all', 'All'], ['sale', 'Sales'], ['payment', 'Payments'], ['return', 'Returns']] }],
      cards: [
        { l: 'Opening balance', k: 'opening_balance', f: 'money' }, { l: 'Debit', k: 'total_debit', f: 'money' },
        { l: 'Credit', k: 'total_credit', f: 'money' }, { l: 'Closing balance', k: 'closing_balance', f: 'money', tone: 'sign-due' },
        { l: 'Entries', k: 'total_transactions', f: 'int' },
      ],
      cols: [
        { k: 'date', t: 'Date', f: 'date' }, { k: 'voucher_no', t: 'Voucher', f: 'text', bold: true },
        { k: 'particular', t: 'Particular', f: 'text' }, { k: 'details', t: 'Details', f: 'text', hide: 'md' },
        { k: 'method', t: 'Method', f: 'cap', hide: 'md' },
        { k: 'debit', t: 'Debit', f: 'money0', num: true }, { k: 'credit', t: 'Credit', f: 'money0', num: true },
        { k: 'due', t: 'Balance', f: 'money', num: true },
      ],
    },
    'customer-due': {
      title: 'Customer Due / Advance', api: '/api/reports/customer-due-advance/', dates: true, paged: true, period: 'all',
      note: 'Who owes you, and who has paid ahead.',
      filters: [CUSTOMERS, { key: 'status', type: 'chips', param: 'status', def: 'all', options: [['all', 'All'], ['due', 'Due'], ['advance', 'Advance']] }],
      cards: [
        { l: 'Customers', k: 'total_customers', f: 'int' }, { l: 'Total sales', k: 'total_sales_amount', f: 'money' },
        { l: 'Received', k: 'total_received_amount', f: 'money', tone: 'ok' }, { l: 'Due', k: 'total_due_amount', f: 'money', tone: 'due' },
        { l: 'Advance', k: 'total_advance_amount', f: 'money', tone: 'ok' }, { l: 'Net balance', k: 'net_balance', f: 'money', tone: 'sign' },
      ],
      cols: [
        { k: 'customer_no', t: 'No.', f: 'text', hide: 'md' }, { k: 'customer_name', t: 'Customer', f: 'text', bold: true },
        { k: 'phone', t: 'Phone', f: 'text', hide: 'md' }, { k: 'total_sales', t: 'Sales', f: 'money', num: true, hide: 'md' },
        { k: 'total_received', t: 'Received', f: 'money', num: true, hide: 'md' },
        { k: 'present_due', t: 'Due', f: 'money0', num: true, tone: 'due' }, { k: 'present_advance', t: 'Advance', f: 'money0', num: true, tone: 'ok' },
      ],
    },
    'supplier-ledger': {
      title: 'Supplier Ledger', api: '/api/reports/supplier-ledger/', dates: true, paged: true, period: 'all', require: 'supplier',
      note: 'Choose a supplier to see every purchase, payment and return with the running balance.',
      requireText: 'Choose a supplier to see their ledger.',
      filters: [Object.assign({}, SUPPLIERS, { required: true }), { key: 'type', type: 'chips', param: 'transaction_type', def: 'all', options: [['all', 'All'], ['purchase', 'Purchases'], ['payment', 'Payments'], ['return', 'Returns']] }],
      cards: [
        { l: 'Opening balance', k: 'opening_balance', f: 'money' }, { l: 'Debit', k: 'total_debit', f: 'money' },
        { l: 'Credit', k: 'total_credit', f: 'money' }, { l: 'Closing balance', k: 'closing_balance', f: 'money', tone: 'sign-due' },
        { l: 'Entries', k: 'total_transactions', f: 'int' },
      ],
      cols: [
        { k: 'date', t: 'Date', f: 'date' }, { k: 'voucher_no', t: 'Voucher', f: 'text', bold: true },
        { k: 'particular', t: 'Particular', f: 'text' }, { k: 'details', t: 'Details', f: 'text', hide: 'md' },
        { k: 'method', t: 'Method', f: 'cap', hide: 'md' },
        { k: 'debit', t: 'Debit', f: 'money0', num: true }, { k: 'credit', t: 'Credit', f: 'money0', num: true },
        { k: 'due', t: 'Balance', f: 'money', num: true },
      ],
    },
    'supplier-due': {
      title: 'Supplier Due / Advance', api: '/api/reports/supplier-due-advance/', dates: true, paged: true, period: 'all',
      note: 'Which suppliers you still owe, and which you have paid ahead.',
      filters: [SUPPLIERS, { key: 'status', type: 'chips', param: 'status', def: 'all', options: [['all', 'All'], ['due', 'Due'], ['advance', 'Advance']] }],
      cards: [
        { l: 'Suppliers', k: 'total_suppliers', f: 'int' }, { l: 'Due', k: 'total_due_amount', f: 'money', tone: 'due' },
        { l: 'Advance', k: 'total_advance_amount', f: 'money', tone: 'ok' }, { l: 'Net balance', k: 'net_balance', f: 'money', tone: 'sign' },
      ],
      cols: [
        { k: 'supplier_no', t: 'No.', f: 'text', hide: 'md' }, { k: 'supplier_name', t: 'Supplier', f: 'text', bold: true },
        { k: 'phone', t: 'Phone', f: 'text', hide: 'md' }, { k: 'email', t: 'Email', f: 'text', hide: 'md' },
        { k: 'present_due', t: 'Due', f: 'money0', num: true, tone: 'due' }, { k: 'present_advance', t: 'Advance', f: 'money0', num: true, tone: 'ok' },
      ],
    },
    expenses: {
      title: 'Expense Report', api: '/api/reports/expenses/', dates: true, paged: true, period: 'month',
      note: 'Running costs in the period by head and payment method.',
      filters: [{ key: 'category', type: 'combo', param: 'category', label: 'Head', source: '/api/expenses/expense-heads/', icon: 'expense' },
        { key: 'method', type: 'chips', param: 'payment_method', def: '', options: [['', 'Any method'], ['Cash', 'Cash'], ['Bank', 'Bank'], ['Mobile banking', 'Mobile banking']] }],
      cards: [{ l: 'Expenses', k: 'total_count', f: 'int' }, { l: 'Total spent', k: 'total_amount', f: 'money', tone: 'due' }],
      cols: [
        { k: 'expense_date', t: 'Date', f: 'date' }, { k: 'head', t: 'Head', f: 'text', bold: true }, { k: 'subhead', t: 'Sub head', f: 'text', hide: 'md' },
        { k: 'payment_method', t: 'Method', f: 'text', hide: 'md' }, { k: 'note', t: 'Note', f: 'text', hide: 'md' },
        { k: 'amount', t: 'Amount', f: 'money', num: true },
      ],
    },
  };
  window.REPORT_TITLES = Object.fromEntries(Object.entries(REPORTS).map(([k, v]) => [k, v.title]));

  window.reportPage = function (key, init) {
    const cfg = REPORTS[key];
    const filters = cfg.filters || [];
    const defaults = () => Object.fromEntries(filters.map(f => [f.key, f.def !== undefined ? f.def : '']));
    return {
      cfg, presets: PRESETS, init0: init || {},
      f: Object.assign({ preset: cfg.period || 'month', from: '', to: '' }, defaults()),
      opts: {},
      page: 1, rows: [], meta: { count: 0, total_pages: 1 }, summary: null, stmt: null,
      loading: !cfg.require, error: null, exporting: false, _req: 0, _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        if (cfg.dates) {
          this.f.preset = p.get('period') || this.f.preset;
          this.f.from = p.get('from') || ''; this.f.to = p.get('to') || '';
          if (this.f.preset !== 'custom') [this.f.from, this.f.to] = rangeOf(this.f.preset);
        }
        filters.forEach(fl => { if (p.has(fl.key)) this.f[fl.key] = p.get(fl.key); });
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        filters.filter(fl => fl.type === 'combo').forEach(fl => {
          App.api(fl.source, fl.source.includes('categories') ? { query: { no_pagination: 'true' } } : undefined).then(r => {
            this.opts[fl.key] = listOf(r).map(x => ({ value: String(x.id), label: x.name, sub: x.phone || '' }));
          }).catch(() => { this.opts[fl.key] = []; });
        });
        this.fetch();
        filters.forEach(fl => {
          if (fl.type === 'search' || fl.type === 'number') this.$watch('f.' + fl.key, () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 450); });
          else this.$watch('f.' + fl.key, () => this.reset());
        });
      },

      setPreset(k) { this.f.preset = k; if (k !== 'custom') { [this.f.from, this.f.to] = rangeOf(k); this.reset(); } },
      applyCustom() { if (this.f.from && this.f.to && this.f.from > this.f.to) [this.f.from, this.f.to] = [this.f.to, this.f.from]; this.reset(); },
      get needs() { return !!(cfg.require && !this.f[cfg.require]); },
      get filtered() {
        const d = defaults();
        return filters.some(fl => String(this.f[fl.key] || '') !== String(d[fl.key] || '')) || (cfg.dates && this.f.preset !== (cfg.period || 'month'));
      },
      clearAll() { Object.assign(this.f, defaults(), { preset: cfg.period || 'month' }); if (cfg.dates) [this.f.from, this.f.to] = rangeOf(this.f.preset); this.reset(); },
      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.meta.total_pages || p === this.page) return;
        this.page = p; this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },

      query(page, size) {
        const q = {};
        if (cfg.dates) { q.start = this.f.from; q.end = this.f.to; }
        filters.forEach(fl => {
          let v = this.f[fl.key];
          if (fl.type === 'search') v = String(v || '').trim();
          if (fl.type === 'chips' && (v === 'all' || v === '')) return;
          if (v !== '' && v != null) q[fl.param] = v;
        });
        if (cfg.paged) { q.page = page; q.page_size = size; }
        return q;
      },
      syncUrl() {
        const p = new URLSearchParams();
        if (cfg.dates && this.f.preset !== (cfg.period || 'month')) p.set('period', this.f.preset);
        if (cfg.dates && this.f.preset === 'custom') { if (this.f.from) p.set('from', this.f.from); if (this.f.to) p.set('to', this.f.to); }
        const d = defaults();
        filters.forEach(fl => { if (String(this.f[fl.key] || '') !== String(d[fl.key] || '')) p.set(fl.key, this.f[fl.key]); });
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },
      parse(r) {
        const d = r.data || {};
        if (cfg.kind === 'statement') return { stmt: d };
        const rep = d.report;
        let rows, count, pages;
        if (Array.isArray(rep)) { rows = rep; count = rep.length; pages = 1; }
        else { rows = (rep && rep.results) || []; count = rep && rep.count != null ? rep.count : rows.length; pages = (rep && rep.total_pages) || Math.max(1, Math.ceil(count / PAGE)); }
        return { rows, count, pages, summary: d.summary || null };
      },
      async fetch() {
        if (this.needs) { this.rows = []; this.summary = null; this.loading = false; this.error = null; this.syncUrl(); return; }
        const id = ++this._req;
        this.loading = true; this.error = null; this.syncUrl();
        try {
          const r = await App.api(cfg.api, { query: this.query(this.page, PAGE) });
          if (id !== this._req) return;
          const o = this.parse(r);
          if (o.stmt) this.stmt = o.stmt;
          else { this.rows = o.rows; this.meta = { count: o.count, total_pages: o.pages }; this.summary = o.summary; }
        } catch (e) {
          if (id !== this._req) return;
          this.error = e.message; this.rows = []; this.stmt = null;
        }
        this.loading = false;
      },

      // ───── display ─────
      taka: (v) => App.taka(v),
      int, fmtDate,
      get from() { return this.meta.count ? (this.page - 1) * PAGE + 1 : 0; },
      get to() { return Math.min(this.page * PAGE, this.meta.count); },
      get pages() {
        const t = this.meta.total_pages, c = this.page, out = [];
        for (let i = 1; i <= t; i++) {
          if (i === 1 || i === t || Math.abs(i - c) <= 2) out.push(i);
          else if (out[out.length - 1] !== '…') out.push('…');
        }
        return out;
      },
      fmt(v, f) {
        if (f === 'money') return App.taka(v);
        if (f === 'money0') return n(v) === 0 ? '—' : App.taka(v);
        if (f === 'int') return int(v);
        if (f === 'pct') return n(v).toFixed(1) + '%';
        if (f === 'date') return fmtDate(v);
        if (f === 'cap') return v ? cap(v) : '—';
        return v === null || v === undefined || v === '' ? '—' : String(v);
      },
      cell(r, c) { return this.fmt(r[c.k], c.f); },
      tone(v, tone) {
        if (tone === 'due') return n(v) > 0 ? 'txt-due' : '';
        if (tone === 'ok') return n(v) > 0 ? 'txt-ok' : '';
        if (tone === 'sign') return n(v) < 0 ? 'txt-due' : (n(v) > 0 ? 'txt-ok' : '');
        if (tone === 'sign-due') return n(v) > 0 ? 'txt-due' : '';
        return '';
      },
      card(c) { return this.summary ? this.fmt(this.summary[c.k], c.f) : '—'; },
      get periodText() {
        if (!cfg.dates) return 'As of ' + fmtDate(iso(today()));
        const s = this.summary && this.summary.date_range;
        const a = (s && s.start) || this.f.from, b = (s && s.end) || this.f.to;
        if (this.f.preset === 'all') return 'All time';
        return a === b ? fmtDate(a) : fmtDate(a) + ' – ' + fmtDate(b);
      },
      get subject() {
        const fl = filters.find(x => x.required);
        if (!fl) return '';
        if (this.summary && (this.summary.customer_name || this.summary.supplier_name)) return this.summary.customer_name || this.summary.supplier_name;
        const o = (this.opts[fl.key] || []).find(x => x.value === String(this.f[fl.key]));
        return o ? o.label : '';
      },
      // Profit / Loss — backend যেমন দেয়
      get st() {
        const s = this.stmt; if (!s) return null;
        const hasRet = s.sales_returns !== undefined || s.purchase_returns !== undefined;
        return { s, hasRet };
      },
      print() { window.print(); },

      async exportCsv() {
        if (this.exporting || this.needs) return;
        this.exporting = true;
        try {
          let all = [];
          if (cfg.paged) {
            let page = 1, pages = 1;
            do {
              const r = await App.api(cfg.api, { query: this.query(page, 1000) });
              const o = this.parse(r); all = all.concat(o.rows); pages = Math.ceil((o.count || 0) / 1000) || 1; page++;
            } while (page <= pages && page <= 50);
          } else all = this.rows;
          const q = (v) => '"' + String(v === null || v === undefined ? '' : v).replace(/"/g, '""') + '"';
          const cols = cfg.cols;
          const lines = [cols.map(c => q(c.t)).join(',')].concat(all.map(r => cols.map(c => q(c.f === 'money' || c.f === 'money0' || c.f === 'int' ? n(r[c.k]) : r[c.k])).join(',')));
          const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = key + '-' + iso(today()) + '.csv';
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(a.href), 2000);
        } catch (e) { this.error = 'Could not export: ' + e.message; }
        this.exporting = false;
      },
    };
  };
})();
