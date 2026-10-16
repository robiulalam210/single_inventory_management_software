(function () { try { var t = localStorage.getItem('mm-theme'); if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t); } catch (e) { /* ignore */ } })();
/*
 * Meherin Mart web — সব module এর সাধারণ JavaScript helper।
 *
 * App.api('/api/...') — একই backend API, browser এর session দিয়ে:
 *   • CSRF token নিজে থেকেই যায় (POST/PATCH/DELETE)
 *   • X-Client-Source: web — audit log এ "Web app" হিসেবে দেখায়
 *   • session শেষ হলে login page এ নিয়ে যায়, ফিরে আসার ঠিকানা সহ
 */
(function () {
  'use strict';

  function cookie(name) {
    const m = document.cookie.match('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)');
    return m ? decodeURIComponent(m[1]) : null;
  }

  function toLogin() {
    const next = encodeURIComponent(location.pathname + location.search);
    location.href = '/app/login/?expired=1&next=' + next;
  }

  async function api(path, opts) {
    opts = opts || {};
    const method = (opts.method || 'GET').toUpperCase();
    const headers = Object.assign({
      'Accept': 'application/json',
      'X-Client-Source': 'web',
      'X-Requested-With': 'XMLHttpRequest',
    }, opts.headers || {});
    let body = opts.body;
    if (body && !(body instanceof FormData) && typeof body !== 'string') {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
    if (method !== 'GET' && method !== 'HEAD') headers['X-CSRFToken'] = cookie('csrftoken') || '';

    let url = path;
    if (opts.query) {
      const q = new URLSearchParams();
      Object.entries(opts.query).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== '') q.append(k, v); });
      const s = q.toString();
      if (s) url += (url.includes('?') ? '&' : '?') + s;
    }

    let res;
    try {
      res = await fetch(url, { method, headers, body, credentials: 'same-origin' });
    } catch (e) {
      throw new ApiError('Cannot reach the server. Check your internet or network connection.', 0);
    }
    if (res.status === 401 || res.status === 403) {
      // session শেষ (403 এ CSRF/permission ও হতে পারে — তখন বার্তা দেখাই)
      const data = await res.json().catch(() => ({}));
      const msg = (data && (data.detail || data.message)) || '';
      if (res.status === 401 || /credentials|authenticat/i.test(msg)) { toLogin(); return new Promise(() => {}); }
      throw new ApiError(msg || 'You do not have permission to do this.', res.status, data);
    }
    const data = await res.json().catch(() => null);
    if (!res.ok || (data && data.status === false)) {
      const msg = (data && (data.message || data.detail)) || ('Request failed (' + res.status + ')');
      throw new ApiError(msg, res.status, data);
    }
    return data;
  }

  class ApiError extends Error {
    constructor(message, status, data) { super(message); this.status = status; this.data = data; }
  }

  const fmtMoney = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  /*
   * টাকা কথায় — রসিদে লেখার জন্য, দেশি গণনায় (crore / lakh / thousand)।
   * 1512.50 → "Taka one thousand five hundred twelve and paisa fifty only"
   */
  const ONES = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven',
    'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'];
  const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];
  function under100(n) { return n < 20 ? ONES[n] : TENS[Math.floor(n / 10)] + (n % 10 ? '-' + ONES[n % 10] : ''); }
  function under1000(n) {
    const h = Math.floor(n / 100), r = n % 100;
    return [h ? ONES[h] + ' hundred' : '', r ? under100(r) : ''].filter(Boolean).join(' ');
  }
  function inWords(n) {
    if (n === 0) return 'zero';
    const parts = [];
    const crore = Math.floor(n / 1e7); n %= 1e7;
    const lakh = Math.floor(n / 1e5); n %= 1e5;
    const thousand = Math.floor(n / 1e3); n %= 1e3;
    if (crore) parts.push(inWords(crore) + ' crore');
    if (lakh) parts.push(under100(lakh) + ' lakh');
    if (thousand) parts.push(under100(thousand) + ' thousand');
    if (n) parts.push(under1000(n));
    return parts.join(' ');
  }
  function takaWords(v) {
    const total = Math.round(Math.abs(Number(v || 0)) * 100);
    const taka = Math.floor(total / 100), paisa = total % 100;
    let out = 'Taka ' + inWords(taka);
    if (paisa) out += ' and paisa ' + inWords(paisa);
    return out + ' only';
  }

  window.App = {
    api,
    ApiError,
    cookie,
    takaWords,
    // theme: 'light' | 'dark' | 'system' — browser এ মনে রাখে
    theme: {
      get() { try { return localStorage.getItem('mm-theme') || 'system'; } catch (e) { return 'system'; } },
      set(t) {
        try { if (t === 'light' || t === 'dark') localStorage.setItem('mm-theme', t); else localStorage.removeItem('mm-theme'); } catch (e) { /* private window */ }
        if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t); else document.documentElement.removeAttribute('data-theme');
      },
    },
    // ৳ আর অঙ্কের মাঝে non-breaking space — দুই লাইনে ভাঙে না
    taka: (v) => '৳\u00A0' + fmtMoney.format(Number(v || 0)),
  };
})();

/*
 * combo — search সহ dropdown (সব module এ ব্যবহারের জন্য)।
 * ব্যবহার: {% include "web/_combo.html" with model="f.customer" source="customers" placeholder="All customers" %}
 *   • options: [{ value, label, sub }]  • ↑ ↓ দিয়ে বাছাই, Enter এ নির্বাচন, Esc এ বন্ধ
 */
document.addEventListener('alpine:init', () => {
  Alpine.data('combo', (cfg = {}) => ({
    value: '',
    options: [],
    open: false,
    q: '',
    hi: 0,
    placeholder: cfg.placeholder || 'Select',
    get label() {
      const o = this.options.find(o => String(o.value) === String(this.value));
      return o ? o.label : '';
    },
    get filtered() {
      const q = this.q.trim().toLowerCase();
      const list = q ? this.options.filter(o => (o.label + ' ' + (o.sub || '')).toLowerCase().includes(q)) : this.options;
      return list.slice(0, 200);
    },
    toggle() {
      this.open = !this.open;
      if (this.open) {
        this.q = '';
        this.hi = Math.max(0, this.filtered.findIndex(o => String(o.value) === String(this.value)));
        this.$nextTick(() => this.$refs.q && this.$refs.q.focus());
      }
    },
    close() { this.open = false; },
    pick(o) { this.value = o ? o.value : ''; this.open = false; },
    move(d) {
      const n = this.filtered.length;
      if (!n) return;
      this.hi = (this.hi + d + n) % n;
      this.$nextTick(() => {
        const el = this.$refs.list && this.$refs.list.children[this.hi];
        if (el) el.scrollIntoView({ block: 'nearest' });
      });
    },
    enter() { const o = this.filtered[this.hi]; if (o) this.pick(o); },
  }));
});
