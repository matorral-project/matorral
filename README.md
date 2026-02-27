[![Codecov](https://codecov.io/gh/matorral-project/matorral/branch/main/graph/badge.svg)](https://codecov.io/gh/matorral-project/matorral) [![Django Packages](https://img.shields.io/badge/PyPI-matorral-tags.svg)](https://djangopackages.org/packages/p/matorral/) [![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0) [![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/release/python-3140/) [![Django 6.0](https://img.shields.io/badge/django-6.0-green.svg)](https://docs.djangoproject.com/en/6.0/)

<h1 align="center">Matorral</h1>
<p align="center">
  <strong>A simple and fast open-source project management tool</strong>
</p>

<p align="center">
  <a href="https://matorral.matagus.dev/">Live Demo</a> •
  <a href="#features">Features</a> •
  <a href="#getting-started">Getting Started</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## Features

- **Workspaces** - Organize your teams and projects in isolated workspaces
- **Projects** - Create multiple projects per workspace with unique issue keys
- **Issue Hierarchy** - Structure work as Epics → Stories → Subtasks and Bugs
- **Milestones** - Group and track issues toward key delivery points
- **Sprints** - Plan and execute iterative development cycles
- **Priorities & Assignees** - Keep your team aligned on what matters most
- **Search & Filters** - Quickly find any issue across your project
- **Authentication** - Email and GitHub OAuth login support

![Matorral Screenshot](https://raw.githubusercontent.com/matorral-project/matorral/main/apps/landing_pages/static/landing_pages/images/app-screenshot.png)

## Try it out!

An example demo instance is available at **[matorral.matagus.dev](https://matorral.matagus.dev/)**

| Credential | Value |
|---|---|
| Username | `demo@example.com` |
| Password | `demouser789` |

## Getting Started

### Requirements

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [just](https://github.com/casey/just) command runner

### Setup

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

## Roadmap

### Available Now

| Feature | Description |
|---|---|
| **Workspaces** | Isolated multi-tenant workspaces for your teams |
| **Projects** | Multiple projects per workspace with unique issue keys |
| **Issue Hierarchy** | Epics → Stories → Subtasks and Bugs |
| **Milestones** | Group and track issues toward delivery goals |
| **Sprints** | Plan and execute iterative development cycles |
| **Priorities & Assignees** | Assign and prioritize work across your team |
| **Search & Filters** | Find any issue quickly across your project |
| **Authentication** | Email and GitHub OAuth login support |

### Coming Soon

- Realtime updates
- Drag & drop support
- Integration with GitHub, GitLab, and Bitbucket
- Two-way sync with Jira, Linear, and more
- AI features
- Attachments and images
- Notifications and activity feeds
- And more!

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

Test coverage is tracked via [Codecov](https://codecov.io/gh/matorral-project/matorral). Coverage reports are uploaded automatically on every push to `main` and on pull requests.

To set up Codecov for your own fork:
1. Log in at [codecov.io](https://codecov.io) and link your GitHub repository.
2. Copy the `CODECOV_TOKEN` from your Codecov project settings.
3. Add it as a secret named `CODECOV_TOKEN` in your GitHub repository settings under **Settings → Secrets and variables → Actions**.

## Tech Stack

Django · PostgreSQL · Redis · Celery · HTMX · Alpine.js · Tailwind CSS · DaisyUI · Vite

## License

[GNU Affero General Public License v3.0](LICENSE)

---

<p align="center">
  <a href="https://matorral.matagus.dev/">Live Demo</a> •
  <a href="https://github.com/matorral-project/matorral">Star us on GitHub</a> •
  <a href="https://github.com/matorral-project/matorral/issues">Report Bug</a> •
  <a href="https://github.com/matorral-project/matorral/issues">Request Feature</a>
</p>

---
