# syntax = docker/dockerfile:1.5
# Multi-stage production image build

# Stage 1: Python dependencies
FROM python:3.14-slim-bookworm as build-python

# Configure uv for a standalone, reproducible virtualenv:
# - copy link mode avoids hard-link issues across filesystems
# - byte-compile packages for faster startup
# - disable automatic Python downloads
# - install into /code/.venv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/code/.venv

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

# Install Git (needed for git-based dependencies like django-celery-beat)
RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update \
    && apt-get install -y git \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false

# Copy only the lock files into a throw-away directory so they
# don't end up in the final image.
COPY pyproject.toml uv.lock /_lock/

# Synchronize dependencies.
# This layer is cached until uv.lock or pyproject.toml change.
RUN --mount=type=cache,target=/root/.cache \
    cd /_lock && \
    uv sync \
      --frozen \
      --no-group dev \
      --group prod

# Stage 2: Front-end assets
FROM node:22-bookworm-slim AS build-node
RUN npm install -g npm@11.3
RUN nodejs -v && npm -v
WORKDIR /code
COPY *.json *.js /code/
COPY assets /code/assets/
RUN npm install

# full copy needed for Tailwind class detection / purging
COPY . /code
RUN npm run build

# Stage 3: Final runtime image
# Assembles Python deps and compiled front-end assets into a lean image.
FROM python:3.14-slim-bookworm
ENV PYTHONUNBUFFERED=1
ENV DEBUG=0

RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update \
    && apt-get install -y \
    curl \
    libpq-dev \
    gettext \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false

RUN addgroup --system django \
    && adduser --system --ingroup django django

WORKDIR /code
COPY --from=build-python --chown=django:django /code /code
# prefer virtualenv binaries over system Python
ENV PATH="/code/.venv/bin:$PATH"

COPY --chown=django:django . /code
COPY --from=build-node /code/static /code/static

# uv shebang in manage.py won't work without the uv binary — swap it for plain python3
RUN sed -i '1c\#!/usr/bin/env python3' /code/manage.py

# collectstatic must run at build time so assets are baked into the image
RUN DEBUG=False python /code/manage.py collectstatic --noinput --settings=matorral.settings_production
RUN chown django:django -R static_root

USER django

CMD exec gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 0 matorral.asgi:application -k uvicorn.workers.UvicornWorker
