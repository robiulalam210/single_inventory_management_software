/*
 * Low stock সতর্কতা — একটা Alpine store ($store.lowStock), একবারই data আনে।
 *  • web app খোলার সময় (প্রতিটা browser session এ একবার) popup দেখায়
 *  • dashboard এর উপরের banner ও একই store থেকে চলে, banner এর বোতাম popup খোলে
 * Data: GET /api/reports/low-stock-alert/ — active product যার stock_qty <= alert_quantity
 */
document.addEventListener('alpine:init', () => {
  const SEEN_KEY = 'lowStockPopupSeen';
  const SHOW_ITEMS = 8;

  Alpine.store('lowStock', {
    loaded: false,
    open: false,
    total: 0,
    out: 0,
    low: 0,
    items: [],

    get has() { return this.loaded && this.total > 0; },
    get shown() { return this.items.slice(0, SHOW_ITEMS); },
    get more() { return Math.max(0, this.total - SHOW_ITEMS); },
    get headline() {
      if (this.out > 0 && this.low > 0) return this.out + ' out of stock, ' + this.low + ' running low';
      if (this.out > 0) return this.out + ' product' + (this.out === 1 ? ' is' : 's are') + ' out of stock';
      return this.low + ' product' + (this.low === 1 ? ' is' : 's are') + ' running low';
    },
    // Products পেজের chip (view=low / view=out) এ নিয়ে যায়; দুটোই থাকলে "Running low" এ
    get listUrl() { return '/app/products/?view=' + (this.low > 0 || this.out === 0 ? 'low' : 'out'); },

    async init() {
      try {
        const res = await App.api('/api/reports/low-stock-alert/');
        const d = res.data || {};
        const sum = d.summary || {};
        this.items = d.report || [];
        this.total = Number(sum.total_low_stock_items || 0);
        this.out = Number(sum.critical_items || 0);
        this.low = Number(sum.running_low || 0);
      } catch (e) {
        return; // সতর্কতা আনতে না পারলে চুপচাপ থাকি — কাজ আটকানোর দরকার নেই
      }
      this.loaded = true;
      if (this.total > 0 && !this.seen()) {
        this.open = true;
        this.markSeen();
      }
    },

    seen() { try { return sessionStorage.getItem(SEEN_KEY) === '1'; } catch (e) { return false; } },
    markSeen() { try { sessionStorage.setItem(SEEN_KEY, '1'); } catch (e) { /* private mode */ } },
    close() { this.open = false; },
    show() { this.open = true; },
  });
});
