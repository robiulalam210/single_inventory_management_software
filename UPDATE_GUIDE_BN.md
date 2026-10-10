# নতুন ফিচার — Report Excel/PDF ডাউনলোড + বাকি টাকার রিমাইন্ডার

## ১. Report ডাউনলোড (Excel / PDF)
- Reports পেজে এখন **Download Excel** ও **Download PDF** বোতাম আছে (আগের Print ও CSV থাকছে)।
- যে report: Sales, Purchase, Profit/Loss, Expense, Customer Due, Supplier Due, Stock, Low Stock, Top Products।
- screen এ যে তারিখ/filter বাছা, ফাইলেও ঠিক সেটাই — আর পুরো ফলাফল যায় (শুধু প্রথম পাতা নয়)।
- API: `GET /api/reports/export/<key>/?fmt=xlsx|pdf&start=YYYY-MM-DD&end=YYYY-MM-DD` (`<key>` = sales, purchases, profit-loss, …)।
  `format` নয়, `fmt` — কারণ `format` DRF নিজে ব্যবহার করে।
- নতুন package লাগবে: `pip install -r requirements.txt` (openpyxl, reportlab)।
- **PDF এ বাংলা:** reportlab এর ডিফল্ট ফন্টে বাংলা নেই। একটা `.ttf` (যেমন NotoSansBengali-Regular.ttf) `reports/fonts/` এ রাখলে
  বা `settings.py` এ `REPORT_PDF_FONT = BASE_DIR / 'path/to/font.ttf'` দিলে অক্ষর আসবে; তবে reportlab যুক্তাক্ষর (conjunct) জোড়া লাগাতে পারে না।
  ফন্ট না থাকলে বাংলা অক্ষর `?` হয়। Excel এ পুরো বাংলা ঠিক যায়। বাংলা-ভরা report এর নিখুঁত PDF চাইলে আগের Print → "Save as PDF" ই সেরা।

## ২. Due Reminders (Customers মেনুর নিচে)
- পেজ: `/app/customers/due-reminders/` — যাদের কাছে বাকি, বাকির পরিমাণ, সবচেয়ে পুরনো বাকির বয়স।
- প্রতিটা customer এর পাশে **WhatsApp** ও **SMS** বোতাম: চাপলে বার্তা লেখা অবস্থায় WhatsApp/SMS app খোলে — **পাঠানোর বোতাম দোকানি নিজে চাপেন**।
  (SMS বোতাম মোবাইলে কাজ করে; ডেস্কটপে WhatsApp বা **Copy** ব্যবহার করুন।)
- বার্তার ছাঁচ "Edit message" থেকে বদলানো যায় (`{name} {amount} {invoices} {days} {shop} {phone}`); এই browser এ মনে থাকে।
- "Reminded 3 days ago" চিহ্ন শুধু ওই browser এ থাকে; সার্ভারে কিছু জমা হয় না (migration লাগে না)।
- বাকির হিসাব Customers পেজের সাথে এক: মোট বিক্রি − মোট পাওয়া − advance।
- **স্বয়ংক্রিয় SMS** (নিজে নিজে সবাইকে পাঠানো) করতে SMS gateway (যেমন BulkSMSBD/SSL Wireless) লাগে — পেইড সার্ভিস; gateway বাছলে যোগ করা যাবে।
- API: `GET /api/reports/customer-due-reminders/?q=&min_days=&min_amount=&template=`

## ৩. একটা ভুল ঠিক করা হয়েছে
- **Profit/Loss** এ শেষ তারিখের বিক্রি বাদ পড়ত (যেমন "This month" এ আজকের বিক্রি)। এখন পুরো শেষ দিন ধরা হয়।

## ৪. পরীক্ষা
```bash
pip install -r requirements.txt
python manage.py check
python manage.py test reports
```

---

# একটাই ব্যবসা — Company সরানোর আপডেট (WIP৩)

**অবস্থা:** Python কোড থেকে Company পুরো সরানো হয়েছে (মডেল, সিরিয়ালাইজার, ভিউ, admin, shop, web, commands, tests)।
Django চালিয়ে দেখা হয়নি — আপনার পরিবেশে প্রথম `check` ও `migrate` চালালে কিছু ছোট ভুল ধরা পড়তে পারে, তা জানালে ঠিক করে দেব।

## ফ্রেশ ডাটাবেসে চালু করা (পুরনো ডাটা রাখা হচ্ছে না)

```bash
python tools/reset_migrations.py        # পুরনো migration মোছে
python manage.py makemigrations
python manage.py migrate
python manage.py setup_erp --create-superuser --username admin --password <পাসওয়ার্ড>
python manage.py check
```

