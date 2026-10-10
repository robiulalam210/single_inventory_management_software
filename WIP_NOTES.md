# WIP — Company সরানোর কাজ (ধাপ ৪ শেষ) — এই কপি এখনো চালু হবে না

## শেষ (ধাপ ১ + ২)
- core, products, accounts, customers/models.py (আগের ধাপ)
- সব models.py: sales, money_receipts, transactions(+services), returns, purchases, expenses, income,
  account_transfer, supplier_payment, suppliers, payroll, shop, offline_sync
- offline_sync: models, views, signals, registry, utils, middleware, admin, check_money
- সব serializers.py (account_transfer, customers, expenses, income, money_receipts, purchases,
  returns, sales, supplier_payment, suppliers, transactions)

## বাকি
- views: transactions(99), reports(78), expenses(65), returns, payroll, income, money_receipts, suppliers,
  customers, supplier_payment/view.py, purchases, sales, account_transfer, shop/views+staff_views
- admin: purchases, returns, expenses, sales, supplier_payment, income
- web: views.py, context_processors.py, menu.py, urls.py, templates, JS
- core management commands, tests, settings.py থেকে 'company' অ্যাপ, shop/urls.py, shop/forms.py
- নতুন migrations, seed_products, UI (ছবির আইডিয়া), UPDATE_GUIDE_BN.md


## ধাপ ৩ (এই ZIP)
- ভিউ থেকে company সরানো: transactions, expenses, income, returns, payroll, money_receipts, suppliers, customers, supplier_payment, purchases, sales, account_transfer, reports (স্ক্রিপ্ট + হাতে ঠিক)
- শুধু Python syntax পরীক্ষা, Django চালানো হয়নি — বাকি comment/বার্তায় 'company' শব্দ আছে, কাজে বাধা নেই
- এখনো বাকি: shop/views.py, shop/staff_views.py, shop/urls.py, shop/forms.py, web/views.py, web/context_processors.py, web/menu.py, web/urls.py, admin ফাইল, core commands, tests, settings.py, templates/JS


## ধাপ ৪ (এই ZIP)
- shop (views, urls, forms, staff_views, tests), web (views, context_processors, menu, urls) থেকে Company সরানো; Platform/Companies পেজ মোছা
- admin ফাইল, core commands (setup_erp নতুন, create_staff, check_user), tests, settings.py থেকে 'company' অ্যাপ
- profile.js → /api/business/, audit থেকে company ফিল্টার
- static undefined-name পরীক্ষা পাস (Django এখানে নেই, চালানো হয়নি)
- বাকি: নতুন migrations (tools/reset_migrations.py + makemigrations), seed_products, e-commerce UI
