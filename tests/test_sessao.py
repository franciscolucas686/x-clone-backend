"""Ciclo de vida da sessão: renovação, rotação e limite de tentativas."""

import pytest
from django.core.cache import cache
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpa_o_balde_do_throttle():
    """O throttle guarda o histórico no cache, que sobrevive entre testes."""
    cache.clear()
    yield
    cache.clear()


def _login(api, username, password="SenhaForte123!"):
    return api.post(
        reverse("token_obtain_pair"), {"username": username, "password": password}, format="json"
    )


class TestRenovacaoDeSessao:
    """`REFRESH_TOKEN_LIFETIME` era `timedelta(seconds=0)`: o refresh nascia expirado e
    não havia rota para usá-lo. Passadas 6 horas o usuário era desconectado no meio do
    que estava fazendo, sem aviso."""

    def test_login_devolve_um_refresh_utilizavel(self, api, make_user):
        make_user(username="ana")

        entrada = _login(api, "ana")

        assert entrada.data["refresh"]

    def test_refresh_devolve_um_access_novo(self, api, make_user):
        make_user(username="ana")
        refresh = _login(api, "ana").data["refresh"]

        renovacao = api.post(reverse("token_refresh"), {"refresh": refresh}, format="json")

        assert renovacao.status_code == 200
        assert renovacao.data["access"]

    def test_refresh_usado_duas_vezes_e_recusado(self, api, make_user):
        """ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION: um refresh vazado só serve
        até o dono usar o dele."""
        make_user(username="ana")
        refresh = _login(api, "ana").data["refresh"]

        primeira = api.post(reverse("token_refresh"), {"refresh": refresh}, format="json")
        segunda = api.post(reverse("token_refresh"), {"refresh": refresh}, format="json")

        assert primeira.status_code == 200
        assert segunda.status_code == 401
        assert segunda.data["code"] == "TOKEN_NOT_VALID"

    def test_access_token_renovado_funciona(self, api, make_user):
        make_user(username="ana")
        refresh = _login(api, "ana").data["refresh"]
        novo_access = api.post(reverse("token_refresh"), {"refresh": refresh}, format="json").data[
            "access"
        ]

        api.credentials(HTTP_AUTHORIZATION=f"Bearer {novo_access}")
        perfil = api.get(reverse("profile"))

        assert perfil.status_code == 200
        assert perfil.data["username"] == "ana"


class TestLimiteDeTentativas:
    def test_forca_bruta_no_login_e_barrada(self, api, make_user):
        """Sem limite, tentar senha por força bruta contra /token/ não tem custo."""
        make_user(username="ana")

        respostas = [_login(api, "ana", password="ErradaDeProposito1!") for _ in range(12)]
        codes = [r.data.get("code") for r in respostas]

        assert "TOO_MANY_REQUESTS" in codes
        assert respostas[-1].status_code == 429

    def test_cadastro_em_massa_e_barrado(self, api):
        respostas = [
            api.post(
                reverse("register"),
                {
                    "username": f"massa{i}",
                    "name": "Massa",
                    "password": "SenhaForte123!",
                    "confirm_password": "SenhaForte123!",
                },
                format="json",
            )
            for i in range(12)
        ]

        assert respostas[-1].status_code == 429
        assert respostas[-1].data["code"] == "TOO_MANY_REQUESTS"
