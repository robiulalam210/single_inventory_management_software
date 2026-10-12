from django.contrib import admin

from .models import DayClose


@admin.register(DayClose)
class DayCloseAdmin(admin.ModelAdmin):
    list_display = ('date', 'total_expected', 'total_counted', 'difference', 'closed_by', 'closed_at')
