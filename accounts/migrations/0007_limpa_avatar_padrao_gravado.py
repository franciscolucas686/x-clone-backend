"""Zera o `avatar` das linhas que guardam a URL do avatar padrão.

A URL padrão deixou de ser gravada: `avatar == ""` significa "nunca escolheu foto", e a
URL é resolvida na leitura por `AvatarUrlField` (accounts/serializers.py). As linhas
criadas antes disso guardam uma cópia da configuração, o que reintroduz o problema por
outro caminho — `has_custom_avatar` diria que essas pessoas escolheram uma foto, e a
edição de perfil ofereceria "remover foto" para um avatar que já é o padrão.

Quem já está com `""` não precisa de nada: passa a renderizar o padrão em vez de
`<img src="">`.
"""

from django.conf import settings
from django.db import migrations


def limpa_avatar_padrao(apps, schema_editor):
    User = apps.get_model("accounts", "User")

    urls_padrao = {
        settings.DEFAULT_AVATAR_URL,
        # Literal histórico: esteve escrito à mão em accounts/serializers.py e no
        # frontend, e é o que está gravado no banco publicado. Se DEFAULT_AVATAR_URL já
        # foi trocada por variável de ambiente, a entrada acima não casa com nada e esta
        # continua sendo a que limpa as linhas antigas.
        "https://res.cloudinary.com/dh5rxxtqe/image/upload/v1763632324/xclone/avatars/default.png",
    }

    User.objects.filter(avatar__in=urls_padrao).update(avatar="")


def sem_volta(apps, schema_editor):
    """A reversão não regrava a URL: depois do backfill não há como distinguir quem tinha
    a URL padrão gravada de quem sempre esteve vazio — e as duas leem igual de qualquer
    forma."""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_backfill_blank_text_fields")]

    operations = [migrations.RunPython(limpa_avatar_padrao, sem_volta)]
