# Roamwise security pass #2

This patch is designed to be applied **after security pass #1**.

## Adds

- Per-IP rate limiting with Flask-Limiter:
  - login POST: 10/minute
  - registration POST: 5/hour
  - forgot-password POST: 5/15 minutes
  - password-reset POST: 10/hour
- Forgot-password and password-reset pages.
- Signed reset tokens that expire (default: 1 hour).
- Previously issued reset tokens become invalid immediately after a password change.
- Generic forgot-password responses to avoid revealing which email addresses are registered.
- SMTP email delivery using environment variables.
- Explicit local-development log-only reset-link mode.
- Friendly HTTP 429 page.
- Auth security tests.

## Required install

```bash
pip install -r requirements.txt
```

## Local password-reset test

For local development only:

```bash
export PASSWORD_RESET_LOG_LINKS=1
export PUBLIC_APP_URL='http://127.0.0.1:5000'
```

Request a reset from `/auth/forgot-password`. The reset URL will be written to the Flask server log instead of emailed.

**Never enable `PASSWORD_RESET_LOG_LINKS` in production.** Reset links are credentials.

## Production email environment variables

```bash
export PUBLIC_APP_URL='https://YOUR-DOMAIN'
export SMTP_HOST='smtp.your-provider.com'
export SMTP_PORT='587'
export SMTP_USERNAME='YOUR_USERNAME'
export SMTP_PASSWORD='YOUR_PASSWORD'
export SMTP_USE_TLS='1'
export SMTP_USE_SSL='0'
export MAIL_FROM='Roamwise <no-reply@YOUR-DOMAIN>'
```

Use either TLS/STARTTLS or SSL according to the provider. For SSL (commonly port 465), set `SMTP_USE_SSL=1` and `SMTP_USE_TLS=0`.

## Rate-limit storage

The default `memory://` backend is fine for local development and a simple single-process beta instance. It is not shared across multiple workers/containers.

For a multi-worker production deployment, configure a shared Flask-Limiter-supported storage backend, commonly Redis, for example:

```bash
export RATELIMIT_STORAGE_URI='redis://...'
```

We should choose the exact value when the production host is selected.

## CSS

Append `AUTH_STYLES_APPEND.css` to the end of `core/static/styles.css`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```
