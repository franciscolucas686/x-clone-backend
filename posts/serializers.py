from rest_framework import serializers

from accounts.serializers import UserFeedSerializer

from .models import Comment, Post


class CommentSerializer(serializers.ModelSerializer):
    user = UserFeedSerializer(read_only=True)
    post = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "user", "post", "text", "created_at"]


class PostSerializer(serializers.ModelSerializer):
    """Post como aparece numa listagem.

    Os comentários **não** vêm aninhados. Vinham, completos e sem limite, em todo post do
    feed — cada um com o objeto do autor. O tamanho da resposta crescia sem teto e sem
    relação com o que a tela mostra: `Post.tsx` exibe só `comments_count`, então um post
    com 500 comentários era baixado inteiro para renderizar o número 500. Paginar 10
    posts por página não limitava nada.

    Quem precisa dos comentários usa GET /api/v1/posts/<id>/comments/, que é paginado e
    ordenado. É a mesma separação entre DTO de listagem e DTO de detalhe do
    api-real-estate.
    """

    user = UserFeedSerializer(read_only=True)
    # Anotados em posts/selectors.py. `is_liked` era um EXISTS por post dentro do
    # serializer, apesar de `likes` já estar no prefetch.
    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Post
        fields = ["id", "user", "text", "created_at", "likes_count", "comments_count", "is_liked"]
