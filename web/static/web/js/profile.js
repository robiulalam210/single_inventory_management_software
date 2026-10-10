/*
 * Business Profile — invoice আর রসিদের মাথায় যা ছাপা হয়।
 *   GET   /api/business/
 *   PATCH /api/business/                name, phone, email, address, trade_license, website, logo:null
 *   PATCH /api/business/logo/           multipart { logo }
 */
(function () {
  'use strict';

  const FIELDS = ['name', 'phone', 'email', 'address', 'trade_license', 'website'];
  const fmtDate = (s) => {
    if (!s) return '—';
    const d = new Date(String(s).length === 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };
  const errsOf = (e) => { const d = e && e.data && e.data.data; return d && typeof d === 'object' && !Array.isArray(d) ? d : (e && e.data && typeof e.data === 'object' && !e.data.message ? e.data : {}); };

  window.companyProfile = function (init) {
    return {
      id: init.id, canEdit: init.can_edit,
      co: null, f: {}, orig: {}, fe: {}, loading: true, error: null, saving: false, formError: '',
      logoBusy: false, logoErr: '', drag: false, toast: '',

      async init() {
        try {
          const r = await App.api('/api/business/');
          this.set(r.data && r.data.id ? r.data : r);
        } catch (e) { this.error = e.message; }
        this.loading = false;
        window.addEventListener('beforeunload', (ev) => { if (this.dirty) { ev.preventDefault(); ev.returnValue = ''; } });
      },
      set(co) {
        this.co = co;
        const f = {}; FIELDS.forEach(k => { f[k] = co[k] || ''; });
        this.f = f; this.orig = { ...f };
      },
      get dirty() { return FIELDS.some(k => (this.f[k] || '').trim() !== (this.orig[k] || '').trim()); },
      get initial() { return (this.f.name || '?').trim().slice(0, 1).toUpperCase(); },
      date: fmtDate,
      get daysText() {
        const d = this.co && this.co.days_until_expiry;
        if (d == null) return '';
        if (d < 0) return 'Ended';
        if (d === 0) return 'Ends today';
        return `${d} day${d === 1 ? '' : 's'} left`;
      },
      planLabel(v) { return ({ basic: 'Basic', standard: 'Standard', premium: 'Premium' })[v] || v; },
      pct(a, b) { return Math.min(100, (Number(a) || 0) / Math.max(1, Number(b) || 1) * 100); },

      async save() {
        if (!this.canEdit || this.saving || !this.dirty) return;
        const f = this.f, fe = {};
        if (!f.name.trim()) fe.name = 'Your shop needs a name — it is printed on every invoice.';
        if (f.email.trim() && !/^\S+@\S+\.\S+$/.test(f.email.trim())) fe.email = 'Enter a valid email address.';
        this.fe = fe;
        if (Object.keys(fe).length) return;
        this.saving = true; this.formError = '';
        let web = f.website.trim();
        if (web && !/^https?:\/\//i.test(web)) web = 'https://' + web;
        const body = {};
        FIELDS.forEach(k => { const v = k === 'website' ? web : f[k].trim(); if (v !== (this.orig[k] || '').trim()) body[k] = v || null; });
        if ('name' in body && !body.name) delete body.name;
        try {
          const r = await App.api('/api/business/', { method: 'PATCH', body });
          this.set(r.data && r.data.id ? r.data : r);
          this.flash('Saved. New invoices and receipts use these details.');
        } catch (e) {
          const d = errsOf(e); const fe2 = {};
          Object.entries(d).forEach(([k, v]) => { fe2[k] = Array.isArray(v) ? v[0] : String(v); });
          if (fe2.name && /exists/i.test(fe2.name)) fe2.name = 'This name is not valid.';
          if (fe2.website) fe2.website = 'Enter a web address like example.com';
          this.fe = fe2; this.formError = Object.keys(fe2).length ? '' : e.message;
        }
        this.saving = false;
      },
      undo() { this.f = { ...this.orig }; this.fe = {}; this.formError = ''; },

      // ───── logo ─────
      pick() { this.$refs.logoIn && this.$refs.logoIn.click(); },
      async upload(file) {
        if (!file || !this.canEdit) return;
        this.logoErr = '';
        if (!/^image\//.test(file.type)) { this.logoErr = 'Pick an image (PNG, JPG or WebP).'; return; }
        if (file.size > 5 * 1024 * 1024) { this.logoErr = 'Use an image under 5 MB.'; return; }
        this.logoBusy = true;
        const body = new FormData(); body.append('logo', file);
        try {
          const r = await App.api('/api/business/logo/', { method: 'PATCH', body });
          this.co = { ...this.co, logo: r.data.logo };
          this.flash('Logo updated.');
        } catch (e) { this.logoErr = e.message; }
        this.logoBusy = false;
        if (this.$refs.logoIn) this.$refs.logoIn.value = '';
      },
      onDrop(ev) { this.drag = false; const f = ev.dataTransfer && ev.dataTransfer.files[0]; if (f) this.upload(f); },
      async removeLogo() {
        if (!this.canEdit || this.logoBusy) return;
        this.logoBusy = true; this.logoErr = '';
        try {
          const r = await App.api('/api/business/', { method: 'PATCH', body: { logo: null } });
          const co = r.data && r.data.id ? r.data : r;
          this.co = { ...this.co, logo: co.logo || null };
          this.flash('Logo removed.');
        } catch (e) { this.logoErr = e.message; }
        this.logoBusy = false;
      },
      flash(m) { this.toast = m; clearTimeout(this._t); this._t = setTimeout(() => { this.toast = ''; }, 3500); },
    };
  };
})();
