# CLAUDE.md

This file provides guidance to LLMs, AI agents and tools like Claude Code, Codex, OpenCode and other when working with code in this repository.

## Project Overview

Matorral is a Django-based project management tool with workspace-scoped multi-tenancy. Issues are organized hierarchically. There are 3 alternative hierarchies:
 * Workspace → Project → Milestone → Epic → Story / Bug / Chore → Subtask
 * Workspace → Project → Epic → Story / Bug / Chore → Subtask
 * Workspace → Project → Story / Bug / Chore → Subtask

- **Python**: 3.14+ (managed via `uv`)
- **Backend**: Django + PostgreSQL + Redis + Celery
- **Frontend**: Vite + TypeScript + Tailwind CSS v4 + DaisyUI v5 + Alpine.js + HTMX

## Development Environment

Requires Docker Compose. `just` is the task runner.

```bash
just init               # First-time setup: copy .env, build containers, migrate, seed DB. This will delete the existing DB if it exists!
just start              # Start all containers with logs
just start-detached     # Start in background
just stop               # Stop containers
just restart            # Stop + start
```

Any change to `pyproject.toml` requires `just requirements` to rebuild containers.

## Common Commands

### Environment
```bash
just --list                         # List all recipes with descriptions
just doctor                         # Verify environment is healthy (.env, containers, migrations)
just check                          # Run all checks (tests, migrations, pre-commit) - CI-friendly
just status                         # Show status of all containers
```

### Django Management
```bash
just migrate                        # Run migrations
just make-migrations                # Create migrations
just check-migrations               # Check for uncreated migrations (CI-friendly)
just manage <command>               # Run any Django manage.py command
just shell                          # Django shell
just dbshell                        # PostgreSQL shell
just loaddata <fixture>             # Load fixture data
just dumpdata <model>               # Dump data to fixture
```

### Testing & Quality
```bash
just test [module]                  # e.g., just test apps.issues.tests.test_views
just test-cov [module]              # Run tests with coverage
just cov                            # Run tests with coverage and generate reports
just pre-commit                     # Run all pre-commit hooks on all files
just lint                           # Run ruff linter
just fmt                            # Run ruff formatter
```

### Frontend
```bash
just npm-build                      # Build frontend assets in container
just npm-type-check                 # Run TypeScript type checker
npm run dev                         # Watch mode (via Vite dev server, outside Docker)
```

### Logs (Service-specific)
```bash
just logs                           # All services
just logs-django                    # Django only
just logs-db                        # PostgreSQL only
just logs-celery                    # Celery worker
just logs-redis                     # Redis
just logs-vite                      # Vite dev server
```

## Running Tests

Tests use Django's built-in test runner (`manage.py test`). Test data is provided by factories using `factory-boy`.

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

### Settings
 * local + test: matorral/settings/settings.py
 * dev/qa/production: matorral/settings/production.py


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

* Workspaces are containers of Projects.
* Projects are containers of everything else: Milestones, Epics and working items (Stories, Bugs, Chores).

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

# HTMX delete pattern: use build_htmx_delete_response() for detail page deletions
# This returns HX-Location with target="#page-content" to swap only main content,
# preserving sidebar and layout. Returns HX-Refresh for embedded list deletions.
from apps.issues.helpers import build_htmx_delete_response
def form_valid(self, form):
    deleted_url = self.object.get_absolute_url()
    redirect_url = self.get_success_url()
    self.object.delete()
    if self.request.htmx:
        return build_htmx_delete_response(self.request, deleted_url, redirect_url)
    return redirect(redirect_url)
