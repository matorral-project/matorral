import sys

import django

from django.conf import settings
from django.conf.urls import url
from django.conf.urls.static import static
from django.contrib import admin
from django.core.management import execute_from_command_line
from django.http import HttpResponse
from django.urls import include, path

import environ

env = environ.Env(
    DEBUG=(bool, False)
)

# reading .env file
environ.Env.read_env()

# False if not in os.environ
DEBUG = env('DEBUG')

DATABASES = {
    # read os.environ['DATABASE_URL'] and raises ImproperlyConfigured exception if not found
    'default': env.db(default='sqlite:////tmp/alameda.db')
}

STATIC_ROOT = 'statics'
STATIC_URL = '/static/'

settings.configure(
    DEBUG=DEBUG,
    ROOT_URLCONF=sys.modules[__name__],
    ALLOWED_HOSTS=['127.0.0.1', 'localhost', 'alameda-tool.herokuapp.com'],
    DATABASES=DATABASES,
    INSTALLED_APPS=[
        'django.contrib.staticfiles',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.messages',
        'django.contrib.sessions',
        'django.contrib.admin',
        'django.contrib.sites',
        'simple_history',
        'tagulous',
        'taggit',
        'django_comments_xtd',
        'django_comments',
        'django_admin_listfilter_dropdown',
        'stories',
    ],
    TEMPLATES=[
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'OPTIONS': {
                'debug': DEBUG,
                'loaders': [
                    'django.template.loaders.filesystem.Loader',
                    'django.template.loaders.app_directories.Loader',
                ],
                'context_processors': [
                    'django.template.context_processors.debug',
                    'django.template.context_processors.request',
                    'django.contrib.auth.context_processors.auth',
                    'django.template.context_processors.i18n',
                    'django.template.context_processors.media',
                    'django.template.context_processors.static',
                    'django.template.context_processors.tz',
                    'django.contrib.messages.context_processors.messages',
                ],
            },
        },
    ],
    MIDDLEWARE=(
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'simple_history.middleware.HistoryRequestMiddleware',
    ),
    STATIC_ROOT=STATIC_ROOT,
    STATIC_URL=STATIC_URL,
    SITE_ID=1,
    COMMENTS_APP='django_comments_xtd',
    COMMENTS_XTD_MAX_THREAD_LEVEL=2,
)

django.setup()


def index(request):
    return HttpResponse('<h1>Hello from Alamaneda!</h1>')


urlpatterns = [
    path('admin/', admin.site.urls),
    url(r'^comments/', include('django_comments_xtd.urls')),
    url(r'^$', index),
] + static(STATIC_URL, document_root=STATIC_ROOT)


if __name__ == '__main__':
    execute_from_command_line(sys.argv)
