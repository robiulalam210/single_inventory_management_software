# branch_warehouse/admin.py
from django.contrib import admin
from .model import Branch, Warehouse

admin.site.register(Branch)
admin.site.register(Warehouse)
