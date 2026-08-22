from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Paginação padrão de todas as listagens.

    Vivia em `backend/settings/pagination.py` — código de aplicação dentro do pacote de
    settings. E o `PAGE_SIZE: 20` que estava em REST_FRAMEWORK era configuração morta: o
    atributo de classe abaixo tem precedência, então o valor efetivo sempre foi 10.
    Dois números, um deles engano.
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50
