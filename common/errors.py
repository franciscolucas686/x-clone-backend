"""Erros de domínio com códigos estáveis.

O contrato entre backend e frontend é o `code`, nunca a mensagem.

Antes não havia contrato nenhum: cada erro saía num formato diferente
(`{"detail": ...}`, `{"campo": [...]}`, `{"message": ...}`), e o frontend compensava com
um `translateError()` que procurava **substrings em inglês** dentro do texto gerado pelo
Django — `"too short"`, `"already exists"`, `"No active account found"`. Atualizar o
Django, mudar LANGUAGE_CODE ou trocar um validador de senha fazia o `.includes()` parar
de casar, e o usuário passava a ver a mensagem crua em inglês no meio do cadastro.
Nenhum teste e nenhum type-check pegavam isso.

Com um código estável, o frontend traduz por identificador (`ERROR_CODE_MESSAGES` em
`shared/api/error-code-map.ts`) e o teste afirma o código, não uma frase.

Convenção: `<SUJEITO>_<CONDIÇÃO>` em SCREAMING_SNAKE_CASE, espelhando o nome da classe
sem o sufixo `Error`. Status: não encontrado -> 404, erro de quem chamou -> 400,
unicidade -> 409, credencial -> 401, autorização -> 403, infraestrutura -> 503.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class DomainError(APIException):
    """Base de todo erro de negócio.

    Herda de APIException para que o DRF já a reconheça como resposta esperada — e não
    como falha do servidor —, mas quem define a forma da resposta é o
    `common.exception_handler`, que lê o `code` daqui.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    code = "DOMAIN_ERROR"
    default_detail = "Não foi possível concluir a operação."

    def __init__(self, detail=None, *, details=None):
        super().__init__(detail or self.default_detail)
        # Erros por campo, quando existirem, para o formulário destacar o campo certo.
        self.details = details


# ─── Autenticação e conta ───────────────────────────────────────────────────────


class InvalidCredentials(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_CREDENTIALS"
    default_detail = "Usuário ou senha incorretos."


class UsernameAlreadyExists(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "USERNAME_ALREADY_EXISTS"
    default_detail = "Esse nome de usuário já está em uso."


class PasswordMismatch(DomainError):
    code = "PASSWORD_MISMATCH"
    default_detail = "As senhas não coincidem."


class UserNotFound(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "USER_NOT_FOUND"
    default_detail = "Usuário não encontrado."


# ─── Posts ──────────────────────────────────────────────────────────────────────


class PostNotFound(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "POST_NOT_FOUND"
    default_detail = "Esse post não existe mais."


# ─── Seguir ─────────────────────────────────────────────────────────────────────


class CannotFollowSelf(DomainError):
    code = "CANNOT_FOLLOW_SELF"
    default_detail = "Você não pode seguir a si mesmo."


# ─── Armazenamento de imagens ───────────────────────────────────────────────────


class StorageNotConfigured(DomainError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "STORAGE_NOT_CONFIGURED"
    default_detail = "O envio de imagens está indisponível no momento."


class AvatarUploadFailed(DomainError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "AVATAR_UPLOAD_FAILED"
    default_detail = "Não foi possível enviar a imagem agora. Tente novamente."


class UnsupportedMediaType(DomainError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "UNSUPPORTED_MEDIA_TYPE"
    default_detail = "Formato de arquivo não suportado. Envie uma imagem JPG, PNG ou WEBP."


class FileTooLarge(DomainError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "FILE_TOO_LARGE"
    default_detail = "A imagem é grande demais."
