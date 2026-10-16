from decimal import ROUND_CEILING, Decimal

from django.db import models, transaction


class ShopOrder(models.Model):
    """কাস্টমারের অনলাইন অর্ডার।

    স্টক: অর্ডার দেওয়ার সময়ই reserve (stock_deducted=True); cancel করলে ফেরত।
    হিসাব: "Delivered" চাপলে reserve ছেড়ে দিয়ে একটা Sale (invoice) তৈরি হয় — সেই Sale এর SaleItem ই স্টক কমায়,
    তাই স্টক একবারই কমে। নগদ টাকা পেলে (Cash received) Sale.receive_payment() → MoneyReceipt → Transaction → Account।
    """
    PENDING, CONFIRMED, DELIVERED, CANCELLED = 'pending', 'confirmed', 'delivered', 'cancelled'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (CONFIRMED, 'Confirmed'),
        (DELIVERED, 'Delivered'),
        (CANCELLED, 'Cancelled'),
    ]

    order_no = models.CharField(max_length=20, blank=True)
    customer_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    note = models.TextField(blank=True, default='')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    delivery_charge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))  # আইটেম + delivery
    stock_deducted = models.BooleanField(default=False)
    sale = models.OneToOneField('sales.Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='shop_order')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status'])]

    def __str__(self):
        return f"{self.order_no or self.pk} — {self.customer_name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.order_no:
            self.order_no = f"WEB-{self.pk:05d}"
            super().save(update_fields=['order_no'])

    # ── stock ──
    def _locked_products(self):
        from products.models import Product
        ids = [i.product_id for i in self.items.all() if i.product_id]
        return {p.id: p for p in Product.objects.select_for_update().filter(id__in=ids)}

    def deduct_stock(self):
        """Confirm এর সময় — যথেষ্ট stock না থাকলে ValueError"""
        if self.stock_deducted:
            return
        items = list(self.items.all())
        products = self._locked_products()
        need = {}                                  # product_id → বেস ইউনিটে মোট দরকার (গ্রাম/পিস)
        for it in items:
            if products.get(it.product_id) is None:
                raise ValueError(f"'{it.product_name}' is no longer in the inventory.")
            need[it.product_id] = need.get(it.product_id, 0) + it.stock_need
        for it in items:
            p = products[it.product_id]
            if p.stock_qty < need[it.product_id]:
                raise ValueError(f"Not enough stock for '{it.product_name}' (in stock: {p.stock_qty}, ordered: {need[it.product_id]}).")
        for pid, qty in need.items():
            p = products[pid]
            p.stock_qty -= qty
            p.save(update_fields=['stock_qty'])
        self.stock_deducted = True

    def restore_stock(self):
        """Confirm হওয়ার পর বাতিল হলে stock ফেরত"""
        if not self.stock_deducted:
            return
        products = self._locked_products()
        for it in self.items.all():
            p = products.get(it.product_id)
            if p is not None:
                p.stock_qty += it.stock_need
                p.save(update_fields=['stock_qty'])
        self.stock_deducted = False

    def _create_sale(self, user):
        """Delivered এ: reserve ছেড়ে Sale + SaleItem তৈরি (SaleItem নিজেই স্টক কমায়)।"""
        from customers.models import Customer
        from products.models import Product
        from sales.models import Sale, SaleItem

        items = list(self.items.all())
        if any(not it.product_id for it in items):
            raise ValueError('A product in this order was removed from the inventory, so it can\'t be invoiced.')

        self.restore_stock()                      # reserve ফেরত → নিচের SaleItem আবার কমাবে
        products = {p.id: p for p in Product.objects.select_for_update().filter(id__in=[i.product_id for i in items])}

        customer = Customer.objects.filter(phone=self.phone).first()
        if customer is None:
            customer = Customer.objects.create(name=self.customer_name, phone=self.phone,
                                               address=self.address, created_by=user)
        remark = f"Online order {self.order_no} · {self.phone} · {self.address}"
        if self.note:
            remark += f" · Note: {self.note}"

        sale = Sale(created_by=user, sale_by=user, sale_type='retail',
                    customer=customer, customer_name=self.customer_name,
                    customer_type='saved_customer' if customer else 'walk_in',
                    with_money_receipt='No', remark=remark[:1000],
                    overall_delivery_charge=self.delivery_charge,
                    overall_delivery_type='fixed' if self.delivery_charge else None)
        sale.save()
        for it in items:
            # কাস্টমারকে অর্ডারের সময় যে দাম (line_total) বলা হয়েছে ইনভয়েসেও ঠিক সেটাই যাবে —
            # পরে সেল মোডের দাম বদলে গেলেও। SaleItem দাম নতুন করে হিসাব করে না যদি unit_price দেওয়া থাকে।
            kw = {}
            unit_price = it.unit_price
            if it.sale_mode_id:
                is_flat = it.sale_mode.price_type == 'flat'
                mult = Decimal(it.qty) if is_flat else Decimal(it.base_qty or it.qty)
                per = (it.line_total / mult).quantize(Decimal('0.01'), rounding=ROUND_CEILING)
                diff = per * mult - it.line_total           # রাউন্ডিং এর ছোট পার্থক্য ছাড় হিসেবে মিলিয়ে দেওয়া হয়
                unit_price = per
                if is_flat:
                    kw['flat_price'] = per
                if diff > 0:
                    kw.update(discount_type='fixed', discount=diff)
            SaleItem(sale=sale, product=products[it.product_id], sale_mode=it.sale_mode,
                     quantity=Decimal(it.qty), unit_price=unit_price, **kw).save()
        sale.refresh_from_db()
        return sale

    @transaction.atomic
    def change_status(self, new_status, user=None, cash_received=False):
        order = ShopOrder.objects.select_for_update().get(pk=self.pk)
        allowed = {
            self.PENDING: {self.CONFIRMED, self.CANCELLED},
            self.CONFIRMED: {self.DELIVERED, self.CANCELLED},
        }
        if new_status not in allowed.get(order.status, set()):
            raise ValueError(f"Can't change an order from {order.status} to {new_status}.")
        if new_status == self.CANCELLED:
            order.restore_stock()
        elif new_status == self.DELIVERED:
            order.sale = order._create_sale(user)
            if cash_received:
                order.sale.receive_payment(order.sale.grand_total, payment_method='Cash', received_by=user)
        order.status = new_status
        order.save()
        return order


