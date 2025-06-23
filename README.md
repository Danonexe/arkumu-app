# arkumu

Archive der Kunst- und Musikhochschulen

This is the repository for [arkumu.nrw](https://www.dh.nrw/kooperationen/arkumu.nrw-108), a consortium project of art and music universities in North Rhine-Westphalia, Germany. The project aims to digitize and make available multimedia content from participating institutions, providing access to artistic-scientific digital archives for research, teaching, and the general public.

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

License: MIT

## Quick Start with Docker

To get the application running locally:

    $ docker compose -f docker-compose.local.yml up

Create a superuser account:

    $ docker compose -f docker-compose.local.yml run --rm django python manage.py createsuperuser

Once created, you can login with your superuser credentials at `http://localhost:8000/admin/` to access the Django admin interface.

## Development

For detailed development instructions, testing, deployment, and other advanced features, see the [Cookiecutter Django documentation](https://cookiecutter-django.readthedocs.io/).
