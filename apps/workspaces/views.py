from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from apps.users.models import CustomUser
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from .decorators import login_and_workspace_membership_required, workspace_admin_required
from .forms import InvitationForm, MembershipForm, WorkspaceChangeForm
from .invitations import clear_invite_from_session, process_invitation, send_invitation
from .limits import LimitExceededError, check_invitation_limit, check_member_limit
from .models import Invitation, Membership, Workspace
from .roles import ROLE_ADMIN, is_admin, is_member

from allauth.account.models import EmailAddress
from allauth.account.views import SignupView


class WorkspaceDetailView(LoginAndWorkspaceRequiredMixin, DetailView):
    """Display Workspace details."""

    model = Workspace
    template_name = "workspaces/workspace_detail.html"
    context_object_name = "workspace"
    slug_url_kwarg = "workspace_slug"

    def get_queryset(self):
        return Workspace.objects.all()

    def get_template_names(self):
        if self.request.htmx:
            return ["workspaces/workspace_detail.html#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.object.name
        context["active_tab"] = "workspaces"
        return context


@login_required
def manage_workspaces(request):
    workspaces = Workspace.objects.for_user(request.user)
    template = "workspaces/list_workspaces.html#page-content" if request.htmx else "workspaces/list_workspaces.html"
    return render(
        request,
        template,
        {
            "workspaces": workspaces,
            "page_title": _("My Workspaces"),
        },
    )


def accept_invitation(request, invitation_id):
    invitation = get_object_or_404(Invitation, id=invitation_id)
    if not invitation.is_accepted:
        request.session["invitation_id"] = str(invitation_id)
    else:
        clear_invite_from_session(request)
    if request.user.is_authenticated and is_member(request.user, invitation.workspace):
        messages.info(
            request,
            _("It looks like you're already a member of the {workspace} workspace. You've been redirected.").format(
                workspace=invitation.workspace.name
            ),
        )
        return HttpResponseRedirect(reverse("landing_pages:home"))

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, _("Please log in again to accept your invitation."))
            return HttpResponseRedirect(reverse("account_login"))
        else:
            if invitation.is_accepted:
                messages.error(request, _("Sorry, it looks like that invitation link has expired."))
                return HttpResponseRedirect(reverse("landing_pages:home"))
            else:
                process_invitation(invitation, request.user)
                clear_invite_from_session(request)
                messages.success(
                    request,
                    _("You successfully joined {}").format(invitation.workspace.name),
                )
                return HttpResponseRedirect(reverse("landing_pages:home"))

    account_exists = CustomUser.objects.filter(email=invitation.email).exists()
    owned_email_address = None
    user_workspace_count = 0
    if request.user.is_authenticated:
        owned_email_address = EmailAddress.objects.filter(email=invitation.email, user=request.user).first()
        user_workspace_count = request.user.workspaces.count()
    return render(
        request,
        "workspaces/accept_invite.html",
        {
            "invitation": invitation,
            "account_exists": account_exists,
            "user_owns_email": bool(owned_email_address),
            "email_verified": owned_email_address and owned_email_address.verified,
            "user_workspace_count": user_workspace_count,
        },
    )


class SignupAfterInvite(SignupView):
    @cached_property
    def invitation(self) -> Invitation:
        invitation_id = self.kwargs["invitation_id"]
        invitation = get_object_or_404(Invitation, id=invitation_id)
        if invitation.is_accepted:
            messages.error(
                self.request,
                _("Sorry, it looks like that invitation link has expired."),
            )
            raise Http404
        return invitation

    def get_initial(self):
        initial = super().get_initial()
        if self.invitation:
            initial["workspace_name"] = self.invitation.workspace.name
            initial["email"] = self.invitation.email
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.invitation:
            context["invitation"] = self.invitation
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if settings.ACCOUNT_EMAIL_VERIFICATION != "none" and hasattr(self, "user") and self.invitation:
            email_address = EmailAddress.objects.filter(user=self.user, email=self.invitation.email).first()
            if email_address:
                email_address.set_verified(commit=True)
        return response


