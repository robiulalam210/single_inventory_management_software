from urllib.parse import urlencode

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    PageNumberPagination that returns an API-friendly pagination block
    including count, total_pages, current_page, page_size, next, previous,
    and from/to (for "Showing X to Y of Z entries").
    Next/previous values are returned as relative querystring links like:
      ?page=2&page_size=20
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def _build_page_querystring(self, page_number, page_size):
        params = self.request.query_params.copy()
        params['page'] = page_number
        # make sure page_size is present so frontend can keep selection
        params['page_size'] = page_size
        qs = params.urlencode()
        return f'?{qs}' if qs else None

    def get_paginated_response(self, data):
        total_count = self.page.paginator.count
        page_size = self.get_page_size(self.request) or self.page_size
        current_page = self.page.number
        total_pages = self.page.paginator.num_pages

        next_qs = None
        prev_qs = None
        if self.page.has_next():
            next_qs = self._build_page_querystring(current_page + 1, page_size)
        if self.page.has_previous():
            prev_qs = self._build_page_querystring(current_page - 1, page_size)

        # compute "from" and "to" (1-based indices)
        showing_from = (current_page - 1) * page_size + 1 if total_count > 0 else 0
        showing_to = min(total_count, current_page * page_size)

        return Response({
            'results': data,
            'pagination': {
                'count': total_count,
                'total_pages': total_pages,
                'current_page': current_page,
                'page_size': page_size,
                'next': next_qs,
                'previous': prev_qs,
                'from': showing_from,
                'to': showing_to
            }
        })