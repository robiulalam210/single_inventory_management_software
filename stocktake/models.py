"""
Stock adjustment (এক পণ্যের স্টক হাতে ঠিক করা) আর Stocktake (সব/কিছু পণ্য গুনে সিস্টেমের সাথে মেলানো)।

• প্রতিটা পরিবর্তন StockAdjustment এ লেখা থাকে — আগে কত ছিল, এখন কত, কেন, কে করেছে, টাকার হিসেবে কত লাভ/ক্ষতি।
• Stocktake: গণনা শুরুর মুহূর্তে প্রতিটা পণ্যের system স্টক "snapshot" হয়ে যায়। গুনে সংখ্যা লিখলে পার্থক্য
  (গণনা − snapshot) বের হয়। Apply করলে সেই পার্থক্য *এখনকার* স্টকে যোগ/বিয়োগ হয় — তাই গণনার মাঝে বিক্রি হলেও
  হিসাব ঠিক থাকে।
"""
from decimal import Decimal

from django.conf import settings
from django.db import models


class Stocktake(models.Model):
    DRAFT, APPLIED, CANCELLED = 'draft', 'applied', 'cancelled'
    STATUS_CHOICES = [(DRAFT, 'Counting'), (APPLIED, 'Applied'), (CANCELLED, 'Cancelled')]

    number = models.CharField(max_length=20, blank=True, default='', db_index=True)
    title = models.CharField(max_length=150, blank=True, default='')
    note = models.TextField(blank=True, default='')
    category = models.ForeignKey('products.Category', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='+')
    category_name = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    applied_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.number} {self.title}".strip()


class StocktakeLine(models.Model):
    stocktake = models.ForeignKey(Stocktake, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='+')
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, blank=True, default='')
    category_name = models.CharField(max_length=120, blank=True, default='')
    system_qty = models.PositiveIntegerField()                 # গণনা শুরুর সময়ের স্টক
    counted_qty = models.PositiveIntegerField(null=True, blank=True)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    counted_at = models.DateTimeField(null=True, blank=True)
    applied_change = models.IntegerField(null=True, blank=True)  # Apply এ স্টকে আসলে কতটা বদলেছে

    class Meta:
        ordering = ['category_name', 'product_name', 'id']
        constraints = [models.UniqueConstraint(fields=['stocktake', 'product'], name='uniq_stocktake_product')]

    @property
    def variance(self):
        return None if self.counted_qty is None else self.counted_qty - self.system_qty


class StockAdjustment(models.Model):
    REASONS = [
        ('count', 'Stock count'),
        ('damaged', 'Damaged'),
        ('expired', 'Expired'),
        ('lost', 'Lost / stolen'),
        ('found', 'Found / extra'),
        ('correction', 'Entry mistake'),
        ('opening', 'Opening stock'),
        ('other', 'Other'),
    ]

    number = models.CharField(max_length=20, blank=True, default='', db_index=True)
    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='stock_adjustments')
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, blank=True, default='')
    qty_before = models.PositiveIntegerField()
    qty_after = models.PositiveIntegerField()
    change = models.IntegerField()                              # সংকেতসহ: +৫ বাড়ল, −৩ কমল
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    value_change = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    reason = models.CharField(max_length=12, choices=REASONS, default='other')
    note = models.CharField(max_length=300, blank=True, default='')
    stocktake = models.ForeignKey(Stocktake, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='adjustments')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-id']
        indexes = [models.Index(fields=['product', 'created_at'])]

    def __str__(self):
        return f"{self.number} {self.product_name} {self.change:+d}"
