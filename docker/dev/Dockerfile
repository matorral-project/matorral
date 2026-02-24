# syntax = docker/dockerfile:1.5
FROM python:3.14-bookworm
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

# system packages
RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install -yqq \
      # needed by Django's compilemessages / makemessages
      gettext \
      # psycopg2 build dependency; also required on ARM
      libpq-dev

# uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/

ARG MY_UID=1000
ARG MY_GID=1000
# ensure uid/gid match the host user to avoid permission issues with bind mounts
RUN groupadd -g $MY_GID -r django || \
  (groupmod -g $MY_GID django 2>/dev/null || true) && \
  useradd -u $MY_UID -r -g django -m -d /home/django django 2>/dev/null || \
  usermod -u $MY_UID -g django -d /home/django django

RUN mkdir /code && chown django:django /code
WORKDIR /code

ENV UV_CACHE_DIR=/tmp/uv-cache/
RUN mkdir -p /tmp/uv-cache && chown django:django /tmp/uv-cache

USER django
ENV UV_PROJECT_ENVIRONMENT=/home/django/.venv
ENV PATH="/home/django/.venv/bin:$PATH"

# copy lock files first so this layer is only invalidated when dependencies change
COPY --chown=django:django uv.lock pyproject.toml ./
RUN --mount=type=cache,target=/tmp/uv-cache,uid=$MY_UID,gid=$MY_GID uv sync --frozen

COPY --chown=django:django . /code/
