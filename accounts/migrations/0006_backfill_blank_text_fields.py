"""Converte os NULLs existentes em string vazia.

Sem este passo, as linhas gravadas antes da mudança continuariam com NULL em `name` e
`avatar`, e o código que passou a assumir string sempre encontraria `None` nelas.
"""

from django.db import migrations


def null_para_vazio(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(name__isnull=True).update(name="")
    User.objects.filter(avatar__isnull=True).update(avatar="")


def sem_volta(apps, schema_editor):
    """A reversão não recria os NULLs: string vazia é a representação correta, e
    distinguir "era NULL" de "era vazio" não é possível depois do backfill."""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_normalize_blank_text_fields")]

    operations = [migrations.RunPython(null_para_vazio, sem_volta)]
