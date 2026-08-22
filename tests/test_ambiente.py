"""Validação das variáveis de ambiente.

A aplicação precisa se recusar a subir mal configurada. `SECRET_KEY` tinha o default
literal `"unsafe-default-key"`, versionado no repositório: sem a variável, produção subia
assinando os JWT com uma chave pública, e nada nos logs indicava isso.

Os testes exercitam `backend/settings/env.py` diretamente, sem importar as settings de
produção — importá-las teria efeito colateral no processo de teste.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured

from backend.settings import env


class TestVariavelObrigatoria:
    def test_ausente_aborta_nomeando_a_variavel(self, monkeypatch):
        monkeypatch.delenv("VARIAVEL_INEXISTENTE", raising=False)

        with pytest.raises(ImproperlyConfigured, match="VARIAVEL_INEXISTENTE"):
            env.require("VARIAVEL_INEXISTENTE")

    def test_string_vazia_conta_como_ausente(self, monkeypatch):
        """Num arquivo .env não há como escrever "indefinido": quem quer deixar a
        variável de fora apaga a linha ou escreve `VAR=`. Os dois precisam significar a
        mesma coisa, senão um `VAR=` reprova numa validação logo abaixo de um comentário
        mandando deixá-la vazia."""
        monkeypatch.setenv("VARIAVEL_VAZIA", "   ")

        with pytest.raises(ImproperlyConfigured, match="VARIAVEL_VAZIA"):
            env.require("VARIAVEL_VAZIA")

    def test_presente_e_devolvida(self, monkeypatch):
        monkeypatch.setenv("VARIAVEL_OK", "valor")

        assert env.require("VARIAVEL_OK") == "valor"


class TestTamanhoMinimo:
    def test_segredo_curto_e_recusado_com_instrucao(self, monkeypatch):
        monkeypatch.setenv("SEGREDO", "curto")

        with pytest.raises(ImproperlyConfigured) as excecao:
            env.require("SEGREDO", min_length=env.MIN_SECRET_KEY_LENGTH)

        mensagem = str(excecao.value)
        assert "50 caracteres" in mensagem
        # A mensagem ensina a gerar uma chave válida, em vez de só reprovar.
        assert "get_random_secret_key" in mensagem

    def test_segredo_do_tamanho_certo_passa(self, monkeypatch):
        monkeypatch.setenv("SEGREDO", "x" * env.MIN_SECRET_KEY_LENGTH)

        assert env.require("SEGREDO", min_length=env.MIN_SECRET_KEY_LENGTH)


class TestLista:
    def test_lista_vazia_e_recusada(self, monkeypatch):
        monkeypatch.setenv("ORIGENS", " , , ")

        with pytest.raises(ImproperlyConfigured, match="ORIGENS"):
            env.require_list("ORIGENS")

    def test_lista_e_separada_por_virgula_ignorando_espacos(self, monkeypatch):
        monkeypatch.setenv("ORIGENS", "https://a.com, https://b.com ")

        assert env.require_list("ORIGENS") == ["https://a.com", "https://b.com"]


class TestBooleano:
    @pytest.mark.parametrize("valor", ["true", "TRUE", "1", "yes", "on"])
    def test_valores_verdadeiros(self, monkeypatch, valor):
        monkeypatch.setenv("FLAG", valor)
        assert env.get_bool("FLAG") is True

    @pytest.mark.parametrize("valor", ["false", "0", "no", ""])
    def test_valores_falsos(self, monkeypatch, valor):
        monkeypatch.setenv("FLAG", valor)
        assert env.get_bool("FLAG") is False

    def test_ausente_usa_o_default(self, monkeypatch):
        monkeypatch.delenv("FLAG", raising=False)
        assert env.get_bool("FLAG", default=True) is True


class TestConfiguracaoDoBanco:
    """`DATABASE_URL` é o formato que todo Postgres gerenciado entrega.

    Aceitar só as quatro variáveis separadas fazia o caminho óbvio — copiar a string do
    painel do Neon ou do Render e colar — abortar o boot pedindo `DATABASE_NAME`.
    """

    def test_url_completa_e_quebrada_nos_campos_do_django(self):
        config = env.parse_database_url(
            "postgresql://usuario:senha@ep-teste.us-east-2.aws.neon.tech:5432/meubanco"
        )

        assert config["NAME"] == "meubanco"
        assert config["USER"] == "usuario"
        assert config["PASSWORD"] == "senha"
        assert config["HOST"] == "ep-teste.us-east-2.aws.neon.tech"
        assert config["PORT"] == "5432"

    def test_senha_percent_encoded_e_decodificada(self):
        """Senhas geradas por painel trazem `@`, `/` e `#` escapados. Passá-las
        codificadas adiante faz a autenticação falhar com "senha incorreta" — o erro que
        menos aponta para a causa."""
        config = env.parse_database_url("postgresql://user:p%40ss%2Fword@host:5432/banco")

        assert config["PASSWORD"] == "p@ss/word"

    def test_sslmode_da_url_vence_o_default(self):
        config = env.parse_database_url("postgresql://u:p@host/banco?sslmode=verify-full")

        assert config["OPTIONS"]["sslmode"] == "verify-full"

    def test_sem_sslmode_na_url_usa_require(self):
        """Todo Postgres gerenciado exige TLS. O default do driver é `prefer`, que cai
        para texto puro em silêncio se o TLS falhar."""
        config = env.parse_database_url("postgresql://u:p@host/banco")

        assert config["OPTIONS"]["sslmode"] == env.DEFAULT_SSLMODE == "require"

    def test_porta_ausente_cai_para_5432(self):
        assert env.parse_database_url("postgresql://u:p@host/banco")["PORT"] == "5432"

    def test_esquema_invalido_e_recusado(self):
        with pytest.raises(ImproperlyConfigured, match="postgres"):
            env.parse_database_url("mysql://u:p@host/banco")

    def test_url_sem_nome_de_banco_e_recusada(self):
        with pytest.raises(ImproperlyConfigured, match="nome do banco"):
            env.parse_database_url("postgresql://u:p@host")

    def test_database_url_tem_precedencia_sobre_as_variaveis_separadas(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host-da-url/banco-da-url")
        monkeypatch.setenv("DATABASE_NAME", "banco-separado")

        assert env.database_config(required=True)["NAME"] == "banco-da-url"

    def test_sem_url_usa_as_variaveis_separadas(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        for chave, valor in {
            "DATABASE_NAME": "banco",
            "DATABASE_USER": "u",
            "DATABASE_PASSWORD": "p",
            "DATABASE_HOST": "h",
        }.items():
            monkeypatch.setenv(chave, valor)

        config = env.database_config(required=True)

        assert config["NAME"] == "banco"
        assert config["HOST"] == "h"

    def test_em_producao_a_ausencia_das_duas_formas_aborta(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        for chave in ("DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD", "DATABASE_HOST"):
            monkeypatch.delenv(chave, raising=False)

        with pytest.raises(ImproperlyConfigured, match="DATABASE_NAME"):
            env.database_config(required=True)
