# branch_warehouse/models.py
from django.db import models

class Branch(models.Model):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Warehouse(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='warehouses')
    name = models.CharField(max_length=120)
    location = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
