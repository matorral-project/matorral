# Matorral

**WARNING** This is a work in progress. This codebase is not working yet.

Matorral is a simple and fast open-source project management tool built with Django, HTMX, and Tailwind CSS.
It supports workspaces, projects, milestones, epics, stories, and sprints.

## Try it out!

An example demo instance is available at **[matorral.matagus.dev](https://matorral.matagus.dev/)**
 * username: `demo@example.com`
 * password: `demouser789`

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
just start              # start with logs
just start-detached     # start in background
just logs               # tail logs (useful after start-bg)
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

Pull requests are welcome. Please run `just test` and configure `pre-commit` before committing and pushing changes.

## Deployment

Matorral is configured to deploy to [Fly.io](https://fly.io) via the `fly.toml` at the root of the repo.

## Tech stack

Django · PostgreSQL · Redis · Celery · HTMX · Alpine.js · Tailwind CSS · DaisyUI · Vite

## License

[GNU Affero General Public License v3.0](LICENSE)
