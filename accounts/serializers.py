from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from common.errors import PasswordMismatch, UsernameAlreadyExists

from .models import User
from .services import default_avatar_url, issue_tokens, upload_avatar


class AvatarUrlField(serializers.ReadOnlyField):
    """URL do avatar, com o padrão resolvido na **leitura**.

    `avatar == ""` é como o banco representa "nunca escolheu foto" — uma representação
    para um estado, igual à decisão de `blank` sem `null` registrada em accounts/models.py.
    A URL do avatar padrão é configuração (`settings.DEFAULT_AVATAR_URL`), e configuração
    não se grava em cada linha.

    Antes só o `create()` do registro injetava a URL padrão. Quem nascia por
    `create_user`/`create_superuser` — o superusuário do admin, as factories dos testes,
    um seed com arquivo faltando — ficava com `""`, e o frontend renderizava `<img src="">`
    em sete dos oito lugares onde mostra avatar: nenhum deles tinha fallback.

    Resolvendo aqui, trocar `DEFAULT_AVATAR_URL` passa a valer para todo mundo na hora,
    sem migração de dados, e o contrato da API nunca devolve string vazia.
    """

    def to_representation(self, value):
        return value or default_avatar_url()


class RegisterSerializer(serializers.ModelSerializer):
    # Declarado com os validadores do modelo, explicitamente. A versão anterior era um
    # `CharField` cru com apenas o UniqueValidator, o que descartava em silêncio o
    # max_length=150 e o UnicodeUsernameValidator que o ModelSerializer traria sozinho —
    # ou seja, aceitava username de qualquer tamanho e com qualquer caractere.
    username = serializers.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
    )
    # `validate_password` não é mais um validador de campo: preso ao campo, o Django o
    # chama sem o argumento `user`, e o UserAttributeSimilarityValidator (que compara a
    # senha com username/name/email) faz `if not user: return` e nunca reprova nada — a
    # cadeia declarada em AUTH_PASSWORD_VALIDATORS ficava três quartos aplicada. Chamado
    # em validate(), com o usuário em construção, os quatro validadores valem.
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    avatar = serializers.FileField(required=False, allow_null=True, write_only=True)
    avatar_url = AvatarUrlField(source="avatar")
    joined_display = serializers.SerializerMethodField()

    # Aditivo: o par de tokens do usuário recém-criado, para o cliente não precisar
    # chamar /token/ logo depois de /register/ e pagar um segundo hash de senha. Um
    # cliente que não leia este campo continua funcionando exatamente como antes.
    tokens = serializers.SerializerMethodField()

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
            "tokens",
        ]

    def get_joined_display(self, obj) -> str:
        return obj.date_joined.strftime("%d/%m/%Y")

    def get_tokens(self, obj) -> dict:
        return issue_tokens(obj)

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

        # Usuário só em memória, nunca salvo: é o bastante para o
        # UserAttributeSimilarityValidator comparar a senha com username/name.
        candidato = User(username=data.get("username", ""), name=data.get("name", ""))
        try:
            validate_password(data["password"], user=candidato)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc

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
        #
        # Sem foto, nada é gravado: `avatar` fica "" e o AvatarUrlField resolve o padrão na
        # leitura. Gravar a URL padrão aqui deixava uma cópia da configuração em cada linha
        # e apagava a diferença entre "escolheu esta foto" e "não escolheu nenhuma" — que é
        # o que a edição de perfil precisa saber para oferecer o botão de remover.
        if avatar:
            user.avatar = upload_avatar(avatar, user=user)
            user.save(update_fields=["avatar"])
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    joined_display = serializers.SerializerMethodField()

    # `validate_password` também aqui. O cadastro aplicava a cadeia de validadores do
    # Django e a **troca de senha não**: dava para registrar com senha forte e depois
    # trocá-la por "123" pelo perfil. A regra valia só na porta da frente.
    # Mesmo motivo do RegisterSerializer: preso ao campo, validate_password roda sem
    # `user` e o UserAttributeSimilarityValidator não faz nada. Aqui `self.instance` já é
    # o usuário de verdade, então nem precisa de um objeto provisório.
    password = serializers.CharField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)

    # `allow_null` para que o cliente possa **remover** a foto e voltar ao avatar
    # padrão. Não havia como: o botão "remover" do EditProfileModal só limpava o preview
    # local, porque o thunk filtrava valores vazios do FormData e o campo nunca chegava
    # ao servidor.
    avatar = serializers.FileField(required=False, allow_null=True, write_only=True)
    avatar_url = AvatarUrlField(source="avatar")

    # "Esta pessoa escolheu uma foto?" — o fato, em vez de o cliente deduzi-lo.
    #
    # O EditProfileModal decidia se mostrava o botão "remover foto" comparando a URL atual
    # com a do avatar padrão. Para isso o frontend precisava conhecer essa URL, e ela
    # acabou escrita à mão nos dois repositórios (accounts/serializers.py e config.ts),
    # onde podiam divergir em silêncio: bastava trocar DEFAULT_AVATAR_URL de um lado.
    has_custom_avatar = serializers.SerializerMethodField()

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
            "has_custom_avatar",
        ]

    def get_has_custom_avatar(self, obj) -> bool:
        return bool(obj.avatar)

    def get_joined_display(self, obj) -> str:
        # Method field de propósito: é formatação de data, não consulta. Os quatro que
        # foram removidos daqui custavam uma query cada, por usuário serializado.
        return obj.date_joined.strftime("%d/%m/%Y")

    def validate(self, data):
        password = data.get("password")
        confirm_password = data.get("confirm_password")

        if (password or confirm_password) and password != confirm_password:
            raise PasswordMismatch(details={"confirm_password": ["As senhas não coincidem."]})

        if password:
            try:
                validate_password(password, user=self.instance)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc

        return data

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        validated_data.pop("confirm_password", None)

        # `avatar` ausente significa "não mexeu"; `avatar` presente e nulo significa
        # "remover". São coisas diferentes, e tratá-las igual é o que tornava a remoção
        # impossível de expressar.
        if "avatar" in validated_data:
            arquivo = validated_data.pop("avatar")
            # Remover devolve o campo a "", o mesmo estado de quem nunca escolheu foto — e
            # o AvatarUrlField resolve o padrão na leitura.
            instance.avatar = upload_avatar(arquivo, user=instance) if arquivo else ""

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance


class UserFeedSerializer(serializers.ModelSerializer):
    avatar_url = AvatarUrlField(source="avatar")

    class Meta:
        model = User
        fields = ["id", "username", "name", "avatar_url"]
