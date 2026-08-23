"""Testes de regressão: cada um fixa uma falha concreta que já existiu.

O nome do teste descreve a regra; o comentário descreve o defeito que ele impede de
voltar. Sem isso, um teste que passa não conta a ninguém por que foi escrito.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_curtir_post_inexistente_devolve_404_e_nao_500(auth):
    """`Post.objects.get()` levantava DoesNotExist, que escapa do DRF e vira 500.

    Curtir um post recém-apagado é rotina num feed; um 500 aí é indistinguível de falha
    real do servidor.
    """
    resposta = auth.post(reverse("like-post", kwargs={"pk": 999_999}))

    assert resposta.status_code == 404


def test_comentar_post_inexistente_devolve_404_e_nao_500(auth):
    resposta = auth.post(
        reverse("comment-post", kwargs={"pk": 999_999}),
        {"text": "comentário órfão"},
        format="json",
    )

    assert resposta.status_code == 404


class TestGuardasDoSeed:
    """`entrypoint.prod.sh` rodava `python seed_data.py` a cada boot de produção, e o
    `run()` daquele script começava com `reset_database()` — `User.objects.all().delete()`
    incluído. Todo deploy apagava os dados reais.

    As duas guardas abaixo são independentes de propósito: uma protege contra o ambiente
    errado, a outra contra a execução não intencional no ambiente certo.
    """

    def test_recusa_rodar_com_settings_de_producao(self, monkeypatch, make_user):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        monkeypatch.setattr("common.env_flags.settings_module_is_production", lambda: True)
        monkeypatch.setenv("RUN_SEED", "true")
        make_user(username="preexistente")

        with pytest.raises(CommandError, match="produção"):
            call_command("seed_demo", "--reset")

        # O que realmente importa: nada foi apagado.
        from django.contrib.auth import get_user_model

        assert get_user_model().objects.filter(username="preexistente").exists()

    def test_recusa_rodar_sem_run_seed(self, db, monkeypatch):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        monkeypatch.delenv("RUN_SEED", raising=False)

        with pytest.raises(CommandError, match="RUN_SEED"):
            call_command("seed_demo")

    def test_sem_reset_nao_apaga_nada(self, db, monkeypatch, make_user):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command

        monkeypatch.setenv("RUN_SEED", "true")
        make_user(username="preexistente")

        call_command("seed_demo", "--seed", "1")

        assert get_user_model().objects.filter(username="preexistente").exists()

    def test_ensure_superuser_nao_troca_a_senha_de_quem_ja_existe(self, db, monkeypatch, make_user):
        """O entrypoint antigo redefinia a senha do admin a cada deploy, em silêncio."""
        from django.core.management import call_command

        admin = make_user(username="admin", password="SenhaOriginal123!")
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "admin")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "OutraSenha456!")

        call_command("ensure_superuser")

        admin.refresh_from_db()
        assert admin.check_password("SenhaOriginal123!")


class TestAvataresDoSeed:
    """`seed_demo` gravava a mesma URL genérica (DEFAULT_AVATAR_URL) para os quatro
    usuários de demonstração, ignorando os arquivos em `media-seed/avatars/` — que
    existiam só para isso e nunca eram usados. Rodar o backend localmente mostrava os
    quatro perfis com o avatar padrão, em vez de fotos distintas."""

    def test_cada_usuario_recebe_um_avatar_distinto(self, db, monkeypatch):
        from django.core.management import call_command

        monkeypatch.setenv("RUN_SEED", "true")

        call_command("seed_demo", "--seed", "1")

        from django.contrib.auth import get_user_model

        avatares = list(
            get_user_model().objects.exclude(is_superuser=True).values_list("avatar", flat=True)
        )
        assert len(avatares) == len(set(avatares)), "usuários com o mesmo avatar"

    def test_o_avatar_e_uma_url_absoluta_servivel_pelo_backend(self, db, monkeypatch, settings):
        """Gravar um caminho relativo já foi o bug: o navegador resolvia contra a
        origem do frontend (:5173), não a da API (:8000), e a imagem dava 404."""
        from django.core.management import call_command

        monkeypatch.setenv("RUN_SEED", "true")

        call_command("seed_demo", "--seed", "1")

        from django.contrib.auth import get_user_model

        user = get_user_model().objects.get(username="franciscolucas")
        assert user.avatar == f"{settings.LOCAL_MEDIA_BASE_URL}/media/avatars/user1.png"

    def test_o_arquivo_do_avatar_existe_em_media_root(self, db, monkeypatch, settings):
        from django.core.management import call_command

        monkeypatch.setenv("RUN_SEED", "true")

        call_command("seed_demo", "--seed", "1")

        from pathlib import Path

        assert (Path(settings.MEDIA_ROOT) / "avatars" / "user1.png").exists()

    def test_rodar_de_novo_sem_reset_conserta_avatar_antigo(self, db, monkeypatch, settings):
        """O cenário real: um banco já seedado antes desta correção tinha os quatro
        usuários com DEFAULT_AVATAR_URL. `get_or_create` só aplica `defaults` na
        criação — sem tratamento explícito, rodar o seed de novo não teria efeito
        nenhum sobre quem já existia."""
        from django.contrib.auth import get_user_model
        from django.core.management import call_command

        monkeypatch.setenv("RUN_SEED", "true")
        call_command("seed_demo", "--seed", "1")

        user = get_user_model().objects.get(username="franciscolucas")
        user.avatar = settings.DEFAULT_AVATAR_URL
        user.save(update_fields=["avatar"])

        call_command("seed_demo")

        user.refresh_from_db()
        assert user.avatar == f"{settings.LOCAL_MEDIA_BASE_URL}/media/avatars/user1.png"


class TestGuardaDoResetDeProducao:
    """`reset_producao` é a reativação deliberada, só para este portfólio, do mesmo tipo
    de reset que o incidente acima descreve — mas atrás de uma variável própria
    (RESET_DB_ON_DEPLOY), nunca ligada por acidente."""

    def test_recusa_rodar_sem_a_variavel(self, db, monkeypatch, make_user):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        from django.core.management.base import CommandError

        monkeypatch.delenv("RESET_DB_ON_DEPLOY", raising=False)
        make_user(username="preexistente")

        with pytest.raises(CommandError, match="RESET_DB_ON_DEPLOY"):
            call_command("reset_producao")

        assert get_user_model().objects.filter(username="preexistente").exists()

    def test_com_a_variavel_apaga_tudo_inclusive_superusuario(self, db, monkeypatch, make_user):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command

        User = get_user_model()
        make_user(username="usuariocomum")
        User.objects.create_superuser(username="admin", password="SenhaForte123!")

        monkeypatch.setenv("RESET_DB_ON_DEPLOY", "true")
        call_command("reset_producao")

        assert User.objects.count() == 0
