/*
 * Payroll — Salary Sheet (salarySheet), Advances (advanceList), Payroll Report (payrollReport)।
 *   API: /api/payroll/slips/ · slips/generate/ · slips/<id>/ (PATCH/DELETE) · slips/<id>/pay|unpay/
 *        /api/payroll/advances/ · advances/<id>/ · /api/payroll/report/
 *   বেতন/অগ্রিম দিলে backend একটা Expense লেখে, তাই account balance আর Transaction নিজে থেকে মেলে।
 */
(function () {
  'use strict';

  const pad = (x) => String(x).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const ym = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
  const n = (v) => { const x = Number(String(v == null ? '' : v).replace(/,/g, '')); return isFinite(x) ? x : 0; };
  const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;
  const listOf = (r) => (Array.isArray(r && r.data) ? r.data : (r && r.data && r.data.results) || []);
  const fmtDate = (s) => {
    if (!s) return '—';
    const d = new Date(String(s).length <= 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const monthName = (s) => {
    const d = new Date(String(s).slice(0, 7) + '-01T00:00');
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  };
  const shift = (m, by) => { const [y, mo] = m.split('-').map(Number); return ym(new Date(y, mo - 1 + by, 1)); };
  const METHODS = [['cash', 'Cash'], ['bank', 'Bank'], ['mobile', 'Mobile banking'], ['card', 'Card'], ['other', 'Other']];
  const money = (v) => App.taka(v);

  // Object.assign getter গুলো চালিয়ে ফেলে — তাই descriptor সহ মেলাই
  const mix = (...parts) => parts.reduce((o, p) => Object.defineProperties(o, Object.getOwnPropertyDescriptors(p)), {});

  const base = {
    taka: money, fmtDate, monthName, methods: METHODS, n,
    flash(msg) { this.toast = msg; clearTimeout(this._toast); this._toast = setTimeout(() => { this.toast = ''; }, 3500); },
    loadAccounts() {
      return App.api('/api/accounts/', { query: { no_pagination: 'true' } }).then(r => {
        this.accounts = listOf(r).filter(a => a.is_active !== false).map(a => ({ value: String(a.id), label: a.name, sub: money(a.balance), balance: n(a.balance) }));
      }).catch(() => { this.accounts = []; });
    },
    accBalance(id) { const a = this.accounts.find(x => x.value === String(id)); return a ? a.balance : null; },
  };

  /* ───────────── Salary Sheet ───────────── */
  window.salarySheet = function () {
    return mix(base, {
      month: ym(new Date()), status: '', rows: [], summary: null, page: 1, meta: { count: 0, total_pages: 1 },
      loading: true, error: null, accounts: [], toast: '', _req: 0,
      generating: false, working: false,
      edit: null, editOpen: false, editErr: '', pay: null, payOpen: false, payErr: '', confirm: null, confirmErr: '', slip: null, slipOpen: false,
      statuses: [['', 'All'], ['unpaid', 'Unpaid'], ['paid', 'Paid']],

      init() {
        const p = new URLSearchParams(location.search);
        if (/^\d{4}-\d{2}$/.test(p.get('month') || '')) this.month = p.get('month');
        this.status = p.get('status') || '';
        this.loadAccounts();
        this.fetch();
        this.$watch('status', () => { this.page = 1; this.fetch(); });
      },
      setMonth(m) { if (/^\d{4}-\d{2}$/.test(m || '')) { this.month = m; this.page = 1; this.fetch(); } },
      move(by) { this.setMonth(shift(this.month, by)); },
      get isFuture() { return this.month >= shift(ym(new Date()), 1); },
      get isCurrent() { return this.month === ym(new Date()); },

      async fetch() {
        const id = ++this._req;
        this.loading = true; this.error = null;
        const q = new URLSearchParams();
        if (this.month !== ym(new Date())) q.set('month', this.month);
        if (this.status) q.set('status', this.status);
        history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q : ''));
        try {
          const r = await App.api('/api/payroll/slips/', { query: { month: this.month, status: this.status, page: this.page } });
          if (id !== this._req) return;
          const d = r.data || {};
          this.rows = d.results || []; this.summary = d.summary || null;
          this.meta = { count: d.count || 0, total_pages: d.total_pages || 1 };
        } catch (e) { if (id !== this._req) return; this.error = e.message; this.rows = []; }
        this.loading = false;
      },
      go(p) { if (p < 1 || p > this.meta.total_pages) return; this.page = p; this.fetch(); },

      async generate() {
        if (this.generating) return;
        this.generating = true;
        try {
          const r = await App.api('/api/payroll/slips/generate/', { method: 'POST', body: { month: this.month } });
          const d = r.data || {};
          this.flash(d.created ? `${d.created} slip(s) prepared for ${monthName(this.month)}.` : 'Every staff member already has a slip for this month.');
          this.fetch();
        } catch (e) { this.flash(e.message); }
        this.generating = false;
      },

      // ── edit ──
      openEdit(r) {
        this.editErr = ''; this.editOpen = true;
        this.edit = { id: r.id, name: r.staff_name, month: r.month, open: n(r.open_advance),
          basic: String(n(r.basic)), commission: String(n(r.commission)), bonus: String(n(r.bonus)), other_addition: String(n(r.other_addition)),
          advance_deduction: String(n(r.advance_deduction)), other_deduction: String(n(r.other_deduction)), note: r.note || '' };
      },
      get editNet() {
        const e = this.edit; if (!e) return 0;
        return round2(n(e.basic) + n(e.commission) + n(e.bonus) + n(e.other_addition) - n(e.advance_deduction) - n(e.other_deduction));
      },
      async saveEdit() {
        const e = this.edit; if (!e || this.working) return;
        if (this.editNet < 0) { this.editErr = 'Deductions are more than the salary.'; return; }
        if (n(e.advance_deduction) > e.open) { this.editErr = `Advance still owed is only ${money(e.open)}.`; return; }
        this.working = true; this.editErr = '';
        try {
          await App.api('/api/payroll/slips/' + e.id + '/', { method: 'PATCH', body: {
            basic: n(e.basic), commission: n(e.commission), bonus: n(e.bonus), other_addition: n(e.other_addition),
            advance_deduction: n(e.advance_deduction), other_deduction: n(e.other_deduction), note: e.note } });
          this.editOpen = false; this.flash('Slip updated.'); this.fetch();
        } catch (er) { this.editErr = er.message; }
        this.working = false;
      },

      // ── pay ──
      openPay(r) {
        this.payErr = ''; this.payOpen = true;
        this.pay = { id: r.id, name: r.staff_name, net: n(r.net), account: this.accounts.length === 1 ? this.accounts[0].value : '', method: 'cash', date: iso(new Date()) };
      },
      get payShort() { const b = this.pay && this.accBalance(this.pay.account); return b !== null && b !== undefined && this.pay && this.pay.net > b; },
      async savePay() {
        const p = this.pay; if (!p || this.working) return;
        if (!p.account) { this.payErr = 'Choose the account the salary is paid from.'; return; }
        if (this.payShort) { this.payErr = 'This account does not have enough balance.'; return; }
        this.working = true; this.payErr = '';
        try {
          await App.api('/api/payroll/slips/' + p.id + '/pay/', { method: 'POST', body: { account_id: p.account, payment_method: p.method, date: p.date } });
          this.payOpen = false; this.flash(`Salary paid to ${p.name}.`); this.loadAccounts(); this.fetch();
        } catch (er) { this.payErr = er.message; }
        this.working = false;
      },

      // ── unpay / delete ──
      ask(kind, r) { this.confirm = { kind, r }; this.confirmErr = ''; },
      get confirmText() {
        const c = this.confirm; if (!c) return null;
        if (c.kind === 'unpay') return { title: 'Cancel this payment?', body: `${money(c.r.net)} goes back to ${c.r.account_name || 'the account'} and ${c.r.staff_name}'s slip becomes unpaid again. Any advance cut from it is owed again.`, btn: 'Cancel payment', danger: true };
        return { title: 'Delete this slip?', body: `${c.r.staff_name}'s slip for ${monthName(c.r.month)} will be removed. You can prepare it again later.`, btn: 'Delete slip', danger: true };
      },
      async runConfirm() {
        const c = this.confirm; if (!c || this.working) return;
        this.working = true; this.confirmErr = '';
        try {
          if (c.kind === 'unpay') await App.api('/api/payroll/slips/' + c.r.id + '/unpay/', { method: 'POST', body: {} });
          else await App.api('/api/payroll/slips/' + c.r.id + '/', { method: 'DELETE' });
          this.confirm = null; this.flash(c.kind === 'unpay' ? 'Payment cancelled.' : 'Slip deleted.'); this.loadAccounts(); this.fetch();
        } catch (er) { this.confirmErr = er.message; }
        this.working = false;
      },

      // ── payslip ──
      showSlip(r) { this.slip = r; this.slipOpen = true; },
      gross(r) { return n(r.basic) + n(r.commission) + n(r.bonus) + n(r.other_addition); },
      deduct(r) { return n(r.advance_deduction) + n(r.other_deduction); },
      printSlip() { window.print(); },
      get from() { return this.meta.count ? (this.page - 1) * 50 + 1 : 0; },
      get to() { return Math.min(this.page * 50, this.meta.count); },
    });
  };

  /* ───────────── Advances ───────────── */
  window.advanceList = function () {
    return mix(base, {
      rows: [], balances: {}, staff: [], accounts: [], loading: true, error: null, toast: '',
      filter: '', openOnly: false, form: null, formOpen: false, formErr: '', working: false, confirm: null, confirmErr: '',
      init() {
        this.loadAccounts();
        App.api('/api/payroll/staff/').then(r => {
          this.staff = listOf(r).map(s => ({ value: String(s.id), label: s.name, sub: s.designation || '' }));
        }).catch(() => { this.staff = []; });
        this.fetch();
        this.$watch('filter', () => this.fetch());
        this.$watch('openOnly', () => this.fetch());
      },
      async fetch() {
        this.loading = true; this.error = null;
        try {
          const r = await App.api('/api/payroll/advances/', { query: { staff: this.filter, open: this.openOnly ? '1' : '' } });
          const d = r.data || {};
          this.rows = d.results || []; this.balances = d.balances || {};
        } catch (e) { this.error = e.message; this.rows = []; }
        this.loading = false;
      },
      get totalOwed() { return Object.values(this.balances).reduce((a, b) => a + n(b), 0); },
      get staffOwing() { return Object.values(this.balances).filter(b => n(b) > 0).length; },
      get shown() { return this.rows.reduce((a, r) => a + n(r.amount), 0); },
      openForm() { this.formErr = ''; this.formOpen = true; this.form = { staff: this.filter || '', amount: '', account: this.accounts.length === 1 ? this.accounts[0].value : '', method: 'cash', date: iso(new Date()), note: '' }; },
      get short() { const b = this.form && this.accBalance(this.form.account); return b !== null && b !== undefined && n(this.form.amount) > b; },
      async save() {
        const f = this.form; if (!f || this.working) return;
        if (!f.staff) { this.formErr = 'Choose a staff member.'; return; }
        if (!(n(f.amount) > 0)) { this.formErr = 'Enter the advance amount.'; return; }
        if (!f.account) { this.formErr = 'Choose the account the advance is paid from.'; return; }
        if (this.short) { this.formErr = 'This account does not have enough balance.'; return; }
        this.working = true; this.formErr = '';
        try {
          await App.api('/api/payroll/advances/', { method: 'POST', body: { staff_id: f.staff, amount: n(f.amount), account_id: f.account, payment_method: f.method, date: f.date, note: f.note } });
          this.formOpen = false; this.flash('Advance recorded.'); this.loadAccounts(); this.fetch();
        } catch (e) { this.formErr = e.message; }
        this.working = false;
      },
      async runConfirm() {
        const c = this.confirm; if (!c || this.working) return;
        this.working = true; this.confirmErr = '';
        try {
          await App.api('/api/payroll/advances/' + c.id + '/', { method: 'DELETE' });
          this.confirm = null; this.flash('Advance cancelled.'); this.loadAccounts(); this.fetch();
        } catch (e) { this.confirmErr = e.message; }
        this.working = false;
      },
    });
  };

  /* ───────────── Report ───────────── */
  window.payrollReport = function () {
    const now = new Date();
    return mix(base, {
      start: `${now.getFullYear()}-01`, end: ym(now), rows: [], summary: null, loading: true, error: null, toast: '', _req: 0,
      init() {
        const p = new URLSearchParams(location.search);
        if (/^\d{4}-\d{2}$/.test(p.get('start') || '')) this.start = p.get('start');
        if (/^\d{4}-\d{2}$/.test(p.get('end') || '')) this.end = p.get('end');
        this.fetch();
      },
      apply() { if (this.start > this.end) [this.start, this.end] = [this.end, this.start]; this.fetch(); },
      preset(k) {
        const y = now.getFullYear();
        if (k === 'month') { this.start = this.end = ym(now); }
        else if (k === 'last') { this.start = this.end = shift(ym(now), -1); }
        else if (k === '3m') { this.start = shift(ym(now), -2); this.end = ym(now); }
        else if (k === 'year') { this.start = `${y}-01`; this.end = ym(now); }
        this.fetch();
      },
      async fetch() {
        const id = ++this._req; this.loading = true; this.error = null;
        history.replaceState(null, '', location.pathname + `?start=${this.start}&end=${this.end}`);
        try {
          const r = await App.api('/api/payroll/report/', { query: { start: this.start, end: this.end } });
          if (id !== this._req) return;
          this.rows = (r.data && r.data.results) || []; this.summary = (r.data && r.data.summary) || null;
        } catch (e) { if (id !== this._req) return; this.error = e.message; this.rows = []; }
        this.loading = false;
      },
      get periodText() { return this.start === this.end ? monthName(this.start) : monthName(this.start) + ' – ' + monthName(this.end); },
      print() { window.print(); },
      exportCsv() {
        const q = (v) => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
        const head = ['Staff', 'Designation', 'Months', 'Basic', 'Additions', 'Deductions', 'Net salary', 'Paid', 'Unpaid'];
        const lines = [head.map(q).join(',')].concat(this.rows.map(r => [r.staff_name, r.designation, r.months, n(r.basic), n(r.additions), n(r.deductions), n(r.net), n(r.paid), n(r.unpaid)].map(q).join(',')));
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
        a.download = `payroll-${this.start}-to-${this.end}.csv`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      },
    });
  };
})();