@login_and_workspace_membership_required
def manage_workspace(request, workspace_slug):
    workspace = request.workspace
    workspace_form = None
    if request.method == "POST":
        if is_admin(request.user, workspace):
            workspace_form = WorkspaceChangeForm(request.POST, instance=workspace)
            if workspace_form.is_valid():
                messages.success(request, _("Workspace details saved!"))
                workspace_form.save()
                if workspace.slug != workspace_slug:
                    return HttpResponseRedirect(reverse("workspaces:manage_workspace", args=[workspace.slug]))
        else:
            messages.error(request, _("Sorry you don't have permission to do that."))
    if workspace_form is None:
        workspace_form = WorkspaceChangeForm(instance=workspace)
    if not request.workspace_membership.is_admin():
        for field in workspace_form.fields.values():
            field.disabled = True

    template = "workspaces/manage_workspace.html#page-content" if request.htmx else "workspaces/manage_workspace.html"
    return render(
        request,
        template,
        {
            "workspace": workspace,
            "active_tab": "manage-workspace",
            "page_title": _("My Workspace | {workspace}").format(workspace=workspace),
            "workspace_form": workspace_form,
            "is_only_workspace": request.user.workspaces.count() == 1,
        },
    )


@login_and_workspace_membership_required
def manage_workspace_members(request, workspace_slug):
    workspace = request.workspace
    template = (
        "workspaces/manage_workspace_members.html#page-content"
        if request.htmx
        else "workspaces/manage_workspace_members.html"
    )
    return render(
        request,
        template,
        {
            "workspace": workspace,
            "active_tab": "manage-workspace",
            "page_title": _("Members | {workspace}").format(workspace=workspace),
            "invitation_form": InvitationForm(workspace=workspace),
            "pending_invitations": Invitation.objects.filter(workspace=workspace, is_accepted=False).order_by(
                "-created_at"
            ),
        },
    )


@workspace_admin_required
@require_POST
def delete_workspace(request, workspace_slug):
    user = request.user
    workspace = request.workspace
    is_only_workspace = user.workspaces.count() == 1

    if is_only_workspace and "delete_account" not in request.POST:
        messages.error(
            request,
            _(
                "You cannot delete your only workspace. "
                "Create a new workspace first, or delete your workspace and account together."
            ),
        )
        return HttpResponseRedirect(reverse("workspaces:manage_workspace", args=[workspace_slug]))

    workspace_name = workspace.name
    workspace.delete()

    if is_only_workspace:
        messages.success(request, _("Your workspace and account have been permanently deleted."))
        logout(request)
        user.delete()
    else:
        messages.success(
            request,
            _('The "{workspace}" workspace was successfully deleted').format(workspace=workspace_name),
        )

    return HttpResponseRedirect(reverse("landing_pages:home"))


@login_required
def create_workspace(request):
    if request.method == "POST":
        form = WorkspaceChangeForm(request.POST)
        if form.is_valid():
            workspace = form.save()
            Membership.objects.create(workspace=workspace, user=request.user, role=ROLE_ADMIN)
            messages.success(request, _('Workspace "{name}" created!').format(name=workspace.name))
            return HttpResponseRedirect(reverse("workspaces:manage_workspaces"))
    else:
        form = WorkspaceChangeForm()
    return render(
        request,
        "workspaces/create_workspace.html",
        {
            "form": form,
            "page_title": _("Create Workspace"),
        },
    )


@workspace_admin_required
@require_POST
def resend_invitation(request, workspace_slug, invitation_id):
    invitation = get_object_or_404(Invitation, workspace=request.workspace, id=invitation_id)
    send_invitation(invitation)
    return HttpResponse('<span class="btn btn-disabled">Sent!</span>')


