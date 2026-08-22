"""Custo em queries das listagens.

`assertNumQueries` transforma performance em contrato: um N+1 reintroduzido vira um teste
vermelho com o número exato, e não uma lentidão que alguém nota meses depois em produção.

O padrão que estes testes protegem: contagens e flags calculadas por
`SerializerMethodField` disparam uma query por objeto serializado. Numa página de 10
usuários, os quatro method fields de UserProfileSerializer custavam ~40 queries.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_listagem_de_usuarios_nao_cresce_com_o_numero_de_usuarios(
    auth, user, make_user, make_follow, make_post, django_assert_num_queries
):
    """O custo tem que ser o mesmo para 1 e para 8 usuários na página."""
    outros = [make_user() for _ in range(8)]
    for outro in outros[:4]:
        make_follow(follower=user, following=outro)
        make_post(outro)

    with django_assert_num_queries(2):
        # Uma contagem da paginação e uma da página. Só isso: as três contagens
        # (posts, seguidores, seguindo) e o is_following saem anotados na própria
        # query da página. Antes eram 34 para estes mesmos 8 usuários.
        resposta = auth.get(reverse("user-list"))

    assert len(resposta.data["results"]) == 8


def test_feed_nao_cresce_com_o_numero_de_posts(
    auth, user, make_user, make_post, make_like, django_assert_num_queries
):
    autor = make_user()
    from followers.models import Follow

    Follow.objects.create(follower=user, following=autor)
    for _ in range(8):
        post = make_post(autor)
        make_like(user=user, post=post)

    with django_assert_num_queries(2):
        # Antes eram 12 para estes mesmos 8 posts: um EXISTS por post para o
        # `is_liked`, além dos prefetches de likes e comentários. Hoje `is_liked` e as
        # duas contagens são anotações, e os comentários não vêm mais aninhados.
        resposta = auth.get(reverse("following-posts"))

    assert len(resposta.data["results"]) == 8
    assert all(item["is_liked"] for item in resposta.data["results"])


def test_lista_de_seguidores_nao_cresce_com_o_numero_de_seguidores(
    api, make_user, make_follow, django_assert_num_queries
):
    alvo = make_user()
    for _ in range(8):
        make_follow(follower=make_user(), following=alvo)

    with django_assert_num_queries(2):
        resposta = api.get(reverse("followers-list", kwargs={"user_id": alvo.id}))

    assert resposta.data["count"] == 8
