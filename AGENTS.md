# Repository Guidelines

## Source of Truth
Read `context.md` first. It defines the MVP goal, user roles, workflow, trusted data sources, and evaluation criteria for architecture decisions. If this guide and `context.md` conflict, follow `context.md`.

## Project Structure & Module Organization
This is an early-stage Django API project.
- `core/manage.py`: Django management entrypoint
- `core/core/settings.py`: settings, PostgreSQL config, installed apps
- `core/core/urls.py`: root URL routing
- `.env`: local environment values (`DB_NAME`, `DB_USER`, `DB_PASS`/`DB_PASSWORD`, `DB_HOST`, `DB_PORT`)

When adding features, create apps under `core/` (example: `core/accounts/`, `core/claims/`, `core/factchecks/`) and keep DRF code separated into `serializers.py`, `views.py`, `permissions.py`, and `urls.py`.

## Build, Test, and Development Commands
```bash
source .venv/bin/activate
python core/manage.py check
python core/manage.py runserver
python core/manage.py test
```

Schema workflow:
```bash
python core/manage.py makemigrations
python core/manage.py migrate
```
Important: define custom user model and `AUTH_USER_MODEL` before first stable auth migrations.

## Coding Style & Naming Conventions
- PEP 8, 4-space indentation
- `snake_case` for functions/variables, `PascalCase` for classes
- Lowercase app/module names
- Keep settings environment-driven; never hardcode secrets
- Prefer explicit, readable service logic over dense abstractions

## Testing Guidelines
- Framework: Django `TestCase` + DRF API tests
- Test location: per app (`tests.py` or `tests/` package)
- Naming: `test_<behavior>`
- Minimum expectation for new endpoints: success case, validation failure, and permission checks

## Commit & Pull Request Guidelines
- Commit format: `type(scope): summary` (example: `feat(claims): create claim submission endpoint`)
- Keep commits focused and migration-safe
- PRs must include: what changed, why, migration impact, test evidence, and example API request/response

## Security & Configuration Tips
- Do not commit real secrets in `.env`
- Restrict `ALLOWED_HOSTS` and set `DEBUG=False` in production
- Use trusted source ingestion only (RSS/newspapers/official statements) as defined in `context.md`
