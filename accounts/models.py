from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # `blank=True` sem `null=True`: em campo de texto, NULL e string vazia significariam
    # a mesma coisa e criariam duas representações do mesmo estado — cada consulta
    # precisaria testar as duas, e cada consumidor tratar `null` além de `""`.
    name = models.CharField(max_length=150, blank=True, default="")
    # URL do avatar. Não é ImageField: o arquivo vive no Cloudinary e o que guardamos é o
    # endereço público dele. O upload passa por accounts/services.py.
    avatar = models.CharField(max_length=500, blank=True, default="")

    def __str__(self):
        return self.username
