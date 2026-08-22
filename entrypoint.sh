#!/bin/sh
# Entrypoint de desenvolvimento (docker-compose).
set -e

echo "Aguardando o banco de dados em ${DATABASE_HOST:-db}:${DATABASE_PORT:-5432}..."
until nc -z "${DATABASE_HOST:-db}" "${DATABASE_PORT:-5432}"; do
  sleep 1
done
echo "Banco disponível."

echo "Aplicando migrações..."
python manage.py migrate --noinput

python manage.py ensure_superuser

# O seed é opt-in via RUN_SEED, e o próprio comando recusa rodar com settings de
# produção. Aqui ele é apenas oferecido: sem a variável, o comando aborta com uma
# mensagem clara em vez de popular o banco de quem só queria subir o projeto.
if [ "${RUN_SEED}" = "true" ]; then
  echo "Populando dados de demonstração..."
  python manage.py seed_demo
fi

echo "Iniciando servidor..."
exec "$@"
