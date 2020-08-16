import ujson

from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView

from .tasks import do_in_bulk
from ..utils import get_clean_next_url

class BaseConfig:
    def __init__(self, model, params):
        self._model = model
        self._params = params

    def as_dict(self):
        _meta = self._model._meta

        return {
            'model': {
                'names': {
                    'singular': _meta.verbose_name,
                    'plural': _meta.verbose_name_plural
                }
            },
            'urls': {
                'add_url': reverse_lazy(f'{_meta.app_label}:{_meta.model_name}-add', args=[self._params['workspace']]),
                'list_url': reverse_lazy(f'{_meta.app_label}:{_meta.model_name}-list', args=[self._params['workspace']]),
            }
        }


class ColumnList:
    def __init__(self, model, column_list, params):
        self._column_list = column_list
        self._params = params
        self._app_model = f'{model._meta.app_label}:{model._meta.model_name}'

    def __iter__(self):
        for item in self._column_list:
            yield item

    def action_list(self):
        return [
            {
                'url': reverse_lazy(f'{self._app_model}-add', args=[self._params['workspace']]),
                'name': 'Create', 'icon': 'plus', 'class': 'is-ilink'
            },
        ]


class Result:
    def __init__(self, queryset_item, app_label, model_name, field_list, params):
        self._field_list = field_list
        self._result = queryset_item
        self._app_label = app_label
        self._model_name = model_name
        self._params = params

    def unique_id(self):
        return f'{self._app_label}-{self._model_name}-{self._result.id}'

    def field_list(self):
        for field, widget in self._field_list:
            value = getattr(self._result, field.name)

            url = None
            if widget == 'link':
                try:
                    url = value.get_absolute_url()
                except AttributeError:
                    url = self._result.get_absolute_url()

            if field.choices:
                yield {'value': dict(field.choices)[value], 'widget': widget, 'url': url}
            else:
                yield {'value': value, 'widget': widget, 'url': url}

    def action_list(self):
        return [
            {
                'url': reverse_lazy(
                    f'{self._app_label}:{self._model_name}-edit',
                    args=[self._params['workspace'], self._result.id]
                 ),
                'name': 'edit', 'icon': 'edit', 'class': 'is-primary is-outlined'
            }
        ]


class ResultList:
    def __init__(self, model, queryset, field_list, params):
        self._model = model
        self._queryset = queryset
        self._field_list = field_list
        self._params = params

    def __iter__(self):
        _meta = self._model._meta
        for result in self._queryset:
            yield Result(result, _meta.app_label, _meta.model_name, self._field_list, self._params)


class ListViewConfig(BaseConfig):
    def __init__(self, model, params, queryset, column_list):
        self._model = model
        self._queryset = queryset
        self._params = params

        self._column_list = column_list

        self._field_list = [
            (self._model._meta.get_field(column['name']), column.get('widget')) for column in column_list
        ]

        super().__init__(self._model, self._params)

    def as_dict(self):
        config = super().as_dict()

        _meta = self._model._meta

        config.update({
            'title': _meta.verbose_name_plural.capitalize(),
            'column_list': ColumnList(self._model, self._column_list, self._params),
            'result_list': ResultList(self._model, self._queryset, self._field_list, self._params)
        })

        return config


class GenericListView(ListView):
    paginate_by = 10

    view_config = []
    filter_fields = {}
    select_related = None
    prefetch_related = None
    default_search = 'id__exact'

    template_name = 'generic_ui/object_list.html'

    def get_view_config(self):
        return self.view_config

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
                params[self.default_search] = part

        return params

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['current_workspace'] = self.kwargs['workspace']

        context['view_config'] = ListViewConfig(
            self.model, self.kwargs, context['page_obj'].object_list, self.get_view_config()
        ).as_dict()

        return context

    def get_queryset(self):
        qs = super().get_queryset()

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

    def post(self, *args, **kwargs):
        params = ujson.loads(self.request.body)

        _meta = self.model._meta
        object_list  = [t.split('-') for t in params.keys() if f'{_meta.app_label}-{_meta.model_name}-' in t]

        if len(object_list) > 0:
            if params.get('remove') == 'yes':
                do_in_bulk.delay('delete', object_list)

            if params.get('duplicate') == 'yes':
                do_in_bulk.delay('duplicate', object_list)

        url = self.request.get_full_path()

        if self.request.META.get('HTTP_X_FETCH') == 'true':
            return JsonResponse(dict(url=url))
        else:
            return HttpResponseRedirect(url)


class FormViewConfig(BaseConfig):
    def __init__(self, model, instance, params):
        self._model = model
        self._instance = instance
        self._params = params
        super().__init__(self._model, self._params)

    def as_dict(self):
        _meta = self._model._meta
        config = super().as_dict()
        config['title'] = self._instance and f'Editing {self._instance}' or f'Create {_meta.verbose_name}'
        return config


class BaseCreateUpdateView(object):

    template_name = 'generic_ui/object_form.html'

    @property
    def success_url(self):
        _meta = self.model._meta
        workspace = self.kwargs['workspace']
        return get_clean_next_url(self.request, reverse_lazy(f'{_meta.app_label}:{_meta.model_name}-list', args=[workspace]))

    def set_attributes(self, request, form):
        """Allow subclasses to set some instance attributes before saving it"""
        pass

    def form_valid(self, form):
        self.set_attributes(self.request, form)

        response = super().form_valid(form)

        url = self.get_success_url()

        if self.request.META.get('HTTP_X_FETCH') == 'true':
            return JsonResponse(dict(url=url))

        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workspace = self.kwargs['workspace']
        context['current_workspace'] = workspace

        context['view_config'] = FormViewConfig(
            self.model, context.get('object'), self.kwargs
        ).as_dict()

        return context

    def post(self, *args, **kwargs):
        data = ujson.loads(self.request.body)

        if data.get('save-as-new'):
            form = self.get_form_class()(data)
        else:
            if isinstance(self, CreateView):
                form = self.get_form_class()(data)
            else:
                form = self.get_form_class()(data, instance=self.get_object())

        return self.form_valid(form)


class GenericCreateView(BaseCreateUpdateView, CreateView):
    pass


class GenericUpdateView(BaseCreateUpdateView, UpdateView):
    pass


class DetailViewConfig(BaseConfig):
    def __init__(self, model, instance, params):
        self._model = model
        self._instance = instance
        self._params = params
        super().__init__(self._model, self._params)

    def as_dict(self):
        config = super().as_dict()
        config['title'] = self._instance
        _meta = self._model._meta
        config['urls']['edit_url'] = reverse_lazy(f'{_meta.app_label}:{_meta.model_name}-edit', args=[self._params['workspace'], self._instance.id])
        return config


class GenericDetailView(DetailView):

    template_name = 'generic_ui/object_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_workspace'] = self.kwargs['workspace']

        context['view_config'] = DetailViewConfig(
            self.get_queryset().model, context.get('object'), self.kwargs
        ).as_dict()

        return context

    def post(self, *args, **kwargs):
        params = ujson.loads(self.request.body)

        if params.get('remove') == 'yes':
            remove_stories.delay([self.get_object().id])

            _meta = self.model._meta
            url = reverse_lazy(f'{_meta.app_label}:{_meta.model_name}-list', args=[self.kwargs['workspace']])

            if self.request.META.get('HTTP_X_FETCH') == 'true':
                return JsonResponse(dict(url=url))
            else:
                return HttpResponseRedirect(url)

        url = self.request.get_full_path()

        if self.request.META.get('HTTP_X_FETCH') == 'true':
            return JsonResponse(dict(url=url))
        else:
            return HttpResponseRedirect(url)
