"""Testes de caracterização dos fluxos de ponta a ponta.

Estes testes afirmam o que a API faz **hoje**, incluindo formatos de resposta. Eles não
julgam se o comportamento é bom — existem para que qualquer mudança de comportamento
durante a revitalização apareça como um teste vermelho, e não como uma descoberta em
produção.

Quando uma correção mudar um contrato de propósito, o teste correspondente muda junto,
no mesmo commit, e o diff mostra exatamente o que o cliente vai notar.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


# ─── Registro e autenticação ────────────────────────────────────────────────────


def test_registro_cria_usuario_e_devolve_201(api):
    resposta = api.post(
        reverse("register"),
        {
            "username": "novousuario",
            "name": "Novo Usuário",
            "password": "SenhaForte123!",
            "confirm_password": "SenhaForte123!",
        },
        format="json",
    )

    assert resposta.status_code == 201
    assert resposta.data["username"] == "novousuario"
    # O avatar padrão é atribuído no create() do serializer, não pelo cliente.
    assert resposta.data["avatar_url"]
    # `tokens` evita a segunda ida a /token/ e o segundo hash de senha que o cadastro
    # pagava: o access token devolvido aqui já autentica, sem precisar logar de novo.
    assert resposta.data["tokens"]["access"]
    assert resposta.data["tokens"]["refresh"]

    autenticado = api.get(
        reverse("profile"), HTTP_AUTHORIZATION=f"Bearer {resposta.data['tokens']['access']}"
    )
    assert autenticado.status_code == 200
    assert autenticado.data["username"] == "novousuario"


def test_registro_recusa_senhas_diferentes(api):
    resposta = api.post(
        reverse("register"),
        {
            "username": "outro",
            "name": "Outro",
            "password": "SenhaForte123!",
            "confirm_password": "OutraSenha456!",
        },
        format="json",
    )

    assert resposta.status_code == 400


def test_login_devolve_access_token(api, make_user):
    make_user(username="login_ok", password="SenhaForte123!")

    resposta = api.post(
        reverse("token_obtain_pair"),
        {"username": "login_ok", "password": "SenhaForte123!"},
        format="json",
    )

    assert resposta.status_code == 200
    assert "access" in resposta.data


def test_login_com_senha_errada_devolve_401(api, make_user):
    make_user(username="login_falha", password="SenhaForte123!")

    resposta = api.post(
        reverse("token_obtain_pair"),
        {"username": "login_falha", "password": "SenhaErrada000!"},
        format="json",
    )

    assert resposta.status_code == 401


# ─── Perfil ─────────────────────────────────────────────────────────────────────


def test_perfil_exige_autenticacao(api):
    assert api.get(reverse("profile")).status_code == 401


def test_perfil_devolve_o_usuario_da_credencial(auth, user):
    resposta = auth.get(reverse("profile"))

    assert resposta.status_code == 200
    assert resposta.data["username"] == user.username
    # Contadores fazem parte do contrato que o frontend consome.
    for campo in ("followers_count", "following_count", "posts_count", "is_following"):
        assert campo in resposta.data


def test_perfil_atualiza_nome(auth, user):
    resposta = auth.patch(reverse("profile"), {"name": "Nome Novo"}, format="multipart")

    assert resposta.status_code == 200
    user.refresh_from_db()
    assert user.name == "Nome Novo"


# ─── Posts ──────────────────────────────────────────────────────────────────────


def test_criar_post_associa_ao_usuario_autenticado(auth, user):
    resposta = auth.post(reverse("post-list-create"), {"text": "Olá mundo"}, format="json")

    assert resposta.status_code == 201
    assert resposta.data["user"]["username"] == user.username
    assert resposta.data["text"] == "Olá mundo"


def test_listagem_de_posts_vem_paginada(auth, user, make_post):
    make_post(user)

    resposta = auth.get(reverse("post-list-create"))

    assert resposta.status_code == 200
    # O envelope de paginação do DRF é o que o frontend desempacota.
    assert set(resposta.data) >= {"count", "next", "previous", "results"}


def test_feed_traz_posts_de_quem_sigo_e_os_meus(auth, user, make_user, make_post, make_follow):
    seguido = make_user()
    estranho = make_user()
    make_follow(follower=user, following=seguido)
    make_post(user, text="meu post")
    make_post(seguido, text="post de quem eu sigo")
    make_post(estranho, text="post de estranho")

    resposta = auth.get(reverse("following-posts"))

    textos = [item["text"] for item in resposta.data["results"]]
    assert "meu post" in textos
    assert "post de quem eu sigo" in textos
    assert "post de estranho" not in textos


def test_feed_ordena_do_mais_recente_para_o_mais_antigo(auth, user, make_post):
    make_post(user, text="primeiro")
    make_post(user, text="segundo")

    resposta = auth.get(reverse("following-posts"))

    textos = [item["text"] for item in resposta.data["results"]]
    assert textos == ["segundo", "primeiro"]


def test_posts_de_um_usuario_sao_publicos(api, user, make_post):
    make_post(user, text="post publico")

    resposta = api.get(reverse("user-posts", kwargs={"username": user.username}))

    assert resposta.status_code == 200
    assert resposta.data["results"][0]["text"] == "post publico"


# ─── Curtidas ───────────────────────────────────────────────────────────────────


def test_curtir_e_descurtir_alternam_no_mesmo_endpoint(auth, user, make_post):
    post = make_post(user)
    url = reverse("like-post", kwargs={"pk": post.pk})

    primeira = auth.post(url)
    assert primeira.status_code == 200
    assert post.likes.count() == 1

    segunda = auth.post(url)
    assert segunda.status_code == 200
    assert post.likes.count() == 0


def test_is_liked_reflete_a_curtida_de_quem_pergunta(auth, user, make_post, make_like):
    post = make_post(user)
    make_like(user=user, post=post)

    resposta = auth.get(reverse("following-posts"))

    assert resposta.data["results"][0]["is_liked"] is True
    assert resposta.data["results"][0]["likes_count"] == 1


# ─── Comentários ────────────────────────────────────────────────────────────────


def test_comentar_associa_post_e_autor(auth, user, make_post):
    post = make_post(user)

    resposta = auth.post(
        reverse("comment-post", kwargs={"pk": post.pk}),
        {"text": "Belo post"},
        format="json",
    )

    assert resposta.status_code == 201
    assert resposta.data["user"]["username"] == user.username
    assert resposta.data["post"] == post.pk
    assert post.comments.count() == 1


# ─── Seguir ─────────────────────────────────────────────────────────────────────


def test_seguir_devolve_201_e_deixar_de_seguir_devolve_200(auth, user, make_user):
    alvo = make_user()
    url = reverse("follow-toggle", kwargs={"user_id": alvo.id})

    seguir = auth.post(url)
    assert seguir.status_code == 201
    assert seguir.data["is_following"] is True

    parar = auth.post(url)
    assert parar.status_code == 200
    assert parar.data["is_following"] is False


def test_nao_e_possivel_seguir_a_si_mesmo(auth, user):
    resposta = auth.post(reverse("follow-toggle", kwargs={"user_id": user.id}))

    assert resposta.status_code == 400


def test_listas_de_seguidores_e_seguindo_sao_paginadas(api, make_user, make_follow):
    alvo = make_user()
    seguidor = make_user()
    make_follow(follower=seguidor, following=alvo)

    seguidores = api.get(reverse("followers-list", kwargs={"user_id": alvo.id}))
    assert seguidores.status_code == 200
    assert seguidores.data["count"] == 1
    assert seguidores.data["results"][0]["username"] == seguidor.username

    seguindo = api.get(reverse("following-list", kwargs={"user_id": seguidor.id}))
    assert seguindo.data["count"] == 1
    assert seguindo.data["results"][0]["username"] == alvo.username


# ─── Listagem de usuários ───────────────────────────────────────────────────────


def test_listagem_de_usuarios_exclui_a_si_mesmo_e_administradores(auth, user, make_user):
    make_user(username="comum")
    make_user(username="staff", is_staff=True)

    resposta = auth.get(reverse("user-list"))

    usernames = [item["username"] for item in resposta.data["results"]]
    assert "comum" in usernames
    assert user.username not in usernames
    assert "staff" not in usernames
