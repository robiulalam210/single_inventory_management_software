/*
 * Category / Brand / Group / Source — একই রকম ছোট তালিকা, তাই একটাই page।
 *   GET    <api>            সব, সাথে product_count
 *   POST   <api>            { name, description? }
 *   PATCH  <api><id>/       { name, description? } বা { is_active }
 *   DELETE <api><id>/       product থাকলে inactive হয়, না থাকলে মুছে যায় (204)
 */
(function () {
  'use strict';

  const listOf = (r) => (Array.isArray(r && r.data) ? r.data : (r && r.data && r.data.results) || []);
  const norm = (s) => String(s || '').trim().toLowerCase();
  function explain(e) {
    const d = e.data && e.data.data;
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const [k, v] = Object.entries(d)[0] || [];
      if (k) return (Array.isArray(v) ? v[0] : String(v));
    }
    return e.message;
  }

  window.lookupList = function (cfg) {
    return {
      cfg, perms: cfg.perms,
      items: [], loading: true, error: null,
      q: '', view: 'active',
      formOpen: false, form: {}, fe: {}, formError: '', formSaving: false, addMore: false,
      del: null, delError: '', deleting: false,
      busy: {}, adding: {}, toast: '',

      init() { this.load(); },
      async load() {
        this.loading = true; this.error = null;
        try {
          const r = await App.api(cfg.api);
          this.items = listOf(r).sort((a, b) => a.name.localeCompare(b.name));
        } catch (e) { this.error = e.message; }
        this.loading = false;
      },
      get counts() {
        const on = this.items.filter(x => x.is_active !== false).length;
        return { active: on, inactive: this.items.length - on, all: this.items.length };
      },
      get views() {
        return [{ key: 'active', label: 'Active', n: this.counts.active }, { key: 'inactive', label: 'Inactive', n: this.counts.inactive }, { key: 'all', label: 'All', n: this.counts.all }];
      },
      get rows() {
        const q = norm(this.q);
        return this.items.filter(x => {
          if (this.view === 'active' && x.is_active === false) return false;
          if (this.view === 'inactive' && x.is_active !== false) return false;
          return !q || norm(x.name).includes(q) || norm(x.description).includes(q);
        });
      },
      get unusedExamples() { return cfg.examples.filter(n => !this.items.some(x => norm(x.name) === norm(n))); },
      used(x) { return Number(x.product_count) || 0; },
      usage(x) { const n = this.used(x); return n ? n + (n === 1 ? ' product' : ' products') : 'No products yet'; },
      productsLink(x) { return cfg.filter_param ? `/app/products/?${cfg.filter_param}=${x.id}` : ''; },

      // ───── quick add (empty state chips) ─────
      async quickAdd(name) {
        if (!this.perms.create || this.adding[name]) return;
        this.adding = { ...this.adding, [name]: true };
        try { await App.api(cfg.api, { method: 'POST', body: { name } }); await this.load(); this.flash(`${name} added.`); }
        catch (e) { this.flash(explain(e)); }
        this.adding = { ...this.adding, [name]: false };
      },

      // ───── add / edit ─────
      openForm(x) {
        if (x ? !this.perms.edit : !this.perms.create) return;
        this.form = x ? { id: x.id, name: x.name || '', description: x.description || '', used: this.used(x) }
                      : { id: null, name: '', description: '', used: 0 };
        this.fe = {}; this.formError = ''; this.formOpen = true;
        this.$nextTick(() => this.$refs.lkName && this.$refs.lkName.focus());
      },
      async saveForm() {
        const f = this.form, name = (f.name || '').trim();
        const clash = name && this.items.find(x => x.id !== f.id && norm(x.name) === norm(name));
        this.fe = {};
        if (!name) this.fe.name = `Give the ${cfg.singular} a name.`;
        else if (clash) this.fe.name = `"${clash.name}" already exists${clash.is_active === false ? ' (inactive — turn it back on instead)' : ''}.`;
        if (this.fe.name || this.formSaving) return;
        this.formSaving = true; this.formError = '';
        const body = { name };
        if (cfg.has_description) body.description = (f.description || '').trim() || null;
        try {
          f.id ? await App.api(`${cfg.api}${f.id}/`, { method: 'PATCH', body })
               : await App.api(cfg.api, { method: 'POST', body });
          this.flash(f.id ? 'Saved.' : `${name} added.`);
          await this.load();
          if (!f.id && this.addMore) { this.form = { id: null, name: '', description: '', used: 0 }; this.$nextTick(() => this.$refs.lkName && this.$refs.lkName.focus()); }
          else this.formOpen = false;
        } catch (e) { this.formError = explain(e); }
        this.formSaving = false;
      },

      async toggle(x) {
        if (!this.perms.edit || this.busy[x.id]) return;
        this.busy = { ...this.busy, [x.id]: true };
        const on = x.is_active === false;
        try {
          await App.api(`${cfg.api}${x.id}/`, { method: 'PATCH', body: { is_active: on } });
          this.flash(on ? `${x.name} is active again.` : `${x.name} is hidden from new products.`);
          await this.load();
        } catch (e) { this.flash(explain(e)); }
        this.busy = { ...this.busy, [x.id]: false };
      },
      askDelete(x) { this.del = x; this.delError = ''; },
      async remove() {
        if (!this.del || this.deleting) return;
        this.deleting = true; this.delError = '';
        try {
          const r = await App.api(`${cfg.api}${this.del.id}/`, { method: 'DELETE' });
          this.flash((r && r.message) || `${this.del.name} deleted.`);
          this.del = null; await this.load();
        } catch (e) { this.delError = e.message; }
        this.deleting = false;
      },
      escape() { if (this.formOpen) this.formOpen = false; else this.del = null; },
      flash(m) { this.toast = m; clearTimeout(this._t); this._t = setTimeout(() => { this.toast = ''; }, 3500); },
    };
  };
})();
