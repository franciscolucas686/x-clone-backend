"""Cria o superusuário do admin a partir do ambiente, se ele ainda não existir.

    python manage.py ensure_superuser

Substitui o heredoc que os dois entrypoints executavam via `manage.py shell`, e que
interpolava variáveis de shell direto no código Python:

    username = "${DJANGO_SUPERUSER_USERNAME}"

Uma aspa na senha quebrava o script — e, com a senha certa, executava o que viesse junto.
Além disso o entrypoint de produção **redefinia a senha a cada deploy**, silenciosamente,
e escrevia `first_name` enquanto a aplicação inteira lê `name`.

A senha só é alterada com --update-password. Um deploy não deve mudar credencial sem que
alguém tenha pedido.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from backend.settings.env import get

User = get_user_model()


class Command(BaseCommand):
    help = "Cria o superusuário definido em DJANGO_SUPERUSER_USERNAME/_PASSWORD, se não existir."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update-password",
            action="store_true",
            help="Redefine a senha se o usuário já existir.",
        )

    def handle(self, *args, **options):
        username = get("DJANGO_SUPERUSER_USERNAME")
        password = get("DJANGO_SUPERUSER_PASSWORD")

        if not username or not password:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME/_PASSWORD não definidos — nada a fazer.")
            return

        name = get("DJANGO_SUPERUSER_NAME", "Administrador")

        user = User.objects.filter(username=username).first()
        if user is None:
            User.objects.create_superuser(username=username, password=password, name=name)
            self.stdout.write(self.style.SUCCESS(f"Superusuário '{username}' criado."))
            return

        if options["update_password"]:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS(f"Senha de '{username}' atualizada."))
        else:
            self.stdout.write(f"Superusuário '{username}' já existe — nada alterado.")
