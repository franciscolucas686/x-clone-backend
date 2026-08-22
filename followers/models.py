from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Follow(models.Model):
    follower = models.ForeignKey(User, related_name="following", on_delete=models.CASCADE)
    following = models.ForeignKey(User, related_name="followers", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["follower", "following"], name="unique_follow_relation"
            ),
            # `condition=`, não `check=`: o segundo foi depreciado no Django 5.1 e emitia
            # RemovedInDjango60Warning em todo import do módulo.
            #
            # Esta constraint existia só no models.py — nunca foi migrada. A regra
            # "não pode seguir a si mesmo" estava declarada em três lugares (a view, um
            # serializer que ninguém usava, e aqui) e vigorava em um só. No banco não
            # havia nada impedindo a linha.
            models.CheckConstraint(
                condition=~models.Q(follower=models.F("following")),
                name="prevent_self_follow",
            ),
        ]

    def __str__(self):
        return f"{self.follower} segue {self.following}"
