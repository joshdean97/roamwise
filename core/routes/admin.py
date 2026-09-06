from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.orm import joinedload

from core.decorators import admin_required
from core.extensions import db
from core.models.user import User
from core.models.city import City
from core.models.country import Country
from core.models.analytics_event import AnalyticsEvent
from core.models.city_data_report import CityDataReport, REPORT_STATUSES


admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin"
)


# ============================================================
# Admin dashboard
# ============================================================

@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():

    now = datetime.utcnow()

    # --------------------------------------------------------
    # Freshness
    # --------------------------------------------------------

    # "Fresh this month" means updated since the first day
    # of the current calendar month.
    start_of_month = datetime(
        year=now.year,
        month=now.month,
        day=1,
    )

    # A city is considered stale after 30 days without
    # an update.
    stale_cutoff = now - timedelta(days=30)

    # --------------------------------------------------------
    # Main stats
    # --------------------------------------------------------

    city_count = City.query.count()

    country_count = Country.query.count()

    user_count = User.query.count()

    open_data_report_count = (
        CityDataReport.query
        .filter(CityDataReport.status == "open")
        .count()
    )

    # --------------------------------------------------------
    # Stale cities
    # --------------------------------------------------------

    stale_city_count = (
        City.query
        .filter(
            City.last_updated < stale_cutoff
        )
        .count()
    )

    # --------------------------------------------------------
    # Schengen coverage
    # --------------------------------------------------------

    schengen_country_count = (
        Country.query
        .filter(
            Country.is_schengen.is_(True)
        )
        .count()
    )

    # --------------------------------------------------------
    # Number of different currencies
    # --------------------------------------------------------

    currency_count = (
        db.session
        .query(Country.currency_code)
        .filter(
            Country.currency_code.isnot(None)
        )
        .distinct()
        .count()
    )

    # --------------------------------------------------------
    # Cities updated during current month
    # --------------------------------------------------------

    fresh_city_count = (
        City.query
        .filter(
            City.last_updated >= start_of_month
        )
        .count()
    )

    # --------------------------------------------------------
    # Build stats dictionary expected by dashboard.html
    # --------------------------------------------------------

    stats = {
        "city_count": city_count,
        "country_count": country_count,
        "user_count": user_count,
        "open_data_report_count": open_data_report_count,
        "stale_city_count": stale_city_count,
        "schengen_country_count": schengen_country_count,
        "currency_count": currency_count,
        "fresh_city_count": fresh_city_count,
    }

    # --------------------------------------------------------
    # Most recently updated cities
    # --------------------------------------------------------

    recent_cities = (
        City.query
        .order_by(
            City.last_updated.desc()
        )
        .limit(5)
        .all()
    )

    # --------------------------------------------------------
    # Render dashboard
    # --------------------------------------------------------

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_cities=recent_cities,
        title="Admin Dashboard"
    )


# ============================================================
# Product analytics
# ============================================================

