from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.issues.cascade import _apply_cascade_down, _apply_cascade_up
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin
from apps.workspaces.models import Workspace


class CascadeStatusApplyView(LoginAndWorkspaceRequiredMixin, View):
    """POST endpoint to apply cascade status changes."""

    http_method_names = ["post"]

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.workspace = get_object_or_404(Workspace.objects, slug=kwargs["workspace_slug"])

    def post(self, request, *args, **kwargs):
        cascade_down = request.POST.get("cascade_down") == "1"
        cascade_up = request.POST.get("cascade_up") == "1"

        # CASCADE DOWN - supports multiple groups (indexed fields)
        if cascade_down:
            group_count_str = request.POST.get("down_group_count", "")
            if group_count_str.isdigit() and int(group_count_str) > 0:
                # New multi-group format
                group_count = int(group_count_str)
                for i in range(group_count):
                    ids_str = request.POST.get(f"down_ids_{i}", "")
                    pks = [int(pk) for pk in ids_str.split(",") if pk.strip().isdigit()]
                    status = request.POST.get(f"down_status_{i}", "")
                    model_type = request.POST.get(f"down_model_type_{i}", "")
                    if pks and status:
                        _apply_cascade_down(pks, status, model_type, request.user)
            else:
                # Legacy single-group format (backward compat)
                down_ids_str = request.POST.get("down_ids", "")
                down_pks = [int(pk) for pk in down_ids_str.split(",") if pk.strip().isdigit()]
                down_status = request.POST.get("down_status", "")
                down_model_type = request.POST.get("down_model_type", "")
                if down_pks and down_status:
                    _apply_cascade_down(down_pks, down_status, down_model_type, request.user)

        # CASCADE UP params
        if cascade_up:
            up_pk_str = request.POST.get("up_id", "")
            up_pk = int(up_pk_str) if up_pk_str.isdigit() else None
            up_status = request.POST.get("up_status", "")
            up_model_type = request.POST.get("up_model_type", "")
            if up_pk and up_status:
                _apply_cascade_up(up_pk, up_status, up_model_type, request.user)

        return HttpResponse(status=204)
