from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Стандартная пагинация страниц с поддержкой query-параметра ?page= и ?page_size=."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
