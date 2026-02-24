from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render

from apps.dashboard.helpers import get_onboarding_status, get_user_dashboard_data
from apps.workspaces.decorators import login_and_workspace_membership_required


@login_and_workspace_membership_required
def workspace_home(request, workspace_slug):
    workspace = request.workspace

    onboarding = get_onboarding_status(request.user, workspace)

    # Only fetch dashboard data if onboarding is complete/dismissed
    dashboard_data = {} if onboarding["should_show"] else get_user_dashboard_data(request.user, workspace)

    template = "dashboard/home.html#page-content" if request.htmx else "dashboard/home.html"

    return render(
        request,
        template,
        context={
            "workspace": workspace,
            "active_tab": "dashboard",
            "page_title": workspace.name,
            "onboarding": onboarding,
            **dashboard_data,
        },
    )


@login_and_workspace_membership_required
def dismiss_onboarding(request, workspace_slug):
    """Mark onboarding as completed/dismissed for the current user."""
    if request.method == "POST":
        request.user.onboarding_completed = True
        request.user.save(update_fields=["onboarding_completed"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "onboarding-dismissed"
        return response

    return HttpResponseNotAllowed(["POST"])
