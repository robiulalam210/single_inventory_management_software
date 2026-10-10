/*
 * Expense Head / Sub Head / Income Head — খরচ বা আয়ের খাত।
 * খরচের head এর নিচে sub head থাকে (যেমন Utilities › Electricity, Water)।
 * কোনো খাতে খরচ/আয় থাকলে মোছা যায় না, বন্ধ হয় — তাতে পুরনো হিসাবে খাতের নাম থেকে যায়।
 */
(function () {
  'use strict';
  const listOf = (r) => (Array.isArray(r && r.data) ? r.data : (r && r.data && r.data.results) || []);
  const norm = (s) => String(s || '').trim().toLowerCase();
  const errOf = (e) => { const d = e && e.data && e.data.data; if (d && typeof d === 'object') { const v = Object.values(d)[0]; return Array.isArray(v) ? v[0] : String(v); } return e.message; };

  window.headsPage = function (cfg) {
    const isExp = cfg.kind === 'expense';
    return {
      cfg, isExp, perms: cfg.perms,
      heads: [], subs: [], loading: true, error: null, q: '', showOff: false,
      open: {}, form: null, fe: '', saving: false, del: null, delError: '', deleting: false, toast: '',

      init() { this.load().then(() => { if (cfg.focus_sub && this.heads.length) this.heads.forEach(h => { this.open[h.id] = true; }); }); },
      async load() {
        this.loading = true; this.error = null;
        try {
          const [h, s] = await Promise.all([App.api(cfg.heads_api), isExp ? App.api(cfg.subheads_api) : Promise.resolve({ data: [] })]);
          this.heads = listOf(h).sort((a, b) => a.name.localeCompare(b.name)); this.subs = listOf(s);
        } catch (e) { this.error = e.message; }
        this.loading = false;
      },
      subsOf(h) { return this.subs.filter(s => s.head === h.id && (this.showOff || s.is_active !== false)).sort((a, b) => a.name.localeCompare(b.name)); },
      get shown() {
        const q = norm(this.q);
        return this.heads.filter(h => (this.showOff || h.is_active !== false)
          && (!q || norm(h.name).includes(q) || this.subs.some(s => s.head === h.id && norm(s.name).includes(q))));
      },
      get offCount() { return this.heads.filter(h => h.is_active === false).length + this.subs.filter(s => s.is_active === false).length; },
      count(h) { return Number(isExp ? h.expense_count : h.income_count) || 0; },
      total(h) { return isExp ? h.expense_total : h.income_total; },
      taka: (v) => App.taka(v),
      listLink(h) { return `${cfg.list_url}?head=${h.id}&period=all`; },
      toggleOpen(h) { this.open = { ...this.open, [h.id]: !this.open[h.id] }; },

      // form: { type: 'head'|'sub', id, name, head }
      edit(type, item, head) {
        if (item ? !this.perms.edit : !this.perms.create) return;
        this.form = { type, id: item ? item.id : null, name: item ? item.name : '', head: head ? head.id : (item && item.head) || null };
        this.fe = '';
        if (type === 'sub' && head) this.open = { ...this.open, [head.id]: true };
        this.$nextTick(() => { const el = document.getElementById('hd-name'); if (el) el.focus(); });
      },
      async saveForm() {
        const f = this.form; if (!f || this.saving) return;
        const name = (f.name || '').trim();
        if (!name) { this.fe = 'Enter a name.'; return; }
        const pool = f.type === 'head' ? this.heads : this.subs.filter(s => s.head === f.head);
        if (pool.some(x => x.id !== f.id && norm(x.name) === norm(name))) { this.fe = `"${name}" already exists${f.type === 'sub' ? ' under this head' : ''}.`; return; }
        this.saving = true;
        const api = f.type === 'head' ? cfg.heads_api : cfg.subheads_api;
        const body = f.type === 'head' ? { name } : { name, head: f.head };
        try {
          f.id ? await App.api(`${api}${f.id}/`, { method: 'PATCH', body }) : await App.api(api, { method: 'POST', body });
          this.flash(f.id ? 'Saved.' : `${name} added.`);
          this.form = null; await this.load();
        } catch (e) { this.fe = errOf(e); }
        this.saving = false;
      },
      async toggle(type, item) {
        if (!this.perms.edit) return;
        const api = type === 'head' ? cfg.heads_api : cfg.subheads_api;
        try {
          await App.api(`${api}${item.id}/`, { method: 'PATCH', body: { is_active: item.is_active === false } });
          this.flash(item.is_active === false ? `${item.name} is active again.` : `${item.name} is turned off. Past entries keep it.`);
          await this.load();
        } catch (e) { this.flash(errOf(e)); }
      },
      askDelete(type, item) { this.del = { type, item }; this.delError = ''; },
      get delUsed() {
        if (!this.del) return false;
        if (this.del.type === 'head') return this.count(this.del.item) > 0 || this.subs.some(s => s.head === this.del.item.id);
        return null; // sub head এর ব্যবহার এখানে জানা নেই — server ঠিক করবে
      },
      async remove() {
        if (!this.del || this.deleting) return;
        this.deleting = true; this.delError = '';
        const api = this.del.type === 'head' ? cfg.heads_api : cfg.subheads_api;
        try {
          const r = await App.api(`${api}${this.del.item.id}/`, { method: 'DELETE' });
          this.flash((r && r.message) || `${this.del.item.name} deleted.`);
          this.del = null; await this.load();
        } catch (e) { this.delError = errOf(e); }
        this.deleting = false;
      },
      escape() { if (this.del) this.del = null; else this.form = null; },
      flash(m) { this.toast = m; clearTimeout(this._t); this._t = setTimeout(() => { this.toast = ''; }, 3600); },
    };
  };
})();
