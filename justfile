# =============================================================================
# Matorral Justfile - Task Runner for Development
# https://github.com/casey/just
# =============================================================================
#
# Quick start:
#   just init              # First-time setup
#   just start             # Start all services
#   just test              # Run the test suite
#
# For LLMs/Agents:
#   just --list            # List all recipes with descriptions
#   just check             # Run all checks (tests, migrations, pre-commit)
#   just doctor            # Verify environment is ready
# =============================================================================

# Default: List all available recipes with descriptions
[private]
default:
    @just --list --unsorted

# =============================================================================
# Development Environment
# =============================================================================

# First-time setup: copy .env, build, start services, migrate, seed DB (WARNING: resets DB!)
[doc("Initialize project for first-time development")]
init:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🚀 Initializing Matorral development environment..."
    if [ ! -f .env ]; then
        echo "📋 Copying .env.example to .env..."
        cp .env.example .env
    fi
    echo "🐳 Building and starting containers..."
    docker compose up -d --build
    echo "⏳ Waiting for services to be healthy..."
    sleep 5
    echo "🗄️  Running migrations..."
    just migrate
    echo "✅ Initialization complete! Run 'just doctor' to verify."

# Verify environment is ready (check .env, containers, migrations)
[doc("Check if development environment is properly configured")]
doctor:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🔍 Running environment checks..."
    FAILED=0
    # Check .env exists
    if [ ! -f .env ]; then
        echo "❌ .env file missing - run 'just init'"
        FAILED=1
    else
        echo "✅ .env file exists"
    fi
    # Check containers are running
    if docker compose ps | grep -q "Up"; then
        echo "✅ Docker containers are running"
    else
        echo "❌ Docker containers not running - run 'just start'"
        FAILED=1
       fi
    # Check Django can import
    if docker compose exec -T django python -c "import django" 2>/dev/null; then
        echo "✅ Django is accessible"
    else
        echo "❌ Django not accessible - check logs with 'just logs'"
        FAILED=1
    fi
    # Check for unapplied migrations
    if docker compose run --rm django python manage.py showmigrations --plan 2>/dev/null | grep -q "\[ \]"; then
        echo "⚠️  Unapplied migrations found - run 'just migrate'"
    else
        echo "✅ All migrations applied"
    fi
    if [ $FAILED -eq 0 ]; then
        echo "🎉 Environment is healthy!"
        exit 0
    else
        echo "❌ Environment has issues - see above"
        exit 1
    fi

# Rebuild Docker images and restart (use after Dockerfile changes)
[doc("Rebuild containers after Dockerfile or requirements changes")]
rebuild: stop
    docker compose up -d --build
    @echo "✅ Rebuild complete. Run 'just doctor' to verify."

# =============================================================================
# Container Lifecycle
# =============================================================================

# Start all Docker containers in the foreground (logs visible)
[doc("Start all services in foreground (logs visible, Ctrl+C to stop)")]
start:
    docker compose up

# Start all Docker containers in detached mode (background)
[doc("Start all services in background")]
start-detached:
    docker compose up -d
    @echo "✅ Services started. Use 'just logs' to view logs."

# Stop and remove all Docker containers
[doc("Stop all services")]
stop:
    docker compose down

# Restart all Docker containers in the foreground (runs sequentially)
[doc("Restart all services in foreground")]
restart:
    just stop
    just start

# Restart all Docker containers in detached mode
[doc("Restart all services in background")]
restart-detached:
    just stop
    just start-detached

# Show status of all containers
[doc("Show status of all containers")]
status:
    docker compose ps

# =============================================================================
# Logs
# =============================================================================

# Follow live logs from all Docker containers
[doc("Follow logs from all services")]
logs:
    docker compose logs -f

# Follow logs from Django only
[doc("Follow Django logs only")]
logs-django:
    docker compose logs -f django

# Follow logs from database only
[doc("Follow PostgreSQL logs only")]
logs-db:
    docker compose logs -f db

# Follow logs from Redis only
[doc("Follow Redis logs only")]
logs-redis:
    docker compose logs -f redis

# Follow logs from Celery only
[doc("Follow Celery worker logs only")]
logs-celery:
    docker compose logs -f celery

# Follow logs from Vite only
[doc("Follow Vite dev server logs only")]
logs-vite:
    docker compose logs -f vite

# =============================================================================
# Django Commands
# =============================================================================

# Run arbitrary Django management command (e.g., `just manage shell`, `just manage dbshell`)
[doc("Run any Django management command: just manage <command>")]
manage *args:
    docker compose run --rm django python manage.py {{args}}

# Apply pending Django database migrations
[doc("Apply database migrations")]
migrate:
    docker compose run --rm django python manage.py migrate

# Generate new Django database migrations
[doc("Create new database migrations")]
make-migrations *args:
    docker compose run --rm django python manage.py makemigrations {{args}}

# Check for missing migrations (CI-friendly)
[doc("Check for uncreated migrations (CI-friendly)")]
check-migrations:
    docker compose run --rm django python manage.py makemigrations --check --dry-run

# Open an interactive Django Python shell
[doc("Open Django shell")]
shell:
    docker compose run --rm django python manage.py shell

# Open a PostgreSQL database shell (psql)
[doc("Open PostgreSQL shell")]
dbshell:
    docker compose exec db psql -U postgres matorral

# Run the Django createsuperuser management command
[doc("Create a superuser interactively")]
createsuperuser:
    docker compose run --rm django python manage.py createsuperuser

