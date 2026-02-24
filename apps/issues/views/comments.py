from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext_lazy as _
from django.views import View

from apps.issues.models import BaseIssue
from apps.issues.utils import get_cached_content_type
from apps.projects.models import Project
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin
from apps.workspaces.models import Workspace

from django_comments_xtd.models import XtdComment


class IssueCommentsViewMixin:
    """Base mixin for issue comment views that loads workspace, project, and issue from URL."""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.workspace = get_object_or_404(Workspace.objects, slug=kwargs["workspace_slug"])
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["project_key"],
        )
        self.issue = get_object_or_404(
            BaseIssue.objects.for_project(self.project).select_related(
                "project", "project__workspace", "polymorphic_ctype"
            ),
            key=kwargs["key"],
        )

    def _get_comments_context(self):
        content_type = get_cached_content_type(type(self.issue))
        comments = (
            XtdComment.objects.filter(
                content_type=content_type,
                object_pk=str(self.issue.pk),
                is_removed=False,
            )
            .select_related("user")
            .order_by("submit_date")
        )
        return {
            "workspace": self.workspace,
            "project": self.project,
            "issue": self.issue,
            "comments": comments,
        }


class IssueCommentsView(LoginAndWorkspaceRequiredMixin, IssueCommentsViewMixin, View):
    """GET comments list for an issue via HTMX."""

    def get(self, request, *args, **kwargs):
        return render(
            request,
            "issues/includes/comments_list.html",
            self._get_comments_context(),
        )


class IssueCommentPostView(LoginAndWorkspaceRequiredMixin, IssueCommentsViewMixin, View):
    """POST new comment and return updated comments list."""

    def post(self, request, *args, **kwargs):
        comment_text = request.POST.get("comment", "").strip()

        if not comment_text:
            return HttpResponseBadRequest(_("Comment cannot be empty"))

        content_type = get_cached_content_type(type(self.issue))

        XtdComment.objects.create(
            content_type=content_type,
            object_pk=str(self.issue.pk),
            site_id=1,
            user=request.user,
            comment=comment_text,
        )

        return render(
            request,
            "issues/includes/comments_list.html",
            self._get_comments_context(),
        )


class IssueCommentEditView(LoginAndWorkspaceRequiredMixin, IssueCommentsViewMixin, View):
    """POST to edit an existing comment. Only the comment owner can edit."""

    def post(self, request, *args, **kwargs):
        comment = get_object_or_404(XtdComment, pk=kwargs["comment_pk"], is_removed=False)

        if comment.user != request.user:
            return HttpResponseForbidden(_("You can only edit your own comments."))

        comment_text = request.POST.get("comment", "").strip()
        if not comment_text:
            return HttpResponseBadRequest(_("Comment cannot be empty"))

        comment.comment = comment_text
        comment.save(update_fields=["comment"])

        return render(
            request,
            "issues/includes/comments_list.html",
            self._get_comments_context(),
        )


class IssueCommentDeleteView(LoginAndWorkspaceRequiredMixin, IssueCommentsViewMixin, View):
    """POST to soft-delete a comment. Only the comment owner can delete."""

    def post(self, request, *args, **kwargs):
        comment = get_object_or_404(XtdComment, pk=kwargs["comment_pk"], is_removed=False)

        if comment.user != request.user:
            return HttpResponseForbidden(_("You can only delete your own comments."))

        comment.is_removed = True
        comment.save(update_fields=["is_removed"])

        return render(
            request,
            "issues/includes/comments_list.html",
            self._get_comments_context(),
        )
