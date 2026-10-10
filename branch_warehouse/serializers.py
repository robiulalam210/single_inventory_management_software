from rest_framework import serializers
from .model import Branch, Warehouse

# Branch & Warehouse
class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = '__all__'


class WarehouseSerializer(serializers.ModelSerializer):
    branch = BranchSerializer(read_only=True)
    branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), source='branch', write_only=True
    )

    class Meta:
        model = Warehouse
        fields = ['id', 'name', 'location', 'branch', 'branch_id']