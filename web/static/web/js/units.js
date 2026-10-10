/*
 * Units — product কোন মাপে বিক্রি হয় (Pcs, Kg, Litre…)।
 *   GET    /api/units/            সব unit, সাথে product_count / sale_mode_count
 *   POST   /api/units/            { name, code }
 *   PATCH  /api/units/<id>/       { name, code } বা { is_active }
 *   DELETE /api/units/<id>/       ব্যবহার হলে inactive হয়, না হলে মুছে যায় (204)
 */
(function () {
  'use strict';

  const listOf = (r) => (Array.isArray(r && r.data) ? r.data : (r && r.data && r.data.results) || []);
  const norm = (s) => String(s || '').trim().toLowerCase();

  // নতুন দোকানে সাধারণত যেগুলো লাগে। on = আগে থেকে টিক দেওয়া থাকবে।
  const COMMON = [
    { name: 'Pieces', code: 'pcs', on: true, note: 'Single items: a pen, a phone, a shirt' },
    { name: 'Kilogram', code: 'kg', on: true, note: 'Rice, sugar, vegetables' },
    { name: 'Gram', code: 'g', on: true, note: 'Spices, small loose items' },
    { name: 'Litre', code: 'L', on: true, note: 'Oil, milk, liquids' },
    { name: 'Box', code: 'box', on: true, note: 'Items sold by the box' },
    { name: 'Packet', code: 'pkt', on: true, note: 'Biscuits, noodles, sachets' },
    { name: 'Dozen', code: 'dz', on: true, note: 'Eggs, bananas — 12 at a time' },
    { name: 'Millilitre', code: 'ml', on: false, note: 'Small bottles, medicine' },
    { name: 'Bottle', code: 'btl', on: false, note: 'Drinks, sauces' },
    { name: 'Carton', code: 'ctn', on: false, note: 'Wholesale cartons' },
    { name: 'Bag', code: 'bag', on: false, note: 'Sacks of rice, flour, cement' },
    { name: 'Metre', code: 'm', on: false, note: 'Cloth, wire, pipe' },
    { name: 'Feet', code: 'ft', on: false, note: 'Wood, tiles, pipe' },
    { name: 'Pair', code: 'pair', on: false, note: 'Shoes, socks' },
    { name: 'Set', code: 'set', on: false, note: 'Item sold together as a set' },
  ];

  function explain(e) {
    const d = e.data && e.data.data;
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const [k, v] = Object.entries(d)[0] || [];
      if (k) return (Array.isArray(v) ? v[0] : String(v));
    }
    return e.message;
  }

  window.unitList = function (perms) {
    return {
      perms,
      units: [], loading: true, error: null,
      q: '', view: 'active',
      formOpen: false, form: {}, fe: {}, formError: '', formSaving: false,
      del: null, delError: '', deleting: false,
      quickOpen: false, quick: [], quickSaving: false, quickError: '',
      busy: {}, toast: '',
      norm,

      init() { this.load(); },
      async load() {
        this.loading = true; this.error = null;
        try {
          const r = await App.api('/api/units/');
          this.units = listOf(r).sort((a, b) => a.name.localeCompare(b.name));
        } catch (e) { this.error = e.message; }
        this.loading = false;
      },

      get counts() {
        const active = this.units.filter(u => u.is_active !== false).length;
        return { all: this.units.length, active, inactive: this.units.length - active };
      },
      get views() {
        return [
          { key: 'active', label: 'Active', n: this.counts.active },
          { key: 'inactive', label: 'Inactive', n: this.counts.inactive },
          { key: 'all', label: 'All', n: this.counts.all },
        ];
      },
      get rows() {
        const q = norm(this.q);
        return this.units.filter(u => {
          if (this.view === 'active' && u.is_active === false) return false;
          if (this.view === 'inactive' && u.is_active !== false) return false;
          return !q || norm(u.name).includes(q) || norm(u.code).includes(q);
        });
      },
      get unused() { return this.units.filter(u => u.is_active !== false && !u.product_count).length; },
      usage(u) {
        const p = Number(u.product_count) || 0, s = Number(u.sale_mode_count) || 0;
        if (!p && !s) return 'Not used yet';
        const parts = [];
        if (p) parts.push(p + (p === 1 ? ' product' : ' products'));
        if (s) parts.push(s + (s === 1 ? ' sale mode' : ' sale modes'));
        return parts.join(' · ');
      },
      inUse(u) { return (Number(u.product_count) || 0) + (Number(u.sale_mode_count) || 0) > 0; },

      // ───── add / edit ─────
      openForm(u) {
        if (u ? !this.perms.edit : !this.perms.create) return;
        this.form = u ? { id: u.id, name: u.name || '', code: u.code || '', used: Number(u.product_count) || 0 }
                      : { id: null, name: '', code: '', used: 0 };
        this.fe = {}; this.formError = ''; this.formOpen = true;
        this.$nextTick(() => this.$refs.unName && this.$refs.unName.focus());
      },
      clash(name, code, exceptId) {
        const n = norm(name), c = norm(code);
        return {
          name: n && this.units.find(u => u.id !== exceptId && norm(u.name) === n),
          code: c && this.units.find(u => u.id !== exceptId && norm(u.code) === c),
        };
      },
      async saveForm() {
        const f = this.form, fe = {};
        const name = f.name.trim(), code = f.code.trim();
        const hit = this.clash(name, code, f.id);
        if (!name) fe.name = 'Give the unit a name, like Kilogram or Pieces.';
        else if (hit.name) fe.name = `"${hit.name.name}" already exists${hit.name.is_active === false ? ' (inactive — activate it instead)' : ''}.`;
        if (!fe.name && hit.code) fe.code = `"${hit.code.name}" already uses this short name.`;
        this.fe = fe;
        if (Object.keys(fe).length || this.formSaving) return;
        this.formSaving = true; this.formError = '';
        const body = { name, code: code || null };
        try {
          f.id ? await App.api(`/api/units/${f.id}/`, { method: 'PATCH', body })
               : await App.api('/api/units/', { method: 'POST', body });
          this.formOpen = false;
          this.flash(f.id ? 'Unit updated.' : `${name} added.`);
          await this.load();
        } catch (e) { this.formError = explain(e); }
        this.formSaving = false;
      },

      async toggle(u) {
        if (!this.perms.edit || this.busy[u.id]) return;
        this.busy = { ...this.busy, [u.id]: true };
        const on = u.is_active === false;
        try {
          await App.api(`/api/units/${u.id}/`, { method: 'PATCH', body: { is_active: on } });
          this.flash(on ? `${u.name} is active again.` : `${u.name} is hidden from new products.`);
          await this.load();
        } catch (e) { this.flash(explain(e)); }
        this.busy = { ...this.busy, [u.id]: false };
      },

      // ───── delete ─────
      askDelete(u) { this.del = u; this.delError = ''; },
      async remove() {
        if (!this.del || this.deleting) return;
        this.deleting = true; this.delError = '';
        try {
          const r = await App.api(`/api/units/${this.del.id}/`, { method: 'DELETE' });
          // মুছে গেলে server 204 দেয়, তখন body থাকে না
          this.flash((r && r.message) || `${this.del.name} deleted.`);
          this.del = null;
          await this.load();
        } catch (e) { this.delError = e.message; }
        this.deleting = false;
      },

      // ───── common units ─────
      openQuick() {
        this.quick = COMMON.map(c => {
          const have = this.clash(c.name, c.code, null);
          const exists = have.name || have.code;
          return { ...c, exists: exists ? exists.name : '', pick: !exists && c.on };
        });
        this.quickError = ''; this.quickOpen = true;
      },
      get quickPicked() { return this.quick.filter(c => c.pick && !c.exists); },
      get quickMissing() { return COMMON.filter(c => { const h = this.clash(c.name, c.code, null); return !h.name && !h.code; }).length; },
      async addQuick() {
        const list = this.quickPicked;
        if (!list.length || this.quickSaving) return;
        this.quickSaving = true; this.quickError = '';
        let ok = 0; const failed = [];
        // একটা একটা করে — একটা আটকালেও বাকিগুলো যোগ হয়
        for (const c of list) {
          try { await App.api('/api/units/', { method: 'POST', body: { name: c.name, code: c.code } }); ok++; c.exists = c.name; c.pick = false; }
          catch (e) { failed.push(c.name + ': ' + explain(e)); }
        }
        await this.load();
        this.quickSaving = false;
        if (failed.length) { this.quickError = (ok ? ok + ' added. ' : '') + 'Could not add ' + failed.join('; '); return; }
        this.quickOpen = false;
        this.flash(ok + (ok === 1 ? ' unit added.' : ' units added.'));
      },

      flash(msg) {
        this.toast = msg;
        clearTimeout(this._toast);
        this._toast = setTimeout(() => { this.toast = ''; }, 3500);
      },
    };
  };
})();
