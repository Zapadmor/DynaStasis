# syntax=docker/dockerfile:1

# ── Étape 1 : dépendances Python (lockfile) dans un venv isolé ────────────────
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt

# ── Étape 2 : socle d'exécution commun ────────────────────────────────────────
FROM python:3.12-slim AS base
ARG UID=1000
ARG GID=1000
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH=/opt/venv/bin:$PATH \
    HOME=/home/dynastasie

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${GID}" dynastasie \
    && useradd --uid "${UID}" --gid "${GID}" --home-dir "${HOME}" --create-home dynastasie \
    # `user:` du compose peut imposer un autre UID : le home et les volumes doivent rester inscriptibles
    && mkdir -p /app/data /app/dbdata \
    && chmod 0777 "${HOME}" /app/data /app/dbdata

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Code en dernier : une modification du code ne réinvalide pas les couches de dépendances
COPY . .

# le gestionnaire de thèmes écrit .streamlit/themes/.current
RUN chmod -R a+rwX /app/.streamlit/themes

USER dynastasie
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "src/app/ui_main.py"]

# ── Cible `adb` : ajoute adb pour la synchronisation du temps d'écran Android ──
#   docker build --target adb .
FROM base AS adb
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends adb \
    && rm -rf /var/lib/apt/lists/*
USER dynastasie

# ── Cible par défaut (dernière étape) : sans adb ──────────────────────────────
FROM base AS runtime
