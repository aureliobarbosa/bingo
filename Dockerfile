# Imagem do serviço de bingo.
#
# Três estágios: `desenvolvimento` é o que o devcontainer usa, `construcao`
# monta o ambiente e `producao` só recebe o resultado. Assim o Python, o
# reportlab e o pillow testados são exatamente os que servem em produção, sem
# que o uv e as ferramentas de build acompanhem a imagem final.
#
# Os três partem da MESMA base, e isso não é preferência de estilo: `producao`
# recebe o `.venv` pronto de `construcao`, e um venv não é relocável entre
# instalações diferentes de Python. Ele grava o caminho absoluto do
# interpretador (`/usr/local/bin/python3`, no `pyvenv.cfg` e nos symlinks de
# `bin/`) e traz extensões compiladas contra uma libc — os `.so` são
# `cpython-314-x86_64-linux-gnu`. Trocar a base de um estágio só (Alpine, por
# exemplo) quebra a cópia de forma silenciosa.
#
# O uv entra por `COPY --from`, com a versão fixa em UV_VERSION. A alternativa
# `ghcr.io/astral-sh/uv:python3.14-bookworm-slim` é esta mesma base oficial com
# o uv embutido, mas não tem a versão do uv no nome da tag: a ferramenta
# flutuaria a cada rebuild, enquanto o `uv.lock` fixa só as dependências.
ARG UV_VERSION=0.9.30
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# --- desenvolvimento -------------------------------------------------------
# O código vem montado pelo devcontainer, não copiado, para que as edições
# apareçam na hora. O ambiente fica em /opt/venv, FORA do diretório montado:
# dentro dele, o .venv do host esconderia o do container e os caminhos
# absolutos gravados nele não valeriam aqui.
FROM python:3.14-slim-bookworm AS desenvolvimento
COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1

# Ferramentas de trabalho dentro do container. O `git` não vem na imagem base:
# sem ele o repositório montado em /app fica ilegível pelo terminal. O binário
# `claude` vem do pacote npm oficial da Anthropic; Node vem do repositório do
# NodeSource porque o do Debian bookworm está velho demais para o CLI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "bingo.api:app", \
     "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- construção ------------------------------------------------------------
FROM python:3.14-slim-bookworm AS construcao
COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- produção --------------------------------------------------------------
# Sem uv, sem ferramentas de build e sem o grupo dev. `src/` e `static/`
# precisam manter a árvore do projeto: RAIZ_PROJETO é calculada a partir de
# src/bingo/pdf.py, e é ela que localiza o diretório estático e o logo.
FROM python:3.14-slim-bookworm AS producao

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=construcao /app/.venv /app/.venv
COPY src/ ./src/
COPY static/ ./static/

# Servir como usuário sem privilégios: a rota é pública e sem autenticação.
RUN useradd --create-home --uid 1000 bingo && chown -R bingo:bingo /app
USER bingo

# Documenta a porta padrão. O Cloud Run injeta PORT=8080 e ignora o EXPOSE; as
# duas instruções abaixo leem a variável para servir na porta certa nos dois
# ambientes.
EXPOSE 8000

# Lê PORT em Python, e não na forma exec do CMD, que não expande variáveis.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", \
         "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/').read(1)"]

# Forma shell porque a exec não expande ${PORT}. O `exec` mantém o uvicorn como
# PID 1: sem ele o sh fica no lugar e engole o SIGTERM do encerramento.
#
# --proxy-headers com --forwarded-allow-ips: sem isso todo pedido chega com o IP
# do proxy do Google, e o limite de taxa por IP da Etapa 8.3 veria o tráfego
# inteiro como um cliente só. Confiar em qualquer proxy é aceitável porque o
# contêiner só recebe tráfego do Google Front End.
CMD ["sh", "-c", \
     "exec uvicorn bingo.api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
