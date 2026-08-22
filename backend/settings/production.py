"""Settings de produção.

Diferente de development.py, aqui nada tem default: cada `require()` abaixo aborta o boot
nomeando a variável que falta. Subir mal configurado é o modo de falha que este arquivo
existe para tornar impossível.
"""

import os

from .base import *  # noqa: F403
from .env import MIN_SECRET_KEY_LENGTH, database_config, require, require_list, require_origin_list

SECRET_KEY = require("SECRET_KEY", min_length=MIN_SECRET_KEY_LENGTH)

DEBUG = False

ALLOWED_HOSTS = require_list("ALLOWED_HOSTS")

# O Render publica o hostname do serviço em runtime. Aceitá-lo evita ter que repetir um
# valor que a plataforma já conhece — e que muda quando o serviço é recriado.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS if not host.startswith("*")]

# Aceita `DATABASE_URL` (o formato que Neon, Render e Supabase entregam) ou as quatro
# variáveis separadas. Ver backend/settings/env.py.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        **database_config(required=True),
        # Reaproveita conexões entre requisições. Sem isto cada request abre e fecha uma
        # conexão com o Postgres gerenciado, o que domina o tempo de resposta.
        "CONN_MAX_AGE": 60,
    }
}

INSTALLED_APPS += [  # noqa: F405
    "cloudinary",
    "cloudinary_storage",
]

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": require("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": require("CLOUDINARY_API_KEY"),
    "API_SECRET": require("CLOUDINARY_API_SECRET"),
}

STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405

# STORAGES, e não DEFAULT_FILE_STORAGE/STATICFILES_STORAGE.
#
# Aquelas duas settings foram removidas no Django 5.1, e este projeto está no 5.2:
# settings desconhecidas são ignoradas em silêncio, então as duas linhas antigas não
# faziam nada. O efeito era o WhiteNoise servir os estáticos sem compressão nem hash de
# cache, e a storage do Cloudinary nunca ser ativada — enquanto o upload de avatar
# funcionava por outro caminho, chamando a API do Cloudinary direto.
STORAGES = {
    "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

# ─── CORS ───────────────────────────────────────────────────────────────────────
#
# Vem inteiro do ambiente. Antes o domínio do deploy estava escrito no código
# (`https://x-clone-frontend-nu.vercel.app`) junto de `localhost:5173` — que ficava
# aceito como origem **em produção**, ou seja, qualquer página rodando na porta 5173 da
# máquina de um visitante podia falar com a API real. Trocar de domínio também exigia
# editar código e refazer deploy, em vez de mudar uma variável.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = require_origin_list("CORS_ALLOWED_ORIGINS")

if "*" in CORS_ALLOWED_ORIGINS:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        'CORS_ALLOWED_ORIGINS="*" não é permitido em produção. Liste as origens '
        "explicitamente, separadas por vírgula."
    )

# ─── Cabeçalhos de segurança ────────────────────────────────────────────────────
#
# Sem SECURE_PROXY_SSL_HEADER o Django não sabe que está atrás do proxy HTTPS do Render:
# `request.is_secure()` responde False e as URLs absolutas que o DRF gera na paginação
# (o campo `next`) saem como http:// para um site servido em https://, que o navegador
# bloqueia como conteúdo misto. É o mais load-bearing dos quatro.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
