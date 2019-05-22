web: gunicorn config.wsgi:application --backlog ${GUNICORN_BACKLOG:-256} -w ${GUNICORN_WORKERS:-2}  --max-requests ${GUNICORN_MAX_REQUESTS:-1000} --max-requests-jitter ${GUNICORN_JITTER:-50} -k ${GUNICORN_WORKER_CLASS:-tornado} --log-level ${GUNICORN_LOG_LEVEL:-INFO} --preload
worker: celery worker --app=alameda.taskapp --loglevel=info
beat: celery beat --app=alameda.taskapp --loglevel=info
