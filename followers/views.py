from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import UserProfileSerializer
from common.errors import CannotFollowSelf, UserNotFound

from .models import Follow

User = get_user_model()


@extend_schema(
    request=None,
    responses=inline_serializer(
        name="FollowToggleResponse",
        fields={
            "is_following": serializers.BooleanField(),
            "followers_count": serializers.IntegerField(),
            "target_user": UserProfileSerializer(required=False),
        },
    ),
    summary="Alterna seguir/deixar de seguir",
    description="201 ao começar a seguir, 200 ao deixar de seguir.",
)
class FollowToggleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, user_id):
        try:
            target_user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise UserNotFound() from None

        if request.user == target_user:
            # A mesma regra também existe como CheckConstraint em followers/models.py.
            # Aqui ela produz uma mensagem; lá ela garante que nem um bug nem um acesso
            # direto ao banco consigam gravar a linha.
            raise CannotFollowSelf()

        follow, created = Follow.objects.get_or_create(follower=request.user, following=target_user)

        if not created:
            follow.delete()
            return Response(
                {"is_following": False, "followers_count": target_user.followers.count()},
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "is_following": True,
                "followers_count": target_user.followers.count(),
                "target_user": UserProfileSerializer(
                    target_user, context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class FollowersListView(generics.ListAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        user_id = self.kwargs.get("user_id")
        return User.objects.filter(following__following=user_id).distinct().order_by("id")


class FollowingListView(generics.ListAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        user_id = self.kwargs.get("user_id")
        return User.objects.filter(followers__follower=user_id).distinct().order_by("id")
