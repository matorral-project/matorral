# Matorral

[![codecov](https://codecov.io/gh/matorral-project/matorral/branch/main/graph/badge.svg)](https://codecov.io/gh/matorral-project/matorral)

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

# Run tests with coverage and print report
just cov

# Run tests with coverage only
just test-cov

# Print coverage report from last run
just cov-report
```

Pull requests are welcome. Please run `just test` and configure `pre-commit` before committing and pushing changes.

## Coverage

Test coverage is tracked via [Codecov](https://codecov.io/gh/matorral-project/matorral). Coverage reports are uploaded automatically on every push to `main` and on pull requests.

To set up Codecov for your own fork:
1. Log in at [codecov.io](https://codecov.io) and link your GitHub repository.
2. Copy the `CODECOV_TOKEN` from your Codecov project settings.
3. Add it as a secret named `CODECOV_TOKEN` in your GitHub repository settings under **Settings → Secrets and variables → Actions**.

## Tech stack

Django · PostgreSQL · Redis · Celery · HTMX · Alpine.js · Tailwind CSS · DaisyUI · Vite

## License

[GNU Affero General Public License v3.0](LICENSE)
