# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Matorral is a Django-based project management tool with workspace-scoped multi-tenancy. Issues are organized hierarchically: Workspace → Project → Milestone → Epic (tree root) → Story (child) → Subtask/Bug.

- **Django settings module**: `matorral.settings.settings`
- **Python**: 3.14+ (managed via `uv`)
- **Frontend**: Vite + TypeScript + Tailwind CSS v4 + DaisyUI v5 + Alpine.js + HTMX

## Development Environment

Requires Docker Compose. `just` is the task runner.

```bash
just init               # First-time setup: copy .env, build containers, migrate, seed DB
just start              # Start all containers with logs
just start-detached     # Start in background
just stop               # Stop containers
just restart            # Stop + start
```

Any change to `pyproject.toml` requires `just requirements` to rebuild containers.

## Common Commands

```bash
# Django management
just migrate                        # Run migrations
just make-migrations                # Create migrations (for new apps: just manage ARGS='makemigrations <app_name>')
just manage ARGS='<command>'        # Arbitrary manage.py command
just shell                          # Django shell
just dbshell                        # PostgreSQL shell

# Testing
just test [module]                  # e.g., just test apps.issues.tests.test_views

# Frontend
just npm-build                      # Build frontend assets in container
npm run dev                         # Watch mode (via Vite dev server)
```

Outside Docker, use `uv run python manage.py test apps` (requires a running PostgreSQL instance).

## Running Tests

Tests use Django's built-in test runner (`manage.py test`). Test data uses `factory-boy`.

```bash
# Via just (recommended, runs inside Docker)
just test                                        # Run all tests
just test apps.issues                            # Run all tests in an app
just test apps.issues.tests.test_models          # Run a specific test module
just test apps.issues.tests.test_models.MilestoneKeyAutoGenerationTest          # Run a test class
just test apps.issues.tests.test_models.MilestoneKeyAutoGenerationTest.test_key_auto_generated_when_blank  # Single test

# Via uv locally (requires a running PostgreSQL instance)
uv run python manage.py test apps
uv run python manage.py test apps.issues
uv run python manage.py test apps.issues.tests.test_models.MilestoneKeyAutoGenerationTest
```

Use dotted module paths (not file paths) when passing arguments to `just test`.

Coverage reports:

```bash
just test-cov        # Run tests with coverage
just cov-report      # Print coverage summary (after test-cov)
just cov             # Both in one step
```

## Architecture

### URL Structure
All app URLs are workspace-scoped at `/w/<workspace_slug>/`. Projects use `/w/<workspace_slug>/p/<project_key>/`.

### Request Flow
1. `WorkspacesMiddleware` sets `request.workspace` and `request.workspace_members`
2. Workspace-scoped views use `@login_and_workspace_membership_required` decorator
3. `WorkspaceScopedManager` auto-filters querysets by current workspace context

### Apps Overview
- **workspaces**: Workspace, Membership, Invitation, Flag (Waffle feature flags). Owns decorators, middleware, adapter, signals.
- **projects**: Project with auto-generated unique 3-6 letter keys. Issue IDs are `{project_key}-{number}`.
- **issues**: Milestone, Epic, Story, Subtask, Bug. Uses `django-treebeard` (MP_Node) and `django-polymorphic`.
- **sprints**: Sprint management with Celery task for auto-creating next sprints.
- **users**: `CustomUser` extending `AbstractUser`. Auth via `django-allauth` (email-only, GitHub OAuth).
- **landing_pages**: Public pages, context processors, S3/local storage backends.
- **utils**: `BaseModel` (abstract, provides `created_at`/`updated_at`), shared template tags/utilities.

### Key Patterns

**Treebeard for hierarchies:**
```python
# Epics use kwargs pattern
Epic.add_root(project=project, title="Epic title", milestone=milestone)

# Stories use instance pattern
epic.add_child(instance=Story(project=project, title="Story title"))
```

**ContentType caching** (use in hot paths to prevent deadlocks):
```python
from apps.issues.utils import get_cached_content_type
# NOT: ContentType.objects.get_for_model(model)
```

**FBV tests** (views with `@login_and_workspace_membership_required`):
```python
# Use force_login, not call_view_with_middleware (CBV-only)
self.client.force_login(user)
response = self.client.get(url)
```

**django-htmx patterns** (v1.27.0):
```python
# Typed response classes — always use these, never set headers manually
from django_htmx.http import HttpResponseClientRedirect, HttpResponseClientRefresh
return HttpResponseClientRedirect(url)   # sets HX-Redirect (status 200, not 204)
return HttpResponseClientRefresh()       # sets HX-Refresh: true (no args)

# Safe current URL path (returns None for cross-origin, unlike urlparse)
current_path = request.htmx.current_url_abs_path or ""

# History restore: always guard partial-fragment returns
def get_template_names(self):
    if self.request.htmx and not self.request.htmx.history_restore_request:
        return [f"{self.template_name}#page-content"]
    return [self.template_name]

# Vary header: add to every view that returns different content for HTMX vs full-page
# CBVs: override dispatch() in the mixin; FBVs: call after render()
from django.utils.cache import patch_vary_headers
patch_vary_headers(response, ("HX-Request",))
```

**Circular imports**: Use `django.apps.apps.get_model()`. Never put imports inside functions or methods — always at file top.

**Celery periodic tasks**: Scheduled tasks are defined in `SCHEDULED_TASKS` in `settings.py` and registered via a data migration (see `apps/sprints/migrations/0004_schedule_celery_tasks.py`). To add a new periodic task: add it to `SCHEDULED_TASKS`, then create a data migration in the relevant app using `apps.get_model("django_celery_beat", ...)` with `IntervalSchedule`/`CrontabSchedule` + `PeriodicTask.objects.update_or_create(...)`. Always include a reverse function that deletes the rows.

## Code Style

- **Ruff**: formatter + linter. Line length: 120. Double quotes. Rules: E, F, UP, B, SIM.
- **Pre-commit**: ruff, black, isort (black profile), pyupgrade (Python 3.14 target), codespell.
- Ruff auto-sorts imports: third-party before framework imports.
- Avoid `assertRaises(Exception)` — use specific exception types (ruff B017).

## Frontend

Assets live in `assets/`. Built output goes to `static/`.

- Entry points: `site-base.css`, `site-tailwind.css`, `site.js`, `app.js`
- CSS classes are prefixed `mt-*` (not `pg-*`)
- HTMX for partial page updates; Alpine.js for reactivity
- `{% load django_vite %}` and `{% vite_js "app" %}` in templates

## Environment & Services

Services (docker-compose.yml): PostgreSQL 17, Redis, Django web, Vite dev server, Celery worker+beat.

Key env vars: `DATABASE_URL`, `REDIS_URL`, `USE_S3_MEDIA`, `FLY_API_TOKEN`.

## CI/CD

GitHub Actions runs on push/PR to `main`:
- `tests.yml`: pytest with PostgreSQL and Redis services
- `pre-commit.yml`: ruff, black, isort, pyupgrade
- `migrations.yml`: checks for missing migrations (`--check --dry-run`)
- `deploy.yml`: deploys to Fly.io via `flyctl deploy`

Build frontend before running tests (CI does `npm ci && npm run build` first).
