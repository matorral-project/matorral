"""
Management command to find and fix orphaned issues (issues whose parent was deleted).
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.issues.models import BaseIssue


class Command(BaseCommand):
    help = _("Find and fix orphaned issues (issues with depth > 1 whose parent no longer exists)")

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete orphaned issues (default: promote to root)",
        )
        parser.add_argument(
            "--fix-tree",
            action="store_true",
            help="Run treebeard's fix_tree() after fixing orphans to repair any remaining inconsistencies",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        delete_orphans = options["delete"]
        fix_tree = options["fix_tree"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made\n"))

        orphans = self._find_orphaned_issues()

        if not orphans:
            self.stdout.write(self.style.SUCCESS("No orphaned issues found."))
            if fix_tree and not dry_run:
                self._run_fix_tree()
            return

        self.stdout.write(f"Found {len(orphans)} orphaned issue(s):\n")
        for issue in orphans:
            issue_type = issue.get_issue_type_display()
            self.stdout.write(f"  - [{issue.key}] {issue.title} ({issue_type}, depth={issue.depth})")

        if dry_run:
            action = "Would delete" if delete_orphans else "Would promote to root"
            self.stdout.write(f"\n{action} {len(orphans)} orphaned issue(s).")
            return

        if delete_orphans:
            self._delete_orphans(orphans)
        else:
            self._promote_orphans_to_root(orphans)

        if fix_tree:
            self._run_fix_tree()

        self.stdout.write(self.style.SUCCESS("\nDone!"))

    def _find_orphaned_issues(self):
        """
        Find issues that have depth > 1 (should have a parent) but their parent doesn't exist.

        In treebeard's materialized path, each node's path is built from its ancestors.
        A node at depth 2 has a path like "XXXX0001" where "XXXX" is the parent's path.
        If the parent is deleted without cascading, the child becomes orphaned.
        """
        orphans = []

        # Get all non-root issues (depth > 1 means they should have a parent)
        non_root_issues = BaseIssue.objects.filter(depth__gt=1).order_by("path")

        # Build a set of all existing paths for quick lookup
        all_paths = set(BaseIssue.objects.values_list("path", flat=True))

        # The step size for path segments (treebeard default is 4 chars per level)
        steplen = BaseIssue.steplen

        for issue in non_root_issues:
            # Extract parent path (all but the last segment)
            parent_path = issue.path[:-steplen]

            if parent_path and parent_path not in all_paths:
                orphans.append(issue)

        return orphans

    def _delete_orphans(self, orphans):
        """Delete orphaned issues.

        Note: We can't use treebeard's delete() because it tries to find the
        parent to update numchild, which fails for orphans.
        Instead, we delete each orphan's polymorphic child table row first,
        then the base table row.
        """
        from django.db import connection

        with transaction.atomic():
            orphan_pks = [issue.pk for issue in orphans]
            orphan_keys = {issue.pk: issue.key for issue in orphans}

            if not orphan_pks:
                return

            # Group orphans by their actual model class (Story, Bug, etc.)
            # to delete from child tables first
            orphans_by_model = {}
            for issue in orphans:
                model_class = type(issue)
                if model_class not in orphans_by_model:
                    orphans_by_model[model_class] = []
                orphans_by_model[model_class].append(issue.pk)

            with connection.cursor() as cursor:
                # Delete from child tables first (Story, Bug, Chore, etc.)
                for model_class, pks in orphans_by_model.items():
                    if model_class != BaseIssue:
                        child_table = model_class._meta.db_table
                        placeholders = ", ".join(["%s"] * len(pks))
                        cursor.execute(
                            f"DELETE FROM {child_table} WHERE baseissue_ptr_id IN ({placeholders})",  # noqa: S608
                            pks,
                        )

                # Now delete from base table
                base_table = BaseIssue._meta.db_table
                placeholders = ", ".join(["%s"] * len(orphan_pks))
                cursor.execute(
                    f"DELETE FROM {base_table} WHERE id IN ({placeholders})",  # noqa: S608
                    orphan_pks,
                )
                deleted_count = cursor.rowcount

            for pk in orphan_pks:
                self.stdout.write(f"  Deleted: [{orphan_keys[pk]}]")

            self.stdout.write(self.style.SUCCESS(f"\nDeleted {deleted_count} orphaned issue(s)."))

    def _promote_orphans_to_root(self, orphans):
        """Move orphaned issues to become root nodes.

        Note: We can't use treebeard's move() because it tries to update the
        old parent's numchild, which fails when the parent doesn't exist.
        Instead, we directly update path/depth and then run fix_tree().
        """
        with transaction.atomic():
            promoted_count = 0

            # Get the next available root step number
            last_root = BaseIssue.get_last_root_node()
            next_step = int(last_root.path, 36) + 1 if last_root else 1

            for issue in orphans:
                issue_key = issue.key

                # Generate a new root path using treebeard's _get_path
                # _get_path(parent_path, depth, step_number)
                new_path = BaseIssue._get_path(None, 1, next_step)
                issue.path = new_path
                issue.depth = 1
                issue.numchild = 0  # Orphans are leaf nodes
                issue.save(update_fields=["path", "depth", "numchild"])

                next_step += 1
                promoted_count += 1
                self.stdout.write(f"  Promoted to root: [{issue_key}]")

            self.stdout.write(self.style.SUCCESS(f"\nPromoted {promoted_count} orphaned issue(s) to root level."))
            self.stdout.write(self.style.WARNING("Note: Running fix_tree() is recommended after promoting orphans."))

    def _run_fix_tree(self):
        """Run treebeard's fix_tree() to repair any remaining tree inconsistencies."""
        self.stdout.write("\nRunning fix_tree() to repair tree structure...")

        # Check for problems first
        problems = BaseIssue.find_problems()
        if problems:
            self.stdout.write(f"  Found {len(problems)} tree problem(s), fixing...")
            for problem in problems[:10]:  # Show first 10
                self.stdout.write(f"    - {problem}")
            if len(problems) > 10:
                self.stdout.write(f"    ... and {len(problems) - 10} more")

        BaseIssue.fix_tree()
        self.stdout.write(self.style.SUCCESS("  Tree structure repaired."))
