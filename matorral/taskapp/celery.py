
from __future__ import absolute_import
import os

import environ

from celery import Celery

from django.apps import AppConfig
from django.conf import settings


env = environ.Env(DEBUG=(bool, False),)
environ.Env.read_env('config/settings/.env')  # reading .env file

if not settings.configured:
    # set the default Django settings module for the 'celery' program.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')  # pragma: no cover


app = Celery('matorral')


class CeleryConfig(AppConfig):
    name = 'matorral.taskapp'
    verbose_name = 'Celery Config'

    def ready(self):
        # Using a string here means the worker will not have to
        # pickle the object when using Windows.
        app.config_from_object('django.conf:settings')
        app.autodiscover_tasks(lambda: settings.INSTALLED_APPS, force=True)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))  # pragma: no cover
