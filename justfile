

makemigrations:
  DJANGO_SETTINGS_MODULE=project.settings.development ./project/manage.py makemigrations

migrate:
  DJANGO_SETTINGS_MODULE=project.settings.development ./project/manage.py migrate

test:
  DJANGO_SETTINGS_MODULE=project.settings.test uv run pytest | tee /tmp/blueflow-test-$(date +'%Y%m%d%H%M')

run:
  i
  DJANGO_SETTINGS_MODULE=project.settings.development ./project/manage.py runserver

up:
  docker-compose up

install:
  uv sync --all-extras

