# LeavePrints security pass 1

Overlay these files onto the current LeavePrints project.

Changes:
- Enables global Flask-WTF CSRF protection.
- Reads `SECRET_KEY` from the environment instead of source code.
- Adds secure session-cookie defaults and basic security headers.
- Makes logout POST-only, login-required and CSRF protected.
- Validates password confirmation and basic field lengths server-side.
- Normalises email login/registration and uses the User password helpers.
- Handles duplicate-registration races safely.
- Points Flask-Login protected routes to the real login page.
- Avoids hard-coded debug mode unless `FLASK_DEBUG=1` is explicitly set.
- Adds `.gitignore` rules for databases, virtualenvs and local secrets.
- Adds `requirements.txt` including Flask-WTF.

Before running:
1. `pip install -r requirements.txt`
2. Set `SECRET_KEY` as described in `SECURITY_SETUP.md`.
3. For local HTTP use `SESSION_COOKIE_SECURE=0`.
4. For production HTTPS use `SESSION_COOKIE_SECURE=1`.

This patch intentionally does not include your `instance/*.db` files or virtual environment.