@workspace_admin_required
@require_POST
def send_invitation_view(request, workspace_slug):
    form = InvitationForm(request.workspace, request.POST)
    if form.is_valid():
        invitation = form.save(commit=False)
        invitation.workspace = request.workspace
        invitation.invited_by = request.user
        try:
            invitation.validate_unique()
            check_member_limit(request.workspace)
            check_invitation_limit(request.workspace)
        except (ValidationError, LimitExceededError) as e:
            error_msg = e.messages[0] if isinstance(e, ValidationError) else str(e)
            form.add_error(None, error_msg)
        else:
            invitation.save()
            send_invitation(invitation)
            pending_invitations = Invitation.objects.filter(workspace=request.workspace, is_accepted=False).order_by(
                "-created_at"
            )
            response = render(
                request,
                "workspaces/includes/invite_success.html",
                {
                    "invitation_form": InvitationForm(request.workspace),
                    "pending_invitations": pending_invitations,
                },
            )
            response["HX-Trigger"] = "invitationSent"
            return response
    return render(
        request,
        "workspaces/includes/invite_form_fields.html",
        {"invitation_form": form},
    )


@workspace_admin_required
@require_POST
def cancel_invitation_view(request, workspace_slug, invitation_id):
    invitation = get_object_or_404(Invitation, workspace=request.workspace, id=invitation_id)
    invitation.delete()
    return HttpResponse("")


@login_and_workspace_membership_required
def workspace_membership_details(request, workspace_slug, membership_id):
    membership = get_object_or_404(Membership, workspace=request.workspace, pk=membership_id)
    editing_self = membership.user == request.user
    can_edit_workspace_members = request.workspace_membership.is_admin()
    if not can_edit_workspace_members and not editing_self:
        messages.error(request, _("Sorry, you don't have permission to access that page."))
        return HttpResponseRedirect(reverse("workspaces:manage_workspace_members", args=[request.workspace.slug]))

    if request.method == "POST":
        if not can_edit_workspace_members:
            return HttpResponseForbidden(_("You don't have permission to edit workspace members."))
        if editing_self:
            messages.error(request, _("You aren't allowed to change your own role."))
            membership_form = MembershipForm(instance=membership)
        else:
            membership_form = MembershipForm(request.POST, instance=membership)
            if membership_form.is_valid():
                membership = membership_form.save()
                messages.success(
                    request,
                    _("Role for {member} updated.").format(member=membership.user.get_display_name()),
                )
    else:
        membership_form = MembershipForm(instance=membership)
    if editing_self:
        for field in membership_form.fields.values():
            field.disabled = True
    return render(
        request,
        "workspaces/workspace_membership_details.html",
        {
            "active_tab": "manage-workspace",
            "membership": membership,
            "membership_form": membership_form,
            "editing_self": editing_self,
        },
    )


@login_and_workspace_membership_required
@require_POST
def remove_workspace_membership(request, workspace_slug, membership_id):
    membership = get_object_or_404(Membership, workspace=request.workspace, pk=membership_id)
    removing_self = membership.user == request.user
    can_edit_workspace_members = request.workspace_membership.is_admin()
    if not can_edit_workspace_members and not removing_self:
        return HttpResponseForbidden(_("You don't have permission to remove others from that workspace."))
    if membership.role == ROLE_ADMIN:
        admin_count = Membership.objects.filter(workspace=request.workspace, role=ROLE_ADMIN).count()
        if admin_count == 1:
            messages.error(
                request,
                _(
                    "You cannot remove the only administrator from a workspace. "
                    "Make another workspace member an administrator and try again."
                ),
            )
            return HttpResponseRedirect(reverse("workspaces:manage_workspace_members", args=[request.workspace.slug]))
    membership.delete()
    messages.success(
        request,
        _("{member} was removed from {workspace}.").format(
            member=membership.user.get_display_name(), workspace=request.workspace.name
        ),
    )
    if removing_self:
        return HttpResponseRedirect(reverse("landing_pages:home"))
    else:
        return HttpResponseRedirect(reverse("workspaces:manage_workspace_members", args=[request.workspace.slug]))
