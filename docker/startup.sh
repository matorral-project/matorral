#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

PORT=${PORT:-8000}

echo "Django migrate"
python manage.py migrate --noinput
echo "Run Gunicorn"
gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 0 matorral.asgi:application -k uvicorn.workers.UvicornWorker
