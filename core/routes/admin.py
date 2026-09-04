from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import login_required

from core.decorators import admin_required
from core.extensions import db
from core.models.user import User
from core.models.city import City
from core.models.country import Country


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