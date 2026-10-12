"""
Day close — দিন শেষে হিসাব বন্ধ।

একটা তারিখে একটাই DayClose। বন্ধ করার সময় ওই দিনের সারাংশ (summary) আর প্রতিটা account এর
"সিস্টেম অনুযায়ী থাকার কথা" বনাম "হাতে গুনে পাওয়া" (lines) সংরক্ষণ হয়, যাতে পরে বদলালেও
সেদিনের রিপোর্ট একই থাকে। এটা শুধু রেকর্ড — লেনদেন তালা দেয় না।
"""
from decimal import Decimal

from django.conf import settings
from django.db import models


class DayClose(models.Model):
    date = models.DateField(unique=True)
    summary = models.JSONField(default=dict, blank=True)
    lines = models.JSONField(default=list, blank=True)
    total_expected = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_counted = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    difference = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    note = models.TextField(blank=True, default='')
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+')
    closed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Day close {self.date}"
