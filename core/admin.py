from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import Group
from django.utils.functional import lazy
from .models import User, BusinessProfile, StaffRole, Staff, UserPermission


class SuperUserAdmin(admin.ModelAdmin):
    """Base class for models that should be fully accessible to superusers"""
    
    def has_module_permission(self, request):
        return request.user.is_superuser
    
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def has_add_permission(self, request):
        return request.user.is_superuser
    
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(BusinessProfile)
class BusinessProfileAdmin(SuperUserAdmin):
    """একটাই ব্যবসা — এখানে নাম বদলালে সব জায়গায় (লগইন, ড্যাশবোর্ড, ইনভয়েস, শপ) নতুন নাম দেখাবে।"""
    list_display = ("name", "phone", "email", "updated_at")
    readonly_fields = ("updated_at",)
    fieldsets = (
        ("ব্যবসার নাম ও লোগো", {"fields": ("name", "tagline", "logo")}),
        ("যোগাযোগ", {"fields": ("phone", "whatsapp", "email", "address", "website")}),
        ("অন্যান্য", {"fields": ("trade_license", "currency", "updated_at")}),
    )

    def has_add_permission(self, request):
        # মাত্র একটি রেকর্ড; না থাকলে তবেই নতুন বানানো যাবে
        return request.user.is_superuser and not BusinessProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        ("Personal Information", {
            "fields": ("username", "password", "first_name", "last_name", "email")
        }),
        ("Role", {
            "fields": (
                "role", 
                "permission_source",
                "phone",
                "profile_picture",
                "date_of_birth"
            )
        }),
        ("Dashboard Permissions", {
            "fields": ("can_access_dashboard",),
            "classes": ("collapse",)
        }),
        ("Sales & Money Receipt Permissions", {
            "fields": (
                "sales_view", "sales_create", "pos_sales_create", "short_sales_create", "sales_edit", "sales_delete",
                "money_receipt_view", "money_receipt_create", "money_receipt_edit", "money_receipt_delete",
            ),
            "classes": ("collapse",)
        }),
        ("Purchases & Products Permissions", {
            "fields": (
                "purchases_view", "purchases_create", "purchases_edit", "purchases_delete",
                "products_view", "products_create", "products_edit", "products_delete",
            ),
            "classes": ("collapse",)
        }),
        ("Accounts & Customers Permissions", {
            "fields": (
                "accounts_view", "accounts_create", "accounts_edit", "accounts_delete",
                "customers_view", "customers_create", "customers_edit", "customers_delete",
            ),
            "classes": ("collapse",)
        }),
        ("Suppliers & Expense Permissions", {
            "fields": (
                "suppliers_view", "suppliers_create", "suppliers_edit", "suppliers_delete",
                "expense_view", "expense_create", "expense_edit", "expense_delete",
            ),
            "classes": ("collapse",)
        }),
        ("Return & Reports Permissions", {
            "fields": (
                "return_view", "return_create", "return_edit", "return_delete",
                "reports_view", "reports_create", "reports_export",
            ),
            "classes": ("collapse",)
        }),
        ("Users & Administration Permissions", {
            "fields": (
                "users_view", "users_create", "users_edit", "users_delete",
                "administration_view", "administration_create", "administration_edit", "administration_delete",
            ),
            "classes": ("collapse",)
        }),
        ("Settings & Verification", {
            "fields": (
                "settings_view", "settings_edit",
                "is_verified", "last_login_ip"
            ),
            "classes": ("collapse",)
        }),
        ("Status", {
            "fields": ("is_active", "is_staff", "is_superuser")
        }),
        ("Important Dates", {
            "fields": ("last_login", "date_joined", "created_at", "updated_at"),
            "classes": ("collapse",)
        })
    )
    
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2", "email"),
        }),
        ("Personal Information", {
            "fields": ("first_name", "last_name", "phone", "date_of_birth")
        }),
        ("Role", {
            "fields": ("role",)
        }),
        ("Status", {
            "fields": ("is_active", "is_staff", "is_superuser")
        }),
    )

    list_display = (
        "username", 
        "email", 
        "full_name",
        "role", 
        "permission_source_display",
        "is_staff", 
        "is_superuser",
        "is_active", 
        "is_verified",
        "last_login",
        "permissions_summary",
        "custom_permissions_count"
    )
    
    list_filter = (
        "role", 
        "permission_source",
        "is_staff", 
        "is_superuser",
        "is_active", 
        "is_verified",
        "last_login"
    )
    
    search_fields = (
        "username", 
        "email", 
        "first_name", 
        "last_name",
        "phone"
    )
    
    readonly_fields = (
        "permission_source",
        "last_login", 
        "date_joined",
        "created_at",
        "updated_at",
        "last_login_ip"
    )
    
    ordering = ("username",)
    list_per_page = 25
    
    def full_name(self, obj):
        name = obj.get_full_name()
        if name:
            return name
        return format_html('<span style="color: #999;">No Name</span>')
    full_name.short_description = "Full Name"
    full_name.admin_order_field = "first_name"
    
    def permission_source_display(self, obj):
        colors = {
            'ROLE': '#5bc0de',
            'CUSTOM': '#5cb85c',
            'MIXED': '#f0ad4e'
        }
        color = colors.get(obj.permission_source, '#777')
        return format_html(
            '<span style="color: white; background: {}; padding: 3px 8px; border-radius: 10px; font-size: 11px;">{}</span>',
            color,
            obj.get_permission_source_display()
        )
    permission_source_display.short_description = "Permission Source"
    permission_source_display.admin_order_field = "permission_source"
    
    def custom_permissions_count(self, obj):
        count = obj.custom_permissions.filter(is_active=True).count()
        if count > 0:
            url = reverse("admin:core_userpermission_changelist") + f"?user__id__exact={obj.id}"
            return format_html(
                '<a href="{}" style="color: #5cb85c; font-weight: bold;">{} custom</a>',
                url, count
            )
        return "-"
    custom_permissions_count.short_description = "Custom Perms"
    
    def permissions_summary(self, obj):
        if obj.is_superuser:
            return format_html('<span style="color: green; font-weight: bold; background: #e8f5e8; padding: 2px 8px; border-radius: 3px;">SUPERUSER</span>')
        
        # Get permissions
        perms = obj.get_permissions()
        
        # Count active modules
        active_modules = 0
        for module, module_perms in perms.items():
            if module == 'permission_source':
                continue
            if any(module_perms.values()):
                active_modules += 1
        
        if active_modules == 0:
            return format_html('<span style="color: orange; background: #fff3cd; padding: 2px 8px; border-radius: 3px;">No Permissions</span>')
        
        # Show summary based on permission source
        if obj.permission_source == 'ROLE':
            color = '#5bc0de'
            text = f'Role ({active_modules} modules)'
        elif obj.permission_source == 'CUSTOM':
            color = '#5cb85c'
            text = f'Custom ({active_modules} modules)'
        else:  # MIXED
            color = '#f0ad4e'
            text = f'Mixed ({active_modules} modules)'
        
        return format_html(
            '<span style="color: white; background: {}; padding: 2px 8px; border-radius: 3px; font-size: 12px;">{}</span>',
            color, text
        )
    
    permissions_summary.short_description = "Permissions"
    permissions_summary.allow_tags = True
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return qs.prefetch_related('custom_permissions')
        return qs.none()
    
    # Add custom actions
    actions = ['reset_to_role_permissions']
    
    def reset_to_role_permissions(self, request, queryset):
        """Reset selected users to role permissions"""
        for user in queryset:
            user.reset_to_role_permissions()
        self.message_user(request, f"{queryset.count()} users reset to role permissions.")
    reset_to_role_permissions.short_description = "Reset to role permissions"


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = (
        "user_display",
        "module_display",
        "permission_badges",
        "is_active",
        "created_by_display",
        "created_at"
    )
    
    list_filter = (
        "module",
        "is_active",
        "created_at",
    )
    
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "module"
    )
    
    readonly_fields = ("created_at", "updated_at", "created_by")
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("user", "module", "is_active")
        }),
        ("Permissions", {
            "fields": (
                ("can_view", "can_create", "can_edit", "can_delete"),
                ("can_create_pos", "can_create_short", "can_export")
            )
        }),
        ("Metadata", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",)
        })
    )
    
    def user_display(self, obj):
        name = obj.user.get_full_name() or obj.user.username
        url = reverse("admin:core_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, name)
    user_display.short_description = "User"
    user_display.admin_order_field = "user__username"
    
    def module_display(self, obj):
        return obj.get_module_display()
    module_display.short_description = "Module"
    module_display.admin_order_field = "module"
    
    def permission_badges(self, obj):
        badges = []
        
        # Basic permissions
        if obj.can_view:
            badges.append('<span style="background: #5bc0de; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin: 1px;">View</span>')
        if obj.can_create:
            badges.append('<span style="background: #5cb85c; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin: 1px;">Create</span>')
        if obj.can_edit:
            badges.append('<span style="background: #f0ad4e; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin: 1px;">Edit</span>')
        if obj.can_delete:
            badges.append('<span style="background: #d9534f; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin: 1px;">Delete</span>')
        
        # Special permissions
        if obj.can_create_pos:
            badges.append('<span style="background: #17a2b8; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin: 1px;">POS</span>')
        if obj.can_create_short:
            badges.append('<span style="background: #6f42c1; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin: 1px;">Short</span>')
        if obj.can_export:
            badges.append('<span style="background: #20c997; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin: 1px;">Export</span>')
        
        if not badges:
            return format_html('<span style="color: #999; font-style: italic;">No permissions</span>')
        
        return format_html(" ".join(badges))
    permission_badges.short_description = "Permissions"
    permission_badges.allow_tags = True
    
    def created_by_display(self, obj):
        if obj.created_by:
            name = obj.created_by.get_full_name() or obj.created_by.username
            url = reverse("admin:core_user_change", args=[obj.created_by.id])
            return format_html('<a href="{}">{}</a>', url, name)
        return "-"
    created_by_display.short_description = "Created By"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            'user', 'created_by'
        )
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return qs
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on create
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = (
        "name", 
        "role_type", 
        "is_active",
        "staff_count",
        "created_at"
    )
    
    list_filter = ("role_type", "is_active", "created_at")
    
    search_fields = ("name", "description")
    
    readonly_fields = ("created_at", "updated_at", "staff_count")
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "role_type", "is_active")
        }),
        ("Description", {
            "fields": ("description",)
        }),
        ("Default Permissions", {
            "fields": ("default_permissions",),
            "classes": ("collapse",)
        }),
        ("Statistics", {
            "fields": ("staff_count",),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        })
    )
    
    def staff_count(self, obj):
        count = obj.staff_members.count()
        url = reverse("admin:core_staff_changelist") + f"?role__id__exact={obj.id}"
        return format_html('<a href="{}">{}</a>', url, count)
    staff_count.short_description = "Staff Members"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return qs
        return qs.none()


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = (
        "user_display",
        "role", 
        "designation",
        "employment_type",
        "status_display", 
        "is_main_user", 
        "phone", 
        "joining_date",
        "salary_display",
        "employment_duration_display",
        "action_buttons"
    )
    
    list_filter = (
        "status", 
        "role", 
        "is_main_user",
        "employment_type",
        "joining_date"
    )
    
    search_fields = (
        "user__username", 
        "user__email", 
        "user__first_name",
        "user__last_name",
        "role__name", 
        "phone",
        "employee_id",
        "designation"
    )
    
    readonly_fields = (
        "created_at", 
        "updated_at",
        "employee_id",
        "employment_duration",
        "total_compensation"
    )
    
    fieldsets = (
        ("Basic Information", {
            "fields": (
                "user",
                "role",
                "employee_id",
                "image"
            )
        }),
        ("Employment Details", {
            "fields": (
                "designation",
                "department",
                "employment_type",
                "joining_date",
                "leaving_date",
                "contract_end_date"
            )
        }),
        ("Compensation", {
            "fields": (
                "salary",
                "commission", 
                "bonus",
                "total_compensation"
            )
        }),
        ("Status & Contact", {
            "fields": (
                "status",
                "is_main_user",
                "phone", 
                "alternate_phone",
                "address",
                "emergency_contact",
                "emergency_phone"
            )
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        })
    )
    
    list_per_page = 25
    
    def user_display(self, obj):
        name = obj.user.get_full_name() or obj.user.username
        url = reverse("admin:core_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, name)
    user_display.short_description = "Staff Member"
    user_display.admin_order_field = "user__username"
    
    def status_display(self, obj):
        status_colors = {
            0: "#777",   # Inactive
            1: "#5cb85c",  # Active
            2: "#d9534f",    # Suspended
            3: "#f0ad4e", # On Leave
        }
        color = status_colors.get(obj.status, "black")
        return format_html(
            '<span style="color: white; background: {}; padding: 3px 8px; border-radius: 10px; font-size: 12px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = "Status"
    status_display.allow_tags = True
    
    def salary_display(self, obj):
        if obj.salary:
            return f"৳{obj.salary:,.2f}"
        return "-"
    salary_display.short_description = "Salary"
    salary_display.admin_order_field = "salary"
    
    def employment_duration_display(self, obj):
        days = obj.employment_duration
        if days <= 0:
            return "N/A"
        if days >= 365:
            years = days // 365
            return f"{years}y"
        elif days >= 30:
            months = days // 30
            return f"{months}m"
        else:
            return f"{days}d"
    employment_duration_display.short_description = "Duration"
    
    def action_buttons(self, obj):
        edit_url = reverse("admin:core_staff_change", args=[obj.id])
        user_url = reverse("admin:core_user_change", args=[obj.user.id])
        perms_url = reverse("admin:core_userpermission_changelist") + f"?user__id__exact={obj.user.id}"
        
        return format_html(
            '<a href="{}" class="button" style="padding: 2px 6px; background: #417690; color: white; text-decoration: none; border-radius: 3px; margin: 1px; font-size: 11px;">Edit Staff</a>'
            '<a href="{}" class="button" style="padding: 2px 6px; background: #5a9c23; color: white; text-decoration: none; border-radius: 3px; margin: 1px; font-size: 11px;">Edit User</a>'
            '<a href="{}" class="button" style="padding: 2px 6px; background: #8a6d3b; color: white; text-decoration: none; border-radius: 3px; margin: 1px; font-size: 11px;">Permissions</a>',
            edit_url, user_url, perms_url
        )
    action_buttons.short_description = "Actions"
    action_buttons.allow_tags = True
    
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('user', 'role')
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return qs
        return qs.none()


# Customize admin site — নাম আসে BusinessProfile থেকে (ক্লায়েন্ট যা দেবে)
def _business_name():
    try:
        return BusinessProfile.get().name
    except Exception:  # টেবিল তৈরি হওয়ার আগে (migrate চলাকালীন)
        return "Business"


_lazy_name = lazy(_business_name, str)
_lazy_header = lazy(lambda: f"{_business_name()} — Administration", str)
_lazy_welcome = lazy(lambda: f"Welcome to {_business_name()} Admin Panel", str)
admin.site.site_header = _lazy_header()
admin.site.site_title = _lazy_name()
admin.site.index_title = _lazy_welcome()

# Optionally unregister Group if not needed
# admin.site.unregister(Group)

# Add custom CSS for better admin interface
class CustomAdminSite(admin.AdminSite):
    def get_app_list(self, request, app_label=None):
        """
        Return a sorted list of all the installed apps that have been
        registered in this site.
        """
        app_list = super().get_app_list(request)
        
        # Sort apps by custom order
        app_order = {
            'auth': 1,  # Authentication
            'core': 2,  # Your main app
            'sales': 3,
            'products': 4,
            'customers': 5,
            'purchases': 6,
            'accounts': 7,
            'reports': 8,
        }
        
        # Sort the app list
        app_list.sort(key=lambda x: app_order.get(x['app_label'], 999))
        
        return app_list

# Override the default admin site
admin.site.__class__ = CustomAdminSite