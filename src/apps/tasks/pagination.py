from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Стандартна пагінація сторінок з підтримкою query-параметрів ?page= та ?page_size=."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
