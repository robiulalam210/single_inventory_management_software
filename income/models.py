from django.db import models, transaction as db_transaction
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from accounts.models import Account

class IncomeHead(models.Model):
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date_created = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
        
    def __str__(self):
        return self.name

class Income(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('mobile', 'Mobile Banking'),
        ('card', 'Card'),
        ('other', 'Other'),
    ]

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date_created = models.DateTimeField(default=timezone.now)
    payment_method = models.CharField(max_length=100, choices=PAYMENT_METHOD_CHOICES, default='cash')
    head = models.ForeignKey(IncomeHead, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, blank=True, null=True, related_name='incomes')
    income_date = models.DateField(default=timezone.now)
    note = models.TextField(blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['-income_date', '-date_created']

    def __str__(self):
        description = self.note[:50] + '...' if self.note and len(self.note) > 50 else self.note or ''
        return f"{self.invoice_number} - {description} - {self.amount}"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Income amount must be greater than 0")

    def save(self, *args, **kwargs):
        """
        নতুন আয় → account এ একবার credit।
        আগে credit Transaction (যেটা নিজেই balance বাড়ায়) + হাতে balance += দুটোই হতো — প্রতিটা আয় দ্বিগুণ উঠত।
        Edit এ টাকা বা account বদলালে আগেরটা উল্টে নতুনটা বসাই (আগে কিছুই হতো না, balance ভুল থেকে যেত)।
        """
        is_new = self.pk is None
        old = None if is_new else Income.objects.filter(pk=self.pk).values('account_id', 'amount').first()
        if is_new and not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        self.clean()
        with db_transaction.atomic():
            super().save(*args, **kwargs)
            if is_new:
                self.create_income_transaction(is_new=True)
            elif old and (old['account_id'] != self.account_id or old['amount'] != self.amount):
                self._reverse_transaction('Edited')
                self.create_income_transaction(is_new=True)

    def active_transaction(self):
        return self.transactions.filter(transaction_type='credit', status='completed').order_by('-id').first()

    def _reverse_transaction(self, why):
        """আগের credit টা বাতিল করে সমান debit — টাকা খরচ হয়ে গিয়ে থাকলে (balance কম) এখানেই আটকায়"""
        from transactions.models import Transaction
        original = self.active_transaction()
        if not original:
            return
        Transaction.objects.create(
            transaction_type='debit',
            amount=original.amount,
            account=original.account,
            payment_method=self.payment_method,
            description=f"Reversal - {why} income: {self.invoice_number}",
            reference_no=self.invoice_number,
            status='completed',
            transaction_date=timezone.localdate(),
            created_by=self.created_by,
        )
        original.status = 'cancelled'
        original.save(update_fields=['status'])

    def delete(self, *args, **kwargs):
        with db_transaction.atomic():
            self._reverse_transaction('Deleted')
            super().delete(*args, **kwargs)

    def generate_invoice_number(self):
        from django.db.models import Max
        from django.db.models.functions import Cast, Substr
        max_income = Income.objects.filter(
            invoice_number__regex=r'^INC-\d+$'
        ).aggregate(
            max_number=Max(
                Cast(
                    Substr('invoice_number', 5),
                    output_field=models.IntegerField()
                )
            )
        )
        next_number = (max_income['max_number'] or 1000) + 1
        invoice_number = f"INC-{next_number}"
        counter = 0
        while Income.objects.filter(invoice_number=invoice_number).exists():
            counter += 1
            invoice_number = f"INC-{next_number + counter}"
        return invoice_number

    def create_income_transaction(self, is_new=True):
        if not self.account:
            return
        from transactions.models import Transaction
        if is_new:
                Transaction.objects.create(
                    transaction_type='credit',
                    amount=self.amount,
                    account=self.account,
                    description=f"Income: {self.head.name if self.head else ''} - {self.note or ''}",
                    reference_no=self.invoice_number,
                    income=self,
                    payment_method=self.payment_method,  # INCLUDE payment method!
                    status='completed',
                    transaction_date=self.income_date,
                    created_by=self.created_by
                )
                # Transaction.save() নিজেই balance বাড়ায় — এখানে আবার বাড়ালে দ্বিগুণ হয়