

makemigrations:
  DJANGO_SETTINGS_MODULE=project.settings.development ./project/manage.py makemigrations

migrate:
  DJANGO_SETTINGS_MODULE=project.settings.development ./project/manage.py migrate

test:
  DJANGO_SETTINGS_MODULE=project.settings.test uv run pytest | tee /tmp/blueflow-test-$(date +'%Y%m%d%H%M')

run:
  DJANGO_SETTINGS_MODULE=project.settings.development ./project/manage.py runserver

up:
  docker-compose up

install:
  uv sync --all-extras

api-docs:
  DJANGO_SETTINGS_MODULE=project.settings.development ./project/manage.py spectacular --validate

security-check:
  uv run bandit --severity-level high --confidence-level medium -f json --output /tmp/report.json --recursive blueflow

security-report:
  uv run bandit --exit-zero --severity-level high --confidence-level medium -f json --output /tmp/report.json --recursive blueflow
  uv run python -c 'import json; totals = json.loads(open("/tmp/report.json").read())["metrics"]["_totals"]; print(json.dumps(totals, indent=2, sort_keys=True))' > bandit.json

