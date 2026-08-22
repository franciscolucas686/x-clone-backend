# Arquitetura

Este documento explica **por que** o código está organizado como está. Cada decisão aqui
substituiu algo concreto que não funcionava; onde isso for relevante, o defeito anterior
está descrito, porque é ele que justifica a escolha.

---

## Princípio geral

O projeto é pequeno — cerca de 1.500 linhas de Python. As camadas abaixo existem porque
havia um problema específico, não porque uma arquitetura de referência as pede. Não há
repositórios, casos de uso nem injeção de dependência: nesse tamanho seriam cerimônia, e
cerimônia é tão cara quanto acoplamento.

---

## Camadas

```
HTTP        views.py          recebe, autoriza, delega, responde
Domínio     services.py       operações que mudam estado ou falam com o mundo externo
Leitura     selectors.py      consultas, com as anotações que evitam N+1
Contrato    serializers.py    forma da entrada e da saída
Dados       models.py         estrutura e invariantes
```

**As views não têm regra de negócio.** Elas traduzem HTTP em chamada de domínio e de
volta. Antes, uma view decidia se um usuário podia seguir a si mesmo, um serializer
chamava a API do Cloudinary, e as contagens de perfil eram quatro consultas escondidas
dentro de métodos de serialização.

**Os services não conhecem HTTP.** Não importam `Request`, `Response` nem `HttpStatus`.
Comunicam falha levantando `DomainError`, e quem decide o status é o exception handler.

**Os selectors devolvem querysets, não listas.** Isso mantém a paginação lazy e permite
que a view componha mais filtros por cima.

### Por que `selectors.py` existe

`UserProfileSerializer` tinha quatro `SerializerMethodField` — `posts_count`,
`followers_count`, `following_count`, `is_following` — cada um com sua própria consulta,
executada **por usuário serializado**. Uma página de 10 usuários custava cerca de 40
consultas além da página.

Pior: `UserListView` já anotava `is_following` com `Exists()`, mas um
`SerializerMethodField` de mesmo nome sombreia a anotação — o banco fazia o `EXISTS` e o
serializer refazia a consulta. O custo era pago duas vezes e aproveitado nenhuma.

Hoje as anotações vivem em `selectors.py` e o serializer só lê:

```python
posts_count = serializers.IntegerField(read_only=True)
```

Medido em `tests/test_consultas.py`: **34 consultas → 2** para 8 usuários; **12 → 2** para
8 posts no feed. Os testes fixam esses números, então um N+1 reintroduzido falha com o
número exato.

As contagens usam subquery correlacionada (`common/selectors.count_of`) em vez de
`Count(..., distinct=True)`: com três contagens sobre relações reversas diferentes, o
Django emite três LEFT JOINs e materializa o produto cartesiano. `distinct=True` corrige
o número, não o tamanho do resultado intermediário.

---

## Erros

Um tipo base com código estável, uma classe por falha de negócio, e um tradutor único.

```python
class DomainError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "DOMAIN_ERROR"

class InvalidCredentials(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_CREDENTIALS"
```

`common/exception_handler.py` traduz **tudo** — erros de domínio, exceções do DRF,
exceções do simplejwt e falhas não previstas — para um envelope só:

```json
{ "code": "...", "message": "...", "details": null, "status_code": 401, "path": "..." }
```

**Por que o `code` e não a mensagem.** Não havia envelope: cada erro saía num formato
(`{"detail"}`, `{"campo": [...]}`, `{"message"}`) e o frontend compensava procurando
substrings em inglês dentro do texto do Django — `"too short"`, `"already exists"`,
`"No active account found"`. Atualizar o Django, mudar `LANGUAGE_CODE` ou trocar um
validador de senha fazia o `.includes()` parar de casar, e o usuário via a frase crua em
inglês no meio do cadastro. Nem teste nem type-check pegavam.

Códigos de biblioteca são mapeados para os nossos: o simplejwt distingue
`token_not_valid` de `no_active_account`, e o cliente precisa dessa diferença — um manda
renovar a sessão, o outro manda conferir a senha.

