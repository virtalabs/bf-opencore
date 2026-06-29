

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
  uv run bandit --configfile pyproject.toml --severity-level high --confidence-level medium -f json --output /tmp/report.json --recursive blueflow

security-report:
  uv run bandit --configfile pyproject.toml --exit-zero --severity-level high --confidence-level medium -f json --output /tmp/report.json --recursive blueflow
  uv run python -c 'import json; totals = json.loads(open("/tmp/report.json").read())["metrics"]["_totals"]; print(json.dumps(totals, indent=2, sort_keys=True))' > bandit.json

diff-security:
  uv run python -c '\
  import json;\
  import sys;\
  new = json.load(open("/tmp/report.json"))["metrics"]["_totals"];\
  historic = json.load(open("bandit.json"));\
  del new["loc"];\
  del historic["loc"];\
  sys.exit(int(historic != new))'
