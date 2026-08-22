"""Quem pode acessar o quê.

`REST_FRAMEWORK` não definia `DEFAULT_PERMISSION_CLASSES`, e o default do DRF é AllowAny:
uma view nova que esquecesse de declarar `permission_classes` nascia **pública**. Todas as
views existentes declaravam, mas a postura era de falha aberta — o pior default possível
para segurança.

Com o default fail-closed, estes testes fixam as quatro rotas que são públicas **de
propósito**, para que essa escolha continue sendo deliberada.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


ROTAS_PRIVADAS = [
    ("get", "profile", {}),
    ("get", "user-list", {}),
    ("get", "following-posts", {}),
    ("get", "post-list-create", {}),
]


@pytest.mark.parametrize(("metodo", "nome", "kwargs"), ROTAS_PRIVADAS)
def test_rota_privada_recusa_anonimo(api, metodo, nome, kwargs):
    resposta = getattr(api, metodo)(reverse(nome, kwargs=kwargs))

    assert resposta.status_code == 401
    assert resposta.data["code"] == "AUTHENTICATION_REQUIRED"


class TestRotasPublicasDeProposito:
    """Perfis e timelines são públicos por decisão de produto — é uma rede social."""

    def test_timeline_de_um_usuario(self, api, user, make_post):
        make_post(user)
        assert api.get(reverse("user-posts", kwargs={"username": user.username})).status_code == 200

    def test_lista_de_seguidores(self, api, user):
        assert api.get(reverse("followers-list", kwargs={"user_id": user.id})).status_code == 200

    def test_lista_de_seguindo(self, api, user):
        assert api.get(reverse("following-list", kwargs={"user_id": user.id})).status_code == 200

    def test_leitura_de_comentarios(self, api, user, make_post):
        post = make_post(user)
        assert api.get(reverse("post-comments", kwargs={"pk": post.pk})).status_code == 200

    def test_mas_comentar_exige_conta(self, api, user, make_post):
        post = make_post(user)

        resposta = api.post(
            reverse("post-comments", kwargs={"pk": post.pk}), {"text": "oi"}, format="json"
        )

        assert resposta.status_code == 401

    def test_e_o_anonimo_nunca_ve_is_liked_verdadeiro(self, api, user, make_post, make_like):
        post = make_post(user)
        make_like(user=user, post=post)

        resposta = api.get(reverse("user-posts", kwargs={"username": user.username}))

        # Sem sessão não há "eu curti": o selector anota False constante em vez de
        # deixar o campo indefinido.
        assert resposta.data["results"][0]["is_liked"] is False
        assert resposta.data["results"][0]["likes_count"] == 1


class TestHealthz:
    """Alvo do keep-alive externo (UptimeRobot). Precisa ser público, barato e não
    tocar o banco — é chamado a cada 5 minutos, 24h por dia, para o serviço não dormir
    no Render gratuito."""

    def test_publico_e_nao_precisa_de_autenticacao(self, api):
        assert api.get("/healthz/").status_code == 200

    def test_nao_toca_o_banco(self, api, django_assert_num_queries):
        with django_assert_num_queries(0):
            api.get("/healthz/")

    def test_recusa_metodos_que_nao_sao_get(self, api):
        assert api.post("/healthz/").status_code == 405
