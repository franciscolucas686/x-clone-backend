"""Consultas de usuário.

Existe para que as contagens e o `is_following` saiam **anotados** na mesma query da
listagem. Antes eram quatro `SerializerMethodField`, cada um com sua própria query por
objeto serializado: uma página de 10 usuários custava ~40 queries além da própria página.

Pior: `UserListView` já anotava `is_following` com `Exists()`, mas um
`SerializerMethodField` declarado com o mesmo nome sombreia a anotação — o banco fazia o
EXISTS e o serializer refazia a consulta. Custo pago duas vezes e aproveitado nenhuma.
"""

from django.db.models import BooleanField, Exists, OuterRef, Q, QuerySet, Value

from common.selectors import count_of
from followers.models import Follow
from posts.models import Post

from .models import User


def users_with_stats(*, viewer=None) -> QuerySet[User]:
    """Usuários com posts_count, followers_count, following_count e is_following."""
    if viewer is not None and viewer.is_authenticated:
        is_following = Exists(Follow.objects.filter(follower=viewer, following=OuterRef("pk")))
    else:
        # Anônimo não segue ninguém. Anotado como constante para que o serializer leia
        # sempre do mesmo lugar, em vez de ter um ramo para cada caso.
        is_following = Value(False, output_field=BooleanField())

    return User.objects.annotate(
        posts_count=count_of(Post.objects, matching={"user": OuterRef("pk")}),
        followers_count=count_of(Follow.objects, matching={"following": OuterRef("pk")}),
        following_count=count_of(Follow.objects, matching={"follower": OuterRef("pk")}),
        is_following=is_following,
    )


def discoverable_users(*, viewer, search: str = "") -> QuerySet[User]:
    """Usuários que aparecem na busca: exclui o próprio e as contas administrativas.

    O filtro por texto acontece **aqui**, no banco. O ExplorerPage filtrava no cliente,
    sobre a lista já carregada — e como a página tem 10 itens, buscar significava
    procurar entre os 10 primeiros usuários do sistema, nunca entre todos.
    """
    queryset = (
        users_with_stats(viewer=viewer)
        .exclude(pk=viewer.pk)
        .exclude(is_superuser=True)
        .exclude(is_staff=True)
        # Ordenação explícita: sem ela o DRF avisa (UnorderedObjectListWarning) e as
        # páginas ficam não-determinísticas — um usuário podia aparecer duas vezes ou
        # sumir entre a página 1 e a 2.
        .order_by("username")
    )

    if search:
        termo = search.strip()
        if termo:
            queryset = queryset.filter(Q(username__icontains=termo) | Q(name__icontains=termo))

    return queryset


def followers_of(user_id: int, *, viewer=None) -> QuerySet[User]:
    return (
        users_with_stats(viewer=viewer)
        .filter(following__following=user_id)
        .distinct()
        .order_by("id")
    )


def following_of(user_id: int, *, viewer=None) -> QuerySet[User]:
    return (
        users_with_stats(viewer=viewer)
        .filter(followers__follower=user_id)
        .distinct()
        .order_by("id")
    )
