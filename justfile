# Variables exported to all recipes
export MY_UID := "1000"
export MY_GID := "1000"

# List available commands (default)
default:
    @just --list

# Copy .env.example to .env if it doesn't exist
setup-env:
    [ ! -f ./.env ] && cp ./.env.example ./.env || echo ".env file already exists."

# Start the docker containers
start:
    echo "Starting the docker containers"
    docker compose up

# Stop containers
stop:
    docker compose down

# Restart containers
restart: stop start

# Run containers in the background
start-bg:
    docker compose up -d

# Tail docker compose logs
logs:
    docker compose logs -f

# Build containers
build:
    docker compose build

# SSH into running django container
ssh:
    docker compose exec django bash

# Get a bash shell into the django container
bash:
    docker compose run --rm --no-deps django bash

# Create a Django superuser
createsuperuser:
    docker compose run --rm django python manage.py createsuperuser

# Create DB migrations in the container
migrations:
    docker compose run --rm django python manage.py makemigrations

# Run DB migrations in the container
migrate:
    docker compose run --rm django python manage.py migrate

# Rebuild translation files
translations:
    docker compose run --rm --no-deps django python manage.py makemessages --all --ignore node_modules --ignore venv --ignore .venv
    docker compose run --rm --no-deps django python manage.py makemessages -d djangojs --all --ignore node_modules --ignore venv --ignore .venv
    docker compose run --rm --no-deps django python manage.py compilemessages --ignore venv --ignore .venv

# Get a Django shell
shell:
    docker compose run --rm django python manage.py shell

# Get a Database shell
dbshell:
    docker compose exec db psql -U postgres testproject

# Run Django tests. E.g. `just test apps.module.tests.test_file`
test *args:
    docker compose run --rm django python manage.py test {{args}}

# Quickly get up and running (start containers and bootstrap DB)
init: setup-env start-bg migrations migrate

# Rebuild requirements and restart containers
requirements: build stop start-bg

# Runs ruff formatter on the codebase
ruff-format:
    docker compose run --rm --no-deps django uv run ruff format .

# Runs ruff linter on the codebase
ruff-lint:
    docker compose run --rm --no-deps django uv run ruff check --fix .

# Formatting and linting using Ruff
ruff: ruff-format ruff-lint

# Runs npm install for all packages
npm-install-all:
    docker compose run --rm --no-deps vite npm install

# Runs npm install (optionally accepting package names). E.g. `just npm-install react`
npm-install *args:
    docker compose run --rm --no-deps vite npm install {{args}}

# Runs npm uninstall (takes package name(s)). E.g. `just npm-uninstall react`
npm-uninstall *args:
    docker compose run --rm --no-deps vite npm uninstall {{args}}

# Runs npm build (for production assets)
npm-build:
    docker compose run --rm --no-deps vite npm run build

# Runs npm dev
npm-dev:
    docker compose run --rm --no-deps vite npm run dev

# Runs the type checker on the front end TypeScript code
npm-type-check:
    docker compose run --rm --no-deps vite npm run type-check

# Update the JavaScript API client code
build-api-client:
    cp ./api-client/package.json ./package.json.api-client
    rm -rf ./api-client
    mkdir -p ./api-client
    mv ./package.json.api-client ./api-client/package.json
    docker run --rm --network host \
        -v ./api-client:/local \
        --user {{MY_UID}}:{{MY_GID}} \
        openapitools/openapi-generator-cli:v7.9.0 generate \
        -i http://localhost:8000/api/schema/ \
        -g typescript-fetch \
        -o /local/
