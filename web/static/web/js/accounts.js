/*
 * Accounts — সব account এর balance, আর একটা account এর statement।
 *   /api/accounts/?no_pagination=true
 *   /api/accounts/<id>/statement/?start=&end=   (তারিখের ক্রমে, প্রতিটার পরে balance, আর হিসাব মিলছে কিনা)
 *   /api/accounts/<id>/toggle_active/
 */
(function () {
  'use strict';

  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const r2 = (v) => Math.round((n(v) + Number.EPSILON) * 100) / 100;
  const listOf = (r) => (Array.isArray(r.data) ? r.data : (r.data && r.data.results) || []);
  const fmtDate = (s) => {
    if (!s) return '';
    const d = new Date(String(s).length === 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const fmtTime = (s) => { const d = new Date(s); return isNaN(d) || String(s).length === 10 ? '' : d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); };
  const TYPES = ['Cash', 'Bank', 'Mobile banking', 'Other'];
  const KEY = { 'Cash': 'cash', 'Bank': 'bank', 'Mobile banking': 'mobile', 'Other': 'other' };
  function explain(e) {
    const d = e.data && e.data.data;
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const [k, v] = Object.entries(d)[0] || [];
      if (k) return (Array.isArray(v) ? v[0] : String(v));
    }
    return e.message;
  }

  window.accountList = function (perms, company) {
    return {
      perms, company, types: TYPES,
      accounts: [], loading: true, error: null, showInactive: false,
      sel: null,
      presets: [
        { key: 'month', label: 'This month' }, { key: '30d', label: 'Last 30 days' },
        { key: 'year', label: 'This year' }, { key: 'all', label: 'All time' }, { key: 'custom', label: 'Custom' },
      ],
      st: { preset: 'month', from: '', to: '', data: null, loading: false, error: '', rows: null },
      formOpen: false, form: {}, fe: {}, formError: '', formSaving: false,
      confirmDel: false, delError: '', deleting: false,
      toast: '', _sreq: 0,

      init() { this.load(); },
      async load() {
        this.loading = true; this.error = null;
        try {
          const r = await App.api('/api/accounts/', { query: { no_pagination: 'true' } });
          this.accounts = listOf(r).sort((a, b) => (b.is_active - a.is_active) || TYPES.indexOf(a.ac_type) - TYPES.indexOf(b.ac_type) || a.name.localeCompare(b.name));
          if (this.sel) { const fresh = this.accounts.find(a => a.id === this.sel.id); if (fresh) this.sel = fresh; }
        } catch (e) { this.error = e.message; }
        this.loading = false;
      },
      get activeList() { return this.accounts.filter(a => a.is_active !== false); },
      get shown() { return this.showInactive ? this.accounts : this.activeList; },
      get total() { return r2(this.activeList.reduce((s, a) => s + n(a.balance), 0)); },
      get byType() {
        const groups = TYPES.map(t => ({ type: t, key: KEY[t], total: r2(this.activeList.filter(a => a.ac_type === t).reduce((s, a) => s + n(a.balance), 0)) }))
          .filter(g => this.activeList.some(a => a.ac_type === g.type));
        const max = Math.max(1, ...groups.map(g => Math.abs(g.total)));
        groups.forEach(g => { g.pct = Math.max(g.total ? 2 : 0, Math.abs(g.total) / max * 100); });
        return groups;
      },
      typeKey: (a) => KEY[a.ac_type] || 'other',
      taka: (v) => App.taka(v),
      round2: r2,
      date: fmtDate,
      time: fmtTime,

      // ───── statement ─────
      open(a) {
        this.sel = a;
        this.st.data = null; this.st.rows = null; this.st.error = '';
        document.body.style.overflow = 'hidden';
        this.setPreset(this.st.preset);
      },
      shut() { this.sel = null; document.body.style.overflow = ''; },
      print() { window.print(); },
      setPreset(key) {
        this.st.preset = key;
        const t = new Date(); t.setHours(0, 0, 0, 0);
        if (key === 'month') { this.st.from = iso(new Date(t.getFullYear(), t.getMonth(), 1)); this.st.to = iso(t); }
        else if (key === '30d') { const s = new Date(t); s.setDate(s.getDate() - 29); this.st.from = iso(s); this.st.to = iso(t); }
        else if (key === 'year') { this.st.from = iso(new Date(t.getFullYear(), 0, 1)); this.st.to = iso(t); }
        else if (key === 'all') { this.st.from = ''; this.st.to = iso(t); }
        else { if (!this.st.from) this.st.from = iso(new Date(t.getFullYear(), t.getMonth(), 1)); if (!this.st.to) this.st.to = iso(t); }
        this.loadStatement();
      },
      async loadStatement() {
        if (!this.sel) return;
        if (this.st.from && this.st.to && this.st.from > this.st.to) [this.st.from, this.st.to] = [this.st.to, this.st.from];
        const id = ++this._sreq;
        this.st.loading = true; this.st.error = '';
        try {
          const r = await App.api(`/api/accounts/${this.sel.id}/statement/`, { query: { start: this.st.from, end: this.st.to } });
          if (id !== this._sreq) return;
          // সবচেয়ে নতুন উপরে
          const d = r.data;
          d.rows = (d.rows || []).slice().reverse();
          this.st.data = d; this.st.rows = d.rows;
        } catch (e) {
          if (id !== this._sreq) return;
          this.st.error = e.message; this.st.data = null; this.st.rows = [];
        }
        this.st.loading = false;
      },
      get rangeText() {
        if (this.st.preset === 'all') return 'All time, up to ' + fmtDate(this.st.to);
        return fmtDate(this.st.from) + ' – ' + fmtDate(this.st.to);
      },
      label(r) {
        if (r.is_opening_balance) return 'Opening balance';
        const d = (r.description || '').toLowerCase();
        if (d.startsWith('reversal')) return 'Reversed';
        if (d.includes('money receipt')) return 'Payment received';
        if (d.includes('supplier payment')) return 'Paid supplier';
        if (d.includes('purchase cancellation')) return 'Purchase refund';
        if (d.includes('purchase')) return 'Purchase payment';
        if (d.includes('expense')) return 'Expense';
        if (d.includes('income')) return 'Other income';
        if (d.includes('transfer')) return r.type === 'credit' ? 'Transfer in' : 'Transfer out';
        if (d.includes('return')) return 'Return refund';
        return r.type === 'credit' ? 'Money in' : 'Money out';
      },
      async toggleActive() {
        if (!this.sel) return;
        try {
          const r = await App.api(`/api/accounts/${this.sel.id}/toggle_active/`, { method: 'POST' });
          this.flash(r.message || 'Updated.');
          await this.load();
        } catch (e) { this.flash(e.message); }
      },

      // ───── add / edit ─────
      openForm(a) {
        this.form = a ? {
          id: a.id, ac_no: a.ac_no, ac_type: a.ac_type, name: a.name || '', ac_number: a.ac_number || '',
          bank_name: a.bank_name || '', branch: a.branch || '', opening_balance: String(n(a.opening_balance) || ''), was: n(a.opening_balance),
        } : { id: null, ac_type: 'Cash', name: '', ac_number: '', bank_name: '', branch: '', opening_balance: '', was: 0 };
        this.fe = {}; this.formError = ''; this.formOpen = true;
        this.$nextTick(() => this.$refs.afName && this.$refs.afName.focus());
      },
      get openingDelta() { return this.form.id ? r2(n(this.form.opening_balance) - this.form.was) : 0; },
      async saveForm() {
        const f = this.form, fe = {};
        if (!f.name.trim()) fe.name = 'Give the account a name.';
        if ((f.ac_type === 'Bank' || f.ac_type === 'Mobile banking') && !f.ac_number.trim())
          fe.number = f.ac_type === 'Bank' ? 'Enter the bank account number.' : 'Enter the wallet number.';
        this.fe = fe;
        if (Object.keys(fe).length || this.formSaving) return;
        this.formSaving = true; this.formError = '';
        const body = {
          ac_type: f.ac_type, name: f.name.trim(),
          ac_number: f.ac_type === 'Cash' ? null : (f.ac_number.trim() || null),
          bank_name: f.ac_type === 'Bank' ? (f.bank_name.trim() || null) : null,
          branch: f.ac_type === 'Bank' ? (f.branch.trim() || null) : null,
          opening_balance: r2(f.opening_balance).toFixed(2),
        };
        try {
          f.id ? await App.api(`/api/accounts/${f.id}/`, { method: 'PATCH', body })
               : await App.api('/api/accounts/', { method: 'POST', body });
          this.formOpen = false;
          this.flash(f.id ? 'Account updated.' : `${body.name} added.`);
          await this.load();
          if (this.sel) this.loadStatement();
        } catch (e) { this.formError = explain(e); }
        this.formSaving = false;
      },
      askDelete() { this.delError = ''; this.confirmDel = true; },
      async remove() {
        if (!this.sel || this.deleting) return;
        this.deleting = true; this.delError = '';
        try {
          const r = await App.api(`/api/accounts/${this.sel.id}/`, { method: 'DELETE' });
          this.confirmDel = false;
          this.flash(r.message || 'Done.');
          this.shut(); await this.load();
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
