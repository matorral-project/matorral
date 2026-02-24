from django.shortcuts import get_object_or_404

from apps.workspaces.models import Workspace

from ..forms import ProjectForm
from ..models import Project


class ProjectViewMixin:
    """Base mixin for all project views."""

    model = Project

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.workspace = get_object_or_404(Workspace.objects, slug=kwargs["workspace_slug"])

    def get_template_names(self):
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["workspace"] = self.workspace
        return context


class ProjectSingleObjectMixin:
    """Mixin for views that operate on a single project (detail, update, delete)."""

    context_object_name = "project"
    slug_field = "key"
    slug_url_kwarg = "key"


class ProjectFormMixin:
    """Mixin for views with project forms (create, update)."""

    form_class = ProjectForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workspace"] = self.workspace
        kwargs["workspace_members"] = self.request.workspace_members
        return kwargs