`tests/test_contrato_de_erro.py` fixa status e código de cada classe, e falha se uma
classe nova entrar sem estar na tabela.

---

## Configuração

Um mecanismo só: `DJANGO_SETTINGS_MODULE`. Existiam dois — o `manage.py` tinha default de
produção e `backend/settings/__init__.py` lia um `DJANGO_ENV` com default de
desenvolvimento, variável que nenhum Dockerfile, compose ou workflow definia. O efeito
visível era o CI rodar a suíte inteira sob settings de produção sem que nada indicasse.

`backend/settings/env.py` valida o ambiente na importação. Em desenvolvimento tudo tem
default; em produção nada tem, e a falta de uma variável aborta o boot nomeando ela.
`SECRET_KEY` exige 50 caracteres, e `CORS_ALLOWED_ORIGINS="*"` é recusado explicitamente.

O motivo: a `SECRET_KEY` tinha o default literal `"unsafe-default-key"`, versionado. Sem
a variável, produção subia assinando os JWT com uma chave pública, e nada nos logs dizia
isso.

---

## Invariantes no banco

Regra que protege dado vive numa constraint, não só em código de aplicação:

```python
models.UniqueConstraint(fields=["follower", "following"], name="unique_follow_relation")
models.CheckConstraint(condition=~Q(follower=F("following")), name="prevent_self_follow")
```

`prevent_self_follow` estava declarada no `models.py` e **nunca foi migrada**: a regra
existia em três lugares (a view, um serializer que ninguém usava, e o modelo) e vigorava
em um só. O `makemigrations --check` no CI existe para que isso não se repita.

---

## Comandos destrutivos

`manage.py seed_demo` tem duas travas independentes: recusa rodar com settings de
produção, e exige `RUN_SEED=true`. O reset é uma flag explícita, nunca o default.

Os quatro usuários de demonstração recebem um avatar cada, copiado de `media-seed/avatars/`
para `MEDIA_ROOT` e servido pelo próprio Django em desenvolvimento (`static()` em
`backend/urls.py`, ativo com `DEBUG=True`). A URL gravada é absoluta
(`LOCAL_MEDIA_BASE_URL` + `/media/avatars/<arquivo>`), nunca relativa: um caminho relativo
seria resolvido pelo navegador contra a origem do **frontend**, não da API, e a imagem
daria 404 — o mesmo defeito que o antigo `seed_data_dev.py` tinha. Rodar o comando de novo
sem `--reset` também corrige o avatar de quem já foi criado antes desta lógica existir.

`entrypoint.prod.sh` executava `python seed_data.py` a **cada boot de produção**, e o
`run()` daquele script começava com `reset_database()` — `User.objects.all().delete()`
incluído. Todo deploy destruía os dados reais, inclusive o superusuário criado poucas
linhas antes no mesmo entrypoint. As travas são duas de propósito: uma protege contra o
ambiente errado, a outra contra a execução não intencional no ambiente certo.

---

## Versionamento da API

As rotas vivem em `/api/v1/`. Os caminhos antigos continuam respondendo como alias porque
backend e frontend têm deploys independentes: um subir antes do outro não pode derrubar o
app. Os aliases saem num commit próprio, quando os dois lados estiverem em v1.

---

## O que ficou de fora, e por quê

**Cookie `httpOnly` para o token.** É a decisão certa e não foi feita: exige proteção CSRF
e mudança no deploy dos dois lados. O que foi feito reduz o dano — o access token caiu de
6 horas para 15 minutos e os refresh tokens rotacionam com blacklist. Está registrado como
próximo passo no README em vez de fingir que `localStorage` é seguro.

**Cache de respostas.** Nenhuma listagem é cara o bastante depois das anotações. Cache é
invalidação, e invalidação é o tipo de complexidade que só se paga com um problema medido.

**Fila para o upload de imagem.** O upload ao Cloudinary é síncrono dentro da requisição.
Numa aplicação com tráfego isso vira fila; aqui seria infraestrutura a mais para um
problema que não existe.
