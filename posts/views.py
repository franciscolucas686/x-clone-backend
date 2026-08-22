from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.errors import PostNotFound

from .models import Like, Post
from .selectors import comments_of, feed_for, posts_by_username, posts_with_stats
from .serializers import CommentSerializer, PostSerializer


def _get_post_or_404(pk) -> Post:
    """Busca um post ou levanta POST_NOT_FOUND.

    Antes era `Post.objects.get(pk=pk)` cru. `Post.DoesNotExist` não é uma APIException,
    então escapava do DRF e virava **500**. Curtir ou comentar um post que outro usuário
    acabou de apagar é rotina num feed, e um 500 é indistinguível de falha real do
    servidor: polui o monitoramento e não dá ao cliente como reagir.
    """
    try:
        return Post.objects.get(pk=pk)
    except Post.DoesNotExist:
        raise PostNotFound() from None


class PostListCreateView(generics.ListCreateAPIView):
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return posts_with_stats(viewer=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_serializer(self, *args, **kwargs):
        """Reconsulta o post recém-criado pelo selector.

        Sem isto, a resposta do POST sairia sem `likes_count`, `comments_count` e
        `is_liked` — a instância recém-salva não passou pelo annotate, e o serializer
        agora lê esses campos das anotações em vez de recalculá-los.
        """
        return super().get_serializer(*args, **kwargs)

    def create(self, request, *args, **kwargs):
        resposta = super().create(request, *args, **kwargs)
        criado = posts_with_stats(viewer=request.user).get(pk=resposta.data["id"])
        resposta.data = self.get_serializer(criado).data
        return resposta


class FollowingPostsView(generics.ListAPIView):
    """Feed: posts de quem o usuário segue, mais os dele."""

    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return feed_for(self.request.user)


class UserPostsView(generics.ListAPIView):
    """Timeline pública de um usuário."""

    serializer_class = PostSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return posts_by_username(self.kwargs["username"], viewer=self.request.user)


@extend_schema(
    request=None,
    responses=PostSerializer,
    summary="Alterna a curtida no post",
    description="Curte se ainda não curtiu, descurte se já curtiu. Devolve o post atualizado.",
)
class LikePostView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        post = _get_post_or_404(pk)
        like, created = Like.objects.get_or_create(user=request.user, post=post)
        if not created:
            like.delete()

        # Devolve o post inteiro, relido pelo selector: o cliente substitui o item da
        # lista pelo que o servidor afirma, em vez de deduzir o novo estado.
        #
        # A resposta anterior era {"message": "Curtido"|"Descurtido", "post": {...}}, e o
        # frontend comparava `message === "Curtido"` para saber se tinha curtido — uma
        # string de UI em português usada como protocolo. Traduzir a interface para outro
        # idioma quebraria a lógica de curtidas.
        atualizado = posts_with_stats(viewer=request.user).get(pk=post.pk)
        return Response(PostSerializer(atualizado).data, status=status.HTTP_200_OK)


class PostCommentsView(generics.ListCreateAPIView):
    """Comentários de um post: listagem paginada e criação.

    A listagem é nova. Antes a única forma de obter os comentários era pelo feed, que os
    trazia aninhados e sem limite em todo post.
    """

    serializer_class = CommentSerializer

    def get_permissions(self):
        # Ler é público — a timeline de um usuário também é. Escrever exige conta.
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        return comments_of(self.kwargs["pk"])

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, post=_get_post_or_404(self.kwargs["pk"]))


# Alias mantido: o frontend publicado ainda faz POST em /posts/<id>/comment/.
CommentPostView = PostCommentsView
