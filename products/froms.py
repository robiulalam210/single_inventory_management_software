from django import forms
from .models import Category, Unit, Brand, Group, Source, Product

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = '__all__'

class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = '__all__'

class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = '__all__'

class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = '__all__'

class SourceForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = '__all__'

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'