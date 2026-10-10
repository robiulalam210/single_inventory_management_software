/*
 * Money Receipt — তালিকা (receiptList) আর নতুন রসিদ (receiptForm)।
 *   তালিকা: /api/money-receipts/ (প্রতি page এ ৩০) + /api/money-receipts/summary/ (একই filter এর মোট)
 *   নতুন:   POST /api/money-receipts/ — টাকা কোথায় বসবে তা backend ঠিক করে; এখানে আগেই একই নিয়মে দেখাই।
 */
(function () {
  'use strict';

  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const n = (v) => Number(v || 0);
  const round2 = (v) => Math.round(v * 100) / 100;
  const PAGE_SIZE = 30;

  const METHODS = [
    { value: 'Cash', label: 'Cash' },
    { value: 'Bank', label: 'Bank' },
    { value: 'Mobile banking', label: 'Mobile banking' },
  ];
  const TYPE_LABEL = { specific: 'Invoice payment', overall: 'Toward dues', advance: 'Advance' };

  function rangeOf(key) {
    const t = today();
    if (key === 'today') return [iso(t), iso(t)];
    if (key === '7d') { const s = new Date(t); s.setDate(s.getDate() - 6); return [iso(s), iso(t)]; }
    if (key === 'month') return [iso(new Date(t.getFullYear(), t.getMonth(), 1)), iso(t)];
    return ['', ''];
  }
  const fmtDate = (s) => new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const fmtTime = (s) => new Date(s).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);

  // ─────────────────────────────── list ───────────────────────────────
  window.receiptList = function (opts) {
    return {
      presets: [
        { key: 'today', label: 'Today' },
        { key: '7d', label: 'Last 7 days' },
        { key: 'month', label: 'This month' },
        { key: 'all', label: 'All time' },
        { key: 'custom', label: 'Custom' },
      ],
      types: [
        { key: '', label: 'All' },
        { key: 'specific', label: 'Invoice payment' },
        { key: 'overall', label: 'Toward dues' },
        { key: 'advance', label: 'Advance' },
      ],
      methods: METHODS,
      f: { q: '', type: '', customer: '', method: '', seller: '', preset: 'month', from: '', to: '' },
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
      canDelete: !!opts.canDelete,
      confirmDel: false,
      deleting: false,
      delError: '',
      toast: '',
      _req: 0,
      _t: null,

      init() {
        const p = new URLSearchParams(location.search);
        this.f.q = p.get('q') || '';
        this.f.type = p.get('type') || '';
        this.f.customer = p.get('customer') || '';
        this.f.method = p.get('method') || '';
        this.f.seller = p.get('seller') || '';
        this.f.preset = p.get('period') || 'month';
        this.f.from = p.get('from') || '';
        this.f.to = p.get('to') || '';
        this.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
        if (this.f.preset !== 'custom') [this.f.from, this.f.to] = rangeOf(this.f.preset);

        this.loadOptions();
        this.fetch();

        // নতুন রসিদ save হলে ?open=<id> দিয়ে আসে — সরাসরি রসিদটা খুলে দেখাই (print এর জন্য)
        const openId = parseInt(p.get('open') || '', 10);
        if (openId) {
          App.api(`/api/money-receipts/${openId}/`).then(r => { if (r.data) this.open(r.data); }).catch(() => {});
        }

        this.$watch('f.q', () => { clearTimeout(this._t); this._t = setTimeout(() => this.reset(), 350); });
        ['f.type', 'f.customer', 'f.method', 'f.seller'].forEach(k => this.$watch(k, () => this.reset()));
      },

      loadOptions() {
        App.api('/api/customers-active/').then(r => {
          this.customers = listOf(r).map(c => ({ value: String(c.id), label: c.name, sub: c.phone || c.client_no || '' }));
        }).catch(() => {});
        if (this.canSeeUsers) {
          App.api('/api/users/', { query: { status: 1 } }).then(r => {
            this.sellers = listOf(r).map(u => ({ value: String(u.id), label: u.full_name || u.username, sub: u.username }));
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
        this.f = { q: '', type: '', customer: '', method: '', seller: '', preset: 'month', from: '', to: '' };
        [this.f.from, this.f.to] = rangeOf('month');
        this.reset();
      },
      get filtered() {
        const f = this.f;
        return !!(f.q || f.type || f.customer || f.method || f.seller || f.preset !== 'month');
      },

      reset() { this.page = 1; this.fetch(); },
      go(p) {
        if (p < 1 || p > this.meta.total_pages || p === this.page) return;
        this.page = p;
        this.fetch();
        document.getElementById('content').scrollIntoView({ behavior: 'smooth', block: 'start' });
      },

      query() {
        return {
          search: this.f.q.trim(),
          payment_type: this.f.type,
          customer_id: this.f.customer,
          payment_method: this.f.method,
          seller_id: this.f.seller,
          start_date: this.f.from,
          end_date: this.f.to,
        };
      },

      syncUrl() {
        const p = new URLSearchParams();
        const f = this.f;
        if (f.q) p.set('q', f.q);
        if (f.type) p.set('type', f.type);
        if (f.customer) p.set('customer', f.customer);
        if (f.method) p.set('method', f.method);
        if (f.seller) p.set('seller', f.seller);
        if (f.preset !== 'month') p.set('period', f.preset);
        if (f.preset === 'custom') { if (f.from) p.set('from', f.from); if (f.to) p.set('to', f.to); }
        if (this.page > 1) p.set('page', this.page);
        const s = p.toString();
        history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
      },

      async fetch() {
        const id = ++this._req;
        this.loading = true;
        this.error = null;
        this.syncUrl();
        const q = this.query();
        try {
          const [list, sum] = await Promise.all([
            App.api('/api/money-receipts/', { query: Object.assign({ page: this.page, page_size: PAGE_SIZE }, q) }),
            App.api('/api/money-receipts/summary/', { query: q }).catch(() => null),
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
      words: (v) => App.takaWords(v),
      num: (v) => new Intl.NumberFormat('en-US').format(n(v)),
      date: fmtDate,
      time: fmtTime,
      same,
      typeAmount(t) { return n(this.sum && this.sum.by_type && this.sum.by_type[t] && this.sum.by_type[t].amount); },
      typeLabel: (t) => TYPE_LABEL[t] || t || '—',
      appliedTo(r) {
        if (r.payment_type === 'specific') return r.sale_invoice_no ? 'Invoice ' + r.sale_invoice_no : 'One invoice';
        return TYPE_LABEL[r.payment_type] || '—';
      },
      payWith(r) {
        const parts = [r.payment_method, r.account_name].filter(Boolean);
        return parts.filter((v, i) => parts.findIndex(x => same(x, v)) === i).join(', ') || '—';
      },
      customerName(r) { return r.customer_name || 'Walk-in customer'; },
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
      get periodText() {
        if (this.f.preset === 'all' || (!this.f.from && !this.f.to)) return 'All time';
        const fmt = (s) => fmtDate(s + 'T00:00');
        if (this.f.from === this.f.to) return fmt(this.f.from);
        return `${this.f.from ? fmt(this.f.from) : 'Start'} – ${this.f.to ? fmt(this.f.to) : 'today'}`;
      },

      // ───── drawer ─────
      open(r) { this.sel = r; this.delError = ''; document.body.style.overflow = 'hidden'; },
      shut() {
        this.sel = null;
        document.body.style.overflow = '';
        const p = new URLSearchParams(location.search);
        if (p.has('open')) this.syncUrl();
      },
      print() { window.print(); },

      async remove() {
        if (!this.sel || this.deleting) return;
        this.deleting = true;
        this.delError = '';
        const mr = this.sel.mr_no;
        try {
          await App.api(`/api/money-receipts/${this.sel.id}/`, { method: 'DELETE' });
          this.confirmDel = false;
          this.shut();
          this.flash(`${mr} cancelled. Balances have been reversed.`);
          this.fetch();
        } catch (e) {
          // যেমন: advance ইতিমধ্যে খরচ হয়ে গেছে — backend কারণটা বলে দেয়
          this.delError = e.message;
        }
        this.deleting = false;
      },
      flash(msg) {
        this.toast = msg;
        clearTimeout(this._toast);
        this._toast = setTimeout(() => { this.toast = ''; }, 3500);
      },
    };
  };

  // ─────────────────────────────── new receipt ───────────────────────────────
  window.receiptForm = function (init) {
    return {
      methods: METHODS,
      customers: [],
      customerRows: {},       // id → customer API row (due, advance)
      accountsAll: [],
      users: [],
      dues: [],               // এই customer এর বাকি invoice (পুরনো আগে)
      duesLoading: false,
      canPickCollector: !!init.canPickCollector,
      canSeeList: !!init.canSeeList,
      me: init.me,
      form: {
        customer: init.customer ? String(init.customer) : '',
        mode: init.sale ? 'specific' : 'overall',
        sale: init.sale ? String(init.sale) : '',
        amount: '',
        date: iso(today()),
        method: 'Cash',
        account: '',
        seller: String(init.me.id),
        remark: '',
      },
      maxDate: iso(today()),
      errors: {},
      saving: false,
      serverError: '',
      done: null,             // save হওয়া রসিদ

      init() {
        App.api('/api/customers-active/').then(r => {
          const list = listOf(r).filter(c => c.is_active !== false);
          this.customerRows = Object.fromEntries(list.map(c => [String(c.id), c]));
          this.customers = list.map(c => ({
            value: String(c.id), label: c.name,
            sub: n(c.total_due) > 0 ? 'Due ' + App.taka(c.total_due) : (c.phone || ''),
          }));
        }).catch(() => {});
        App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => {
          this.accountsAll = listOf(r).filter(a => a.is_active !== false);
          this.pickAccount();
        }).catch(() => {});
        if (this.canPickCollector) {
          App.api('/api/users/', { query: { status: 1 } }).then(r => {
            this.users = listOf(r).map(u => ({ value: String(u.id), label: u.full_name || u.username, sub: u.username }));
          }).catch(() => { this.canPickCollector = false; });
        }
        if (this.form.customer) this.loadDues(true);

        this.$watch('form.customer', () => { this.form.sale = ''; this.form.amount = ''; this.errors = {}; this.loadDues(false); });
        this.$watch('form.method', () => this.pickAccount());
        this.$watch('form.sale', (v) => {
          // invoice বাছলে তার পুরো due টাকাই বসাই — দরকারে বদলানো যায়
          const s = this.dues.find(d => String(d.id) === String(v));
          if (s) this.form.amount = String(n(s.due_amount));
        });
        this.$watch('form.mode', (m) => { if (m === 'overall') this.form.sale = ''; this.errors.sale = ''; });
      },

      async loadDues(keepSale) {
        const id = this.form.customer;
        this.dues = [];
        if (!id) return;
        this.duesLoading = true;
        const wanted = keepSale ? init.sale : null;
        try {
          const r = await App.api('/api/due/', { query: { customer_id: id, due: 'true' } });
          if (this.form.customer !== id) return; // এর মধ্যে customer বদলেছে
          this.dues = listOf(r).filter(s => n(s.due_amount) > 0);
          if (wanted && this.dues.some(d => String(d.id) === String(wanted))) {
            this.form.mode = 'specific';
            this.form.sale = String(wanted);
            const s = this.dues.find(d => String(d.id) === String(wanted));
            this.form.amount = String(n(s.due_amount));
          }
        } catch (e) {
          this.dues = [];
        }
        this.duesLoading = false;
      },

      // payment method এর সাথে মেলে এমন account — app এর একই নিয়ম (ac_type == method)
      get accounts() {
        return this.accountsAll
          .filter(a => same(a.ac_type, this.form.method))
          .map(a => ({ value: String(a.id), label: a.name, sub: a.ac_number || a.bank_name || '' }));
      },
      pickAccount() {
        const list = this.accounts;
        if (!list.some(a => a.value === this.form.account)) this.form.account = list.length ? list[0].value : '';
      },

      get customer() { return this.customerRows[this.form.customer] || null; },
      get totalDue() { return round2(this.dues.reduce((s, d) => s + n(d.due_amount), 0)); },
      get invoiceOptions() {
        return this.dues.map(d => ({
          value: String(d.id), label: d.invoice_no,
          sub: 'Due ' + App.taka(d.due_amount) + ', ' + fmtDate(d.sale_date),
        }));
      },
      get selectedSale() { return this.dues.find(d => String(d.id) === String(this.form.sale)) || null; },
      get amountNum() {
        const v = parseFloat(String(this.form.amount).replace(/,/g, ''));
        return isFinite(v) ? round2(v) : 0;
      },

      /*
       * backend এর MoneyReceipt._process_overall_payment / _process_specific_invoice_payment এর হুবহু একই:
       *   overall  → পুরনো invoice থেকে শুরু করে due মেটাও, যা বাকি থাকে তা advance
       *   specific → ওই invoice এর due পর্যন্ত, বাড়তি টাকা advance
       */
      get plan() {
        let left = this.amountNum;
        const lines = [];
        if (left <= 0) return { lines, advance: 0 };
        const targets = this.form.mode === 'specific' ? (this.selectedSale ? [this.selectedSale] : []) : this.dues;
        for (const s of targets) {
          if (left <= 0) break;
          const due = n(s.due_amount);
          const take = round2(Math.min(left, due));
          if (take <= 0) continue;
          lines.push({ id: s.id, invoice: s.invoice_no, due, take, clears: take >= due });
          left = round2(left - take);
        }
        return { lines, advance: left };
      },

      fill(v) { this.form.amount = String(round2(v)); this.errors.amount = ''; },

      validate() {
        const e = {};
        if (!this.form.customer) e.customer = 'Choose who is paying.';
        if (this.form.mode === 'specific' && !this.form.sale) e.sale = 'Choose the invoice this payment is for.';
        if (!(this.amountNum > 0)) e.amount = 'Enter an amount greater than 0.';
        if (!this.form.date) e.date = 'Pick the payment date.';
        else if (this.form.date > this.maxDate) e.date = 'The date cannot be in the future.';
        if (!this.form.account) e.account = this.accounts.length ? 'Choose the account the money goes into.'
          : `There is no active ${this.form.method} account. Add one in Accounts first.`;
        this.errors = e;
        return !Object.keys(e).length;
      },

      // আজকের তারিখ হলে এখনকার সময়; পুরনো তারিখে দুপুর ১২টা — তালিকায় ঠিক ক্রমে বসে
      paymentDateTime() {
        if (this.form.date === iso(today())) {
          const d = new Date();
          return `${this.form.date}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
        }
        return `${this.form.date}T12:00:00`;
      },

      async save() {
        this.serverError = '';
        if (!this.validate() || this.saving) {
          this.$nextTick(() => { const el = this.$root.querySelector('.has-error'); if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); });
          return;
        }
        this.saving = true;
        const body = {
          customer_id: Number(this.form.customer),
          amount: this.amountNum.toFixed(2),
          payment_date: this.paymentDateTime(),
          payment_method: this.form.method,
          account_id: Number(this.form.account),
          seller_id: Number(this.form.seller || this.me.id),
          remark: this.form.remark.trim(),
        };
        if (this.form.mode === 'specific') body.sale_id = Number(this.form.sale);
        try {
          const r = await App.api('/api/money-receipts/', { method: 'POST', body });
          this.done = Object.assign({ plan: this.plan }, r.data);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (e) {
          this.serverError = this.explain(e);
        }
        this.saving = false;
      },
      explain(e) {
        const d = e.data && e.data.data;
        if (d && typeof d === 'object') {
          const first = Object.entries(d)[0];
          if (first) {
            const [k, v] = first;
            const msg = Array.isArray(v) ? v[0] : (typeof v === 'string' ? v : JSON.stringify(v));
            return (k === 'non_field_errors' ? '' : k.replace(/_id$/, '').replace(/_/g, ' ') + ': ') + msg;
          }
        }
        return e.message;
      },

      again() {
        const keepMethod = this.form.method, keepAccount = this.form.account;
        this.done = null;
        this.form = Object.assign(this.form, { customer: '', sale: '', amount: '', remark: '', mode: 'overall',
          date: iso(today()), method: keepMethod, account: keepAccount });
        this.dues = [];
        this.errors = {};
      },

      taka: (v) => App.taka(v),
      words: (v) => App.takaWords(v),
      round2,
      date: fmtDate,
      time: fmtTime,
    };
  };
})();
