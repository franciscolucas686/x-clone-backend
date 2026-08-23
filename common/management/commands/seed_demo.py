"""Popula o banco com dados de demonstração.

    python manage.py seed_demo            # cria o que faltar, não apaga nada
    python manage.py seed_demo --reset    # apaga tudo antes de recriar

Substitui os scripts `seed_data.py` e `seed_data_dev.py`, que eram ~70% duplicados e
rodavam via `django.setup()` manual, cada um fixando o próprio DJANGO_SETTINGS_MODULE no
import — de modo que nenhum dos dois podia ser apontado para outro ambiente.

O motivo de existir como comando com guardas é mais sério que organização:
`entrypoint.prod.sh` executava `python seed_data.py` a **cada boot de produção**, e o
`run()` daquele script abria com `reset_database()`, que fazia
`User.objects.all().delete()`. Todo deploy apagava os usuários, posts, curtidas,
comentários e relações reais — inclusive o superusuário criado poucas linhas antes, no
mesmo entrypoint.
"""

import random
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# Importado como módulo, não como nomes soltos: `from ... import fn` fixa a
# referência no momento do import, e o Django carrega módulos de comando
# preguiçosamente — o que torna o instante do import imprevisível e a função
# impossível de substituir depois. Chamar através do módulo mantém a costura.
from common import env_flags
from followers.models import Follow
from posts.models import Comment, Like, Post

User = get_user_model()

AVATAR_SEED_DIR = Path(settings.BASE_DIR) / "media-seed" / "avatars"

# As senhas saem do ambiente. Antes estavam em texto puro no repositório, para contas que
# o entrypoint recriava em produção a cada deploy — ou seja, credenciais públicas de
# usuários reais da aplicação publicada.
DEMO_PASSWORD = settings.DEMO_USER_PASSWORD

DEMO_USERS = [
    {"username": "franciscolucas", "name": "Francisco Lucas", "avatar": "user1.png"},
    {"username": "matheusfidera", "name": "Matheus Fidera", "avatar": "user2.png"},
    {"username": "raianeester", "name": "Raiane Ester", "avatar": "user3.png"},
    {"username": "solangecarriel", "name": "Solange Carriel", "avatar": "user4.png"},
]

POST_TEXTS = [
    "Lindo dia hoje para fazer um bom trabalho! 🚀",
    "Hoje o café saiu mais forte que o código ☕",
    "O amor move montanhas ❤️",
    "Aprendendo sobre como eu posso melhorar meu inglês.",
    "Curtindo o dia fazendo uma caminhada no parque 🌞",
]

COMMENT_TEXTS = [
    "Muito bom!",
    "Excelente 👏",
    "Adorei esse post 😍",
    "Concordo totalmente!",
    "Boa dica!",
]


class Command(BaseCommand):
    help = "Popula o banco com usuários, posts, curtidas, comentários e seguidores de demonstração."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Apaga TODOS os usuários, posts, curtidas, comentários e follows antes de recriar.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Semente do random, para um conjunto de dados reproduzível.",
        )

    def handle(self, *args, **options):
        self._check_guards()

        if options["seed"] is not None:
            random.seed(options["seed"])

        with transaction.atomic():
            if options["reset"]:
                self._reset()

            users = self._create_users()
            self._create_follows(users)
            posts = self._create_posts(users)
            self._create_likes_and_comments(users, posts)

        self.stdout.write(self.style.SUCCESS("Seed concluído."))

    def _check_guards(self):
        """Duas travas independentes, verificadas antes de qualquer escrita.

        Independentes de propósito: a primeira protege contra rodar no ambiente errado, a
        segunda contra rodar sem querer no ambiente certo. Uma só já teria evitado o
        incidente do entrypoint; duas evitam a próxima variação dele.
        """
        if env_flags.settings_module_is_production():
            raise CommandError(
                "seed_demo recusa rodar com settings de produção "
                f"({settings.SETTINGS_MODULE}). Este comando cria contas com senha "
                "conhecida e, com --reset, apaga o banco inteiro."
            )

        if not env_flags.seed_is_enabled():
            raise CommandError(
                "seed_demo exige RUN_SEED=true no ambiente carregado. É uma trava "
                "deliberada contra execução acidental — defina a variável no seu .env "
                "para liberar."
            )

    def _reset(self):
        self.stdout.write("Apagando dados existentes...")
        Comment.objects.all().delete()
        Like.objects.all().delete()
        Post.objects.all().delete()
        Follow.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write("Banco limpo.")

    def _seed_avatar_url(self, filename: str) -> str:
        """Copia o avatar de `media-seed/avatars/` para `MEDIA_ROOT` e devolve a URL
        absoluta de onde o Django vai servi-lo em desenvolvimento (`static()` em
        `backend/urls.py`, ativo só com `DEBUG=True`).

        Cai para "" se o arquivo de origem não existir — o mesmo estado de um cadastro sem
        foto, e o AvatarUrlField resolve o avatar padrão na leitura. Antes gravava aqui a
        URL padrão, o que espalhava uma cópia da configuração pelas linhas do seed.
        """
        origem = AVATAR_SEED_DIR / filename
        if not origem.exists():
            self.stdout.write(
                self.style.WARNING(f"  avatar de seed ausente: {origem} — usando o padrão")
            )
            return ""

        destino_dir = Path(settings.MEDIA_ROOT) / "avatars"
        destino_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(origem, destino_dir / filename)

        base = settings.LOCAL_MEDIA_BASE_URL.rstrip("/")
        return f"{base}{settings.MEDIA_URL}avatars/{filename}"

    def _create_users(self):
        users = []
        for data in DEMO_USERS:
            avatar_url = self._seed_avatar_url(data["avatar"])

            user, created = User.objects.get_or_create(
                username=data["username"],
                defaults={"name": data["name"], "avatar": avatar_url},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
                self.stdout.write(f"  usuário criado: {user.username}")
            elif user.avatar != avatar_url:
                # Sem `--reset`: um usuário criado antes desta correção continuava com
                # a URL genérica para sempre, porque `get_or_create` só usa `defaults`
                # na criação. Rodar `seed_demo` de novo agora conserta o que já existe.
                user.avatar = avatar_url
                user.save(update_fields=["avatar"])
                self.stdout.write(f"  avatar atualizado: {user.username}")
            users.append(user)
        return users

    def _create_follows(self, users):
        for user in users:
            candidatos = [u for u in users if u != user]
            for alvo in random.sample(candidatos, k=random.randint(1, len(candidatos))):
                Follow.objects.get_or_create(follower=user, following=alvo)
        self.stdout.write("  relações de seguidores criadas")

    def _create_posts(self, users):
        posts = []
        for user in users:
            for _ in range(random.randint(1, 3)):
                posts.append(Post.objects.create(user=user, text=random.choice(POST_TEXTS)))
        self.stdout.write(f"  {len(posts)} posts criados")
        return posts

    def _create_likes_and_comments(self, users, posts):
        for post in posts:
            for liker in random.sample(users, k=random.randint(1, len(users))):
                Like.objects.get_or_create(user=liker, post=post)
            for autor in random.sample(users, k=random.randint(1, len(users))):
                Comment.objects.create(user=autor, post=post, text=random.choice(COMMENT_TEXTS))
        self.stdout.write("  curtidas e comentários criados")
