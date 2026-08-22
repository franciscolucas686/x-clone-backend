from rest_framework import generics, parsers, permissions
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User
from .selectors import discoverable_users, users_with_stats
from .serializers import RegisterSerializer, UserProfileSerializer


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    # Sem limite, criar contas em massa não tem custo nenhum.
    throttle_scope = "auth"


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Login com limite por IP.

    Subclasse só para carregar o escopo: a view do simplejwt não declara nenhum, e sem
    isso tentar senha por força bruta contra /token/ é ilimitado.
    """

    throttle_scope = "auth"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_scope = "auth"


class ProfileView(generics.RetrieveUpdateAPIView):
    """Perfil do usuário autenticado.

    `get_object` devolve `request.user`, então a URL não carrega id e não há como pedir o
    perfil de outra pessoa por aqui.
    """

    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def get_object(self):
        # Passa pelo selector para que o próprio perfil traga as mesmas contagens que a
        # listagem — antes elas vinham de method fields, uma query cada.
        return users_with_stats(viewer=self.request.user).get(pk=self.request.user.pk)


class UserListView(generics.ListAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return discoverable_users(
            viewer=self.request.user,
            search=self.request.query_params.get("search", ""),
        )


class UserDetailView(generics.RetrieveAPIView):
    serializer_class = UserProfileSerializer
    lookup_field = "username"
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return users_with_stats(viewer=self.request.user)
