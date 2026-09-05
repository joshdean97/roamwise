import smtplib
from email.message import EmailMessage

from flask import current_app


def send_password_reset_email(user, reset_url):
    """Send a password reset link using SMTP.

    PASSWORD_RESET_LOG_LINKS=1 is intentionally supported for local development.
    It should remain disabled in production because reset URLs are credentials.
    """

    if current_app.config.get("PASSWORD_RESET_LOG_LINKS"):
        current_app.logger.warning(
            "LOCAL DEV ONLY - password reset link for user id %s: %s",
            user.id,
            reset_url,
        )

    host = current_app.config.get("SMTP_HOST")
    mail_from = current_app.config.get("MAIL_FROM")

    # Local development can use log-only mode without configuring a mail server.
    if not host or not mail_from:
        if current_app.config.get("PASSWORD_RESET_LOG_LINKS"):
            return
        raise RuntimeError(
            "Password reset email is not configured. Set SMTP_HOST and MAIL_FROM."
        )

    message = EmailMessage()
    message["Subject"] = "Reset your Roamwise password"
    message["From"] = mail_from
    message["To"] = user.email
    message.set_content(
        "You asked to reset your Roamwise password.\n\n"
        f"Open this link to choose a new password:\n{reset_url}\n\n"
        "This link expires soon and stops working after your password is changed.\n\n"
        "If you did not request this, you can ignore this email."
    )

    port = current_app.config.get("SMTP_PORT", 587)
    username = current_app.config.get("SMTP_USERNAME")
    password = current_app.config.get("SMTP_PASSWORD")
    use_ssl = bool(current_app.config.get("SMTP_USE_SSL"))
    use_tls = bool(current_app.config.get("SMTP_USE_TLS"))

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP

    with smtp_class(host, port, timeout=10) as server:
        if not use_ssl and use_tls:
            server.starttls()

        if username:
            server.login(username, password or "")

        server.send_message(message)
