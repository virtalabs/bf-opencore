

makemigrations:
   DJANGO_SETTINGS_MODULE=project.settings.development ./project/manage.py makemigrations

migrate:
   DJANGO_SETTINGS_MODULE=project.settings.development ./project/manage.py migrate

test:
   DJANGO_SETTINGS_MODULE=project.settings.test uv run pytest
