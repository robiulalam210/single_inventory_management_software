from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import status
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 30
    page_query_param = 'page'

    def paginate_queryset(self, queryset, request, view=None):
        """
        Paginate a queryset if required, either returning a
        page object, or `None` if pagination is not configured for this view.
        """
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        paginator = Paginator(queryset, page_size)
        page_number = request.query_params.get(self.page_query_param, 1)
        
        # Validate and sanitize page number
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            page_number = 1
            
        # Ensure page number is within valid range
        if page_number < 1:
            page_number = 1
        
        try:
            self.page = paginator.page(page_number)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of results.
            self.page = paginator.page(paginator.num_pages)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page.
            self.page = paginator.page(1)

        if paginator.num_pages > 1 and self.template is not None:
            # The browsable API should display pagination controls.
            self.display_page_controls = True

        self.request = request
        return list(self.page)

    def get_paginated_response(self, data, message="Data fetched successfully."):
        return Response({
            'status': True,
            'message': message,
            'data': {
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.get_page_size(self.request),  # Fixed: use actual page size
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'results': data
            }
        }, status=status.HTTP_200_OK)

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'status': {
                    'type': 'boolean',
                    'example': True
                },
                'message': {
                    'type': 'string',
                    'example': 'Data fetched successfully.'
                },
                'data': {
                    'type': 'object',
                    'properties': {
                        'count': {
                            'type': 'integer',
                            'example': 100
                        },
                        'total_pages': {
                            'type': 'integer',
                            'example': 10
                        },
                        'current_page': {
                            'type': 'integer',
                            'example': 1
                        },
                        'page_size': {
                            'type': 'integer',
                            'example': 10
                        },
                        'next': {
                            'type': 'string',
                            'nullable': True,
                            'example': 'http://api.example.org/accounts/?page=2'
                        },
                        'previous': {
                            'type': 'string',
                            'nullable': True,
                            'example': None
                        },
                        'results': schema
                    }
                }
            }
        }