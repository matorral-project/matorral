# alameda

![Build Status](https://travis-ci.com/matagus/alameda.svg)

## Overview

A project managent system / Taiga.io clone with a simpler UX built @ Málaga

## Installation

1. Create a python 3.7.x virtual environment
2. Activate it
3. Install local requirements: `pip install -r requirements/local.txt`
4. Configure a rabbitmq server with the following credentials / setup: user=guest password=guest host=localhost port=5672 virtual host=/alameda.
5. Run: `honcho -f Procfile.local start`
7. Open your browser at `http://localhost:8000`.

## Deploying to heroku:

1. Install the heroku client: https://devcenter.heroku.com/articles/heroku-cli
2. Login using your credentials
3. Add the git remote: `git remote add heroku https://git.heroku.com/alameda-tool.git`
4. Profit!

Every time you want to deploy a new branch just do:

    git push heroku <branch-name>:master

To deploy master just do:

    git push heroku master

## Links

 * [Django-based web interface](https://alameda.dev/)
 * [API](https://alameda.dev/api/v1/)
 * [Admin](https://alameda.dev/admin/)


## Contribute

PRs accepted.

## License

To be defined!
