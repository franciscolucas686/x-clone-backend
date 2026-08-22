"""Roteamento da API.

As rotas vivem sob `/api/v1/`. Os caminhos antigos, sem versão, continuam respondendo
como **alias** durante a transição: backend e frontend têm deploys independentes (Render
e Vercel), então um subir antes do outro não pode derrubar o app. Os aliases saem num
commit próprio, quando os dois lados já estiverem em v1.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from accounts.views import (
    ProfileView,
    RegisterView,
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
    UserDetailView,
    UserListView,
)
from common.views import healthz
from posts.views import UserPostsView

# Rotas de autenticação e conta. Ficavam soltas na raiz de `/api/` (`/api/register/`,
# `/api/token/`, `/api/profile/`), enquanto posts e follow tinham prefixo de recurso.
auth_patterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path("profile/", ProfileView.as_view(), name="profile"),
]

user_patterns = [
    path("", UserListView.as_view(), name="user-list"),
    # Substitui `/api/posts/user/<username>/posts/`, que dizia "posts" duas vezes e
    # colocava um recurso de usuário sob o prefixo de posts.
    path("<str:username>/posts/", UserPostsView.as_view(), name="user-posts"),
    path("<str:username>/", UserDetailView.as_view(), name="user-detail"),
]

api_v1_patterns = [
    *auth_patterns,
    path("users/", include(user_patterns)),
    path("posts/", include("posts.urls")),
    path("follow/", include("followers.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    # Sem prefixo /api/: um serviço de monitoramento externo aponta para uma URL fixa,
    # e não deveria depender de a API estar versionada em v1, v2 etc.
    path("healthz/", healthz, name="healthz"),
    path("api/v1/", include((api_v1_patterns, "v1"), namespace="v1")),
    # ─── Aliases sem versão, mantidos para a transição ───────────────────────
    #
    # As mesmas views nos caminhos antigos. Este include é o não-namespaced, então
    # `reverse("user-list")` devolve o caminho legado e `reverse("v1:user-list")` o
    # versionado — o que deixa os testes exercitarem explicitamente os dois.
    path("api/", include(api_v1_patterns)),
    # ─── Documentação gerada do código ───────────────────────────────────────
    # A única documentação da API era ler as views; o README não listava um endpoint
    # sequer. Gerada do código, ela não tem como divergir dele.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG:
    # Só em desenvolvimento: em produção os uploads vão para o Cloudinary e os estáticos
    # são servidos pelo WhiteNoise. A chamada era incondicional, o que dava a impressão
    # de que o Django serviria mídia em produção.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
