from django.urls import path

from .views import (
    FollowingPostsView,
    LikePostView,
    PostCommentsView,
    PostListCreateView,
    UserPostsView,
)

# Montado em /api/v1/posts/. A rota de posts de um usuário vive em
# /api/v1/users/<username>/posts/ (ver backend/urls.py): é um recurso de usuário, e
# aqui ela se chamava "user/<username>/posts/", repetindo "posts" no caminho final.
urlpatterns = [
    path("", PostListCreateView.as_view(), name="post-list-create"),
    path("following/", FollowingPostsView.as_view(), name="following-posts"),
    path("<int:pk>/like/", LikePostView.as_view(), name="like-post"),
    path("<int:pk>/comments/", PostCommentsView.as_view(), name="post-comments"),
    # Alias legado: o frontend publicado ainda faz POST em /comment/ (singular).
    path("<int:pk>/comment/", PostCommentsView.as_view(), name="comment-post"),
    # Alias legado. O caminho canônico é /api/v1/users/<username>/posts/; este continua
    # respondendo porque o frontend publicado ainda o chama, e os dois deploys são
    # independentes. Sai junto com os demais aliases, quando os dois lados estiverem
    # em v1.
    path("user/<str:username>/posts/", UserPostsView.as_view(), name="user-posts-legacy"),
]
