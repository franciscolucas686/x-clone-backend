from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from rest_framework import serializers

from common.errors import PasswordMismatch, UsernameAlreadyExists

from .models import User
from .services import default_avatar_url, upload_avatar


class RegisterSerializer(serializers.ModelSerializer):
    # Declarado com os validadores do modelo, explicitamente. A versão anterior era um
    # `CharField` cru com apenas o UniqueValidator, o que descartava em silêncio o
    # max_length=150 e o UnicodeUsernameValidator que o ModelSerializer traria sozinho —
    # ou seja, aceitava username de qualquer tamanho e com qualquer caractere.
    username = serializers.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
    )
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    avatar = serializers.FileField(required=False, allow_null=True, write_only=True)
    avatar_url = serializers.CharField(required=False, source="avatar", read_only=True)
    joined_display = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "name",
            "password",
            "confirm_password",
            "avatar",
            "avatar_url",
            "joined_display",
        ]

    def get_joined_display(self, obj) -> str:
        return obj.date_joined.strftime("%d/%m/%Y")

    def validate_username(self, value):
        """Unicidade como erro de domínio, não como erro de validação genérico.

        O UniqueValidator do DRF produzia a frase em inglês "A user with that username
        already exists.", que o frontend traduzia procurando a substring
        "already exists". Com USERNAME_ALREADY_EXISTS o cliente decide o texto pelo
        código, e `details` mantém o campo para o formulário destacar.
        """
        if User.objects.filter(username__iexact=value).exists():
            raise UsernameAlreadyExists(
                details={"username": ["Esse nome de usuário já está em uso."]}
            )
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise PasswordMismatch(details={"confirm_password": ["As senhas não coincidem."]})
        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        avatar = validated_data.pop("avatar", None)
        user = User.objects.create_user(
            username=validated_data["username"],
            # .get() e não [""]: `name` é blank/null no modelo, então o DRF o gera como
            # required=False. Cadastrar sem enviar `name` levantava KeyError, que virava
            # 500. Nenhum teste pegava porque todos mandavam o campo.
            name=validated_data.get("name", ""),
            password=validated_data["password"],
        )

        # Um caminho só para o avatar, igual ao da edição de perfil. Antes o registro
        # atribuía o objeto de arquivo direto ao CharField, persistindo o nome do
        # arquivo em vez de uma URL — o avatar de quem se cadastrava com foto nunca
        # carregava.
        user.avatar = upload_avatar(avatar, user=user) if avatar else default_avatar_url()
        user.save(update_fields=["avatar"])
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    joined_display = serializers.SerializerMethodField()

    # `validate_password` também aqui. O cadastro aplicava a cadeia de validadores do
    # Django e a **troca de senha não**: dava para registrar com senha forte e depois
    # trocá-la por "123" pelo perfil. A regra valia só na porta da frente.
    password = serializers.CharField(
        write_only=True, required=False, validators=[validate_password]
    )
    confirm_password = serializers.CharField(write_only=True, required=False)

    # `allow_null` para que o cliente possa **remover** a foto e voltar ao avatar
    # padrão. Não havia como: o botão "remover" do EditProfileModal só limpava o preview
    # local, porque o thunk filtrava valores vazios do FormData e o campo nunca chegava
    # ao servidor.
    avatar = serializers.FileField(required=False, allow_null=True, write_only=True)
    avatar_url = serializers.CharField(required=False, source="avatar", read_only=True)

    # Lidos das anotações do selector (accounts/selectors.py), não recalculados aqui.
    # Como SerializerMethodField, cada um destes disparava uma query por usuário
    # serializado: ~40 numa página de 10.
    posts_count = serializers.IntegerField(read_only=True)
    followers_count = serializers.IntegerField(read_only=True)
    following_count = serializers.IntegerField(read_only=True)
    is_following = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "name",
            "avatar",
            "avatar_url",
            "joined_display",
            "password",
            "confirm_password",
            "is_following",
            "followers_count",
            "following_count",
            "posts_count",
        ]

    def get_joined_display(self, obj) -> str:
        # Method field de propósito: é formatação de data, não consulta. Os quatro que
        # foram removidos daqui custavam uma query cada, por usuário serializado.
        return obj.date_joined.strftime("%d/%m/%Y")

    def validate(self, data):
        password = data.get("password")
        confirm_password = data.get("confirm_password")

        if (password or confirm_password) and password != confirm_password:
            raise PasswordMismatch(details={"confirm_password": ["As senhas não coincidem."]})

        return data

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        validated_data.pop("confirm_password", None)

        # `avatar` ausente significa "não mexeu"; `avatar` presente e nulo significa
        # "remover". São coisas diferentes, e tratá-las igual é o que tornava a remoção
        # impossível de expressar.
        if "avatar" in validated_data:
            arquivo = validated_data.pop("avatar")
            instance.avatar = (
                upload_avatar(arquivo, user=instance) if arquivo else default_avatar_url()
            )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance


class UserFeedSerializer(serializers.ModelSerializer):
    avatar_url = serializers.CharField(source="avatar", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "name", "avatar_url"]
