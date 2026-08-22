"""Settings de desenvolvimento local.

Carregado por padrão: manage.py, wsgi.py e asgi.py apontam para cá quando ninguém define
DJANGO_SETTINGS_MODULE. Produção define a variável explicitamente (ver Dockerfile.prod).
"""

from .base import *  # noqa: F403
from .env import database_config, get

# Default óbvio e deliberadamente inseguro: em desenvolvimento a chave não protege nada,
# e exigir configuração aqui só atrapalharia quem acabou de clonar o repositório.
# production.py usa require() e não aceita default nenhum.
SECRET_KEY = get("SECRET_KEY", "dev-insecure-key-nao-use-em-producao")

DEBUG = True

ALLOWED_HOSTS = ["*"]

# `sslmode` cai para "prefer" em desenvolvimento: o Postgres do docker-compose não tem
# TLS configurado, e exigi-lo aqui quebraria o setup local. Em produção o default é
# "require" — ver backend/settings/env.py.
#
# Os defaults abaixo apontam para "localhost" e não para "db", porque precisam servir
# quem roda `manage.py` na própria máquina, que é o caminho do README. Dentro do
# docker-compose o nome do serviço vem do ambiente, onde ele de fato resolve.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        **database_config(required=False),
    }
}

_padroes = {
    "NAME": "xclone_dev",
    "USER": "xclone",
    "PASSWORD": "xclone",
    "HOST": "localhost",
}
for _campo, _valor in _padroes.items():
    if not DATABASES["default"].get(_campo):
        DATABASES["default"][_campo] = _valor

CORS_ALLOW_ALL_ORIGINS = True

# Base para montar URLs absolutas de arquivos servidos localmente (os avatares de
# seed, em media/avatars/). Precisa ser absoluta porque `User.avatar` guarda uma URL
# completa — em produção, a do Cloudinary — e o frontend faz `<img src={avatar_url}>`
# direto. Gravar só o caminho relativo ("/media/avatars/user1.png") já foi o bug: o
# navegador resolvia contra a origem do frontend (:5173), não a da API (:8000), e a
# imagem dava 404. Ver common/management/commands/seed_demo.py.
LOCAL_MEDIA_BASE_URL = get("LOCAL_MEDIA_BASE_URL", "http://localhost:8000")
