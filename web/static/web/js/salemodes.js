/*
 * Sale Mode — একই product ভিন্ন মাপে বিক্রি (KG এর বদলে Gram, Piece এর বদলে Dozen, বস্তা…)।
 * Stock সবসময় product এর নিজের unit এ থাকে; sale mode বলে একবার বিক্রিতে কত unit কমবে।
 *   GET    /api/sale-modes/          সব, সাথে product_count, sale_count
 *   POST   /api/sale-modes/          { name, code, base_unit, conversion_factor, price_type }
 *   PATCH  /api/sale-modes/<id>/
 *   DELETE /api/sale-modes/<id>/     ব্যবহার হলে বন্ধ হয়, না হলে মুছে যায়
 */
(function () {
  'use strict';

  const listOf = (r) => (Array.isArray(r && r.data) ? r.data : (r && r.data && r.data.results) || []);
  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const norm = (s) => String(s || '').trim().toLowerCase();
  // 12.000 → "12", 0.001 → "0.001", 0.333333 → "0.333"
  const fmt = (v, dp = 3) => { const x = Math.round(n(v) * 10 ** dp) / 10 ** dp; return String(x); };
  function explain(e) {
    const d = e.data && e.data.data;
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const [k, v] = Object.entries(d)[0] || [];
      if (k) return (Array.isArray(v) ? v[0] : String(v));
    }
    return e.message;
  }
  const errsOf = (e) => {
    const d = e && e.data && e.data.data, out = {};
    if (d && typeof d === 'object' && !Array.isArray(d)) Object.entries(d).forEach(([k, v]) => { out[k] = Array.isArray(v) ? v[0] : String(v); });
    return out;
  };

  const PRICE = {
    unit: { label: 'By weight / count', short: 'Per unit price', note: (m, b) => `Uses the product's price per ${b}. 250 g of rice at ৳80 per kg costs ৳20.` },
    flat: { label: 'Fixed price', short: 'Fixed price', note: (m, b) => `One set price for a whole ${m} on each product — e.g. a dozen eggs for ৳140.` },
    tier: { label: 'Cheaper in bulk', short: 'Bulk pricing', note: (m, b) => `The price per ${b} drops as the quantity grows. Set the steps on each product.` },
  };

  window.saleModes = function (perms) {
    return {
      perms, priceTypes: PRICE,
      modes: [], units: [], loading: true, error: null,
      q: '', view: 'active',
      formOpen: false, form: {}, fe: {}, formError: '', formSaving: false, invEdit: false,
      del: null, delError: '', deleting: false, busy: {}, toast: '',

      init() { this.load(); },
      async load() {
        this.loading = true; this.error = null;
        try {
          const [m, u] = await Promise.all([App.api('/api/sale-modes/'), App.api('/api/units/')]);
          this.modes = listOf(m); this.units = listOf(u).sort((a, b) => a.name.localeCompare(b.name));
        } catch (e) { this.error = e.message; }
        this.loading = false;
      },
      get counts() {
        const on = this.modes.filter(x => x.is_active !== false).length;
        return { active: on, inactive: this.modes.length - on, all: this.modes.length };
      },
      get views() {
        return [{ key: 'active', label: 'Active', n: this.counts.active }, { key: 'inactive', label: 'Inactive', n: this.counts.inactive }, { key: 'all', label: 'All', n: this.counts.all }];
      },
      // base unit অনুযায়ী ভাগ করে দেখাই — "Kilogram: Gram, Bosta…"
      get groups() {
        const q = norm(this.q), map = new Map();
        this.modes.forEach(m => {
          if (this.view === 'active' && m.is_active === false) return;
          if (this.view === 'inactive' && m.is_active !== false) return;
          if (q && !norm(m.name).includes(q) && !norm(m.code).includes(q) && !norm(m.base_unit_name).includes(q)) return;
          if (!map.has(m.base_unit)) {
            const u = this.units.find(x => x.id === m.base_unit) || { name: m.base_unit_name, code: '' };
            map.set(m.base_unit, { id: m.base_unit, unit: u, modes: [] });
          }
          map.get(m.base_unit).modes.push(m);
        });
        const gs = [...map.values()];
        gs.forEach(g => g.modes.sort((a, b) => n(a.conversion_factor) - n(b.conversion_factor)));
        return gs.sort((a, b) => a.unit.name.localeCompare(b.unit.name));
      },
      get activeUnits() { return this.units.filter(u => u.is_active !== false); },
      unitName(id) { const u = this.units.find(x => x.id === Number(id)); return u ? u.name : 'unit'; },
      fmt,
      rule(m) { return `1 ${m.name} = ${fmt(m.conversion_factor)} ${m.base_unit_name}`; },
      inverse(m) { const f = n(m.conversion_factor); return f && f < 1 ? `1 ${m.base_unit_name} = ${fmt(1 / f, 2)} ${m.name}` : ''; },
      priceShort(t) { return (PRICE[t] || PRICE.unit).short; },
      usage(m) {
        const p = n(m.product_count), s = n(m.sale_count), parts = [];
        if (p) parts.push(p + (p === 1 ? ' product' : ' products'));
        if (s) parts.push(s + (s === 1 ? ' sale line' : ' sale lines'));
        return parts.join(' · ') || 'Not used yet';
      },
      inUse(m) { return n(m.product_count) + n(m.sale_count) > 0; },

      // ───── form ─────
      openForm(m, baseUnit) {
        if (m ? !this.perms.edit : !this.perms.create) return;
        this.form = m
          ? { id: m.id, name: m.name, code: m.code, base_unit: String(m.base_unit), factor: fmt(m.conversion_factor), inv: '', price_type: m.price_type, sold: n(m.sale_count), was: fmt(m.conversion_factor), codeTouched: true }
          : { id: null, name: '', code: '', base_unit: baseUnit ? String(baseUnit) : (this.activeUnits[0] ? String(this.activeUnits[0].id) : ''), factor: '', inv: '', price_type: 'unit', sold: 0, codeTouched: false };
        this.syncInv(); this.invEdit = false;
        this.fe = {}; this.formError = ''; this.formOpen = true;
        this.$nextTick(() => this.$refs.smName && this.$refs.smName.focus());
      },
      get baseName() { return this.unitName(this.form.base_unit); },
      get modeName() { return (this.form.name || '').trim() || 'this mode'; },
      nameInput() {
        this.fe.name = '';
        if (!this.form.codeTouched) this.form.code = (this.form.name || '').replace(/[^A-Za-z0-9]/g, '').slice(0, 6).toUpperCase();
      },
      syncInv() { const f = n(this.form.factor); this.form.inv = f > 0 ? fmt(1 / f, 3) : ''; },
      factorInput() { this.fe.factor = ''; this.form.factor = String(this.form.factor).replace(/[^0-9.]/g, ''); this.syncInv(); },
      invInput() {
        this.fe.factor = ''; this.form.inv = String(this.form.inv).replace(/[^0-9.]/g, '');
        const i = n(this.form.inv); this.form.factor = i > 0 ? fmt(1 / i, 3) : '';
      },
      get sentence() {
        const f = n(this.form.factor);
        if (!f) return '';
        return `Selling 1 ${this.modeName} takes ${fmt(f)} ${this.baseName} out of stock.`;
      },
      // server এ ৩ দশমিক পর্যন্ত রাখা যায় — 1/3 এর মতো মান ঠিকমতো রাখা যায় না
      get precisionIssue() {
        const i = n(this.form.inv), f = n(this.form.factor);
        if (!(f > 0)) return '';
        if (f < 0.001) return `Too small to store. Pick a smaller base unit (e.g. Gram instead of Kilogram).`;
        if (this.invEdit && i > 0 && Math.abs(f * i - 1) > 0.005) return `This is saved as ${fmt(f)} ${this.baseName}, which is about ${fmt(1 / f, 2)} ${this.modeName} — close, but not exact.`;
        return '';
      },
      async saveForm() {
        const f = this.form, fe = {};
        const name = (f.name || '').trim(), code = (f.code || '').trim();
        if (!name) fe.name = 'Give it a name, like Gram or Dozen.';
        else if (this.modes.some(m => m.id !== f.id && norm(m.name) === norm(name))) fe.name = 'A sale mode with this name already exists.';
        if (!code) fe.code = 'Add a short code.';
        else if (this.modes.some(m => m.id !== f.id && norm(m.code) === norm(code))) fe.code = 'Another sale mode already uses this code.';
        if (!f.base_unit) fe.base_unit = 'Pick the unit stock is counted in.';
        const fac = n(f.factor);
        if (!(fac > 0)) fe.factor = 'Say how much one of these is.';
        else if (fac < 0.001) fe.factor = 'Too small to store. Pick a smaller base unit.';
        this.fe = fe;
        if (Object.keys(fe).length || this.formSaving) return;
        this.formSaving = true; this.formError = '';
        const body = { name, code, base_unit: Number(f.base_unit), conversion_factor: fmt(fac), price_type: f.price_type };
        try {
          f.id ? await App.api(`/api/sale-modes/${f.id}/`, { method: 'PATCH', body })
               : await App.api('/api/sale-modes/', { method: 'POST', body });
          this.formOpen = false;
          this.flash(f.id ? 'Saved.' : `${name} added. Set its price on each product that sells this way.`);
          await this.load();
        } catch (e) { this.fe = errsOf(e); if (this.fe.conversion_factor) this.fe.factor = this.fe.conversion_factor; this.formError = Object.keys(this.fe).length ? '' : explain(e); }
        this.formSaving = false;
      },

      async toggle(m) {
        if (!this.perms.edit || this.busy[m.id]) return;
        this.busy = { ...this.busy, [m.id]: true };
        const on = m.is_active === false;
        try {
          await App.api(`/api/sale-modes/${m.id}/`, { method: 'PATCH', body: { is_active: on } });
          this.flash(on ? `${m.name} is active again.` : `${m.name} is hidden from sale screens.`);
          await this.load();
        } catch (e) { this.flash(explain(e)); }
        this.busy = { ...this.busy, [m.id]: false };
      },
      askDelete(m) { this.del = m; this.delError = ''; },
      async remove() {
        if (!this.del || this.deleting) return;
        this.deleting = true; this.delError = '';
        try {
          const r = await App.api(`/api/sale-modes/${this.del.id}/`, { method: 'DELETE' });
          this.flash((r && r.message) || `${this.del.name} deleted.`);
          this.del = null; await this.load();
        } catch (e) { this.delError = e.message; }
        this.deleting = false;
      },
      escape() { if (this.formOpen) this.formOpen = false; else this.del = null; },
      flash(m) { this.toast = m; clearTimeout(this._t); this._t = setTimeout(() => { this.toast = ''; }, 3800); },
    };
  };
})();
