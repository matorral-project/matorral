# Default recipe: List all available recipes
default:
    @just --list

# Start all Docker containers in the foreground
start:
    echo "Starting the docker containers"
    docker compose up

# Stop and remove all Docker containers
stop:
    docker compose down

# Restart all Docker containers
restart: stop start

# Restart all Docker containers in detached mode (background)
restart-detached: stop start-detached

# Start all Docker containers in detached mode (background)
start-detached:
    docker compose up -d

# Follow live logs from all Docker containers
logs:
    docker compose logs -f

# Build or rebuild Docker images
build:
    docker compose build

# Open an interactive bash session in the running Django container
bash:
    docker compose exec django bash

# Spawn a new temporary Django container with a bash shell
bash-temp:
    docker compose run --rm --no-deps django bash

# Run the Django createsuperuser management command
createsuperuser:
    docker compose run --rm django python manage.py createsuperuser

# Promote an existing user to staff and superuser by email (e.g. `just make-superuser user@example.com`)
make-superuser email:
    docker compose run --rm django python manage.py make_superuser {{email}}

# Generate new Django database migrations
make-migrations:
    docker compose run --rm django python manage.py makemigrations

# Apply pending Django database migrations
migrate:
    docker compose run --rm django python manage.py migrate

# Extract and compile Django translation messages (.po/.mo files)
make-translations:
    docker compose run --rm --no-deps django python manage.py makemessages --all --ignore node_modules --ignore venv --ignore .venv
    docker compose run --rm --no-deps django python manage.py makemessages -d djangojs --all --ignore node_modules --ignore venv --ignore .venv
    docker compose run --rm --no-deps django python manage.py compilemessages --ignore venv --ignore .venv

# Open an interactive Django Python shell
shell:
    docker compose run --rm django python manage.py shell

# Open a PostgreSQL database shell (psql)
dbshell:
    docker compose exec db psql -U postgres matorral

# Execute the Django test suite. Pass args to run specific tests (e.g. `just test apps.module.tests`)
test *args:
    docker compose run --rm django python manage.py test {{args}}

# Run tests under coverage
test-cov *args:
    docker compose run --rm django uv run coverage run -m pytest apps/ -v --tb=short {{args}}

# Generate coverage json + terminal report
cov-report:
    docker compose run --rm django sh -c "uv run coverage json && uv run coverage report"

# Run tests under coverage and generate reports
cov *args:
    just test-cov {{args}}
    just cov-report

# Bootstrap the project: start containers and apply migrations
init: start-detached make-migrations migrate

# Rebuild Docker images and restart containers in the background
requirements: build stop start-detached

# Install all Node.js dependencies in the Vite container
npm-install-all:
    docker compose run --rm --no-deps vite npm install

# Install specific Node.js packages (e.g., `just npm-install react`)
npm-install *args:
    docker compose run --rm --no-deps vite npm install {{args}}

# Uninstall specific Node.js packages (e.g., `just npm-uninstall react`)
npm-uninstall *args:
    docker compose run --rm --no-deps vite npm uninstall {{args}}

# Build frontend assets for production using Vite
npm-build:
    docker compose run --rm --no-deps vite npm run build

# Start the Vite development server for frontend assets
npm-dev:
    docker compose run --rm --no-deps vite npm run dev

# Run TypeScript type checking on frontend code
npm-type-check:
    docker compose run --rm --no-deps vite npm run type-check
