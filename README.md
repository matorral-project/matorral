# matorral

## Overview

A very simple project managent tool built with Django & Bulma.io.

Here are some screenshots:

![](https://github.com/matagus/matorral/raw/main/matorral/static/screenshots/stories-1.png)

![](https://github.com/matagus/matorral/raw/main/matorral/static/screenshots/stories-2.png)

![](https://github.com/matagus/matorral/raw/main/matorral/static/screenshots/stories-4.png)

![](https://github.com/matagus/matorral/raw/main/matorral/static/screenshots/epics-1.png)

![](https://github.com/matagus/matorral/raw/main/matorral/static/screenshots/sprints-1.png)


## Features

- Create, edit, delete and list (with pagination) and search Stories, Epics and Sprints
- Stories have assignee, status, priority, points and optionally belong to an Epic and Sprint
- Epics have the same fields and they track progress
- Sprints have start and end dates, and also track progress
- Workspaces to separate stories, epics and sprints
- Login / logout


## Roadmap

- Django 5.0 support
- Enhance test coverage
- Run using docker compose
- Upgrade to Bulma 1.0 + Dark mode
- Support for multiple themes
- Realtime updates
- Milestones
- Multiple assigness
- Kanban view
- History
- Comments everywhere
- Attachments for Stories, Epics and Milestones
- Import data from Jira, Github, Asana, etc
- and more!


## Quick Start

### Install and run locally

1. Clone the repository:

```bash
git clone git@github.com:alameda-project/matorral.git
cd matorral
```

2. Install [hatch](https://hatch.pypa.io/latest/) using `pip`:

```
pip install hatch
```

or see [instructions for alternative methods](https://hatch.pypa.io/latest/install/).

3. Run migrations:

```
hatch run local:migrate
```

4. Run the server:

```
hatch run local:server
```

5. Open your browser at `http://localhost:8000`


### Run Tests

`hatch run test:test` will run the tests in every Python + Django versions combination.

`hatch run test.py3.11-4.2:test will run them for python 3.11 and Django 4.2. Please see possible combinations using
`hatch env show` ("test" matrix).


## Contributing

Contributions are welcome! ❤️


## License

[MPL](https://www.mozilla.org/en-US/MPL/)
