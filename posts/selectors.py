"""Consultas de posts."""

from django.db.models import BooleanField, Exists, OuterRef, Q, QuerySet, Value

from common.selectors import count_of
from followers.models import Follow

from .models import Comment, Like, Post


def posts_with_stats(*, viewer=None) -> QuerySet[Post]:
    """Posts com likes_count, comments_count e is_liked anotados.

    `is_liked` era um `Like.objects.filter(...).exists()` por post dentro do serializer —
    uma query por item da página, apesar de `likes` já estar no prefetch.

    As contagens vinham do cache do prefetch e não custavam nada; agora saem anotadas
    porque o prefetch de `comments` foi removido junto com o campo aninhado (os
    comentários têm endpoint próprio e paginado). Sem a anotação, `comments_count`
    voltaria a ser uma query por post.
    """
    if viewer is not None and viewer.is_authenticated:
        is_liked = Exists(Like.objects.filter(user=viewer, post=OuterRef("pk")))
    else:
        is_liked = Value(False, output_field=BooleanField())

    return (
        Post.objects.select_related("user").annotate(
            likes_count=count_of(Like.objects, matching={"post": OuterRef("pk")}),
            comments_count=count_of(Comment.objects, matching={"post": OuterRef("pk")}),
            is_liked=is_liked,
        )
        # A ordenação vem de Post.Meta.ordering; repeti-la aqui só criaria um segundo
        # lugar para mantê-la.
    )


def feed_for(user) -> QuerySet[Post]:
    """Posts de quem o usuário segue, mais os dele.

    `values_list` mantido lazy de propósito: o Django o compila como subquery na mesma
    consulta, em vez de fazer uma ida ao banco para buscar os ids e outra para os posts.
    """
    seguidos = Follow.objects.filter(follower=user).values_list("following", flat=True)
    return posts_with_stats(viewer=user).filter(Q(user__in=seguidos) | Q(user=user))


def posts_by_username(username: str, *, viewer=None) -> QuerySet[Post]:
    return posts_with_stats(viewer=viewer).filter(user__username=username)


def comments_of(post_id: int) -> QuerySet[Comment]:
    return Comment.objects.filter(post_id=post_id).select_related("user")
