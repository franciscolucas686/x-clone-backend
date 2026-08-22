FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*

# Imagem de desenvolvimento: instala também as dependências de desenvolvimento, para que
# `docker compose exec backend pytest` e `ruff` funcionem dentro do contêiner.
#
# Sem isto, quem escolhesse o caminho todo-em-Docker ficava sem rodar teste nem lint — e
# precisava montar um venv na máquina só para isso, o que anula a razão de escolher
# Docker. A imagem de produção (Dockerfile.prod) continua instalando só requirements.txt:
# ferramenta de teste em contêiner de produção é superfície de ataque sem contrapartida.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

COPY . .

COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
