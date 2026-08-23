"""Apaga todos os dados do banco — usado pelo entrypoint de produção deste portfólio.

    python manage.py reset_producao

Não confundir com `seed_demo --reset`: aquele comando recusa rodar em produção de
propósito (foi a trava colocada depois do incidente em que `entrypoint.prod.sh` apagava
os dados reais a cada boot — ver o docstring de `seed_demo.py`). Este comando existe
porque a decisão deste projeto agora é a oposta: é um portfólio sem usuário real a
proteger, e cada deploy deve devolver um banco limpo para quem for testar percorrer o
caminho cadastro -> login. Por isso a trava aqui não é "nunca em produção" — é "só se
alguém ligou a variável explicitamente".

Apaga também o(s) superusuário(s): `ensure_superuser`, chamado logo depois no
entrypoint, recria o admin a partir do ambiente.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from common import env_flags
from followers.models import Follow
from posts.models import Comment, Like, Post

User = get_user_model()


class Command(BaseCommand):
    help = "Apaga todos os usuários, posts, curtidas, comentários e follows. Gated por RESET_DB_ON_DEPLOY."

    def handle(self, *args, **options):
        if not env_flags.reset_on_deploy_is_enabled():
            raise CommandError(
                "reset_producao exige RESET_DB_ON_DEPLOY=true no ambiente carregado. "
                "É uma trava deliberada: sem a variável, o comando não apaga nada."
            )

        with transaction.atomic():
            self.stdout.write("Apagando todos os dados...")
            Comment.objects.all().delete()
            Like.objects.all().delete()
            Post.objects.all().delete()
            Follow.objects.all().delete()
            User.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Banco de dados zerado."))
