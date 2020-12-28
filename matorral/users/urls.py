# -*- coding: utf-8 -*-
from django.urls import path

from .views import UserCreateView, UserDetailView, UserListView, UserUpdateView

app_name = 'users'

urlpatterns = [
    path('add/', UserCreateView.as_view(), name='user-add'),
    path('<username>/', UserDetailView.as_view(), name='user-detail'),
    path('<username>/edit/', UserUpdateView.as_view(), name='user-edit'),
    path('', UserListView.as_view(), name='user-list'),
]
