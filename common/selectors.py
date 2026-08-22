"""Blocos de consulta reaproveitados pelos selectors de cada app."""

from django.db.models import Count, IntegerField, QuerySet, Subquery
from django.db.models.functions import Coalesce


def count_of(queryset: QuerySet, *, matching: dict) -> Coalesce:
    """Contagem de uma relação como subquery correlacionada.

    Alternativa a `Count("relacao", distinct=True)` dentro de `annotate()`: com três
    contagens sobre relações reversas diferentes — posts, seguidores e seguindo — o
    Django emite três LEFT JOINs e materializa o produto cartesiano entre eles.
    `distinct=True` corrige o número, mas não o tamanho do resultado intermediário.

    A subquery devolve um valor por linha, sem join nenhum, e o `Coalesce` garante 0 em
    vez de NULL para quem não tem nenhum registro relacionado — o serializer espera um
    inteiro.

    Uso:
        count_of(Post.objects, matching={"user": OuterRef("pk")})
    """
    campo_de_agrupamento = next(iter(matching))
    return Coalesce(
        Subquery(
            queryset.filter(**matching)
            .values(campo_de_agrupamento)
            .annotate(total=Count("pk"))
            .values("total"),
            output_field=IntegerField(),
        ),
        0,
    )
