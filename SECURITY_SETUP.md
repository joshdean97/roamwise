# LeavePrints security setup

Before starting LeavePrints, set a persistent random Flask secret:

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

For local HTTP development, leave secure cookies off:

```bash
export SESSION_COOKIE_SECURE=0
```

For production behind HTTPS, set:

```bash
export SESSION_COOKIE_SECURE=1
```

You can override the database connection using `DATABASE_URL`. If it is not
set, LeavePrints continues to use the local `instance/site.db` SQLite database.

Install dependencies with:

```bash
pip install -r requirements.txt
```

Do not commit or deploy the `instance/*.db` files or a local virtual
environment. The included `.gitignore` excludes both.
