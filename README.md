# matorral

![Build Status](https://travis-ci.com/matagus/matorral.svg)

## Overview

A very simple project managent tool built with Django & Bulma.io & Turbolinks, made in order to learn some of the new
Django 2.x features and specially Django Channels :)

Here are some screenshots:

![](https://github.com/matagus/matorral/raw/master/matorral/static/screenshots/stories-1.png)

![](https://github.com/matagus/matorral/raw/master/matorral/static/screenshots/stories-2.png)

![](https://github.com/matagus/matorral/raw/master/matorral/static/screenshots/stories-4.png)

![](https://github.com/matagus/matorral/raw/master/matorral/static/screenshots/epics-1.png)

![](https://github.com/matagus/matorral/raw/master/matorral/static/screenshots/sprints-1.png)

## Installation

1. Create a python 3.7.x virtual environment
2. Activate it
3. Install local requirements: `pip install -r requirements/local.txt`
4. Configure a rabbitmq server with the following credentials / setup: user=guest password=guest host=localhost port=5672 virtual host=/matorral.
5. Run: `honcho -f Procfile.local start`
7. Open your browser at `http://localhost:8000`.

## Deploying to heroku:

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

## Links

 * [Demo](https://matorral.alameda.dev/). Username: `demo` \ password: `demopass`. Please be kind :)
 * [Admin](https://matorral.alameda.dev/admin/)


## Contribute

PRs accepted.

## License

[MPL](https://www.mozilla.org/en-US/MPL/)
