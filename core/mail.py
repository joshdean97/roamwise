import smtplib
from email.message import EmailMessage
from html import escape

from flask import current_app


def _send_message(message):
    host = current_app.config.get("SMTP_HOST")
    mail_from = current_app.config.get("MAIL_FROM")

    if not host or not mail_from:
        raise RuntimeError(
            "Email is not configured. Set SMTP_HOST and MAIL_FROM."
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


def send_password_reset_email(user, reset_url):
    """Send a password reset link using SMTP."""

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
    message["Subject"] = "Reset your LeavePrints password"
    message["From"] = mail_from
    message["To"] = user.email
    message.set_content(
        "You asked to reset your LeavePrints password.\n\n"
        f"Open this link to choose a new password:\n{reset_url}\n\n"
        "This link expires soon and stops working after your password is changed.\n\n"
        "If you did not request this, you can ignore this email."
    )

    _send_message(message)


def send_email_confirmation(user, confirmation_url):
    """Send the account email-confirmation link using the configured SMTP provider."""

    if current_app.config.get("EMAIL_CONFIRMATION_LOG_LINKS"):
        current_app.logger.warning(
            "LOCAL DEV ONLY - email confirmation link for user id %s: %s",
            user.id,
            confirmation_url,
        )

    host = current_app.config.get("SMTP_HOST")
    mail_from = current_app.config.get("MAIL_FROM")

    if not host or not mail_from:
        if current_app.config.get("EMAIL_CONFIRMATION_LOG_LINKS"):
            return
        raise RuntimeError(
            "Email confirmation is not configured. Set SMTP_HOST and MAIL_FROM."
        )

    message = EmailMessage()
    message["Subject"] = "Confirm your LeavePrints email"
    message["From"] = mail_from
    message["To"] = user.email
    message.set_content(
        f"Hey {user.username},\n\n"
        "Welcome to LeavePrints. Confirm your email to finish creating your account:\n\n"
        f"{confirmation_url}\n\n"
        "This link expires in 24 hours.\n\n"
        "If you did not create a LeavePrints account, you can ignore this email."
    )

    _send_message(message)


def send_onboarding_email(user, planner_url):
    """Send the one-off product guide three days after signup."""

    mail_from = current_app.config.get("MAIL_FROM")
    if not current_app.config.get("SMTP_HOST") or not mail_from:
        raise RuntimeError("Onboarding email is not configured.")

    message = EmailMessage()
    message["Subject"] = "Getting the most out of LeavePrints"
    message["From"] = mail_from
    message["To"] = user.email

    reply_to = current_app.config.get("MAIL_REPLY_TO")
    if reply_to:
        message["Reply-To"] = reply_to

    message.set_content(
        "Hey!\n\n"
        "You’ve had a few days to play around with LeavePrints, so I wanted "
        "to share a few ways to get the most out of it.\n\n"
        "Start with a trip, not individual cities.\n"
        "LeavePrints works best when you use it to compare the overall cost "
        "of different routes rather than trying to plan everything perfectly "
        "from the start.\n\n"
        "Play around with the route.\n"
        "Swap cities in and out, change how long you're staying, and see what "
        "it does to your overall budget. Sometimes one small change can make "
        "a surprisingly big difference.\n\n"
        "Use the costs as a starting point.\n"
        "Travel prices obviously change, but the idea is to give you a realistic "
        "baseline before you book anything — especially when you're comparing "
        "different destinations.\n\n"
        f"Plan a trip: {planner_url}\n\n"
        "And this is still a very early version of LeavePrints.\n\n"
        "I'm actively building it based on how people actually use it, so if "
        "there's something you expected it to do, something that confused you, "
        "or something you'd love me to add, just reply to this email.\n\n"
        "I read all of them.\n\n"
        "Josh\n"
        "LeavePrints"
    )

    safe_planner_url = escape(planner_url, quote=True)
    message.add_alternative(
        f"""\
<!doctype html>
<html lang="en">
  <body style="margin:0;background:#f6f1e7;color:#173b2d;font-family:Arial,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
      Three simple ways to plan a better route with LeavePrints.
    </div>
    <div style="max-width:620px;margin:0 auto;padding:32px 18px;">
      <div style="background:#fffdf7;border:1px solid #e4dccb;border-radius:18px;padding:32px;">
        <div style="font-size:23px;font-weight:800;margin-bottom:28px;">LeavePrints</div>
        <p style="font-size:16px;line-height:1.65;margin:0 0 18px;">Hey!</p>
        <p style="font-size:16px;line-height:1.65;margin:0 0 24px;">You’ve had a few days to play around with LeavePrints, so I wanted to share a few ways to get the most out of it.</p>

        <p style="font-size:16px;line-height:1.65;margin:0 0 22px;"><strong>Start with a trip, not individual cities.</strong><br>LeavePrints works best when you use it to compare the overall cost of different routes rather than trying to plan everything perfectly from the start.</p>
        <p style="font-size:16px;line-height:1.65;margin:0 0 22px;"><strong>Play around with the route.</strong><br>Swap cities in and out, change how long you're staying, and see what it does to your overall budget. Sometimes one small change can make a surprisingly big difference.</p>
        <p style="font-size:16px;line-height:1.65;margin:0 0 26px;"><strong>Use the costs as a starting point.</strong><br>Travel prices obviously change, but the idea is to give you a realistic baseline before you book anything &mdash; especially when you're comparing different destinations.</p>

        <p style="margin:0 0 28px;"><a href="{safe_planner_url}" style="display:inline-block;background:#173b2d;color:#fffdf7;text-decoration:none;font-weight:700;padding:13px 20px;border-radius:10px;">Plan a trip</a></p>

        <p style="font-size:16px;line-height:1.65;margin:0 0 18px;">And this is still a very early version of LeavePrints.</p>
        <p style="font-size:16px;line-height:1.65;margin:0 0 18px;">I'm actively building it based on how people actually use it, so if there's something you expected it to do, something that confused you, or something you'd love me to add, just reply to this email.</p>
        <p style="font-size:16px;line-height:1.65;margin:0 0 24px;">I read all of them.</p>
        <p style="font-size:16px;line-height:1.55;margin:0;">Josh<br>LeavePrints</p>
      </div>
    </div>
  </body>
</html>
""",
        subtype="html",
    )

    _send_message(message)

def send_account_deleted_email(email, username=None):
    """Best-effort confirmation after a user permanently deletes their account."""

    mail_from = current_app.config.get("MAIL_FROM")
    if not current_app.config.get("SMTP_HOST") or not mail_from:
        raise RuntimeError("Account deletion email is not configured.")

    message = EmailMessage()
    message["Subject"] = "Your LeavePrints account was deleted"
    message["From"] = mail_from
    message["To"] = email

    greeting = f"Hey {username},\n\n" if username else ""
    message.set_content(
        greeting
        + "Your LeavePrints account has been permanently deleted.\n\n"
        + "Saved trips and public trip links tied to the account have been removed, "
        + "along with account-linked product analytics and data reports you submitted.\n\n"
        + "If you did not request this, contact hello@leaveprints.com."
    )

    _send_message(message)
