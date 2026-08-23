from datetime import timedelta

from .env import BASE_DIR, get, get_bool, get_list, require, require_list  # noqa: F401

# SECRET_KEY não é definida aqui de propósito: a exigência varia por ambiente.
# development.py aceita um default óbvio; production.py usa require(), que aborta o boot
# se a variável faltar. Um default único em base.py é justamente o que fazia produção
# subir assinando JWT com uma chave versionada no repositório.

INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    # Necessário para BLACKLIST_AFTER_ROTATION: sem ele não havia revogação nenhuma —
    # nem endpoint de logout no servidor, nem forma de invalidar um token vazado.
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "common",
    "accounts",
    "posts",
    "followers",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Este bloco não existia, e a ausência dele é que respondia pela lentidão do login.
#
# Sem `PASSWORD_HASHERS`, vale a lista default do Django — e o Django 5.2 subiu o PBKDF2
# para 1.000.000 de iterações. Medido nesta máquina: `check_password` 266–283 ms por
# login, `make_password` 275 ms. O cadastro pagava dois hashes (cria a senha, depois o
# cliente entra), ~550 ms só de CPU. Com Argon2: ~48 ms para verificar, ~69 ms para criar.
#
# Argon2 é mais rápido **e** mais resistente que o PBKDF2 que substitui: o custo dele é em
# memória (100 MiB por hash, `memory_cost` default), o que é justamente o que inviabiliza
# o ataque em GPU. Vale saber do consumo antes de descobrir sob carga — com o throttle de
# `10/min` em /token/ e /register/ (ver DEFAULT_THROTTLE_RATES abaixo) a conta fecha, mas
# uma instância pequena não deve subir `WEB_CONCURRENCY` sem refazê-la.
#
# O PBKDF2 continua na lista, e não é decoração: é ele que lê os hashes já gravados. O
# Django reescreve cada senha no formato do primeiro hasher no próximo login do dono, de
# graça — sem migração, sem reset e sem invalidar ninguém.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]


STATIC_URL = "/static/"

DEFAULT_AVATAR_URL = get(
    "DEFAULT_AVATAR_URL",
    "https://res.cloudinary.com/dh5rxxtqe/image/upload/v1763632324/xclone/avatars/default.png",
)

# Senha das contas de demonstração criadas por `manage.py seed_demo`. Fora do código
# porque as anteriores estavam versionadas e pertenciam a contas que existiam na
# aplicação publicada.
DEMO_USER_PASSWORD = get("DEMO_USER_PASSWORD", "SenhaDemo123!")

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # Fail-closed: uma view nova sem `permission_classes` nasce **privada**. O default
    # do DRF é AllowAny, então antes ela nascia pública — e a única coisa impedindo um
    # vazamento era alguém lembrar de declarar a permissão em cada view.
    #
    # As quatro rotas realmente públicas declaram AllowAny explicitamente:
    # UserPostsView, FollowersListView, FollowingListView e a leitura de comentários.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    # Toda resposta de erro passa por aqui e sai no mesmo envelope, com um `code`
    # estável. Ver common/exception_handler.py.
    "EXCEPTION_HANDLER": "common.exception_handler.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Limite por escopo, aplicado nas rotas que o declaram (ver accounts/views.py).
    # Não havia limite nenhum: /token/ e /register/ aceitavam tentativas ilimitadas, o
    # que deixa força bruta de senha sem custo e criação de contas em massa livre.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "auth": get("THROTTLE_RATE_AUTH", "10/min"),
        "write": get("THROTTLE_RATE_WRITE", "60/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "x-clone API",
    "DESCRIPTION": (
        "API da rede social x-clone: contas, posts, curtidas, comentários e seguidores.\n\n"
        "Todo erro sai no mesmo envelope, com um campo `code` estável — ver "
        "common/errors.py. O cliente deve ramificar pelo `code`, nunca pela `message`."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

SIMPLE_JWT = {
    # 15 minutos, não 6 horas.
    #
    # O access token durava 6h porque o refresh não funcionava: REFRESH_TOKEN_LIFETIME
    # era `timedelta(seconds=0)`, ou seja, o refresh nascia expirado, e não havia rota
    # `/token/refresh/` registrada. Um access token longo era a compensação — e a errada:
    # ampliava a janela em que um token roubado do localStorage continua válido, e ainda
    # assim não evitava a expulsão, porque passadas as 6h o usuário era desconectado no
    # meio do que estava fazendo.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # Cada refresh emite um par novo e invalida o anterior. Um refresh token vazado só
    # serve até o dono usar o dele — a partir daí o vazado está na blacklist.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
