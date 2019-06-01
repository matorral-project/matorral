from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import CreateView, UpdateView

from rest_framework import viewsets

from .models import Sprint
from .serializers import SprintSerializer


class SprintViewSet(viewsets.ModelViewSet):
    serializer_class = SprintSerializer
    queryset = Sprint.objects.all()


class BaseListView(ListView):
    paginate_by = 10

    filter_fields = {}
    select_related = None
    prefetch_related = None

    def _build_filters(self, q):
        params = {}

        for part in (q or '').split():
            if ":" in part:
                field, value = part.split(':')
                try:
                    operator = self.filter_fields[field]
                    params[operator] = value
                except KeyError:
                    continue
            else:
                params['title__icontains'] = part

        return params

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.GET.get('q') is not None:
            context['show_all_url'] = self.request.path

        context['title'] = self.model._meta.verbose_name_plural.capitalize()
        context['singular_title'] = self.model._meta.verbose_name.capitalize()

        return context

    def get_queryset(self):
        qs = self.model.objects

        q = self.request.GET.get('q')

        params = self._build_filters(q)

        if q is None:
            qs = qs.all()
        else:
            qs = qs.filter(**params)

        if self.select_related is not None:
            qs = qs.select_related(*self.select_related)

        if self.prefetch_related is not None:
            qs = qs.prefetch_related(*self.prefetch_related)

        return qs


class SprintList(BaseListView):
    model = Sprint
    filter_fields = {}
    select_related = None
    prefetch_related = None


class BaseView(object):

    def form_valid(self, form):
        messages.add_message(self.request, messages.INFO, self._get_success_message())
        return super().form_valid(form)


class SprintBaseView(BaseView):
    model = Sprint
    fields = [
        'title', 'description'
    ]
    success_url = reverse_lazy('sprints:sprint-list')


class SprintCreateView(SprintBaseView, CreateView):

    def _get_success_message(self):
        return 'Sprint successfully created!'


class SprintUpdateView(SprintBaseView, UpdateView):

    def _get_success_message(self):
        return 'Sprint successfully updated!'
