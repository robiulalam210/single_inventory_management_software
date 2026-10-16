# reports/utils.py
from datetime import datetime, timedelta
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from decimal import Decimal

class ReportPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000

def custom_response(success=True, message="", data=None, status_code=200):
    """
    Standard response format for all APIs.
    """
    return Response({
        "status": success,
        "message": message,
        "data": data
    }, status=status_code)

def _parse_date_safe(date_str):
    """Returns a date or None (safe parse)."""
    if not date_str:
        return None
    return parse_date(date_str)

def get_date_range(request):
    """Get start and end dates from request with default ranges."""
    # FIX: app এর কয়েকটা report `start_date` / `end_date` পাঠাত, এখানে শুধু `start` / `end`
    # পড়া হতো — তাই তারিখ বাছলেও সবসময় "গত ৩০ দিন" আসত। এখন দুই নামই চলে।
    start = _parse_date_safe(request.GET.get('start') or request.GET.get('start_date'))
    end = _parse_date_safe(request.GET.get('end') or request.GET.get('end_date'))
    
    # If no dates provided, default to last 30 days
    if not start and not end:
        end = timezone.now().date()
        start = end - timedelta(days=30)
    # If only start provided, default to today as end
    elif start and not end:
        end = timezone.now().date()
    # If only end provided, default to 30 days before end
    elif end and not start:
        start = end - timedelta(days=30)
    
    return start, end

def get_predefined_range(request):
    """Get predefined date ranges like 'today', 'week', 'month', etc."""
    range_type = request.GET.get('range', '').lower()
    today = timezone.now().date()
    
    if range_type == 'today':
        return today, today
    elif range_type == 'yesterday':
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    elif range_type == 'week':
        start = today - timedelta(days=today.weekday())
        return start, today
    elif range_type == 'month':
        start = today.replace(day=1)
        return start, today
    elif range_type == 'last_week':
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return start, end
    elif range_type == 'last_month':
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        end = today.replace(day=1) - timedelta(days=1)
        return start, end
    elif range_type == 'year':
        start = today.replace(month=1, day=1)
        return start, today
    elif range_type == 'last_year':
        start = today.replace(year=today.year-1, month=1, day=1)
        end = today.replace(year=today.year-1, month=12, day=31)
        return start, end
    else:
        return None, None

def build_summary(report_data, date_range):
    """Build standardized summary for reports."""
    if not report_data:
        return {
            'total_count': 0,
            'total_revenue': 0.0,
            'total_discount': 0.0,
            'total_vat': 0.0,
            'date_range': {
                'start': date_range[0].isoformat() if date_range[0] else None,
                'end': date_range[1].isoformat() if date_range[1] else None
            }
        }
    
    return {
        'total_count': len(report_data),
        'total_revenue': sum(item.get('net_amount', item.get('return_amount', item.get('total_sales', 0))) for item in report_data),
        'total_discount': sum(item.get('total_discount', 0) for item in report_data),
        'total_vat': sum(item.get('total_vat', 0) for item in report_data),
        'date_range': {
            'start': date_range[0].isoformat() if date_range[0] else None,
            'end': date_range[1].isoformat() if date_range[1] else None
        }
    }

def build_advanced_summary(report_data, date_range, report_type='sales'):
    """Build comprehensive summary with type-specific metrics"""
    base_summary = build_summary(report_data, date_range)
    
    if report_type == 'sales' and report_data:
        base_summary['average_sale'] = base_summary['total_revenue'] / base_summary['total_count']
    elif report_type == 'purchase' and report_data:
        base_summary['average_purchase'] = base_summary['total_revenue'] / base_summary['total_count']
    
    return base_summary