## কী কী বদলেছে
- **BusinessProfile** (এক রেকর্ড) এখন দোকানের নাম/লোগো/ঠিকানা রাখে; Company Profile পেজের নাম এখন *Business Profile* (`/api/business/`)।
- **Super Admin → Companies পেজ** ও `Platform` মেনু সরানো হয়েছে।
- **Shop:** `/` ও `/shop/` একই শপ পেজ; অর্ডার ঠিকানা `/shop/order/`। ডোমেইন-ভিত্তিক শপ বাদ। `ShopSettings.load()` একটাই রেকর্ড।
- **সরানো commands:** `clear_all_data`, `fix_admin_user`, `reset_demo_data`, `fix_serial_numbers`, `fix_money_receipt_companies`, `createsuperuser_without_company`।
- **নতুন `setup_erp`:** BusinessProfile, ডিফল্ট role ও ঐচ্ছিক superuser বানায়।
- নম্বর ফরম্যাট: `TXN-100001`, `TRF-100001`, `SR-000001`, `PR-000001`, `MR-000001`।

## এখনো বাকি
- টেমপ্লেট/JS-এ শুধু নামের (`company` ভ্যারিয়েবল) অবশিষ্ট — কাজে বাধা নেই, পরে পরিষ্কার হবে।
- `seed_products`, e-commerce হোম পেজের নতুন ডিজাইন।

---

# আপডেট গাইড — Sale / Money Receipt fix + Desktop Offline Sync + Audit

## ১. কী ঠিক করা হয়েছে (টাকার হিসাব)

আগের code এ একই টাকা account এ কয়েকবার যোগ হত। পরীক্ষায় দেখা গেছে:

| পরিস্থিতি | আগে | এখন |
|---|---|---|
| ৩৬ টাকার বিক্রি, পুরো টাকা নেওয়া | Account +১০৮, ভুয়া advance ৩৬ | Account +৩৬ |
| Walk-in ৫০ দিল, বিল ৩৬ | Account +১৫০ | Account +৩৬, change ১৪ |
| Receipt টিক ছাড়া ১০ টাকা | Account +৩০, ledger entry নেই | Account +১০, ledger entry আছে |
| Invoice এ পরে ৬ টাকা receipt | Account +২২ | Account +৬ |
| Receipt delete | কাজ করত না (404) | Sale, advance, account সব আগের অবস্থায় |

**নতুন নিয়ম — টাকা ঢোকার একটাই পথ:** বিক্রি/পেমেন্ট → Money Receipt → Transaction → Account balance।
প্রতিটা টাকার একটা receipt নম্বর ও ledger entry থাকে, তাই কোনো টাকা দুইবার যোগ হতে পারে না।

যেসব file বদলেছে (backend): `sales/models.py`, `sales/serializers.py`, `sales/views.py`, `sales/signals.py`,
`money_receipts/models.py`, `money_receipts/serializers.py`, `money_receipts/views.py`,
`transactions/models.py`, `core/urls.py`, `returns/models.py`, `account_transfer/models.py`, `inventory_api/settings.py`।

App (mobile + desktop): ৫টা POS screen + নতুন `sale_payment_rules.dart`, ২টা money receipt screen,
`post_response.dart` (200 status কে আগে error ধরা হত)।

## ২. Server এ deploy (ক্রম মেনে)

```bash
# ১. আগে database backup নিন
# ২. code আপলোড করুন, তারপর:
pip install django-cors-headers mysqlclient
python manage.py migrate
python manage.py check_money                 # শুধু রিপোর্ট, কিছু বদলায় না
python manage.py check_money --fix-accounts  # রিপোর্ট দেখে নিশ্চিত হলে
touch tmp/restart.txt                        # cPanel app restart
```

`check_money` কী দেখায়: account এর stored balance বনাম ledger (transaction) অনুযায়ী balance,
sale এর due ঠিক আছে কিনা, কোন receipt account এ জমা হয়নি। **Customer advance স্বয়ংক্রিয়ভাবে বদলানো হয় না** —
পুরনো bug এ ভুয়া advance তৈরি হয়েছিল, কোনটা আসল সেটা আপনি customer list দেখে ঠিক করবেন।

## ৩. App এ নতুন আচরণ

- "With Money Receipt" টিক না থাকলে বিক্রি পুরো বাকিতে যায় (paid = 0)।
- টিক থাকলে payment method ও account বাধ্যতামূলক।
- Walk-in customer এর কাছে বাকি রাখা যায় না।
- ১.৫ kg এর মতো দশমিক পরিমাণ এখন ঠিক যায়।
- Money receipt এর টাকা/invoice/account edit করা যায় না — বদলাতে হলে delete করে নতুন receipt।
  (Delete করলে সব হিসাব নিজে থেকে উল্টে যায়।)

## ৪. Desktop Offline (Windows/macOS/Linux)

Mobile আগের মতোই সম্পূর্ণ online। Desktop:

- **প্রথমবার login:** "এই কম্পিউটার প্রস্তুত করা হচ্ছে" screen — progress bar সহ সব data নামে। একবারই।
- **এরপর:** সব কিছু নিজে থেকে — internet এলে, প্রতি ২ মিনিটে, নতুন entry হলে। কোনো popup নেই,
  শুধু উপরের ছোট chip: সবুজ (Synced) / নীল (sync হচ্ছে) / হলুদ (Offline · ৫ অপেক্ষায়) / লাল (সমস্যা)।