class ShopOrderItem(models.Model):
    order = models.ForeignKey(ShopOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    product_name = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    qty = models.PositiveIntegerField(help_text='সেল মোডের এককে পরিমাণ (প্যাক সংখ্যা / গ্রাম / কেজি)')
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    sale_mode = models.ForeignKey('products.SaleMode', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    mode_name = models.CharField(max_length=60, blank=True, default='')
    base_qty = models.PositiveIntegerField(default=0, help_text='বেস ইউনিটে (যেমন গ্রাম) স্টক থেকে যত কমবে; 0 = qty')

    @property
    def stock_need(self):
        return self.base_qty or self.qty

    def __str__(self):
        return f"{self.product_name}{' · ' + self.mode_name if self.mode_name else ''} × {self.qty}"


class ShopSettings(models.Model):
    """শপ পেজের তথ্য ও চেহারা — inventory এর Shop Settings পেজ থেকে অ্যাডমিন বদলাবে।"""
    # সাধারণ
    is_open = models.BooleanField('Accept orders', default=True)
    shop_name = models.CharField(max_length=80, blank=True, help_text='Leave empty to use the business name.')
    tagline = models.CharField(max_length=140, blank=True)
    brand_color = models.CharField(max_length=7, default='#0f766e', help_text='Hex colour, e.g. #0f766e')
    THEME_CHOICES = [('auto', 'Follow the visitor\'s device'), ('light', 'Always light'), ('dark', 'Always dark')]
    default_theme = models.CharField(max_length=5, choices=THEME_CHOICES, default='auto',
                                     help_text='Visitors can still switch with the sun/moon button.')
    announcement = models.CharField('Top announcement', max_length=200, blank=True)

    # Hero ব্যানার
    hero_title = models.CharField(max_length=120, blank=True)
    hero_subtitle = models.CharField(max_length=240, blank=True)
    hero_button_text = models.CharField(max_length=30, default='Shop now')
    hero_image = models.ImageField(upload_to='shop-banners/', blank=True, null=True)

    # আমাদের সম্পর্কে
    about_title = models.CharField(max_length=80, blank=True)
    about_text = models.TextField(blank=True)

    # যোগাযোগ
    phone = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField('WhatsApp number', max_length=30, blank=True, help_text='With country code, digits only.')
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=240, blank=True)
    opening_hours = models.CharField(max_length=120, blank=True)
    facebook_url = models.URLField(blank=True)

    # ডেলিভারি ও পেমেন্ট
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    free_delivery_min = models.DecimalField('Free delivery above', max_digits=10, decimal_places=2, default=Decimal('0.00'),
                                            help_text='0 = no free delivery.')
    delivery_note = models.CharField(max_length=140, default='Delivery within 1–3 days', blank=True)
    payment_note = models.CharField(max_length=140, default='Cash on delivery', blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Shop settings'

    def __str__(self):
        return "Shop settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # সবসময় একটাই রেকর্ড
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def public_url(self, request):
        """শপের লিংক"""
        from django.urls import reverse
        return request.build_absolute_uri(reverse('shop:store'))

    def delivery_for(self, subtotal):
        if self.free_delivery_min and subtotal >= self.free_delivery_min:
            return Decimal('0.00')
        return self.delivery_charge
