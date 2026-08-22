"""Operações de conta que mudam estado ou falam com o mundo externo.

Separado dos serializers de propósito. O upload de avatar era uma chamada HTTP síncrona
ao Cloudinary feita **dentro** de `UserProfileSerializer.update()`, sem try/except: um
erro do Cloudinary virava 500. E como o `cloudinary.uploader` era importado no topo do
módulo, todo ambiente carregava a biblioteca — inclusive desenvolvimento, onde ela nunca
esteve configurada.

Havia ainda três caminhos diferentes gravando o campo `avatar`, cada um num formato:
o registro atribuía o **objeto de arquivo** direto ao CharField (persistindo o nome do
arquivo, não uma URL); o seed de desenvolvimento gravava um caminho relativo
(`"avatars/user1.png"`, que o navegador resolvia contra a origem do SPA e dava 404); e só
a edição de perfil gravava a URL de verdade. Agora há um caminho só.
"""

import logging

from django.conf import settings

from common.errors import (
    AvatarUploadFailed,
    FileTooLarge,
    StorageNotConfigured,
    UnsupportedMediaType,
)

logger = logging.getLogger(__name__)

MAX_AVATAR_BYTES = 5 * 1024 * 1024
TIPOS_ACEITOS = {"image/jpeg", "image/png", "image/webp"}


def _storage_configurado() -> bool:
    import cloudinary

    config = cloudinary.config()
    return bool(config.cloud_name and config.api_key and config.api_secret)


def validate_avatar(arquivo) -> None:
    """Recusa o que não é imagem ou é grande demais.

    O campo era declarado como `FileField`, não `ImageField`, e não havia checagem
    nenhuma de tipo, tamanho ou extensão — qualquer arquivo era aceito e enviado adiante.
    """
    tamanho = getattr(arquivo, "size", 0)
    if tamanho > MAX_AVATAR_BYTES:
        raise FileTooLarge(
            f"A imagem tem {tamanho // 1024}KB e o limite é {MAX_AVATAR_BYTES // 1024 // 1024}MB."
        )

    content_type = getattr(arquivo, "content_type", "") or ""
    if content_type not in TIPOS_ACEITOS:
        raise UnsupportedMediaType()


def upload_avatar(arquivo, *, user) -> str:
    """Envia o avatar e devolve a URL pública.

    Levanta erro de domínio — nunca 500 — quando o armazenamento não está configurado ou
    o provedor falha. Em desenvolvimento o Cloudinary não é configurado, e recusar com
    STORAGE_NOT_CONFIGURED é a resposta honesta: o frontend mostra "o envio de imagens
    está indisponível" em vez de uma tela de erro genérica.
    """
    validate_avatar(arquivo)

    if not _storage_configurado():
        raise StorageNotConfigured()

    from cloudinary.uploader import upload

    try:
        resultado = upload(
            arquivo,
            folder="xclone/avatars",
            # O `public_id` era o username, que o próprio serializer permite renomear —
            # trocar de nome desatrelava a URL guardada do objeto no Cloudinary. O id é
            # imutável.
            public_id=str(user.pk),
            overwrite=True,
            resource_type="image",
        )
    except Exception:
        # O erro do provedor vai para o log com stack; para o cliente vai um código que
        # ele sabe traduzir. Antes a exceção subia crua e virava 500.
        logger.exception("Falha ao enviar avatar do usuário %s", user.pk)
        raise AvatarUploadFailed() from None

    url = resultado.get("secure_url")
    if not url:
        logger.error("Cloudinary respondeu sem secure_url para o usuário %s", user.pk)
        raise AvatarUploadFailed()
    return url


def default_avatar_url() -> str:
    """URL usada por quem se cadastra sem enviar foto.

    Constante compartilhada com o frontend (`VITE_DEFAULT_AVATAR_URL`). A string já
    esteve escrita à mão nos dois repositórios: no meio do `create()` do serializer e em
    `EditProfileModal.tsx`.
    """
    return settings.DEFAULT_AVATAR_URL
