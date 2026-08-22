"""Leitura e validação das variáveis de ambiente.

O ambiente inteiro é conferido **na importação das settings**, antes de o Django montar
qualquer coisa. Uma variável faltando vira erro de boot nomeando a variável — não uma
falha na primeira requisição que a usa, longe da causa.

O caso concreto que isto resolve: `SECRET_KEY` tinha o default literal
`"unsafe-default-key"`, versionado no repositório. Sem a variável, produção subia
normalmente assinando os JWT com uma chave pública. Nada nos logs dizia isso; a descoberta
seria um token forjado.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# Um `.env` no repositório é conveniência de desenvolvimento. Em produção não existe
# arquivo nenhum: Render, Fly e afins injetam as variáveis direto no processo.
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file))


# Django gera SECRET_KEY com 50 caracteres. Abaixo disso o valor quase certamente é um
# placeholder digitado à mão, não uma chave gerada.
MIN_SECRET_KEY_LENGTH = 50


def get(name: str, default: str = "") -> str:
    """Lê uma variável tratando string vazia como ausente.

    Num arquivo `.env` não há como escrever "indefinido": quem quer deixar uma variável
    de fora ou apaga a linha ou escreve `VAR=`. Os dois precisam significar a mesma
    coisa, senão um `VAR=` reprova numa validação logo abaixo de um comentário mandando
    deixá-la vazia.
    """
    value = os.environ.get(name) or env(name, default="")
    return value.strip() or default


def require(name: str, *, min_length: int | None = None) -> str:
    """Lê uma variável obrigatória, ou aborta o boot dizendo qual é."""
    value = get(name)
    if not value:
        raise ImproperlyConfigured(
            f"A variável de ambiente {name} é obrigatória neste ambiente e não está "
            f"definida. Veja .env.example para o que ela significa."
        )
    if min_length is not None and len(value) < min_length:
        raise ImproperlyConfigured(
            f"A variável de ambiente {name} precisa ter no mínimo {min_length} "
            f"caracteres (tem {len(value)}). Gere uma com:\n"
            f'  python -c "from django.core.management.utils import get_random_secret_key; '
            f'print(get_random_secret_key())"'
        )
    return value


def require_list(name: str) -> list[str]:
    """Lê uma lista separada por vírgula, obrigatória e não vazia."""
    raw = require(name)
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise ImproperlyConfigured(
            f"A variável de ambiente {name} está definida mas não contém nenhum valor "
            f"utilizável. Use uma lista separada por vírgula."
        )
    return values


def require_origin_list(name: str) -> list[str]:
    """Como `require_list`, mas para origens CORS: sem barra no fim.

    Uma origem, por definição do próprio CORS, é só esquema + host + porta — nunca um
    caminho. `django-cors-headers` recusa `"https://exemplo.com/"` com
    `corsheaders.E014` e derruba o boot, mas é um erro fácil demais de cometer: colar a
    URL direto da barra de endereços do navegador já vem com a barra. Normalizar aqui
    evita o boot morrer por um caractere que não muda nada do que a variável deveria
    dizer.
    """
    return [origem.rstrip("/") for origem in require_list(name)]


def get_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = get(name)
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_bool(name: str, default: bool = False) -> bool:
    raw = get(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


# ─── Banco de dados ──────────────────────────────────────────────────────────
#
# Todo Postgres gerenciado — Neon, Render, Supabase, Railway — entrega **uma**
# connection string, não quatro variáveis separadas. Aceitar só as quatro fazia o
# caminho óbvio (copiar a URL do painel e colar) abortar o boot pedindo DATABASE_NAME.
#
# O parse é feito com a stdlib em vez de `dj-database-url`. São vinte linhas, os casos
# que importam estão cobertos por teste, e o pacote já esteve no requirements.txt sem
# nenhum importador — uma dependência a menos para justificar.

# `require` é o default de produção porque todo Postgres gerenciado exige TLS e recusa
# conexão sem ele. Deixar explícito evita depender do default do driver, que é `prefer`
# — e `prefer` cai para texto puro em silêncio se o TLS falhar.
DEFAULT_SSLMODE = "require"


def parse_database_url(url: str) -> dict:
    """Quebra uma connection string do Postgres nos campos que o Django espera.

    Aceita os esquemas `postgres://` e `postgresql://`. Usuário e senha vêm
    percent-decodificados: senhas geradas por painel costumam trazer `@`, `/` e `#`
    escapados, e passá-los codificados adiante faz a autenticação falhar com "senha
    incorreta" — o erro que menos aponta para a causa.
    """
    partes = urlparse(url)

    if partes.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(
            f"DATABASE_URL precisa começar com postgres:// ou postgresql:// "
            f"(recebido: {partes.scheme or 'sem esquema'}://)."
        )

    nome = partes.path.lstrip("/")
    if not nome:
        raise ImproperlyConfigured("DATABASE_URL não indica o nome do banco após a barra.")

    # sslmode declarado na própria URL vence a variável de ambiente: quem colou a string
    # do painel espera que ela seja respeitada por inteiro.
    sslmode = DEFAULT_SSLMODE
    for parametro in partes.query.split("&"):
        chave, _, valor = parametro.partition("=")
        if chave == "sslmode" and valor:
            sslmode = valor

    return {
        "NAME": nome,
        "USER": unquote(partes.username or ""),
        "PASSWORD": unquote(partes.password or ""),
        "HOST": partes.hostname or "",
        "PORT": str(partes.port or 5432),
        "OPTIONS": {"sslmode": sslmode},
    }


def database_config(*, required: bool) -> dict:
    """Config do banco, vinda de DATABASE_URL ou das quatro variáveis separadas.

    `required=True` (produção) aborta o boot se nenhuma das duas formas estiver completa.
    """
    url = get("DATABASE_URL")
    if url:
        return parse_database_url(url)

    ler = require if required else get
    sslmode = get("DATABASE_SSLMODE", DEFAULT_SSLMODE if required else "prefer")

    return {
        "NAME": ler("DATABASE_NAME"),
        "USER": ler("DATABASE_USER"),
        "PASSWORD": ler("DATABASE_PASSWORD"),
        "HOST": ler("DATABASE_HOST"),
        "PORT": get("DATABASE_PORT", "5432"),
        "OPTIONS": {"sslmode": sslmode},
    }
