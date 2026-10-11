from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager
from django.utils.translation import gettext_lazy as _
from datetime import date, timedelta
from decimal import Decimal
import uuid
import random
import string


class BusinessProfile(models.Model):
    """
    এই সফটওয়্যারে শুধু একটাই ব্যবসা থাকে (Multi-company নেই)।
    ক্লায়েন্ট এখানে যে নাম/তথ্য দেবে সেটাই লগইন পেজ, ড্যাশবোর্ড, ইনভয়েস ও
    অনলাইন শপে দেখানো হবে। সবসময় মাত্র একটি রেকর্ড (pk=1) থাকে।
    """
    name = models.CharField(max_length=150, default='My Business')
    tagline = models.CharField(max_length=200, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    whatsapp = models.CharField(max_length=20, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    address = models.TextField(blank=True, default='')
    website = models.URLField(blank=True, default='')
    trade_license = models.CharField(max_length=100, blank=True, default='')
    logo = models.ImageField(upload_to='business/logo/', blank=True, null=True)
    currency = models.CharField(max_length=10, default='BDT')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Business Profile')
        verbose_name_plural = _('Business Profile')

    def save(self, *args, **kwargs):
        self.pk = 1  # সবসময় একটাই রেকর্ড
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # একমাত্র ব্যবসার প্রোফাইল মোছা যাবে না

    @classmethod
    def get(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def code(self):
        """নাম থেকে ৩ অক্ষরের প্রিফিক্স (অ্যাকাউন্ট/ইনভয়েস নম্বরের জন্য)।"""
        letters = ''.join(ch for ch in (self.name or '') if ch.isascii() and ch.isalpha())
        return (letters[:3] or 'BIZ').upper()

    def __str__(self):
        return self.name


class AppUserManager(UserManager):
    """`manage.py createsuperuser` এ role না দিলে ডিফল্ট STAFF হয়ে যেত এবং
    User.save() তাকে superuser থেকে নামিয়ে দিত। তাই এখানে role = SUPER_ADMIN বসানো হয়।"""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', 'SUPER_ADMIN')
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    objects = AppUserManager()

    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", _("Super Admin")
        ADMIN = "ADMIN", _("Admin")
        MANAGER = "MANAGER", _("Manager")
        STAFF = "STAFF", _("Staff")
        VIEWER = "VIEWER", _("Viewer")

    role = models.CharField(
        max_length=20, 
        choices=Role.choices, 
        default=Role.STAFF
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    profile_picture = models.ImageField(
        upload_to='users/profile_pictures/', 
        blank=True, 
        null=True
    )
    date_of_birth = models.DateField(blank=True, null=True)
    
    # ===== DASHBOARD PERMISSIONS =====
    can_access_dashboard = models.BooleanField(default=False)
    
    # ===== SALES MODULE PERMISSIONS =====
    sales_view = models.BooleanField(default=False)
    sales_create = models.BooleanField(default=False)
    pos_sales_create = models.BooleanField(default=False)
    short_sales_create = models.BooleanField(default=False)
    sales_edit = models.BooleanField(default=False)
    sales_delete = models.BooleanField(default=False)
    
    # ===== MONEY RECEIPT PERMISSIONS =====
    money_receipt_view = models.BooleanField(default=False)
    money_receipt_create = models.BooleanField(default=False)
    money_receipt_edit = models.BooleanField(default=False)
    money_receipt_delete = models.BooleanField(default=False)
    
    # ===== PURCHASES MODULE PERMISSIONS =====
    purchases_view = models.BooleanField(default=False)
    purchases_create = models.BooleanField(default=False)
    purchases_edit = models.BooleanField(default=False)
    purchases_delete = models.BooleanField(default=False)
    
    # ===== PRODUCTS MODULE PERMISSIONS =====
    products_view = models.BooleanField(default=False)
    products_create = models.BooleanField(default=False)
    products_edit = models.BooleanField(default=False)
    products_delete = models.BooleanField(default=False)
    
    # ===== ACCOUNTS MODULE PERMISSIONS =====
    accounts_view = models.BooleanField(default=False)
    accounts_create = models.BooleanField(default=False)
    accounts_edit = models.BooleanField(default=False)
    accounts_delete = models.BooleanField(default=False)
    
    # ===== CUSTOMERS MODULE PERMISSIONS =====
    customers_view = models.BooleanField(default=False)
    customers_create = models.BooleanField(default=False)
    customers_edit = models.BooleanField(default=False)
    customers_delete = models.BooleanField(default=False)
    
    # ===== SUPPLIERS MODULE PERMISSIONS =====
    suppliers_view = models.BooleanField(default=False)
    suppliers_create = models.BooleanField(default=False)
    suppliers_edit = models.BooleanField(default=False)
    suppliers_delete = models.BooleanField(default=False)
    
    # ===== EXPENSE MODULE PERMISSIONS =====
    expense_view = models.BooleanField(default=False)
    expense_create = models.BooleanField(default=False)
    expense_edit = models.BooleanField(default=False)
    expense_delete = models.BooleanField(default=False)
    
    # ===== RETURN MODULE PERMISSIONS =====
    return_view = models.BooleanField(default=False)
    return_create = models.BooleanField(default=False)
    return_edit = models.BooleanField(default=False)
    return_delete = models.BooleanField(default=False)
    
    # ===== REPORTS MODULE PERMISSIONS =====
    reports_view = models.BooleanField(default=False)
    reports_create = models.BooleanField(default=False)
    reports_export = models.BooleanField(default=False)
    
    # ===== USERS MODULE PERMISSIONS =====
    users_view = models.BooleanField(default=False)
    users_create = models.BooleanField(default=False)
    users_edit = models.BooleanField(default=False)
    users_delete = models.BooleanField(default=False)
    
    # ===== ADMINISTRATION MODULE PERMISSIONS =====
    administration_view = models.BooleanField(default=False)
    administration_create = models.BooleanField(default=False)
    administration_edit = models.BooleanField(default=False)
    administration_delete = models.BooleanField(default=False)
    
    # ===== SETTINGS PERMISSIONS =====
    settings_view = models.BooleanField(default=False)
    settings_edit = models.BooleanField(default=False)
    
    is_verified = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    
    # নতুন ফিল্ড: পারমিশন সোর্স ট্র্যাক করতে
    permission_source = models.CharField(
        max_length=20,
        choices=[
            ('ROLE', 'Role Based'),
            ('CUSTOM', 'Custom'),
            ('MIXED', 'Mixed')
        ],
        default='ROLE'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_verified']),
            models.Index(fields=['permission_source']),
        ]

    def save(self, *args, **kwargs):
        # নতুন ইউজার is_superuser=True নিয়ে এলে (যেমন Django admin) role ঠিক করে দিই
        if self.pk is None and self.is_superuser and self.role != self.Role.SUPER_ADMIN:
            self.role = self.Role.SUPER_ADMIN
        # সুপারইউজারের জন্য বিশেষ হ্যান্ডলিং
        if self.role == self.Role.SUPER_ADMIN:
            self.is_staff = True
            self.is_superuser = True
            self.permission_source = 'CUSTOM'
            self._set_all_permissions(True)
        else:
            # অন্যান্য ইউজারদের জন্য
            if self.role in [self.Role.ADMIN, self.Role.MANAGER]:
                self.is_staff = True
                self.is_superuser = False
            else:
                self.is_staff = False
                self.is_superuser = False
            
            # Role অনুযায়ী শুধুমাত্র ডিফল্ট পারমিশন সেট করি
            # Admin পরে custom পারমিশন দিতে পারবে
            if self.pk is None:  # শুধুমাত্র নতুন ইউজার তৈরি হলে
                self._set_role_default_permissions()
        
        super().save(*args, **kwargs)

    def _set_role_default_permissions(self):
        """রোল অনুযায়ী শুধুমাত্র ডিফল্ট পারমিশন সেট করি"""
        if self.role == self.Role.ADMIN:
            self._set_admin_default_permissions()
        elif self.role == self.Role.MANAGER:
            self._set_manager_default_permissions()
        elif self.role == self.Role.STAFF:
            self._set_staff_default_permissions()
        elif self.role == self.Role.VIEWER:
            self._set_viewer_default_permissions()
        
        self.permission_source = 'ROLE'

    def _set_admin_default_permissions(self):
        """Admin এর ডিফল্ট পারমিশন (সব পারমিশন True)"""
        self._set_all_permissions(True)
        self.permission_source = 'CUSTOM'  # Admin সবসময় custom পারমিশন পাবে

    def _set_manager_default_permissions(self):
        """Manager এর ডিফল্ট পারমিশন"""
        self.can_access_dashboard = True
        
        # Sales
        self.sales_view = True
        self.sales_create = True
        self.sales_edit = True
        self.sales_delete = True
        
        # Money Receipt
        self.money_receipt_view = True
        self.money_receipt_create = True
        self.money_receipt_edit = True
        self.money_receipt_delete = True
        
        # Purchases
        self.purchases_view = True
        self.purchases_create = True
        self.purchases_edit = True
        self.purchases_delete = True
        
        # Products
        self.products_view = True
        self.products_create = True
        self.products_edit = True
        self.products_delete = True
        
        # Accounts
        self.accounts_view = True
        self.accounts_create = True
        self.accounts_edit = True
        self.accounts_delete = True
        
        # Customers
        self.customers_view = True
        self.customers_create = True
        self.customers_edit = True
        self.customers_delete = True
        
        # Suppliers
        self.suppliers_view = True
        self.suppliers_create = True
        self.suppliers_edit = True
        self.suppliers_delete = True
        
        # Expense
        self.expense_view = True
        self.expense_create = True
        self.expense_edit = True
        self.expense_delete = True
        
        # Return
        self.return_view = True
        self.return_create = True
        self.return_edit = True
        self.return_delete = True
        
        # Reports
        self.reports_view = True
        self.reports_create = True
        self.reports_export = True
        
        # Users - Manager can view but not manage users
        self.users_view = True
        self.users_create = False
        self.users_edit = False
        self.users_delete = False
        
        # Administration
        self.administration_view = True
        self.administration_create = True
        self.administration_edit = True
        self.administration_delete = True
        
        # Settings
        self.settings_view = True
        self.settings_edit = True

    def _set_staff_default_permissions(self):
        """Staff এর ডিফল্ট পারমিশন"""
        self.can_access_dashboard = True
        
        # Sales - Staff can create and edit but not delete
        self.sales_view = True
        self.sales_create = True
        self.pos_sales_create = True
        self.short_sales_create = True
        self.sales_edit = True
        self.sales_delete = False
        
        # Money Receipt
        self.money_receipt_view = True
        self.money_receipt_create = True
        self.money_receipt_edit = True
        self.money_receipt_delete = False
        
        # Purchases - Staff can only view
        self.purchases_view = True
        self.purchases_create = False
        self.purchases_edit = False
        self.purchases_delete = False
        
        # Products - Staff can view and edit but not create/delete
        self.products_view = True
        self.products_create = False
        self.products_edit = True
        self.products_delete = False
        
        # Accounts - Staff can only view
        self.accounts_view = True
        self.accounts_create = False
        self.accounts_edit = False
        self.accounts_delete = False
        
        # Customers - Staff can create and edit but not delete
        self.customers_view = True
        self.customers_create = True
        self.customers_edit = True
        self.customers_delete = False
        
        # Suppliers - Staff can only view
        self.suppliers_view = True
        self.suppliers_create = False
        self.suppliers_edit = False
        self.suppliers_delete = False
        
        # Expense - Staff can only view
        self.expense_view = True
        self.expense_create = False
        self.expense_edit = False
        self.expense_delete = False
        
        # Return - Staff can create and edit but not delete
        self.return_view = True
        self.return_create = True
        self.return_edit = True
        self.return_delete = False
        
        # Reports - Staff can view and export
        self.reports_view = True
        self.reports_create = False
        self.reports_export = True
        
        # Users - Staff cannot access user management
        self.users_view = False
        self.users_create = False
        self.users_edit = False
        self.users_delete = False
        
        # Administration - Staff cannot access
        self.administration_view = False
        self.administration_create = False
        self.administration_edit = False
        self.administration_delete = False
        
        # Settings - Staff can view but not edit
        self.settings_view = True
        self.settings_edit = False

    def _set_viewer_default_permissions(self):
        """Viewer এর ডিফল্ট পারমিশন (শুধু view পারমিশন)"""
        self.can_access_dashboard = True
        
        # All view permissions True, others False
        self.sales_view = True
        self.sales_create = False
        self.pos_sales_create = False
        self.short_sales_create = False
        self.sales_edit = False
        self.sales_delete = False
        
        self.money_receipt_view = True
        self.money_receipt_create = False
        self.money_receipt_edit = False
        self.money_receipt_delete = False
        
        self.purchases_view = True
        self.purchases_create = False
        self.purchases_edit = False
        self.purchases_delete = False
        
        self.products_view = True
        self.products_create = False
        self.products_edit = False
        self.products_delete = False
        
        self.accounts_view = True
        self.accounts_create = False
        self.accounts_edit = False
        self.accounts_delete = False
        
        self.customers_view = True
        self.customers_create = False
        self.customers_edit = False
        self.customers_delete = False
        
        self.suppliers_view = True
        self.suppliers_create = False
        self.suppliers_edit = False
        self.suppliers_delete = False
        
        self.expense_view = True
        self.expense_create = False
        self.expense_edit = False
        self.expense_delete = False
        
        self.return_view = True
        self.return_create = False
        self.return_edit = False
        self.return_delete = False
        
        self.reports_view = True
        self.reports_create = False
        self.reports_export = True
        
        self.users_view = False
        self.users_create = False
        self.users_edit = False
        self.users_delete = False
        
        self.administration_view = False
        self.administration_create = False
        self.administration_edit = False
        self.administration_delete = False
        
        self.settings_view = True
        self.settings_edit = False

    def _set_all_permissions(self, value):
        """Set all permissions to given value"""
        self.can_access_dashboard = value
        
        # Sales
        self.sales_view = value
        self.sales_create = value
        self.pos_sales_create = value
        self.short_sales_create = value
        self.sales_edit = value
        self.sales_delete = value
        
        # Money Receipt
        self.money_receipt_view = value
        self.money_receipt_create = value
        self.money_receipt_edit = value
        self.money_receipt_delete = value
        
        # Purchases
        self.purchases_view = value
        self.purchases_create = value
        self.purchases_edit = value
        self.purchases_delete = value
        
        # Products
        self.products_view = value
        self.products_create = value
        self.products_edit = value
        self.products_delete = value
        
        # Accounts
        self.accounts_view = value
        self.accounts_create = value
        self.accounts_edit = value
        self.accounts_delete = value
        
        # Customers
        self.customers_view = value
        self.customers_create = value
        self.customers_edit = value
        self.customers_delete = value
        
        # Suppliers
        self.suppliers_view = value
        self.suppliers_create = value
        self.suppliers_edit = value
        self.suppliers_delete = value
        
        # Expense
        self.expense_view = value
        self.expense_create = value
        self.expense_edit = value
        self.expense_delete = value
        
        # Return
        self.return_view = value
        self.return_create = value
        self.return_edit = value
        self.return_delete = value
        
        # Reports
        self.reports_view = value
        self.reports_create = value
        self.reports_export = value
        
        # Users
        self.users_view = value
        self.users_create = value
        self.users_edit = value
        self.users_delete = value
        
        # Administration
        self.administration_view = value
        self.administration_create = value
        self.administration_edit = value
        self.administration_delete = value
        
        # Settings
        self.settings_view = value
        self.settings_edit = value

    def update_custom_permissions(self, permissions_dict):
        """
        Admin দ্বারা custom পারমিশন আপডেট করার মেথড
        permissions_dict: {
            'dashboard': {'view': True},
            'sales': {'view': True, 'create': True, 'edit': True, 'delete': False, 'create_pos': True, 'create_short': True},
            ...
        }
        """
        # Validate and update permissions
        permission_mapping = self._get_permission_mapping()
        
        for module, perms in permissions_dict.items():
            if module in permission_mapping:
                module_mapping = permission_mapping[module]
                for action, field_name in module_mapping.items():
                    if action in perms and hasattr(self, field_name):
                        setattr(self, field_name, perms[action])
        
        # Update permission source
        if self.permission_source == 'ROLE':
            self.permission_source = 'MIXED'
        else:
            self.permission_source = 'CUSTOM'
        
        self.save()

    def _get_permission_mapping(self):
        """পারমিশন ফিল্ড ম্যাপিং ডিকশনারি রিটার্ন করে"""
        return {
            'dashboard': {'view': 'can_access_dashboard'},
            'sales': {
                'view': 'sales_view',
                'create': 'sales_create',
                'create_pos': 'pos_sales_create',
                'create_short': 'short_sales_create',
                'edit': 'sales_edit',
                'delete': 'sales_delete'
            },
            'money_receipt': {
                'view': 'money_receipt_view',
                'create': 'money_receipt_create',
                'edit': 'money_receipt_edit',
                'delete': 'money_receipt_delete'
            },
            'purchases': {
                'view': 'purchases_view',
                'create': 'purchases_create',
                'edit': 'purchases_edit',
                'delete': 'purchases_delete'
            },
            'products': {
                'view': 'products_view',
                'create': 'products_create',
                'edit': 'products_edit',
                'delete': 'products_delete'
            },
            'accounts': {
                'view': 'accounts_view',
                'create': 'accounts_create',
                'edit': 'accounts_edit',
                'delete': 'accounts_delete'
            },
            'customers': {
                'view': 'customers_view',
                'create': 'customers_create',
                'edit': 'customers_edit',
                'delete': 'customers_delete'
            },
            'suppliers': {
                'view': 'suppliers_view',
                'create': 'suppliers_create',
                'edit': 'suppliers_edit',
                'delete': 'suppliers_delete'
            },
            'expense': {
                'view': 'expense_view',
                'create': 'expense_create',
                'edit': 'expense_edit',
                'delete': 'expense_delete'
            },
            'return': {
                'view': 'return_view',
                'create': 'return_create',
                'edit': 'return_edit',
                'delete': 'return_delete'
            },
            'reports': {
                'view': 'reports_view',
                'create': 'reports_create',
                'export': 'reports_export'
            },
            'users': {
                'view': 'users_view',
                'create': 'users_create',
                'edit': 'users_edit',
                'delete': 'users_delete'
            },
            'administration': {
                'view': 'administration_view',
                'create': 'administration_create',
                'edit': 'administration_edit',
                'delete': 'administration_delete'
            },
            'settings': {
                'view': 'settings_view',
                'edit': 'settings_edit'
            }
        }

    def get_permissions(self):
        """Return all permissions as a structured dictionary"""
        return {
            'dashboard': {'view': self.can_access_dashboard},
            'sales': {
                'view': self.sales_view,
                'create': self.sales_create,
                'create_pos': self.pos_sales_create,
                'create_short': self.short_sales_create,
                'edit': self.sales_edit,
                'delete': self.sales_delete
            },
            'money_receipt': {
                'view': self.money_receipt_view,
                'create': self.money_receipt_create,
                'edit': self.money_receipt_edit,
                'delete': self.money_receipt_delete
            },
            'purchases': {
                'view': self.purchases_view,
                'create': self.purchases_create,
                'edit': self.purchases_edit,
                'delete': self.purchases_delete
            },
            'products': {
                'view': self.products_view,
                'create': self.products_create,
                'edit': self.products_edit,
                'delete': self.products_delete
            },
            'accounts': {
                'view': self.accounts_view,
                'create': self.accounts_create,
                'edit': self.accounts_edit,
                'delete': self.accounts_delete
            },
            'customers': {
                'view': self.customers_view,
                'create': self.customers_create,
                'edit': self.customers_edit,
                'delete': self.customers_delete
            },
            'suppliers': {
                'view': self.suppliers_view,
                'create': self.suppliers_create,
                'edit': self.suppliers_edit,
                'delete': self.suppliers_delete
            },
            'expense': {
                'view': self.expense_view,
                'create': self.expense_create,
                'edit': self.expense_edit,
                'delete': self.expense_delete
            },
            'return': {
                'view': self.return_view,
                'create': self.return_create,
                'edit': self.return_edit,
                'delete': self.return_delete
            },
            'reports': {
                'view': self.reports_view,
                'create': self.reports_create,
                'export': self.reports_export
            },
            'users': {
                'view': self.users_view,
                'create': self.users_create,
                'edit': self.users_edit,
                'delete': self.users_delete
            },
            'administration': {
                'view': self.administration_view,
                'create': self.administration_create,
                'edit': self.administration_edit,
                'delete': self.administration_delete
            },
            'settings': {
                'view': self.settings_view,
                'edit': self.settings_edit
            },
            'permission_source': self.permission_source
        }

    def has_permission(self, module, action=None):
        """Check if user has specific permission for module and action"""
        permissions = self.get_permissions()
        
        if module not in permissions:
            return False
            
        if action is None:
            # Check if user has any permission for this module
            return any(value for key, value in permissions[module].items() 
                      if key not in ['create_pos', 'create_short'] or action == 'create')
        
        if action not in permissions[module]:
            return False
            
        return permissions[module][action]

    def can_create(self, module):
        """Alias method for create permission"""
        return self.has_permission(module, 'create')

    def can_edit(self, module):
        """Alias method for edit permission"""
        return self.has_permission(module, 'edit')

    def can_delete(self, module):
        """Alias method for delete permission"""
        return self.has_permission(module, 'delete')

    def can_view(self, module):
        """Alias method for view permission"""
        return self.has_permission(module, 'view')

    def can_manage_user(self, target_user):
        """Check if this user can manage another user"""
        if self.role == self.Role.SUPER_ADMIN:
            return True
        if self.role == self.Role.ADMIN:
            return target_user.role != self.Role.SUPER_ADMIN
        return False

    def reset_to_role_permissions(self):
        """রোল অনুযায়ী পারমিশনে রিসেট করুন"""
        if self.role == self.Role.SUPER_ADMIN:
            return  # Super admin এর পারমিশন রিসেট হয় না
        
        self._set_role_default_permissions()
        self.save()

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"


class UserPermission(models.Model):
    """Individual user custom permissions (for admin override)"""
    
    class Module(models.TextChoices):
        DASHBOARD = 'dashboard', _('Dashboard')
        SALES = 'sales', _('Sales')
        MONEY_RECEIPT = 'money_receipt', _('Money Receipt')
        PURCHASES = 'purchases', _('Purchases')
        PRODUCTS = 'products', _('Products')
        ACCOUNTS = 'accounts', _('Accounts')
        CUSTOMERS = 'customers', _('Customers')
        SUPPLIERS = 'suppliers', _('Suppliers')
        EXPENSE = 'expense', _('Expense')
        RETURN = 'return', _('Return')
        REPORTS = 'reports', _('Reports')
        USERS = 'users', _('Users')
        ADMINISTRATION = 'administration', _('Administration')
        SETTINGS = 'settings', _('Settings')
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='custom_permissions'
    )
    module = models.CharField(max_length=50, choices=Module.choices)
    
    # Basic permissions
    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    
    # Special permissions for sales
    can_create_pos = models.BooleanField(default=False)
    can_create_short = models.BooleanField(default=False)
    
    # Report permissions
    can_export = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_permissions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'module']
        verbose_name = _('User Permission')
        verbose_name_plural = _('User Permissions')
        indexes = [
            models.Index(fields=['user', 'module']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_module_display()}"


class RolePermission(models.Model):
    """Permissions for StaffRole"""
    
    class Module(models.TextChoices):
        DASHBOARD = 'dashboard', _('Dashboard')
        SALES = 'sales', _('Sales')
        MONEY_RECEIPT = 'money_receipt', _('Money Receipt')
        PURCHASES = 'purchases', _('Purchases')
        PRODUCTS = 'products', _('Products')
        ACCOUNTS = 'accounts', _('Accounts')
        CUSTOMERS = 'customers', _('Customers')
        SUPPLIERS = 'suppliers', _('Suppliers')
        EXPENSE = 'expense', _('Expense')
        RETURN = 'return', _('Return')
        REPORTS = 'reports', _('Reports')
        USERS = 'users', _('Users')
        ADMINISTRATION = 'administration', _('Administration')
        SETTINGS = 'settings', _('Settings')
    
    staff_role = models.ForeignKey(
        'StaffRole', 
        on_delete=models.CASCADE, 
        related_name='permissions'  # This creates the relationship
    )
    module = models.CharField(max_length=50, choices=Module.choices)
    
    # Basic permissions
    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    
    # Report permissions
    can_export = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['staff_role', 'module']
        verbose_name = _('Role Permission')
        verbose_name_plural = _('Role Permissions')

    def __str__(self):
        return f"{self.staff_role.name} - {self.get_module_display()}"


class StaffRole(models.Model):
    class RoleType(models.TextChoices):
        MANAGEMENT = 'management', _('Management')
        SALES = 'sales', _('Sales')
        WAREHOUSE = 'warehouse', _('Warehouse')
        ACCOUNTS = 'accounts', _('Accounts')
        SUPPORT = 'support', _('Support')
        CUSTOM = 'custom', _('Custom')
    
    name = models.CharField(max_length=100, unique=True)
    role_type = models.CharField(
        max_length=20,
        choices=RoleType.choices,
        default=RoleType.CUSTOM
    )
    description = models.TextField(blank=True, null=True)
    default_permissions = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Staff Role')
        verbose_name_plural = _('Staff Roles')
        ordering = ['name']

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new and not self.default_permissions:
            self.generate_default_permissions()

    def generate_default_permissions(self):
        default_permissions = {
            'management': {
                'dashboard': {'view': True},
                'sales': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'money_receipt': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'purchases': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'products': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'accounts': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'customers': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'suppliers': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'expense': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'return': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'reports': {'view': True, 'create': True, 'export': True},
                'users': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'administration': {'view': True, 'create': True, 'edit': True, 'delete': True},
                'settings': {'view': True, 'edit': True},
            },
            'sales': {
                'dashboard': {'view': True},
                'sales': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'money_receipt': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'customers': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'products': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'reports': {'view': True, 'export': True},
            },
            'warehouse': {
                'dashboard': {'view': True},
                'products': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'purchases': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'suppliers': {'view': True, 'create': False, 'edit': False, 'delete': False},
            },
            'accounts': {
                'dashboard': {'view': True},
                'accounts': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'money_receipt': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'expense': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'reports': {'view': True, 'export': True},
            },
            'support': {
                'dashboard': {'view': True},
                'customers': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'return': {'view': True, 'create': True, 'edit': True, 'delete': False},
            },
            'custom': {}
        }
        
        permissions_map = default_permissions.get(self.role_type, {})
        self.default_permissions = permissions_map
        
        for module, perms in permissions_map.items():
            RolePermission.objects.create(
                staff_role=self,
                module=module,
                can_view=perms.get('view', False),
                can_create=perms.get('create', False),
                can_edit=perms.get('edit', False),
                can_delete=perms.get('delete', False),
                can_export=perms.get('export', False)
            )
        
        self.save()

    def update_permissions(self, permissions_data):
        self.default_permissions = permissions_data
        
        for module, perms in permissions_data.items():
            RolePermission.objects.update_or_create(
                staff_role=self,
                module=module,
                defaults={
                    'can_view': perms.get('view', False),
                    'can_create': perms.get('create', False),
                    'can_edit': perms.get('edit', False),
                    'can_delete': perms.get('delete', False),
                    'can_export': perms.get('export', False)
                }
            )
        
        module_names = permissions_data.keys()
        self.permissions.exclude(module__in=module_names).delete()
        
        self.save()

    def get_permissions_dict(self):
        if not self.default_permissions and self.role_type != 'custom':
            self.generate_default_permissions()
        
        permissions = {}
        for perm in self.permissions.all():
            permissions[perm.module] = {
                'view': perm.can_view,
                'create': perm.can_create,
                'edit': perm.can_edit,
                'delete': perm.can_delete,
                'export': perm.can_export
            }
        
        return permissions

    def __str__(self):
        return f"{self.name} ({self.get_role_type_display()})"


class Staff(models.Model):
    class Status(models.IntegerChoices):
        INACTIVE = 0, _('Inactive')
        ACTIVE = 1, _('Active')
        SUSPENDED = 2, _('Suspended')
        ON_LEAVE = 3, _('On Leave')
    
    class EmploymentType(models.TextChoices):
        FULL_TIME = 'full_time', _('Full Time')
        PART_TIME = 'part_time', _('Part Time')
        CONTRACT = 'contract', _('Contract')
        INTERN = 'intern', _('Intern')

    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='staff_profile'
    )
    role = models.ForeignKey(
        StaffRole, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='staff_members'
    )

    phone = models.CharField(max_length=20, blank=True, null=True)
    alternate_phone = models.CharField(max_length=20, blank=True, null=True)
    image = models.ImageField(upload_to='staff/images/', blank=True, null=True)
    designation = models.CharField(max_length=120, blank=True, null=True)
    
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME
    )
    employee_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    
    salary = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    commission = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    bonus = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    
    is_main_user = models.BooleanField(default=False)
    status = models.IntegerField(
        choices=Status.choices, 
        default=Status.ACTIVE
    )
    
    joining_date = models.DateField(null=True, blank=True)
    leaving_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    
    address = models.TextField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=100, blank=True, null=True)
    emergency_phone = models.CharField(max_length=20, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Staff')
        verbose_name_plural = _('Staff')
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['is_main_user']),
            models.Index(fields=['employment_type']),
        ]

    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = self._generate_employee_id()
            
        super().save(*args, **kwargs)
        
        if self.role and self.user:
            self.user.assign_role_permissions(self.role)

    def _generate_employee_id(self):
        count = Staff.objects.count() + 1
        code = f"EMP-{count:04d}"
        while Staff.objects.filter(employee_id=code).exists():
            count += 1
            code = f"EMP-{count:04d}"
        return code

    @property
    def is_currently_active(self):
        if self.status == self.Status.INACTIVE:
            return False
        if self.leaving_date and self.leaving_date < date.today():
            return False
        return True

    @property
    def employment_duration(self):
        if self.joining_date:
            end_date = self.leaving_date or date.today()
            return (end_date - self.joining_date).days
        return 0

    @property
    def total_compensation(self):
        return self.salary + self.commission + self.bonus

    def __str__(self):
        user_name = self.user.get_full_name() or self.user.username
        designation = self.designation or 'Staff'
        return f"{user_name} - {designation}"