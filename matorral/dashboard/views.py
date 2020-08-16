from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView

from matorral.stories.models import Story


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        me = self.request.user
        context['my_in_progress_stories'] = Story.objects\
            .select_related('epic', 'sprint', 'assignee')\
            .filter(assignee=me, state__slug='ip')\
            .order_by('epic__priority', 'priority')[:3]

        context['my_upcoming_stories'] = Story.objects\
            .select_related('epic', 'sprint', 'assignee')\
            .filter(assignee=me, state__slug='pr')\
            .order_by('epic__priority', 'priority')[:3]

        context['current_workspace'] = self.kwargs['workspace']

        return context