- **Chip এ click = Sync Center:** "এখনই Sync করুন" বাটন, অপেক্ষমাণ entry, সমস্যা, স্টক সতর্কতা।
- **Offline এ যা করা যায়:** বিক্রি, money receipt, ক্রয়, supplier payment, খরচ, আয়, নতুন customer।
  Edit/delete ও report শুধু online এ (report offline এ শেষ দেখা অবস্থায় দেখায়)।
- **স্টক:** offline এ server এর শেষ stock থেকে offline বিক্রি বাদ দিয়ে হিসাব। স্টক না থাকলে বিক্রি আটকায়,
  আর হলুদ banner এ "X টি পণ্যের স্টক শেষ" দেখায়।
- **অন্য PC/মোবাইল একই সময়ে শেষ পিস বিক্রি করলে:** server sale টা নেয় না (stock ঋণাত্মক হয় না),
  Sync Center এ "সমস্যা" হিসেবে দেখায় — ক্রয় এন্ট্রি দিয়ে "আবার পাঠান" অথবা "বাতিল"।
- **Invoice নম্বর:** offline এ `SL-D1-00012` (D1 = এই কম্পিউটার)। Server এও এই নম্বরই থাকে।
- **Offline login:** আগে এই কম্পিউটারে online login করা থাকলে internet ছাড়াও login হয়।
- **Logout:** sync না হওয়া entry থাকলে সতর্ক করে; entry গুলো মুছে যায় না।

### Duplicate কেন হবে না
প্রতিটা write এর একটা অনন্য id (`X-Idempotency-Key`)। একই id দ্বিতীয়বার এলে server নতুন কিছু save করে না,
আগের ফলাফল ফেরত দেয়। Mobile এ double-tap এও এটা কাজ করে। একই phone নম্বরের customer offline এ আবার
বানালে নতুন না বানিয়ে আগেরটার সাথে মিলিয়ে দেয়।

## ৫. Audit log
সব গুরুত্বপূর্ণ data র প্রতিটা create/update/delete রেকর্ড হয় — কে, কখন, কোন app (mobile/desktop/
desktop_offline/admin), কোন কম্পিউটার (D1/D2), field-wise আগের → নতুন মান, আর offline কাজের আসল সময়।

- API: `GET /api/sync/audit/?model=sale&object_id=15` (filter: user_id, action, source, device, date_from, date_to, q)
- Admin panel: Offline Sync & Audit → Change logs (কেউ edit/delete করতে পারে না)
- দেখার অনুমতি: Super Admin, Admin, Manager

## ৬. Flutter build
```bash
flutter pub get        # নতুন: sqflite_common_ffi, sqlite3_flutter_libs, path
flutter build windows
```
`.env` আর `key/meherin.jks` এই zip এ রাখা হয়নি (নিরাপত্তার জন্য) — আপনার কাছে থাকা কপি project এ রাখুন।

## ৭. পরীক্ষা (backend)
```bash
python tools/tests/test_money.py   # ১৬টা টাকার হিসাবের পরীক্ষা
python tools/tests/test_sync.py    # offline sync, duplicate, stock conflict, audit
```
এগুলো আসল database এ data যোগ করে — শুধু test/copy database এ চালাবেন।

## ৮. জানা সীমাবদ্ধতা
- Flutter অংশ এই পরিবেশে compile করা যায়নি (Flutter SDK নেই) — `flutter analyze` চালিয়ে কোনো error থাকলে জানাবেন।
- Offline এ account balance / customer due তাৎক্ষণিক বদলায় না, sync এর পরে ঠিক হয়।
- পুরনো (allocation ছাড়া) "overall" receipt delete করা যায় না — কোন invoice এ কত বসেছিল তার রেকর্ড নেই।

## ৯. Low stock সতর্কতা (Dashboard + অ্যাপ খোলার সময়)
- যে product **active** এবং `stock_qty <= alert_quantity` (প্রতিটা product এর নিজের alert সংখ্যা) — সেগুলোই সতর্কতায় আসে। নতুন field বা migration লাগে না।
- **অ্যাপ খোলার সময়:** web app এর প্রথম পাতা খুললেই (প্রতিটা browser session এ একবার) একটা popup এ কোন product শেষ/কম দেখায়। "Dismiss" চাপলে বন্ধ হয়; browser বন্ধ করে আবার খুললে আবার আসে।
- **Dashboard:** একদম উপরে সবসময় একটা banner (শেষ product থাকলে লাল, নাহলে হলুদ) + "View list" বোতাম। "Restock soon" তালিকাও এখন একই নিয়মে চলে।
- Dashboard এর "Stock alerts" সংখ্যা এখন শুধু active product ধরে (আগে বন্ধ করা product ও গুনত) — Products পেজের সাথে মিলে গেল।
- যারা Dashboard / Products / Purchases / Reports এর কোনোটা দেখতে পায় না, তাদের কিছু দেখায় না।
- API (Flutter app ও ব্যবহার করতে পারে): `GET /api/reports/low-stock-alert/` → `data.report[]` (সবচেয়ে কম stock আগে, সর্বোচ্চ ৫০টা) + `data.summary` (`total_low_stock_items`, `critical_items`, `running_low`)।
- পরীক্ষা: `python manage.py test reports.test_low_stock_alert`