# Promote an existing user to staff and superuser by email
[doc("Promote user to superuser: just make-superuser <email>")]
make-superuser email:
    docker compose run --rm django python manage.py make_superuser {{email}}

# Load fixture data (e.g., `just loaddata initial_data`)
[doc("Load fixture data: just loaddata <fixture_name>")]
loaddata *args:
    docker compose run --rm django python manage.py loaddata {{args}}

# Dump data to fixture (e.g., `just dumpdata auth.User > users.json`)
[doc("Dump data to fixture")]
dumpdata *args:
    docker compose run --rm django python manage.py dumpdata {{args}}

# =============================================================================
# Testing
# =============================================================================

# Run Django tests (e.g., `just test apps.issues`, `just test apps.issues.tests.test_models`)
[doc("Run Django tests: just test [path.to.module]")]
test *args:
    docker compose run --rm django python manage.py test {{args}}

# Run tests under coverage
[doc("Run tests with coverage reporting")]
test-cov *args:
    docker compose run --rm django uv run coverage run manage.py test apps {{args}}

# Generate coverage JSON + terminal report
[doc("Generate coverage reports")]
cov-report:
    docker compose run --rm django sh -c "uv run coverage json && uv run coverage report"

# Run tests under coverage and generate reports
[doc("Run tests with coverage and generate reports")]
cov *args: (test-cov args) cov-report

# =============================================================================
# Code Quality
# =============================================================================

# Run pre-commit on all files
[doc("Run all pre-commit hooks on all files")]
pre-commit:
    pre-commit run --all-files

# Run pre-commit on staged files only
[doc("Run pre-commit on staged files only")]
pre-commit-staged:
    pre-commit run

# Run linter (ruff) via pre-commit
[doc("Run linter (ruff) on all files")]
lint:
    pre-commit run ruff --all-files

# Run code formatter (ruff format) via pre-commit
[doc("Run code formatter on all files")]
fmt:
    pre-commit run ruff-format --all-files

# Run all checks (tests, migrations check, pre-commit)
[doc("Run complete check suite (tests, migrations, pre-commit)")]
check: test check-migrations pre-commit
    @echo "✅ All checks passed!"

# =============================================================================
# Translations
# =============================================================================

# Extract and compile Django translation messages (.po/.mo files)
[doc("Update translation files (.po/.mo)")]
make-translations:
    docker compose run --rm --no-deps django python manage.py makemessages --all --ignore node_modules --ignore venv --ignore .venv
    docker compose run --rm --no-deps django python manage.py makemessages -d djangojs --all --ignore node_modules --ignore venv --ignore .venv
    docker compose run --rm --no-deps django python manage.py compilemessages --ignore venv --ignore .venv

# =============================================================================
# Frontend (Node.js/Vite)
# =============================================================================

# Install all Node.js dependencies
[doc("Install all Node.js dependencies")]
npm-install-all:
    docker compose run --rm --no-deps vite npm install

# Install specific Node.js packages (e.g., `just npm-install react`)
[doc("Install specific npm packages: just npm-install <package>")]
npm-install *args:
    docker compose run --rm --no-deps vite npm install {{args}}

# Uninstall specific Node.js packages (e.g., `just npm-uninstall react`)
[doc("Uninstall specific npm packages: just npm-uninstall <package>")]
npm-uninstall *args:
    docker compose run --rm --no-deps vite npm uninstall {{args}}

# Build frontend assets for production using Vite
[doc("Build frontend assets for production")]
npm-build:
    docker compose run --rm --no-deps vite npm run build

# Start the Vite development server for frontend assets
[doc("Start Vite dev server (foreground)")]
npm-dev:
    docker compose run --rm --no-deps vite npm run dev

# Run TypeScript type checking on frontend code
[doc("Run TypeScript type checker")]
npm-type-check:
    docker compose run --rm --no-deps vite npm run type-check

# Run TypeScript type checking in watch mode
[doc("Run TypeScript type checker in watch mode")]
npm-type-check-watch:
    docker compose run --rm --no-deps vite npm run type-check-watch

# =============================================================================
# Shell Access
# =============================================================================

# Open an interactive bash session in the running Django container
[doc("Open bash in running Django container")]
bash:
    docker compose exec django bash

# Spawn a new temporary Django container with a bash shell
[doc("Spawn temporary Django container with bash")]
bash-temp:
    docker compose run --rm --no-deps django bash

# Open bash in the Vite container
[doc("Open bash in Vite container")]
bash-vite:
    docker compose exec vite bash

# Open bash in the database container
[doc("Open bash in PostgreSQL container")]
bash-db:
    docker compose exec db bash

# =============================================================================
# Cleanup
# =============================================================================

# Remove all containers, volumes, and orphaned containers (WARNING: deletes DB!)
[doc("Clean everything - WARNING: deletes all data!")]
clean:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "⚠️  This will remove all containers and DELETE YOUR DATABASE!"
    read -p "Are you sure? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose down -v --remove-orphans
        echo "✅ Cleanup complete. Run 'just init' to start fresh."
    else
        echo "❌ Cancelled."
    fi

# Remove stopped containers and dangling images
[doc("Prune stopped containers and unused images")]
prune:
    docker system prune -f

# =============================================================================
# Legacy/Deprecated (kept for compatibility)
# =============================================================================

# Rebuild Docker images and restart containers (alias for rebuild)
[doc("Alias for 'just rebuild'")]
requirements: rebuild