@admin_bp.route("/analytics")
@login_required
@admin_required
def analytics_dashboard():
    cutoff = datetime.utcnow() - timedelta(days=30)

    def counts_since(since=None):
        query = db.session.query(
            AnalyticsEvent.name,
            db.func.count(AnalyticsEvent.id),
        )
        if since is not None:
            query = query.filter(AnalyticsEvent.created_at >= since)
        return dict(query.group_by(AnalyticsEvent.name).all())

    event_counts_all = counts_since()
    event_counts_30 = counts_since(cutoff)

    metric_labels = [
        ("landing_viewed", "Landing views"),
        ("account_created", "Signups"),
        ("planner_opened", "Planner opens"),
        ("trip_saved", "Trips saved"),
        ("share_page_viewed", "Share pages"),
        ("public_share_enabled", "Public shares"),
        ("public_trip_viewed", "Public Print views"),
        ("account_deleted", "Account deletions"),
        ("shared_route_loaded", "Routes reused"),
        ("data_report_submitted", "Bad-data reports"),
    ]

    metric_cards = [
        {
            "name": name,
            "label": label,
            "last_30": event_counts_30.get(name, 0),
            "all_time": event_counts_all.get(name, 0),
        }
        for name, label in metric_labels
    ]

    signup_users = {
        row[0]
        for row in db.session.query(AnalyticsEvent.user_id)
        .filter(
            AnalyticsEvent.name == "account_created",
            AnalyticsEvent.user_id.isnot(None),
        )
        .distinct()
        .all()
    }
    saved_users_raw = {
        row[0]
        for row in db.session.query(AnalyticsEvent.user_id)
        .filter(
            AnalyticsEvent.name == "trip_saved",
            AnalyticsEvent.user_id.isnot(None),
        )
        .distinct()
        .all()
    }
    shared_users_raw = {
        row[0]
        for row in db.session.query(AnalyticsEvent.user_id)
        .filter(
            AnalyticsEvent.name == "public_share_enabled",
            AnalyticsEvent.user_id.isnot(None),
        )
        .distinct()
        .all()
    }

    saved_users = signup_users & saved_users_raw
    shared_users = saved_users & shared_users_raw

    funnel = {
        "signup_users": len(signup_users),
        "saved_users": len(saved_users),
        "shared_users": len(shared_users),
        "signup_to_saved": (
            len(saved_users) / len(signup_users) * 100
            if signup_users
            else 0
        ),
        "saved_to_shared": (
            len(shared_users) / len(saved_users) * 100
            if saved_users
            else 0
        ),
    }

    first_city = event_counts_all.get("first_city_added", 0)
    second_city = event_counts_all.get("second_city_added", 0)
    planner_activation = {
        "first_city": first_city,
        "second_city": second_city,
        "first_to_second": (second_city / first_city * 100 if first_city else 0),
    }

    recent_events = (
        AnalyticsEvent.query
        .order_by(AnalyticsEvent.created_at.desc(), AnalyticsEvent.id.desc())
        .limit(50)
        .all()
    )

    return render_template(
        "admin/analytics.html",
        metric_cards=metric_cards,
        event_counts_all=event_counts_all,
        event_counts_30=event_counts_30,
        funnel=funnel,
        planner_activation=planner_activation,
        recent_events=recent_events,
        title="Product Analytics | LeavePrints",
    )


# ============================================================
# Traveller data reports
# ============================================================

@admin_bp.route("/data-reports")
@login_required
@admin_required
def data_reports():
    active_status = (request.args.get("status") or "open").strip().lower()

    if active_status not in REPORT_STATUSES | {"all"}:
        active_status = "open"

    query = (
        CityDataReport.query
        .options(
            joinedload(CityDataReport.city),
            joinedload(CityDataReport.reporter),
        )
        .order_by(CityDataReport.created_at.desc(), CityDataReport.id.desc())
    )

    if active_status != "all":
        query = query.filter(CityDataReport.status == active_status)

    reports = query.limit(250).all()

    status_counts = dict(
        db.session.query(
            CityDataReport.status,
            db.func.count(CityDataReport.id),
        )
        .group_by(CityDataReport.status)
        .all()
    )

    counts = {
        "open": status_counts.get("open", 0),
        "resolved": status_counts.get("resolved", 0),
        "dismissed": status_counts.get("dismissed", 0),
        "all": sum(status_counts.values()),
    }

    return render_template(
        "admin/data_reports.html",
        reports=reports,
        counts=counts,
        active_status=active_status,
        title="Data Reports | LeavePrints",
    )


@admin_bp.post("/data-reports/<int:report_id>/status")
@login_required
@admin_required
def update_data_report_status(report_id):
    report = CityDataReport.query.get_or_404(report_id)
    status = (request.form.get("status") or "").strip().lower()
    note = (request.form.get("resolution_note") or "").strip()
    return_status = (request.form.get("return_status") or "open").strip().lower()

    if status not in REPORT_STATUSES:
        flash("Invalid report status.", "error")
        return redirect(url_for("admin.data_reports", status=return_status))

    if len(note) > 500:
        flash("Internal notes must be 500 characters or fewer.", "error")
        return redirect(url_for("admin.data_reports", status=return_status))

    report.status = status
    report.resolution_note = note or None
    report.resolved_at = datetime.utcnow() if status in {"resolved", "dismissed"} else None
    db.session.commit()

    flash(
        "Report reopened." if status == "open" else f"Report marked {status}.",
        "success",
    )

    if return_status not in REPORT_STATUSES | {"all"}:
        return_status = "open"

    return redirect(url_for("admin.data_reports", status=return_status))


# ============================================================
# Users
# ============================================================

@admin_bp.route("/users/all")
@login_required
@admin_required
def get_all_users():

    users = (
        User.query
        .order_by(User.username)
        .all()
    )

    return render_template(
        "admin/users/all.html",
        users=users,
        title="All Users"
    )