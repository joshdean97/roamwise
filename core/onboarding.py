import time
from datetime import datetime, timedelta, timezone

import click
from flask import current_app
from sqlalchemy import or_, update

from core.extensions import db
from core.mail import send_onboarding_email
from core.models.user import User


CLAIM_TIMEOUT = timedelta(minutes=30)


def _planner_url():
    origin = (current_app.config.get("PUBLIC_APP_URL") or "").rstrip("/")
    if not origin:
        origin = "http://localhost:5000"
    return f"{origin}/plan-trip"


def send_due_onboarding_emails(now=None, limit=100):
    """Send due onboarding emails, safely claiming each user before SMTP."""

    now = now or datetime.now(timezone.utc)
    due_before = now - timedelta(
        hours=current_app.config["ONBOARDING_EMAIL_DELAY_HOURS"]
    )
    stale_before = now - CLAIM_TIMEOUT

    candidate_ids = db.session.scalars(
        db.select(User.id)
        .where(
            User.is_admin.is_(False),
            User.email_confirmed_at.is_not(None),
            User.created_at <= due_before,
            User.onboarding_email_sent_at.is_(None),
            or_(
                User.onboarding_email_claimed_at.is_(None),
                User.onboarding_email_claimed_at < stale_before,
            ),
        )
        .order_by(User.created_at.asc(), User.id.asc())
        .limit(limit)
    ).all()

    sent = 0
    failed = 0

    for user_id in candidate_ids:
        claim = db.session.execute(
            update(User)
            .where(
                User.id == user_id,
                User.is_admin.is_(False),
                User.email_confirmed_at.is_not(None),
                User.created_at <= due_before,
                User.onboarding_email_sent_at.is_(None),
                or_(
                    User.onboarding_email_claimed_at.is_(None),
                    User.onboarding_email_claimed_at < stale_before,
                ),
            )
            .values(onboarding_email_claimed_at=now)
        )
        db.session.commit()

        if claim.rowcount != 1:
            continue

        user = db.session.get(User, user_id)
        if user is None:
            continue

        try:
            send_onboarding_email(user, _planner_url())
        except Exception:
            failed += 1
            current_app.logger.exception(
                "Could not send onboarding email for user id %s",
                user_id,
            )
            user.onboarding_email_claimed_at = None
            db.session.commit()
            continue

        user.onboarding_email_sent_at = now
        user.onboarding_email_claimed_at = None
        db.session.commit()
        sent += 1

    return {"candidates": len(candidate_ids), "sent": sent, "failed": failed}


def register_onboarding_commands(app):
    @app.cli.command("send-onboarding-emails")
    def send_onboarding_emails_command():
        """Send every onboarding email currently due, then exit."""

        if not current_app.config["ONBOARDING_EMAILS_ENABLED"]:
            click.echo("Onboarding emails are disabled.")
            return

        result = send_due_onboarding_emails()
        click.echo(
            "Onboarding email pass complete: "
            f"{result['sent']} sent, {result['failed']} failed."
        )

    @app.cli.command("onboarding-email-worker")
    @click.option("--once", is_flag=True, help="Run one pass and exit.")
    def onboarding_email_worker_command(once):
        """Continuously send onboarding emails as they become due."""

        if not current_app.config["ONBOARDING_EMAILS_ENABLED"]:
            click.echo("Onboarding emails are disabled.")
            return

        interval = current_app.config["ONBOARDING_EMAIL_INTERVAL_SECONDS"]
        click.echo(f"Onboarding email worker running every {interval} seconds.")

        while True:
            try:
                result = send_due_onboarding_emails()
                if result["candidates"]:
                    current_app.logger.info(
                        "Onboarding email pass: %s sent, %s failed",
                        result["sent"],
                        result["failed"],
                    )
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Onboarding email pass failed")

            if once:
                return
            time.sleep(interval)
