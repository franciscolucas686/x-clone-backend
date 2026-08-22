# x-clone — backend

API REST de uma rede social: contas, posts, curtidas, comentários e seguidores.
Django 5.2 + Django REST Framework + PostgreSQL.

O frontend que consome esta API está em
[`x-clone-frontend`](https://github.com/franciscolucas686/x-clone-frontend).

---

## Começando

Requisitos: Docker (para o Postgres) e Python 3.12 **com suporte a venv**.

Em Debian, Ubuntu e WSL o `python3-venv` não vem junto com o Python, e sem ele o
`make setup` falha com `No module named pip` — mensagem que não menciona o pacote que
falta. Para conferir: `python3 -m ensurepip --version`. Se acusar erro:

```bash
sudo apt update && sudo apt install -y python3-venv make
```

O `python3-pip` do sistema não é necessário — o pip vive dentro do venv.

```bash
cp .env.example .env      # valores prontos, não precisa preencher nada
docker compose up -d db   # sobe o Postgres
make setup                # cria o venv e instala as dependências
make migrate
make seed                 # dados de demonstração (opcional)
make run
```

A API sobe em `http://localhost:8000`. A documentação interativa fica em
**`http://localhost:8000/api/docs`** — gerada do próprio código, então não tem como
divergir dele.

Sem `make`, os comandos equivalentes estão todos no `Makefile`; `make help` os lista.

Para subir tudo em contêiner, incluindo a aplicação:

```bash
cp .env.example .env && docker compose up
```

---

## Comandos

| Comando | O que faz |
|---|---|
| `make run` | Servidor de desenvolvimento |
| `make test` | Suíte de testes (111 testes) |
| `make test-cov` | Testes com relatório de cobertura |
| `make lint` | Ruff, sem corrigir — é o que o CI roda |
| `make lint-fix` | Ruff corrigindo e formatando |
| `make check` | `check`, `check --deploy` e migrações pendentes |
| `make migrate` | Aplica as migrações |
| `make seed` | Popula dados de demonstração |
| `make db-up` / `db-down` | Sobe/derruba o Postgres |

---

## Ambiente

O ambiente é escolhido **só** por `DJANGO_SETTINGS_MODULE`. O default é
`backend.settings.development`; produção define `backend.settings.production`
explicitamente (ver `Dockerfile.prod`).

Todas as variáveis estão documentadas em `.env.example`, com o que cada uma significa e o
que quebra sem ela. Em desenvolvimento todas têm default. **Em produção, nenhuma tem**:
`backend/settings/env.py` valida o ambiente na importação das settings e aborta o boot
nomeando a variável que falta, em vez de deixar a aplicação subir mal configurada.

```
$ DJANGO_SETTINGS_MODULE=backend.settings.production python manage.py runserver
ImproperlyConfigured: A variável de ambiente SECRET_KEY é obrigatória neste ambiente
e não está definida. Veja .env.example para o que ela significa.
```

O banco aceita duas formas, e a primeira vence quando existe: uma `DATABASE_URL` única —
o formato que Neon, Render e Supabase entregam no painel — ou as quatro variáveis
`DATABASE_*` separadas. O parse está em `backend/settings/env.py` e preserva o `sslmode`
declarado na própria URL; em produção o padrão é `require`.

---

## Estrutura

```
backend/settings/     base, development, production e env.py (validação fail-fast)
common/               erros de domínio, exception handler, paginação, comandos
  errors.py           DomainError + códigos estáveis
  exception_handler.py  envelope único de erro
  views.py            /healthz/ — alvo de keep-alive, sem tocar o banco
  management/commands/  seed_demo, ensure_superuser
accounts/  posts/
  models.py           dados e invariantes (constraints no banco)
  selectors.py        consultas de leitura, com as anotações
  services.py         operações que mudam estado ou falam com o mundo externo
  serializers.py      forma da entrada e da saída
  views.py            HTTP: recebe, delega, responde
followers/
  models.py           a relação Follow e suas constraints
  views.py            follow/unfollow — as consultas de leitura vivem em
                       accounts/selectors.py, junto das contagens de perfil
tests/                testes de ponta a ponta por assunto
```

`selectors.py` e `services.py` são finos de propósito. Não há repositórios nem casos de
uso: neste tamanho seriam cerimônia. Eles existem porque havia regra de negócio e chamada
de rede dentro de serializers.

---

## Contrato de erro

Toda resposta de erro sai no mesmo formato:

```json
{
  "code": "INVALID_CREDENTIALS",
  "message": "Usuário ou senha incorretos.",
  "details": null,
  "status_code": 401,
  "path": "/api/v1/token/"
}
```

**O contrato é o `code`**, não a `message`. O cliente decide o texto que mostra a partir
do código (`shared/api/error-code-map.ts` no frontend), e nunca lê a frase. `details`
traz os erros por campo, quando houver, para o formulário destacar o campo certo.

Os códigos estão em `common/errors.py` e são fixados por teste em
`tests/test_contrato_de_erro.py`: mudá-los é uma decisão visível no diff, não um efeito
colateral.

---

## Autenticação

JWT via `djangorestframework-simplejwt`.

- `POST /api/v1/token/` → `{access, refresh}`. Access vale 15 minutos, refresh vale 7 dias.
- `POST /api/v1/token/refresh/` → renova o par. Os refresh tokens **rotacionam**: cada uso
  invalida o anterior, então um token vazado só serve até o dono usar o dele.
- `/token/` e `/register/` têm limite de 10 requisições por minuto por IP.

**O access token é guardado em `localStorage` pelo frontend.** É a decisão que este
projeto ainda não corrigiu: cookie `httpOnly` é a resposta certa, mas exige proteção CSRF
e mudança no deploy dos dois lados. Reduzir a vida do access de 6 horas para 15 minutos
diminuiu a janela de exposição; migrar para cookie é o próximo passo.

---

## API

`/api/v1/` é o caminho canônico. Os caminhos antigos, sem versão, continuam respondendo
como alias: backend e frontend têm deploys independentes, e um subir antes do outro não
pode derrubar o app. Os aliases saem quando os dois lados estiverem em v1.

Endpoints em `http://localhost:8000/api/docs`.

`GET /healthz/` fica fora do prefixo `/api/`: é alvo de monitoramento externo (ver
"Keep-alive" abaixo), não faz parte do contrato da API, e um serviço de monitoramento não
deveria depender de versionamento.

---

## Keep-alive em produção

O plano gratuito do Render derruba o processo após 15 minutos sem tráfego. `GET
/healthz/` responde `200` sem tocar o banco — feito para ser pingado por um monitor
externo (recomendado: [UptimeRobot](https://uptimerobot.com), gratuito, 5 minutos fixos)
sem acordar o Neon à toa.

Não use um workflow agendado do GitHub Actions para isto: o cron de lá atrasa de 10 a 30
minutos (o Render dorme em 15) e é desativado sozinho após 60 dias sem commit no
repositório — o que descreve exatamente um portfólio pronto.

---

## Testes

```bash
make test
```

111 testes, organizados por assunto em `tests/`:

| Arquivo | Cobre |
|---|---|
| `test_fluxos_atuais.py` | Os fluxos de ponta a ponta: cadastro, login, feed, curtida, comentário, seguir |
| `test_contrato_de_erro.py` | O envelope e cada `code`, mais a montagem em v1 e nos aliases |
| `test_consultas.py` | Contagem de queries — impede a volta dos N+1 |
| `test_sessao.py` | Renovação, rotação de refresh e limite de tentativas |
| `test_conta.py` | Avatar, busca e troca de senha |
| `test_permissoes.py` | O que é público e o que exige conta, incluindo `/healthz/` |
| `test_ambiente.py` | Validação das variáveis e o parse da `DATABASE_URL` |
| `test_regressoes.py` | Defeitos específicos que não podem voltar (inclui os avatares do seed) |

Os testes de `test_consultas.py` fixam o **número de queries** de cada listagem. Um N+1
reintroduzido vira teste vermelho com o número exato, e não uma lentidão que alguém nota
meses depois.

---

## Escopo

O que existe: contas, perfis, posts, curtidas, comentários paginados, seguir/deixar de
seguir, feed de quem você segue, busca de usuários.

O que **não** existe: mensagens diretas e notificações. As telas correspondentes no
frontend são maquetes estáticas, e estão declaradas como tal no README de lá. Editar ou
apagar um post também não existe.
