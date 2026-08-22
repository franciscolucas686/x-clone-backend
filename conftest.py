"""Fixtures compartilhadas por toda a suíte.

As factories abaixo seguem o padrão "builder com overrides": cada uma monta um objeto
válido por padrão e aceita sobrescritas pontuais. Isso mantém o teste falando só do que
ele realmente exercita — um teste sobre curtidas não precisa escolher um username.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from followers.models import Follow
from posts.models import Comment, Like, Post

User = get_user_model()


@pytest.fixture
def api():
    """Cliente anônimo. Use `auth` quando a rota exigir autenticação."""
    return APIClient()


@pytest.fixture
def make_user(db):
    """Cria um usuário. O contador evita colisão de username entre chamadas."""
    counter = {"n": 0}

    def _make_user(**overrides):
        counter["n"] += 1
        defaults = {
            "username": f"user{counter['n']}",
            "name": f"Usuário {counter['n']}",
            "password": "SenhaForte123!",
        }
        defaults.update(overrides)
        password = defaults.pop("password")
        avatar = defaults.pop("avatar", None)
        user = User.objects.create_user(password=password, **defaults)
        if avatar is not None:
            user.avatar = avatar
            user.save(update_fields=["avatar"])
        return user

    return _make_user


@pytest.fixture
def user(make_user):
    return make_user()


@pytest.fixture
def auth(api, user):
    """Cliente autenticado como `user`.

    `force_authenticate` em vez de bater no /token/: o que estes testes exercitam é a
    rota sob teste, não o fluxo de emissão de token — que tem os seus próprios testes.
    """
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def make_post(db):
    def _make_post(user, **overrides):
        defaults = {"text": "Conteúdo de teste"}
        defaults.update(overrides)
        return Post.objects.create(user=user, **defaults)

    return _make_post


@pytest.fixture
def make_comment(db):
    def _make_comment(user, post, **overrides):
        defaults = {"text": "Comentário de teste"}
        defaults.update(overrides)
        return Comment.objects.create(user=user, post=post, **defaults)

    return _make_comment


@pytest.fixture
def make_like(db):
    def _make_like(user, post):
        return Like.objects.create(user=user, post=post)

    return _make_like


@pytest.fixture
def make_follow(db):
    def _make_follow(follower, following):
        return Follow.objects.create(follower=follower, following=following)

    return _make_follow
