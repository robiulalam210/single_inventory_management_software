import re

from django import forms

from .models import ShopSettings

HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


class ShopSettingsForm(forms.ModelForm):
    remove_hero_image = forms.BooleanField(required=False, label='Remove banner image')

    class Meta:
        model = ShopSettings
        exclude = ['updated_at']
        widgets = {
            'about_text': forms.Textarea(attrs={'rows': 4}),
            'brand_color': forms.TextInput(attrs={'type': 'color'}),
        }

    def clean_brand_color(self):
        v = (self.cleaned_data.get('brand_color') or '').strip()
        if not HEX.match(v):
            raise forms.ValidationError('Use a colour like #0f766e.')
        return v

    def clean_hero_image(self):
        img = self.cleaned_data.get('hero_image')
        if img and hasattr(img, 'size') and img.size > 3 * 1024 * 1024:
            raise forms.ValidationError('Image is too large (max 3 MB).')
        return img

    def clean_whatsapp(self):
        return re.sub(r'\D', '', self.cleaned_data.get('whatsapp') or '')

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get('remove_hero_image') and not self.files.get('hero_image'):
            obj.hero_image = None
        if commit:
            obj.save()
        return obj
