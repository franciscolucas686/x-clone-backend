"""Regras de conta: avatar, busca e troca de senha."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

pytestmark = pytest.mark.django_db


def _imagem(nome="foto.png", content_type="image/png", tamanho=1024):
    return SimpleUploadedFile(nome, b"x" * tamanho, content_type=content_type)


class TestAvatar:
    def test_cadastro_sem_foto_recebe_o_avatar_padrao(self, api, settings):
        resposta = api.post(
            reverse("register"),
            {
                "username": "semfoto",
                "name": "Sem Foto",
                "password": "SenhaForte123!",
                "confirm_password": "SenhaForte123!",
            },
            format="json",
        )

        assert resposta.data["avatar_url"] == settings.DEFAULT_AVATAR_URL

    def test_cadastro_sem_foto_nao_grava_a_url_padrao_no_banco(self, api):
        """A URL padrão é resolvida na leitura (AvatarUrlField), não gravada em cada
        linha. Gravá-la apagaria o fato "nunca escolheu foto", que has_custom_avatar
        precisa para o botão de remover no EditProfileModal."""
        from django.contrib.auth import get_user_model

        api.post(
            reverse("register"),
            {
                "username": "semfotobanco",
                "name": "Sem Foto",
                "password": "SenhaForte123!",
                "confirm_password": "SenhaForte123!",
            },
            format="json",
        )

        user = get_user_model().objects.get(username="semfotobanco")
        assert user.avatar == ""

    def test_usuario_sem_avatar_tem_has_custom_avatar_falso(self, auth, user):
        resposta = auth.get(reverse("profile"))

        assert resposta.data["has_custom_avatar"] is False

    def test_autor_sem_avatar_no_feed_recebe_o_avatar_padrao(
        self, auth, make_user, make_post, settings
    ):
        """UserFeedSerializer alimenta o autor de todo post e comentário. Antes só o
        registro injetava o avatar padrão: um autor criado por `create_user` (a
        factory dos testes, o superusuário do admin) ficava com avatar="" e o feed
        devolvia `avatar_url: ""` — sete das oito telas que mostram avatar não têm
        fallback, e renderizavam `<img src="">`."""
        autor = make_user(avatar="")
        make_post(user=autor)

        resposta = auth.get(reverse("post-list-create"))

        post_do_autor = next(p for p in resposta.data["results"] if p["user"]["id"] == autor.id)
        assert post_do_autor["user"]["avatar_url"] == settings.DEFAULT_AVATAR_URL

    def test_cadastro_sem_o_campo_name_nao_quebra(self, api):
        """`validated_data['name']` levantava KeyError -> 500. `name` é opcional no
        modelo, então o DRF o gera como required=False; nenhum teste pegava porque todos
        mandavam o campo."""
        resposta = api.post(
            reverse("register"),
            {
                "username": "semnome",
                "password": "SenhaForte123!",
                "confirm_password": "SenhaForte123!",
            },
            format="json",
        )

        assert resposta.status_code == 201

    def test_arquivo_que_nao_e_imagem_e_recusado(self, auth):
        """O campo era FileField, não ImageField, e não havia checagem de tipo nenhuma."""
        resposta = auth.patch(
            reverse("profile"),
            {
                "avatar": SimpleUploadedFile(
                    "virus.exe", b"MZ", content_type="application/x-msdownload"
                )
            },
            format="multipart",
        )

        assert resposta.status_code == 415
        assert resposta.data["code"] == "UNSUPPORTED_MEDIA_TYPE"

    def test_imagem_grande_demais_e_recusada(self, auth):
        from accounts.services import MAX_AVATAR_BYTES

        resposta = auth.patch(
            reverse("profile"),
            {"avatar": _imagem(tamanho=MAX_AVATAR_BYTES + 1)},
            format="multipart",
        )

        assert resposta.status_code == 413
        assert resposta.data["code"] == "FILE_TOO_LARGE"

    def test_sem_cloudinary_configurado_o_erro_e_claro(self, auth):
        """Em desenvolvimento o Cloudinary nunca esteve configurado. Antes a exceção
        subia crua do uploader e virava 500; agora o cliente recebe um código que sabe
        traduzir."""
        resposta = auth.patch(reverse("profile"), {"avatar": _imagem()}, format="multipart")

        assert resposta.status_code == 503
        assert resposta.data["code"] == "STORAGE_NOT_CONFIGURED"

    def test_remover_o_avatar_volta_ao_padrao(self, auth, user, settings):
        """Não havia como remover: o campo não aceitava nulo, e o botão do frontend só
        limpava o preview local."""
        user.avatar = "https://exemplo.test/foto-antiga.png"
        user.save(update_fields=["avatar"])

        resposta = auth.patch(reverse("profile"), {"avatar": ""}, format="multipart")

        assert resposta.status_code == 200
        assert resposta.data["avatar_url"] == settings.DEFAULT_AVATAR_URL


class TestBuscaDeUsuarios:
    def test_busca_acontece_no_servidor(self, auth, make_user):
        """O ExplorerPage filtrava no cliente, sobre a página já carregada — com 10 itens
        por página, buscar era procurar entre os 10 primeiros usuários do sistema."""
        make_user(username="mariana", name="Mariana Silva")
        for _ in range(15):
            make_user()

        resposta = auth.get(reverse("user-list"), {"search": "mariana"})

        assert resposta.data["count"] == 1
        assert resposta.data["results"][0]["username"] == "mariana"

    def test_busca_tambem_casa_pelo_nome(self, auth, make_user):
        make_user(username="jd", name="João Pedro")

        resposta = auth.get(reverse("user-list"), {"search": "joão"})

        assert resposta.data["count"] == 1


class TestSimilaridadeComOUsuario:
    """UserAttributeSimilarityValidator compara a senha com username/name/email.

    validate_password estava preso como validador de campo, chamado sem `user` — o
    validador faz `if not user: return` e nunca reprovava nada. A cadeia declarada em
    AUTH_PASSWORD_VALIDATORS ficava três quartos aplicada, em silêncio, nos dois
    serializers.
    """

    def test_senha_parecida_com_username_e_recusada_no_cadastro(self, api):
        resposta = api.post(
            reverse("register"),
            {
                "username": "carlosmendes",
                "name": "Carlos Mendes",
                "password": "carlosmendes123",
                "confirm_password": "carlosmendes123",
            },
            format="json",
        )

        assert resposta.status_code == 400
        assert "password" in resposta.data["details"]

    def test_senha_parecida_com_username_e_recusada_na_troca(self, auth, make_user):
        # Senha e nome de usuário fixos, não derivados de `user.username`: o validador
        # usa razão de similaridade (difflib), sensível a diferenças pequenas de
        # comprimento — um sufixo dinâmico já deixou de ser "parecido o bastante" só por
        # ganhar um caractere. "carlosmendes"/"carlosmendes123" é o par que a suíte já
        # confirma que o Django recusa.
        dono = make_user(username="carlosmendes2", name="Carlos Mendes")
        api = auth
        api.force_authenticate(user=dono)

        resposta = api.patch(
            reverse("profile"),
            {"password": "carlosmendes2123", "confirm_password": "carlosmendes2123"},
            format="multipart",
        )

        assert resposta.status_code == 400
        assert "password" in resposta.data["details"]


class TestNomeCapitalizado:
    """Primeira letra maiúscula em cada palavra do nome, exceto conectivos comuns em
    nomes brasileiros (de, da, do, das, dos, e) quando não são a primeira palavra."""

    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("joão da silva", "João da Silva"),
            ("MARIA DE SOUZA DOS SANTOS", "Maria de Souza dos Santos"),
            ("das neves oliveira", "Das Neves Oliveira"),
            ("ana-beatriz e maria", "Ana-Beatriz e Maria"),
            ("  francisco   lucas  ", "Francisco Lucas"),
        ],
    )
    def test_cadastro_normaliza_o_nome(self, api, entrada, esperado):
        resposta = api.post(
            reverse("register"),
            {
                "username": f"user{abs(hash(entrada)) % 10_000}",
                "name": entrada,
                "password": "SenhaForte123!",
                "confirm_password": "SenhaForte123!",
            },
            format="json",
        )

        assert resposta.status_code == 201
        assert resposta.data["name"] == esperado

    def test_edicao_de_perfil_normaliza_o_nome(self, auth, user):
        resposta = auth.patch(reverse("profile"), {"name": "carlos dos santos"}, format="multipart")

        assert resposta.status_code == 200
        assert resposta.data["name"] == "Carlos dos Santos"
        user.refresh_from_db()
        assert user.name == "Carlos dos Santos"

    def test_nome_vazio_continua_opcional(self, api):
        resposta = api.post(
            reverse("register"),
            {
                "username": "semnomecapitalizado",
                "password": "SenhaForte123!",
                "confirm_password": "SenhaForte123!",
            },
            format="json",
        )

        assert resposta.status_code == 201
        assert resposta.data["name"] == ""


class TestTrocaDeSenha:
    def test_senha_fraca_e_recusada_na_troca(self, auth):
        """O cadastro aplicava a cadeia de validadores do Django e a troca não: dava para
        registrar com senha forte e depois trocá-la por "123"."""
        resposta = auth.patch(
            reverse("profile"),
            {"password": "123", "confirm_password": "123"},
            format="multipart",
        )

        assert resposta.status_code == 400

    def test_senha_forte_e_aceita(self, auth, user):
        resposta = auth.patch(
            reverse("profile"),
            {"password": "OutraSenhaForte456!", "confirm_password": "OutraSenhaForte456!"},
            format="multipart",
        )

        assert resposta.status_code == 200
        user.refresh_from_db()
        assert user.check_password("OutraSenhaForte456!")
