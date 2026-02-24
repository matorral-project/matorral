# Matorral

Matorral is a simple and fast open-source project management tool built with Django, HTMX, and Tailwind CSS.
It supports workspaces, projects, milestones, epics, stories, and sprints.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [just](https://github.com/casey/just) command runner

## Getting started

```bash
git clone https://github.com/matorral-project/matorral.git
cd matorral
just init
```

This copies `.env.example` to `.env`, builds the containers, runs migrations, and seeds the database. Then:

```bash
just start        # start with logs
just start-bg     # start in background
just logs         # tail logs (useful after start-bg)
```

Open http://localhost:8000. Create an admin account:

```bash
just createsuperuser
```

To stop:

```bash
just stop
```

## Configuration

Copy `.env.example` to `.env` and adjust the values as needed. Key settings:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DATABASE_URL` | Postgres connection string |
| `REDIS_URL` | Redis connection string |
| `DEBUG` | Set to `False` in production |

## Contributing

```bash
# Run all tests
just test

# Run a specific test
just test apps.issues.tests.test_views

# Lint and format
just ruff

# Run E2E tests (requires built assets)
just npm-build
just e2e
```

Pull requests are welcome. Please run `just ruff` and `just test` before submitting.

## Deployment

Matorral is configured to deploy to [Fly.io](https://fly.io) via the `fly.toml` at the root of the repo.

### Manual deploy

```bash
flyctl deploy
```

### Continuous deployment (GitHub Actions)

The `deploy.yml` workflow deploys automatically on every push to `main`. It requires a `FLY_API_TOKEN` secret to be set in your GitHub repository:

1. Generate a token: `flyctl auth token`
2. Add it to your repo: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `FLY_API_TOKEN`
   - Value: the token from step 1

## Tech stack

Django · PostgreSQL · Redis · Celery · HTMX · Alpine.js · Tailwind CSS · DaisyUI · Vite

## License

[GNU Affero General Public License v3.0](LICENSE)
