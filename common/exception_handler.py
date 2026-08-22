"""Tradutor único de exceções para resposta HTTP.

Toda resposta de erro da API sai daqui, no mesmo formato:

    {
      "code":        "INVALID_CREDENTIALS",   # identificador estável
      "message":     "Usuário ou senha incorretos.",
      "details":     {"campo": ["..."]} | null,   # erros por campo, quando houver
      "status_code": 401,
      "path":        "/api/v1/token/"
    }

`code` é o contrato. `message` existe para log e para fallback, mas o cliente decide o
texto que mostra a partir do código — é isso que impede a mensagem em português de
depender da prosa em inglês que o Django gera internamente.
"""

import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    Throttled,
    ValidationError,
)
from rest_framework.exceptions import (
    PermissionDenied as DRFPermissionDenied,
)
from rest_framework.exceptions import (
    UnsupportedMediaType as DRFUnsupportedMediaType,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .errors import DomainError, InvalidCredentials

logger = logging.getLogger(__name__)

# Códigos para exceções que o DRF levanta antes de qualquer código nosso rodar, e que
# por isso não têm como carregar um `code` próprio. Sem esta tabela elas cairiam no
# fallback genérico e o frontend não teria como distingui-las.
_EXCEPTION_CODES = {
    NotAuthenticated: "AUTHENTICATION_REQUIRED",
    AuthenticationFailed: "AUTHENTICATION_FAILED",
    DRFPermissionDenied: "PERMISSION_DENIED",
    NotFound: "NOT_FOUND",
    MethodNotAllowed: "METHOD_NOT_ALLOWED",
    ParseError: "PARSE_ERROR",
    Throttled: "TOO_MANY_REQUESTS",
    DRFUnsupportedMediaType: "UNSUPPORTED_MEDIA_TYPE",
    ValidationError: "VALIDATION_ERROR",
}

# Códigos que bibliotecas já produzem, traduzidos para os nossos.
#
# O simplejwt é o caso relevante: ele distingue token expirado/malformado
# ("token_not_valid") de credencial errada no login ("no_active_account"), e o cliente
# precisa dessa distinção — um manda renovar a sessão, o outro manda conferir a senha.
# Sem o mapeamento, os dois viravam AUTHENTICATION_FAILED genérico.
#
# "no_active_account" é justamente o erro cuja mensagem em inglês ("No active account
# found with the given credentials") o translateError do frontend procurava por
# substring para exibir "Usuário ou senha incorretos!".
_LIBRARY_CODES = {
    "token_not_valid": "TOKEN_NOT_VALID",
    "no_active_account": "INVALID_CREDENTIALS",
}

# Códigos de biblioteca cuja **mensagem** também deve ser substituída pela nossa. A
# mensagem do simplejwt para credencial inválida é o literal em inglês "No active account
# found with the given credentials"; o cliente traduz pelo code, mas deixá-la passar faria
# a mesma frase aparecer no log e em qualquer consumidor que use o passthrough.
_LIBRARY_MESSAGES = {
    "INVALID_CREDENTIALS": InvalidCredentials.default_detail,
}


def _collect_codes(codes) -> set[str]:
    """Achata o retorno de `APIException.get_codes()`, que pode ser str, list ou dict."""
    if isinstance(codes, str):
        return {codes}
    if isinstance(codes, list):
        return {c for item in codes for c in _collect_codes(item)}
    if isinstance(codes, dict):
        return {c for value in codes.values() for c in _collect_codes(value)}
    return set()


def _resolve_code(exc) -> str:
    if isinstance(exc, DomainError):
        return exc.code

    if isinstance(exc, APIException):
        # get_codes() é a API do DRF para isso. Ler `exc.detail.code` não serve: no
        # InvalidToken do simplejwt o `detail` é um dict, e dicts não têm `.code`.
        for encontrado in _collect_codes(exc.get_codes()):
            if encontrado in _LIBRARY_CODES:
                return _LIBRARY_CODES[encontrado]

    for klass, code in _EXCEPTION_CODES.items():
        if isinstance(exc, klass):
            return code

    return "INTERNAL_ERROR"


def _flatten_message(detail) -> str:
    """Extrai uma frase legível de qualquer formato que o DRF produza."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return _flatten_message(detail[0]) if detail else "Erro na requisição."
    if isinstance(detail, dict):
        for value in detail.values():
            return _flatten_message(value)
    return str(detail)


def _field_details(exc):
    """Erros por campo, preservados para o formulário destacar o campo certo.

    Só faz sentido em ValidationError: nos demais, `detail` é uma frase só.
    """
    if not isinstance(exc, ValidationError):
        return None
    detail = exc.detail
    if isinstance(detail, dict):
        return {campo: [str(m) for m in _as_list(msgs)] for campo, msgs in detail.items()}
    if isinstance(detail, list):
        return {"non_field_errors": [str(m) for m in detail]}
    return None


def _as_list(value):
    return value if isinstance(value, list) else [value]


def custom_exception_handler(exc, context):
    """Wired em REST_FRAMEWORK["EXCEPTION_HANDLER"]."""
    # Http404 e PermissionDenied do Django não são APIException; o handler do DRF as
    # converte para NotFound/PermissionDenied antes de qualquer coisa.
    if isinstance(exc, Http404):
        exc = NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = DRFPermissionDenied()

    response = drf_exception_handler(exc, context)
    request = context.get("request")
    path = getattr(request, "path", "")

    if response is None:
        # Exceção não tratada: é falha nossa, não do cliente. Vai para o log com stack
        # completo, e para o cliente vai só um código genérico — mensagem de erro
        # interna não é informação que o navegador deva receber.
        logger.exception("Erro não tratado em %s", path)
        return Response(
            {
                "code": "INTERNAL_ERROR",
                "message": "Ocorreu um erro inesperado. Tente novamente em instantes.",
                "details": None,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "path": path,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code = _resolve_code(exc)
    message = _LIBRARY_MESSAGES.get(code) or _flatten_message(getattr(exc, "detail", response.data))
    details = getattr(exc, "details", None) or _field_details(exc)

    if response.status_code >= 500:
        logger.error("[%s] %s em %s", response.status_code, code, path)
    else:
        logger.warning("[%s] %s em %s — %s", response.status_code, code, path, message)

    response.data = {
        "code": code,
        "message": message,
        "details": details,
        "status_code": response.status_code,
        "path": path,
    }
    return response


__all__ = ["custom_exception_handler", "APIException"]
