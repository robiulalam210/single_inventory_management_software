"""
Payroll — মাসিক বেতন স্লিপ + অগ্রিম (advance)।

টাকার হিসাব নতুন করে লিখিনি: বেতন/অগ্রিম দেওয়া মানে একটা Expense (head "Salary" / "Salary Advance") — ফলে
account এর balance, Transaction, Expense report, Profit/Loss সব আগের নিয়মেই মেলে।
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import Account
from core.models import Staff
from expenses.models import Expense

ZERO = Decimal('0.00')


class SalaryAdvance(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='salary_advances')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    deducted = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)  # এ পর্যন্ত বেতন থেকে কাটা
    date = models.DateField(default=timezone.now)
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    payment_method = models.CharField(max_length=30, default='cash')
    expense = models.ForeignKey(Expense, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    note = models.CharField(max_length=255, blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        indexes = [models.Index(fields=['staff'])]

    @property
    def remaining(self):
        return (self.amount or ZERO) - (self.deducted or ZERO)


class SalarySlip(models.Model):
    UNPAID, PAID = 'unpaid', 'paid'
    STATUS_CHOICES = [(UNPAID, 'Unpaid'), (PAID, 'Paid')]

    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='salary_slips')
    month = models.DateField()  # মাসের ১ তারিখ
    basic = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    commission = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    other_addition = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    advance_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    other_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    net = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=UNPAID)
    paid_date = models.DateField(null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    payment_method = models.CharField(max_length=30, blank=True, default='')
    expense = models.ForeignKey(Expense, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    advance_applied = models.JSONField(default=list, blank=True)  # [{"id":.., "amount":..}] — বাতিল করলে ফেরত দিতে
    note = models.CharField(max_length=255, blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-month', 'staff_id']
        constraints = [models.UniqueConstraint(fields=['staff', 'month'], name='uniq_slip_staff_month')]
        indexes = [models.Index(fields=['month', 'status'])]

    def recalc(self):
        self.net = (self.basic + self.commission + self.bonus + self.other_addition
                    - self.advance_deduction - self.other_deduction)
        return self.net
