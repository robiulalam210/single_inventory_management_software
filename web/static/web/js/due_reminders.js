/*
 * Due Reminders — কার কাছে কত বাকি, আর এক চাপে WhatsApp / SMS এ বার্তা তৈরি।
 *   API: /api/reports/customer-due-reminders/  (reports/reminder_views.py)
 *   বার্তার ছাঁচ ({name} {amount} {shop} {phone} {invoices} {days}) দোকানি বদলাতে পারে — এই browser এ মনে থাকে।
 *   "পাঠানো হয়েছে" চিহ্নও এই browser এ থাকে (localStorage) — সার্ভারে কিছু জমা হয় না।
 *   লিংক চাপলে WhatsApp/SMS app এ বার্তা তৈরি হয়ে খোলে; পাঠানোর বোতাম দোকানি নিজে চাপেন।
 */
(function () {
  'use strict';

  const n = (v) => { const x = Number(v); return isFinite(x) ? x : 0; };
  const TPL_KEY = 'dueRemind.template';
  const SENT_KEY = 'dueRemind.sent';
  const DAY = 86400000;

  // localStorage বন্ধ থাকলেও (private mode ইত্যাদি) পেজ চলবে
  const store = {
    get(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
  };
  const money = (v) => { const x = n(v); return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2, minimumFractionDigits: Number.isInteger(x) ? 0 : 2 }).format(x); };
  const fmtDate = (s) => {
    if (!s) return '—';
    const d = new Date(String(s).length === 10 ? s + 'T00:00' : s);
    return isNaN(d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  window.dueReminders = function () {
    return {
      rows: [], summary: null, shop: { name: '', phone: '' }, defaultTpl: '',
      tpl: '', tplOpen: false,
      f: { q: '', days: 0, sort: 'amount' },
      dayOpts: [[0, 'Any age'], [7, '7+ days'], [15, '15+ days'], [30, '30+ days'], [60, '60+ days']],
      sorts: [{ key: 'amount', label: 'Most owed' }, { key: 'age', label: 'Oldest first' }, { key: 'name', label: 'Name' }],
      sent: {}, loading: true, error: '', toast: '', _t: null, _toast: null,

      init() {
        try { this.sent = JSON.parse(store.get(SENT_KEY) || '{}') || {}; } catch (e) { this.sent = {}; }
        this.fetch();
        this.$watch('tpl', (v) => store.set(TPL_KEY, v));
      },

      async fetch() {
        this.loading = true; this.error = '';
        try {
          const r = await App.api('/api/reports/customer-due-reminders/');
          const d = r.data || {};
          this.rows = d.customers || [];
          this.summary = d.summary || null;
          this.shop = d.shop || this.shop;
          this.defaultTpl = d.default_template || '';
          this.tpl = store.get(TPL_KEY) || this.defaultTpl;
        } catch (e) { this.error = e.message; this.rows = []; this.summary = null; }
        this.loading = false;
      },

      // ───── বার্তা ─────
      invoicesText(r) {
        const inv = r.invoices || [];
        const head = inv.slice(0, 5).map(i => (i.invoice_no || '#') + ' (৳' + money(i.due) + ')').join(', ');
        return inv.length > 5 ? head + ' ও আরও ' + (inv.length - 5) + 'টি' : head;
      },
      message(r) {
        const v = { name: r.name || '', amount: money(r.net_due), shop: this.shop.name || '', phone: this.shop.phone || '', invoices: this.invoicesText(r), days: String(r.days_overdue || 0) };
        let out = this.tpl || this.defaultTpl;
        Object.keys(v).forEach(k => { out = out.split('{' + k + '}').join(v[k]); });
        return out.replace(/[ \t]{2,}/g, ' ').trim();
      },
      wa(r) { return r.phone_intl ? 'https://wa.me/' + r.phone_intl + '?text=' + encodeURIComponent(this.message(r)) : ''; },
      sms(r) { return r.phone_intl ? 'sms:+' + r.phone_intl + '?&body=' + encodeURIComponent(this.message(r)) : ''; },
      get preview() { return this.rows.length ? this.message(this.rows[0]) : (this.tpl || this.defaultTpl); },
      resetTpl() { this.tpl = this.defaultTpl; },

      async copy(r) {
        const text = this.message(r);
        try { await navigator.clipboard.writeText(text); this.say('Message copied'); }
        catch (e) {
          const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
          try { document.execCommand('copy'); this.say('Message copied'); } catch (e2) { this.say('Could not copy'); }
          ta.remove();
        }
      },

      // ───── পাঠানো হয়েছে চিহ্ন ─────
      mark(r) { this.sent[r.customer_id] = Date.now(); store.set(SENT_KEY, JSON.stringify(this.sent)); },
      remindedText(r) {
        const t = this.sent[r.customer_id];
        if (!t) return '';
        const d = Math.floor((Date.now() - t) / DAY);
        return d <= 0 ? 'Reminded today' : (d === 1 ? 'Reminded yesterday' : 'Reminded ' + d + ' days ago');
      },

      // ───── তালিকা ─────
      get shown() {
        const q = this.f.q.trim().toLowerCase();
        let out = this.rows.filter(r => r.days_overdue >= this.f.days && (!q || (r.name || '').toLowerCase().includes(q) || (r.phone || '').toLowerCase().includes(q)));
        if (this.f.sort === 'age') out = out.slice().sort((a, b) => b.days_overdue - a.days_overdue || b.net_due - a.net_due);
        else if (this.f.sort === 'name') out = out.slice().sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        return out;
      },
      get shownTotal() { return this.shown.reduce((s, r) => s + n(r.net_due), 0); },
      get filtered() { return !!(this.f.q || this.f.days || this.f.sort !== 'amount'); },
      clearAll() { this.f = { q: '', days: 0, sort: 'amount' }; },

      taka: (v) => App.taka(v),
      fmtDate,
      age(r) { return r.oldest_due_date ? r.days_overdue + (r.days_overdue === 1 ? ' day' : ' days') : '—'; },
      ageCls(r) { return r.days_overdue >= 30 ? 'st-overdue' : (r.days_overdue >= 7 ? 'st-partial' : 'st-paid'); },
      print() { window.print(); },
      say(t) { this.toast = t; clearTimeout(this._toast); this._toast = setTimeout(() => { this.toast = ''; }, 2200); },
    };
  };
})();
