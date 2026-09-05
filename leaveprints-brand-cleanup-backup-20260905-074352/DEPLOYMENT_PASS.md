# Roamwise production deployment pass

This pass prepares the current Flask app for a small public beta on a managed Python host.

## What it changes

- Adds Gunicorn as the production WSGI server.
- Adds psycopg 3 so `DATABASE_URL` can point at PostgreSQL.
- Normalises `postgres://` / `postgresql://` provider URLs to SQLAlchemy's explicit `postgresql+psycopg://` driver internally.
- Refuses accidental SQLite use when `APP_ENV=production` unless explicitly overridden.
- Requires `PUBLIC_APP_URL` in production.
- Defaults production session and remember-me cookies to Secure.
- Adds optional trusted reverse-proxy handling for `X-Forwarded-*` headers.
- Adds HSTS and a small set of safe response headers.
- Adds `/healthz`, including a database connectivity check.
- Extends `.gitignore` so security backups, database dumps, local DBs and real `.env` files stay out of Git while `.env.production.example` remains committable.
- Runs migrations automatically before Gunicorn starts.
- Seeds `city-database.csv` only when the production city table is empty.
- Repairs the historical Alembic baseline so a completely fresh PostgreSQL database can actually migrate from zero.
- Makes the share-trip Boolean migration PostgreSQL-safe.

## Local smoke test after applying

Keep local development on SQLite:

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export APP_ENV=development
export PUBLIC_APP_URL=http://127.0.0.1:5000
pip install -r requirements.txt
python -m compileall app.py core seed_city_data.py gunicorn.conf.py
flask --app app db upgrade
flask --app app run --debug
```

Visit `http://127.0.0.1:5000/healthz`. It should return `{"status":"ok"}`.

## Production environment

Copy values from `.env.production.example` into your hosting provider's environment-variable UI. Do **not** upload an actual `.env` file containing secrets.

Required values:

- `APP_ENV=production`
- `SECRET_KEY=<long random value>`
- `DATABASE_URL=<managed PostgreSQL URL>`
- `PUBLIC_APP_URL=https://...`

For a managed host that terminates HTTPS in front of Flask, set `TRUST_PROXY_HEADERS=1` only if the provider documents that it supplies trusted `X-Forwarded-*` headers.

### Rate limiting and workers

Pass #2 uses Flask-Limiter. `memory://` is process-local, so this deployment defaults to one Gunicorn process with four threads. That keeps beta login throttling coherent without making Redis a launch dependency.

If you later set `WEB_CONCURRENCY` above 1 or run multiple app instances, first configure a shared Flask-Limiter backend such as Redis and set `RATELIMIT_STORAGE_URI` accordingly.

## Start command

Use:

```bash
./start.sh
```

It runs:

1. `flask --app app db upgrade`
2. `python seed_city_data.py` (imports the CSV only if there are zero cities)
3. Gunicorn

## Database migration note

The original first Alembic revision only tried to add an index to `city`; it never created the original `user`, `country`, and `city` tables. That works on the existing local SQLite database because those tables pre-date Alembic, but it fails on a brand-new production database.

This patch makes that first revision a true baseline. Your existing local database is already stamped past that revision, so Alembic will not replay it locally.

The `is_public` server default was also changed from integer `0` to SQLAlchemy `false()`, which is portable to PostgreSQL.

## First deployment checks

After the first deploy, verify:

```text
/healthz                 -> HTTP 200
/                        -> landing page
/auth/register           -> registration works
/auth/login              -> login works
/plan-trip               -> city search is populated
```

Then create a throwaway account, save a trip, log out/in, edit it, and delete it.

## Backups

Prefer automated backups / point-in-time recovery from the managed PostgreSQL provider.

For an extra manual dump from a machine with PostgreSQL client tools installed:

```bash
chmod +x scripts/backup_postgres.sh
./scripts/backup_postgres.sh
```

Do not keep production database dumps in Git or inside the deployed source tree.
