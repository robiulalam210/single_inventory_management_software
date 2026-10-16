"""
কোন data desktop এ offline রাখা হবে, কোন model audit হবে, কোন API offline এ চালানো যাবে —
সব এক জায়গায়। নতুন module যোগ করলে শুধু এই file এ এক লাইন যোগ করলেই হবে।
"""

# ---------------------------------------------------------------------------
# 1) Desktop এ offline রাখা master/lookup data
#    path      = যে list API থেকে app এই data দেখে (একই serializer → একই JSON shape)
#    serializer= APIView হলে (serializer_class নেই) সরাসরি serializer এর path
# ---------------------------------------------------------------------------
SYNC_ENTITIES = {
    "category":          {"model": "products.Category",        "path": "/api/categories/"},
    "unit":              {"model": "products.Unit",            "path": "/api/units/"},
    "brand":             {"model": "products.Brand",           "path": "/api/brands/"},
    "group":             {"model": "products.Group",           "path": "/api/groups/"},
    "source":            {"model": "products.Source",          "path": "/api/sources/"},
    "sale_mode":         {"model": "products.SaleMode",        "path": "/api/sale-modes/"},
    "price_tier":        {"model": "products.PriceTier",       "path": "/api/price-tiers/"},
    "product":           {"model": "products.Product",         "path": "/api/products/"},
    "product_sale_mode": {"model": "products.ProductSaleMode", "path": "/api/product-sale-modes/"},
    "customer":          {"model": "customers.Customer",       "path": "/api/customers/"},
    "supplier":          {"model": "suppliers.Supplier",       "path": "/api/suppliers/"},
    "account":           {"model": "accounts.Account",         "path": "/api/accounts/"},
    "user":              {"model": "core.User",                "path": "/api/users/",
                          "serializer": "core.serializers.UserListSerializer"},
    "expense_head":      {"model": "expenses.ExpenseHead",     "path": "/api/expenses/expense-heads/",
                          "serializer": "expenses.serializers.ExpenseHeadSerializer"},
    "expense_subhead":   {"model": "expenses.ExpenseSubHead",  "path": "/api/expenses/expense-subheads/",
                          "serializer": "expenses.serializers.ExpenseSubHeadSerializer"},
    "income_head":       {"model": "income.IncomeHead",        "path": "/api/income/income-heads/",
                          "serializer": "income.serializers.IncomeHeadSerializer"},
}

# প্রথম setup এ এই ক্রমে download হবে (lookup আগে, product পরে)
SYNC_ORDER = [
    "category", "unit", "brand", "group", "source", "sale_mode", "product",
    "product_sale_mode", "price_tier", "customer", "supplier", "account", "user",
    "expense_head", "expense_subhead", "income_head",
]

# ---------------------------------------------------------------------------
# 2) Audit — এই model গুলোর প্রতিটা create/update/delete ChangeLog এ লেখা হবে
#    (mobile, desktop, admin panel — যেখান থেকেই হোক)
# ---------------------------------------------------------------------------
AUDITED_MODELS = sorted({cfg["model"] for cfg in SYNC_ENTITIES.values()} | {
    "sales.Sale", "sales.SaleItem",
    "purchases.Purchase", "purchases.PurchaseItem",
    "returns.SalesReturn", "returns.SalesReturnItem",
    "returns.PurchaseReturn", "returns.PurchaseReturnItem", "returns.BadStock",
    "money_receipts.MoneyReceipt", "supplier_payment.SupplierPayment",
    "expenses.Expense", "income.Income",
    "transactions.Transaction", "account_transfer.AccountTransfer",
    "core.BusinessProfile", "core.UserPermission", "core.StaffRole", "core.Staff",
})

# Audit এ যেসব field লেখার দরকার নেই বা লেখা উচিত নয়
AUDIT_IGNORED_FIELDS = {"password", "last_login", "updated_at", "date_updated", "modified_at"}

# (Multi-company নেই) — এখন শুধু পুরনো import মিলিয়ে রাখা হয়েছে
COMPANY_PATHS = {
    "sales.SaleItem": "sale",
    "purchases.PurchaseItem": "purchase",
    "returns.SalesReturnItem": "sales_return",
    "returns.PurchaseReturnItem": "purchase_return",
    "products.ProductSaleMode": "product",
    "products.PriceTier": "product_sale_mode.product",
    "core.UserPermission": "user",
}

# ---------------------------------------------------------------------------
# 3) Offline এ যেসব কাজ করা যাবে (শুধু নতুন entry — edit/delete online এ)
#    entity = id mapping এর নাম; temporary id দিয়ে পরের কাজ এটাকে refer করতে পারে
# ---------------------------------------------------------------------------
OFFLINE_WRITE_ENDPOINTS = {
    "/api/customers/":                {"entity": "customer"},
    "/api/sales/":                    {"entity": "sale"},
    "/api/money-receipts/":           {"entity": "money_receipt"},
    "/api/purchases/":                {"entity": "purchase"},
    "/api/supplier-payments/":        {"entity": "supplier_payment"},
    "/api/expenses/expenses/":        {"entity": "expense"},
    "/api/income/incomes/":           {"entity": "income"},
}

# Payload এর ভিতরে যেসব key অন্য record এর id ধরে — negative (local) id হলে
# server এর আসল id দিয়ে বদলে দেওয়া হবে
REMAP_KEYS = {
    "customer": "customer", "customer_id": "customer",
    "supplier": "supplier", "supplier_id": "supplier",
    "sale": "sale", "sale_id": "sale",
    "purchase": "purchase", "purchase_id": "purchase",
}
