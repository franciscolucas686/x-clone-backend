#!/bin/sh
# Entrypoint de produção.
#
# NÃO roda seed. A versão anterior executava `python seed_data.py` a cada boot, e aquele
# script começava apagando User, Post, Like, Comment e Follow — ou seja, todo deploy
# destruía os dados reais. Popular banco de produção não é trabalho de entrypoint; se
# algum dia for necessário, é uma execução manual, deliberada e pontual.
set -e

# Host e porta saem do mesmo `database_config` que o Django usa, em vez de lidos
# direto do ambiente aqui. O motivo é concreto: com `DATABASE_URL` — que é o formato
# entregue por Neon, Render e Supabase — a variável `DATABASE_HOST` não existe, e a
# versão anterior abortava aqui, antes de o Django chegar a ler a URL.
#
# Reusar a função também impede o defeito clássico de dois parsers: um no shell e outro
# no Python, discordando sobre a mesma string.
DB_ENDPOINT=$(python -c "
from backend.settings.env import database_config
config = database_config(required=True)
print(config['HOST'], config['PORT'])
") || exit 1

DB_HOST=$(echo "$DB_ENDPOINT" | cut -d' ' -f1)
DB_PORT=$(echo "$DB_ENDPOINT" | cut -d' ' -f2)

echo "Aguardando o banco de dados em $DB_HOST:$DB_PORT..."
until nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 2
done
echo "Banco disponível."

echo "Aplicando migrações..."
python manage.py migrate --noinput

echo "Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

python manage.py ensure_superuser

echo "Iniciando servidor..."
exec "$@"
