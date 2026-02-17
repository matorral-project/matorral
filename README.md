# Matorral

Open source, built simple. Matorral is a lean project management tool for modern teams. It handles team collaboration, project planning, sprints, and task management—without unnecessary complexity  or bloated features.

## A new version is coming!

https://github.com/user-attachments/assets/eab0ad32-0526-42bd-a657-77c7ff0d7c1b

We've been working on a brand new version of Matorral with a completely redesigned experience and new features. The code will be open sourced soon. A private beta is open -- if you're interested in trying it out early, sign up at **[matorral.matagus.dev](https://matorral.matagus.dev/)**.

Legacy code is available at [legacy-code](https://github.com/matorral-project/matorral/tree/legacy-code) branch.

## Why Matorral Exists

We all know the problem. Project management software has become bloated, expensive, and incredibly complex. Teams are drowning in features they don't need, paying for licensing they don't use, and dealing with tools that slow them down rather than speed them up.

Matorral is different. It's open source. It's simple. And it's designed to get out of your way.

Built with modern tools, keeping simplicity in mind. We use [Django](https://www.djangoproject.com/) for a stable, maintainable backend; [HTMX](https://htmx.org/) and [Alpine.js](https://alpinejs.dev/) for responsive interactivity; and [Tailwind CSS](https://tailwindcss.com/) for beautiful, accessible design.

### Features

#### Team Collaboration & Project Management
  - Multi-tenant workspace management with team-based access control
  - Project and roadmap planning with hierarchical epics and stories
  - Sprint and milestone planning with status tracking
  - Inline editing for quick updates to tasks and project details
  - Bulk actions to update status, priority, assignee, and delete items

#### Interactive User Experience

  - Single-page-app-like experience with HTMX and Alpine.js
  - Responsive design built on Tailwind CSS and DaisyUI components
  - Progressive enhancement for reliability

#### Authentication & Multi-tenancy

  - User authentication via django-allauth
  - Team-based access control and permissions
  - Free tier with usage limits for public beta

### Technical Infrastructure

#### Backend

  - Django REST Framework for APIs with OpenAPI schema
  - PostgreSQL database with optimized queries
  - Celery for async jobs and scheduled tasks
  - Redis for caching and message broker

#### Frontend & DevOps

  - Vite bundler with hot-reload development
  - Docker-based development environment
  - Comprehensive E2E tests (Playwright)
  - Unit tests and code quality tools (Ruff)
  - Sentry monitoring and error tracking
