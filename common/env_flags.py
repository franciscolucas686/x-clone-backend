"""Sinais de ambiente usados pelas guardas dos comandos destrutivos.

Ficam num módulo próprio para poderem ser sobrescritos em teste sem tocar em settings, e
para que a pergunta "isto é produção?" tenha uma resposta só no projeto inteiro.
"""

from django.conf import settings

from backend.settings.env import get_bool


def settings_module_is_production() -> bool:
    return (settings.SETTINGS_MODULE or "").endswith("production")


def seed_is_enabled() -> bool:
    return get_bool("RUN_SEED", default=False)
