# Contributing to Matorral

We welcome contributions! This guide will help you get up and running.

If you have questions, reach out on [GitHub Discussions](https://github.com/orgs/matorral-project/discussions) — we're happy to help.

Found a bug? Please [open an issue](https://github.com/matorral-project/matorral/issues).

---

## Getting Started

### Requirements

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [just](https://github.com/casey/just) command runner
- [pre-commit](https://pre-commit.com/) (see below)

### Fork and clone

1. Fork the repository on GitHub.
2. Clone your fork locally:

```bash
git clone git@github.com:your-username/matorral.git
cd matorral
```

### First-time setup

Copy the example env file and review the values (at minimum, set `SECRET_KEY`):

```bash
cp .env.example .env
```

Then run the init command, which builds containers, runs migrations, and seeds the database:

```bash
just init
```

### Start the app

```bash
just start              # start all containers with logs
just start-detached     # start in background
just logs               # tail logs
```

Open [http://localhost:8000](http://localhost:8000). Create an admin account:

```bash
just createsuperuser
```

To stop:

```bash
just stop
```

> **Note:** Any change to `pyproject.toml` requires `just requirements` to rebuild the containers.

---

## Running Tests

Tests run inside Docker via `just`. Use dotted module paths, not file paths:

```bash
# Run all tests
just test

# Run tests for a specific app
just test apps.issues

# Run a specific test module
just test apps.issues.tests.test_views

# Run a specific test class or method
just test apps/issues/tests/test_models.py::TestIssueModel::test_method

# Run tests with coverage and print report
just cov

# Run tests with coverage only (no report)
just test-cov

# Print coverage report from a previous run
just cov-report
```

You can also run tests locally without Docker using `uv`:

```bash
uv run pytest apps/ -v --tb=short
uv run pytest apps/issues/ -v
```

> **Note:** Running locally requires a reachable PostgreSQL instance. The Docker setup is recommended.

---

## Setting Up pre-commit

We use [pre-commit](https://pre-commit.com/) to run linters and code checks before every commit. **Please set this up before making any changes** — it's what CI will check too.

Install pre-commit (if you don't have it):

```bash
pip install pre-commit
# or via brew:
brew install pre-commit
```

Then install the hooks in your local repo:

```bash
pre-commit install
```

From now on, the following checks will run automatically on `git commit`:

- **ruff** — linter and formatter (line length: 120, double quotes)
- **black** — code formatter
- **isort** — import sorter (black profile)
- **pyupgrade** — upgrades syntax to Python 3.14
- **codespell** — spell checker

You can also run all hooks manually at any time:

```bash
pre-commit run --all-files
```

---

## Making Changes

1. Create a branch for your work:

```bash
git checkout -b my-feature-or-fix
```

2. Make your changes and write tests. We aim for good test coverage — please include tests for any new behavior or bug fixes.

3. Ensure all tests pass:

```bash
just test
```

4. Ensure pre-commit checks pass:

```bash
pre-commit run --all-files
```

5. Push your branch to your fork and open a pull request against `main`.

We typically respond to pull requests within a few days. Pull requests are more likely to be accepted when they:

- Include tests covering the changes
- Follow the existing code style (enforced by pre-commit)
- Have a clear description of what the change does and why

---

## Notes for LLM-Assisted Development

If you are using an AI assistant (Claude, Copilot, Cursor, etc.) to help with contributions, point it at [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md). These files contain architecture notes, patterns, and conventions that help the model understand the codebase correctly.

---

## Tech Stack

Django · PostgreSQL · Redis · Celery · HTMX · Alpine.js · Tailwind CSS · DaisyUI · Vite
