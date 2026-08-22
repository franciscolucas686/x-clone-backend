"""O contrato de erro da API.

Estes testes existem para que o `code` seja tratado como interface pública. Um code que
muda sem que este arquivo mude é uma quebra de contrato com o frontend, que traduz por
código em `shared/api/error-code-map.ts`.

Afirmam o código, nunca a frase: era exatamente a dependência da frase — o
`translateError()` procurando `"too short"` e `"already exists"` dentro do texto em
inglês do Django — que este contrato substitui.
"""

import pytest
from django.urls import reverse

from common import errors

pytestmark = pytest.mark.django_db

ENVELOPE = {"code", "message", "details", "status_code", "path"}


class TestEnvelope:
    def test_todo_erro_sai_no_mesmo_formato(self, api):
        """Antes cada erro tinha uma forma: {"detail"}, {"campo": [...]}, {"message"}."""
        resposta = api.get(reverse("profile"))

        assert resposta.status_code == 401
        assert set(resposta.data) == ENVELOPE
        assert resposta.data["path"] == reverse("profile")
        assert resposta.data["status_code"] == 401

    def test_erro_de_validacao_preserva_os_campos(self, api):
        """`details` é o que permite ao formulário destacar o campo errado.

        O handler antigo do frontend descartava tudo menos `messages[0]`, então um erro
        em três campos aparecia como um só.
        """
        resposta = api.post(
            reverse("register"),
            {"username": "", "name": "", "password": "x", "confirm_password": "y"},
            format="json",
        )

        assert resposta.data["code"] == "VALIDATION_ERROR"
        assert "username" in resposta.data["details"]


class TestCodigosEstaveis:
    """Cada caso: uma situação real -> o código que o frontend recebe."""

    def test_senha_errada_no_login(self, api, make_user):
        make_user(username="alguem", password="SenhaCerta123!")

        resposta = api.post(
            reverse("token_obtain_pair"),
            {"username": "alguem", "password": "SenhaErrada000!"},
            format="json",
        )

        # O simplejwt chama isto de "no_active_account" e responde com uma frase em
        # inglês. Traduzido para um código nosso, o frontend deixa de depender da frase.
        assert resposta.data["code"] == "INVALID_CREDENTIALS"

    def test_token_expirado(self, api, user):
        from datetime import timedelta

        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken.for_user(user)
        token.set_exp(lifetime=timedelta(seconds=-1))
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resposta = api.get(reverse("profile"))

        # Distinto de INVALID_CREDENTIALS de propósito: um manda renovar a sessão, o
        # outro manda conferir a senha.
        assert resposta.data["code"] == "TOKEN_NOT_VALID"

    def test_sem_credencial(self, api):
        assert api.get(reverse("profile")).data["code"] == "AUTHENTICATION_REQUIRED"

    def test_post_inexistente(self, auth):
        resposta = auth.post(reverse("like-post", kwargs={"pk": 999_999}))
        assert resposta.data["code"] == "POST_NOT_FOUND"

    def test_seguir_a_si_mesmo(self, auth, user):
        resposta = auth.post(reverse("follow-toggle", kwargs={"user_id": user.id}))
        assert resposta.data["code"] == "CANNOT_FOLLOW_SELF"

    def test_seguir_usuario_inexistente(self, auth):
        resposta = auth.post(reverse("follow-toggle", kwargs={"user_id": 999_999}))
        assert resposta.data["code"] == "USER_NOT_FOUND"

    def test_username_duplicado(self, api, make_user):
        make_user(username="repetido")

        resposta = api.post(
            reverse("register"),
            {
                "username": "repetido",
                "name": "Outro",
                "password": "SenhaForte123!",
                "confirm_password": "SenhaForte123!",
            },
            format="json",
        )

        assert resposta.data["code"] == "USERNAME_ALREADY_EXISTS"


# Tabela de status + code de toda classe de erro de domínio. É o mesmo papel do
# `domain-error-codes.spec.ts` do api-real-estate: pinar os dois valores para que
# mudá-los seja uma decisão visível no diff, e não um efeito colateral.
CASOS_DE_ERRO = [
    (errors.InvalidCredentials, 401, "INVALID_CREDENTIALS"),
    (errors.UsernameAlreadyExists, 409, "USERNAME_ALREADY_EXISTS"),
    (errors.PasswordMismatch, 400, "PASSWORD_MISMATCH"),
    (errors.UserNotFound, 404, "USER_NOT_FOUND"),
    (errors.PostNotFound, 404, "POST_NOT_FOUND"),
    (errors.CannotFollowSelf, 400, "CANNOT_FOLLOW_SELF"),
    (errors.StorageNotConfigured, 503, "STORAGE_NOT_CONFIGURED"),
    (errors.AvatarUploadFailed, 503, "AVATAR_UPLOAD_FAILED"),
    (errors.UnsupportedMediaType, 415, "UNSUPPORTED_MEDIA_TYPE"),
    (errors.FileTooLarge, 413, "FILE_TOO_LARGE"),
]


@pytest.mark.parametrize(("classe", "status_esperado", "code_esperado"), CASOS_DE_ERRO)
def test_status_e_code_de_cada_erro_de_dominio(classe, status_esperado, code_esperado):
    instancia = classe()

    assert instancia.status_code == status_esperado
    assert instancia.code == code_esperado


def test_todo_erro_de_dominio_esta_na_tabela():
    """Impede que um erro novo entre sem ter status e code fixados aqui."""
    declarados = {
        obj
        for obj in vars(errors).values()
        if isinstance(obj, type)
        and issubclass(obj, errors.DomainError)
        and obj is not errors.DomainError
    }
    na_tabela = {classe for classe, _, _ in CASOS_DE_ERRO}

    assert declarados == na_tabela


class TestMontagemDaAPI:
    """As rotas respondem tanto em /api/v1/ quanto no caminho antigo.

    Backend e frontend têm deploys independentes (Render e Vercel): um subir antes do
    outro não pode derrubar o app. Os aliases saem num commit próprio, quando os dois
    lados estiverem em v1.
    """

    def test_v1_e_alias_respondem_a_mesma_coisa(self, auth, user, make_post):
        make_post(user, text="post de teste")

        v1 = auth.get("/api/v1/posts/")
        alias = auth.get("/api/posts/")

        assert v1.status_code == alias.status_code == 200
        assert v1.data["results"][0]["text"] == alias.data["results"][0]["text"]

    def test_rota_redundante_de_posts_do_usuario_tem_caminho_canonico(self, api, user, make_post):
        """Era /api/posts/user/<username>/posts/ — "posts" duas vezes, e um recurso de
        usuário sob o prefixo de posts."""
        make_post(user, text="post publico")

        canonica = api.get(f"/api/v1/users/{user.username}/posts/")
        legada = api.get(f"/api/posts/user/{user.username}/posts/")

        assert canonica.status_code == 200
        assert legada.status_code == 200

    def test_documentacao_da_api_e_gerada_do_codigo(self, api):
        resposta = api.get("/api/schema/")

        assert resposta.status_code == 200
