from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    text = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # A ordenação estava repetida em três views (`.order_by("-created_at")`). No
        # modelo ela é a regra, e as consultas a herdam — inclusive as que alguém
        # escrever depois e esquecer de ordenar. Uma listagem paginada sem ordenação
        # devolve páginas não-determinísticas: um item pode aparecer duas vezes ou sumir.
        ordering = ["-created_at"]
        indexes = [
            # Toda listagem ordena por esta coluna e nenhuma a indexava. O índice de
            # `user` vem de graça com a FK; o de data, não.
            models.Index(fields=["-created_at"], name="post_created_at_desc_idx"),
            # Timeline de um usuário: filtra por autor e ordena por data, na mesma query.
            models.Index(fields=["user", "-created_at"], name="post_user_created_idx"),
        ]

    def __str__(self):
        return f"Post de {self.user.username}"


class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="likes")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        constraints = [
            # Era `unique_together`, a forma legada. O mesmo par (usuário, post) não pode
            # existir duas vezes — é o que torna `get_or_create` seguro sob concorrência.
            models.UniqueConstraint(fields=["user", "post"], name="unique_like_per_user_post"),
        ]

    def __str__(self):
        return f"{self.user} curtiu {self.post_id}"


class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    # max_length que `Post.text` já tinha e este não: um comentário podia ter qualquer
    # tamanho. Como em TextField o limite é aplicado pelo serializer e não pelo banco, a
    # ausência aqui significava nenhum limite em lugar nenhum.
    text = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Sem ordenação, os comentários voltavam do banco em ordem indefinida.
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["post", "-created_at"], name="comment_post_created_idx"),
        ]

    def __str__(self):
        return f"Comentário de {self.user} em {self.post_id}"