```

**Import Placement**:
- **ALWAYS place imports at the top of the file**
- **NEVER place imports inside functions or methods**
- This is mandatory and non-negotiable

**Circular imports**: Use `django.apps.apps.get_model()`.

## General Coding Preferences

- Follow Zen of Python:
  - Simple is better than complex.
  - Explicit is better than implicit.
  - Flat is better than nested.
  - Readability counts.
  - Errors should never pass silently. Unless explicitly silenced.
- Stay focused on the requested scope; only expand when you fully understand the implications.
- Always try to be DRY: scan the codebase for logic that can be used instead of creating new code.
- Map the blast radius: consider which modules, tests, and migrations your change touches.
- Keep codebase clean: delete unused code, refactor when possible.
- Apply single responsibility principle for functions and classes.
- Modularize and organize the logic logically.
- If replacement is necessary, remove the legacy approach entirely.
- Before introducing new abstractions, exhaust possibilities with current tools.

**After making changes**:
```bash
just pre-commit    # Run pre-commit hooks on all files to catch issues
```

**Celery periodic tasks**: Scheduled tasks are defined in `SCHEDULED_TASKS` in `settings.py` and registered via a data migration (see `apps/sprints/migrations/0004_schedule_celery_tasks.py`). To add a new periodic task: add it to `SCHEDULED_TASKS`, then create a data migration in the relevant app using `apps.get_model("django_celery_beat", ...)` with `IntervalSchedule`/`CrontabSchedule` + `PeriodicTask.objects.update_or_create(...)`. Always include a reverse function that deletes the rows.

## Python/Django Guidelines

### Fat Models

Push complexity downward: models and managers should encapsulate business rules, keeping views lightweight.

- **Build domain-specific QuerySets and Managers** when models have recurring query patterns.
- **Favor fluent interfaces**—chainable methods that return QuerySets for composability:
  ```python
  # Good: composable, readable
  Project.objects.for_workspace(workspace).with_key(key, exclude=self).exists()
  ```
- **Abstract purpose, not mechanics**. Don't obscure Django's built-ins:
  ```python
  # Good: expresses intent
  def for_workspace(self, workspace):
      return self.filter(workspace=workspace)

  # Bad: pointlessly wraps basic Django
  def with_lead(self):
      return self.select_related("lead")  # Just use select_related() directly
  ```
- **Sanitize data in `save()`**—transform to canonical forms (uppercase, trimmed).
- **Generate stable identifiers** in consistent formats (`KEY-1`, `KEY-2`) with collision handling.

### Writing Simple QuerySets

Always query the model you actually need, not intermediate models. Let Django's ORM handle JOINs through relationship traversal.

- **Query the target model directly** using relationship lookups in filters:
  ```python
  # Good: query User directly, let Django handle the JOIN
  User.objects.filter(membership__team_id=workspace.team_id)

  # Bad: query intermediate model and extract related objects
  memberships = Membership.objects.filter(team_id=workspace.team_id).select_related("user")
  users = [m.user for m in memberships]
  ```
- **Use `_id` suffix** to access foreign key values without loading the related object:
  ```python
  # Good: no extra query, workspace_id is stored on the model
  User.objects.filter(membership__team__workspace_id=self.instance.workspace_id)

  # Bad: loads the workspace object first (extra query)
  User.objects.filter(membership__team__workspace=self.instance.workspace)
  ```
- **Traverse relationships in filters** instead of chaining through Python:
  ```python
  # Good: single query with JOINs
  User.objects.filter(membership__team__workspace_id=project.workspace_id)

  # Bad: multiple attribute accesses, potentially multiple queries
  project.workspace.team.members.all()
  ```
- **Prefer simple JOINs over Subquery** unless you have a specific reason (like correlated subqueries or complex aggregations).

### URLs and Views

- **NEVER query Workspace in view setup** - always use `request.workspace` set by middleware:
  ```python
  # Good: uses request.workspace (no DB query)
  class MyViewMixin:
      def setup(self, request, *args, **kwargs):
          super().setup(request, *args, **kwargs)
          if not request.workspace:
              raise Http404
          self.workspace = request.workspace

  # Bad: redundant DB query
  class MyViewMixin:
      def setup(self, request, *args, **kwargs):
          super().setup(request, *args, **kwargs)
          self.workspace = get_object_or_404(Workspace.objects, slug=kwargs["workspace_slug"])
  ```

- **Prefer meaningful identifiers over `pk` in URLs** when a model has a unique slug or key field:
  ```python
  # Good: readable, meaningful URL
  path("<str:key>/", views.project_detail, name="project_detail")
  # /w/workspace/p/PROJ-1/

  # Avoid when better identifier exists
  path("<int:pk>/", views.project_detail, name="project_detail")
  # /w/workspace/p/42/
  ```

## Testing Best Practices

- Use `setUpTestData()` for read-only test data shared across test methods (better performance than `setUp()`).
- Use `setUp()` only when tests need to modify test data.
- Use `factory_boy` factories for creating test data. Factories are in `apps/<app_name>/factories.py`.
- For view tests with workspace context, use shared utilities in `apps.utils.tests.utils`.
- Use `Client` for integration tests that need full request/response cycle.
- Use `@override_settings` for configuration changes needed by tests.
- Place tests in `apps/<app_name>/tests/` directories.

Note: Build frontend before running tests (CI does `npm ci && npm run build` first).

## Template Guidelines

- Indent templates with two spaces.
- Use standard Django template syntax.
- Use translation markup, usually `translate` or `blocktranslate trimmed` with user-facing text. Don't forget to `{% load i18n %}` if needed.
- JavaScript and CSS files built with Vite should be included with `{% vite_js %}` template tag (must have `{% load django_vite %}` at the top of the template).
- Use the Django `{% static %}` tag for loading images and external JavaScript/CSS files not managed by Vite.
- Prefer using Alpine.js for page-level JavaScript, and avoid inline `<script>` tags where possible.
- Break reusable template components into separate templates with `{% include %}` statements.
- Use DaisyUI styling markup for available components. When not available, fall back to standard TailwindCSS classes.
- Stick with the DaisyUI color palette whenever possible.

## JavaScript Guidelines

### Code Style

- Use ES6+ syntax for JavaScript code.
- Use 2 spaces for indentation in JavaScript, JSX, and HTML files.
- Use single quotes for JavaScript strings.
- End statements with semicolons.
- Use camelCase for variable and function names.
- Use PascalCase for component names (React).
- Use explicit type annotations in TypeScript files.
- Use ES6 import/export syntax for module management.

### Preferred Practices

- When using HTMX, follow progressive enhancement patterns.
- Use Alpine.js for client-side interactivity that doesn't require server interaction.
- Avoid inline `<script>` tags wherever possible.
- Validate user input on both client and server side.
- Handle errors explicitly in promise chains and async functions.

## Django Best Practices

### Query Optimization

- **Use `select_related()`** for single-valued relationships (ForeignKey, OneToOne) to fetch related objects in the same query:
  ```python
  # Good: single query with JOIN
  Project.objects.select_related("workspace").all()

  # Bad: N+1 queries
  for project in Project.objects.all():
      print(project.workspace.name)  # Extra query per project
  ```

- **Use `prefetch_related()`** for multi-valued relationships (ManyToMany, reverse FK) to fetch in separate queries:
  ```python
  # Good: 2 queries total
  Project.objects.prefetch_related("members").all()

  # Bad: N+1 queries
  for project in Project.objects.all():
      for member in project.members.all():  # Extra query per project
          print(member.username)
  ```

- **Add `db_index=True`** on fields used in filters, ordering, or joins:
  ```python
  class Project(BaseModel):
      key = models.CharField(max_length=10, db_index=True)
      status = models.CharField(max_length=20, db_index=True)
  ```

- **Use bulk operations** for large datasets:
  ```python
  # Good: single INSERT
  Project.objects.bulk_create([Project(name=f"P{i}") for i in range(1000)])

  # Bad: 1000 separate INSERTs
  for i in range(1000):
      Project.objects.create(name=f"P{i}")
  ```

### Transactions

- **Use `@transaction.atomic`** for multi-step operations requiring data consistency:
  ```python
  from django.db import transaction

  @transaction.atomic
  def transfer_membership(from_user, to_user, workspace):
      Membership.objects.filter(user=from_user, workspace=workspace).delete()
      Membership.objects.create(user=to_user, workspace=workspace)
  ```

### Validation

- **Validate in model's `clean()` method**, call `full_clean()` in `save()`:
  ```python
  class Project(BaseModel):
      def clean(self):
          if self.start_date and self.end_date and self.start_date > self.end_date:
              raise ValidationError("End date must be after start date")

      def save(self, *args, **kwargs):
          self.full_clean()
          super().save(*args, **kwargs)
  ```

## Celery Best Practices

### Task Design

- **Make tasks idempotent** — safe to retry without side effects:
  ```python
  # Good: uses get_or_create, idempotent
  @shared_task
  def ensure_project_stats(project_id):
      project = Project.objects.get(id=project_id)
      stats, _ = ProjectStats.objects.get_or_create(project=project)
      stats.update_counts()
  ```

- **Pass model IDs to tasks, not instances** to avoid serialization issues:
  ```python
  # Good: pass ID
  @shared_task
  def process_project(project_id):
      project = Project.objects.get(id=project_id)

  # Bad: pass instance (may be stale, heavy serialization)
  @shared_task
  def process_project(project):
      project.refresh_from_db()
  ```

### Retries

- **Use exponential backoff** for resilient retry logic:
  ```python
  @shared_task(
      autoretry_for=(Exception,),
      retry_backoff=True,        # Exponential: 1s, 2s, 4s, 8s...
      retry_backoff_max=600,     # Max 10 minutes between retries
      retry_jitter=True,         # Add randomness to prevent thundering herd
      max_retries=5
  )
  def fetch_external_data(url):
      response = requests.get(url, timeout=30)
      response.raise_for_status()
      return response.json()
  ```

### Time Limits

- **Set time limits** to prevent runaway tasks:
  ```python
  @shared_task(
      soft_time_limit=300,   # 5 min - task receives SoftTimeLimitExceeded
      time_limit=360         # 6 min - worker kills task
  )
  def heavy_computation(data):
      try:
          # Long-running work
          pass
      except SoftTimeLimitExceeded:
          # Cleanup before hard limit
          logger.warning("Task approaching time limit, saving partial results")
          save_partial_results()
  ```

### Queue Management

- **Route heavy tasks to dedicated queues**:
  ```python
  # settings.py
  CELERY_TASK_ROUTES = {
      "apps.sprints.tasks.*": {"queue": "sprints"},
      "apps.reports.tasks.*": {"queue": "reports"},
      "apps.notifications.tasks.*": {"queue": "notifications"},
  }

  # Start worker for specific queue
  # celery -A matorral worker -Q reports -n reports_worker@%h
  ```

### Result Handling

- **Store results only when needed** (saves memory in result backend):
  ```python
  # Good: fire-and-forget, no result stored
  @shared_task(ignore_result=True)
  def send_notification(user_id, message):
      user = User.objects.get(id=user_id)
      user.send_message(message)

  # Good: store result for retrieval
  @shared_task(ignore_result=False)  # or omit (default)
  def generate_report(workspace_id):
      return create_report(workspace_id)
  ```

### Error Handling

- **Circuit breakers** prevent cascade failures when calling external services:
  ```python
  from circuitbreaker import circuit

  @circuit(failure_threshold=5, recovery_timeout=60)
  def call_external_api(url):
      response = requests.get(url, timeout=10)
      response.raise_for_status()
      return response

  @shared_task(bind=True, max_retries=3)
  def sync_with_service(self, project_id):
      try:
          result = call_external_api(f"https://api.example.com/{project_id}")
          return result
      except CircuitBreakerError:
          # Service unavailable, defer retry
          raise self.retry(countdown=300)
  ```

- **Dead letter patterns** for tasks that exhaust retry limits:
  ```python
  @shared_task(bind=True, max_retries=3)
  def critical_task(self, data):
      try:
          process_data(data)
      except RetryableError as exc:
          try:
              raise self.retry(exc=exc, countdown=60)
          except MaxRetriesExceededError:
              # Log for manual inspection/alerts
              logger.error(f"Task exhausted retries: data={data}")
              notify_ops_team(f"Critical task failed for data: {data}")
              raise  # Preserve failure record
  ```

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
