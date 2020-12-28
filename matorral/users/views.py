# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, ListView, RedirectView
from rest_framework import viewsets

from matorral.generic_ui.views import GenericCreateView, GenericDetailView, GenericListView, GenericUpdateView

from .models import User
from .serializers import UserSerializer


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self):
        return reverse('users:detail',
                       kwargs={'username': self.request.user.username})


@method_decorator(login_required, name='dispatch')
class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()


class UserDetailView(GenericDetailView):
    model = User
    # These next two lines tell the view to index lookups by username
    slug_field = 'username'
    slug_url_kwarg = 'username'

    fields = ('username', 'first_name', 'last_name', 'email', 'last_login')


class UserListView(GenericListView):
    model = User
    # These next two lines tell the view to index lookups by username
    slug_field = 'username'
    slug_url_kwarg = 'username'

    paginate_by = 10

    filter_fields = dict(
        username='username__contains'
    )

    default_search = 'name__icontains'

    table_config = [
        {'name': 'name', 'title': 'Name'},
        {'name': 'username', 'title': 'Username'},
        {'name': 'email', 'title': 'Email'},
        {'name': 'is_active', 'title': 'Active?'},
    ]


class UserCreateView(GenericCreateView):
    model = User

    fields = [
        'name'
    ]


class UserUpdateView(GenericUpdateView):
    model = User

    fields = [
        'name'
    ]

    def get_object(self):
        # Only get the User record for the user making the request
        return User.objects.get(username=self.request.user.username)
