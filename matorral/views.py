from django.views.generic import ListView


class BaseListView(ListView):
    paginate_by = 16

    filter_fields = {}
    select_related = None
    prefetch_related = None

    def _build_filters(self, q):
        params = {}

        for part in (q or "").split():
            if ":" in part:
                field, value = part.split(":")
                try:
                    operator = self.filter_fields[field]
                    params[operator] = value
                except KeyError:
                    continue
            else:
                params["title__icontains"] = part

        return params

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.GET.get("q") is not None:
            context["show_all_url"] = self.request.path

        context["title"] = self.model._meta.verbose_name_plural.capitalize()
        context["singular_title"] = self.model._meta.verbose_name.capitalize()
        context["current_workspace"] = self.kwargs["workspace"]

        return context

    def get_queryset(self):
        qs = self.model.objects

        q = self.request.GET.get("q")

        params = dict(workspace__slug=self.kwargs["workspace"])

        if q is None:
            qs = qs.filter(**params)
        else:
            params.update(self._build_filters(q))
            qs = qs.filter(**params)

        if self.select_related is not None:
            qs = qs.select_related(*self.select_related)

        if self.prefetch_related is not None:
            qs = qs.prefetch_related(*self.prefetch_related)

        return qs
