from itertools import groupby

from django.db.models import F
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView

from matorral.sprints.forms import SprintGroupByForm
from matorral.sprints.models import Sprint
from matorral.sprints.tasks import duplicate_sprints, remove_sprints, reset_sprint
from matorral.stories.forms import StoryFilterForm
from matorral.stories.tasks import story_set_assignee, story_set_state
from matorral.utils import get_clean_next_url, get_referer_url
from matorral.views import BaseListView


@method_decorator(login_required, name="dispatch")
class SprintDetailView(DetailView):

    model = Sprint

    def get_children(self):
        queryset = (
            self.get_object()
            .story_set.select_related("requester", "assignee", "epic", "state")
            .order_by("epic__priority", "priority")
        )

        config = dict(
            epic=("epic__title", lambda story: story.epic and story.epic.title or "No Epic"),
            state=("state__slug", lambda story: story.state.name),
            requester=("requester__username", lambda story: story.requester and story.requester.username or "Unset"),
            assignee=("assignee__username", lambda story: story.assignee and story.assignee.username or "Unassigned"),
        )

        group_by = self.request.GET.get("group_by")

        try:
            order_by, fx = config[group_by]
        except KeyError:
            return [(None, queryset)]
        else:
            queryset = queryset.order_by(order_by)
            foo = [(t[0], list(t[1])) for t in groupby(queryset, key=fx)]
            return foo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["group_by_form"] = SprintGroupByForm(self.request.GET)
        context["objects_by_group"] = self.get_children()
        context["group_by"] = self.request.GET.get("group_by")
        context["filters_form"] = StoryFilterForm(self.request.POST)
        context["current_workspace"] = self.kwargs["workspace"]
        return context

    def post(self, *args, **kwargs):
        url = get_referer_url(self.request)

        if self.request.POST.get("remove") == "yes":
            remove_sprints.delay([self.get_object().id])
            url = reverse_lazy("sprints:sprint-list", args=[self.kwargs["workspace"]])

        elif self.request.POST.get("sprint-reset") == "yes":
            story_ids = [t[6:] for t in self.request.POST.keys() if "story-" in t]
            reset_sprint.delay(story_ids)

        else:
            state = self.request.POST.get("state")
            if isinstance(state, list):
                state = state[0]
            if state:
                story_ids = [t[6:] for t in self.request.POST.keys() if "story-" in t]
                story_set_state.delay(story_ids, state)

            assignee = self.request.POST.get("assignee")
            if isinstance(assignee, list):
                assignee = assignee[0]
            if assignee:
                story_ids = [t[6:] for t in self.request.POST.keys() if "story-" in t]
                story_set_assignee.delay(story_ids, assignee)

        return HttpResponseRedirect(url)


@method_decorator(login_required, name="dispatch")
class SprintList(BaseListView):
    model = Sprint
    filter_fields = {}
    select_related = None
    prefetch_related = None

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.order_by(F("starts_at").asc(nulls_last=True))

    def _process_in_bulk_actions(self):
        sprint_ids = [t[7:] for t in self.request.POST.keys() if "sprint-" in t]

        if len(sprint_ids) == 0:
            # No sprints selected
            return

        # Remove sprints in bulk
        if self.request.POST.get("remove") == "yes":
            remove_sprints.delay(sprint_ids)

        # Duplicate sprints in bulk
        if self.request.POST.get("duplicate") == "yes":
            duplicate_sprints.delay(sprint_ids)

    def post(self, *args, **kwargs):
        self._process_in_bulk_actions()
        url = self.request.get_full_path()
        return HttpResponseRedirect(url)


class SprintEditMixin:
    model = Sprint
    fields = ["title", "description", "starts_at", "ends_at"]

    @property
    def success_url(self):
        return get_clean_next_url(self.request, reverse_lazy("sprints:sprint-list", args=[self.kwargs["workspace"]]))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sprint_add_url = reverse_lazy("sprints:sprint-add", args=[self.kwargs["workspace"]])
        context["sprint_add_url"] = sprint_add_url
        context["current_workspace"] = self.kwargs["workspace"]
        return context

    def form_valid(self, form):
        form.instance.workspace = self.request.workspace
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class SprintCreateView(SprintEditMixin, CreateView):
    pass


@method_decorator(login_required, name="dispatch")
class SprintUpdateView(SprintEditMixin, UpdateView):

    def post(self, *args, **kwargs):
        if self.request.POST.get("save-as-new"):
            form = self.get_form_class()(self.request.POST)
            return self.form_valid(form)

        return super().post(*args, **kwargs)
