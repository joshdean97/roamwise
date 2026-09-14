from collections import Counter, defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.orm import joinedload, selectinload

from core.decorators import admin_required
from core.extensions import db
from core.models.user import User
from core.models.city import City
from core.models.country import Country
from core.models.analytics_event import AnalyticsEvent
from core.models.city_data_report import CityDataReport, REPORT_STATUSES
from core.models.city_price_snapshot import CityPriceSnapshot
from core.models.trip import Trip, TripStop


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
    now = datetime.utcnow()
    cutoff = now - timedelta(days=30)
    previous_cutoff = now - timedelta(days=60)

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
        ("explore_viewed", "Explore views"),
        ("explore_trip_opened", "Explore Print opens"),
        ("trip_bookmarked", "Print saves"),
        ("shared_route_saved", "Actual route uses"),
        ("account_created", "Signups"),
        ("planner_opened", "Planner opens"),
        ("trip_saved", "Trips saved"),
        ("share_page_viewed", "Share pages"),
        ("public_share_enabled", "Public shares"),
        ("public_trip_viewed", "Public Print views"),
        ("shared_route_loaded", "Routes reused"),
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
        "signup_to_saved": len(saved_users) / len(signup_users) * 100 if signup_users else 0,
        "saved_to_shared": len(shared_users) / len(saved_users) * 100 if saved_users else 0,
    }

    first_city = event_counts_all.get("first_city_added", 0)
    second_city = event_counts_all.get("second_city_added", 0)
    planner_activation = {
        "first_city": first_city,
        "second_city": second_city,
        "first_to_second": second_city / first_city * 100 if first_city else 0,
    }

    trips = (
        Trip.query
        .options(
            selectinload(Trip.stops)
            .selectinload(TripStop.city)
            .selectinload(City.country),
            selectinload(Trip.legs),
        )
        .order_by(Trip.created_at.desc())
        .all()
    )

    destination_stats = defaultdict(lambda: {
        "trips": 0,
        "nights": 0,
        "daily_cost_total": 0.0,
        "daily_cost_rows": 0,
        "last_30": 0,
        "previous_30": 0,
    })
    route_counts = Counter()
    style_counts = Counter()
    currency_counts = Counter()
    trips_by_user = Counter()
    completed_trips = []

    for trip in trips:
        ordered_stops = sorted(trip.stops, key=lambda stop: stop.position)
        trips_by_user[trip.user_id] += 1
        style_counts[trip.travel_style] += 1
        currency_counts[trip.display_currency] += 1

        route = " → ".join(stop.city.name for stop in ordered_stops)
        if route:
            route_counts[route] += 1

        seen_city_ids = set()
        for stop in ordered_stops:
            city_key = (stop.city.id, stop.city.name, stop.city.country.name)
            stats = destination_stats[city_key]
            stats["nights"] += stop.nights
            stats["daily_cost_total"] += float(stop.daily_cost_gbp)
            stats["daily_cost_rows"] += 1
            if stop.city_id not in seen_city_ids:
                stats["trips"] += 1
                seen_city_ids.add(stop.city_id)
                if trip.created_at and trip.created_at >= cutoff:
                    stats["last_30"] += 1
                elif trip.created_at and trip.created_at >= previous_cutoff:
                    stats["previous_30"] += 1

        if trip.total_nights:
            completed_trips.append({
                "name": trip.name,
                "route": route,
                "nights": trip.total_nights,
                "total_cost": trip.total_cost_gbp,
                "daily_cost": trip.total_cost_gbp / trip.total_nights,
            })

    destinations = []
    for (city_id, name, country), values in destination_stats.items():
        previous = values["previous_30"]
        current = values["last_30"]
        change = current - previous
        trend_percent = (change / previous * 100) if previous else (100 if current else 0)
        destinations.append({
            "city_id": city_id,
            "name": name,
            "country": country,
            **values,
            "average_daily_cost": (
                values["daily_cost_total"] / values["daily_cost_rows"]
                if values["daily_cost_rows"] else 0
            ),
            "change": change,
            "trend_percent": trend_percent,
        })

    popular_destinations = sorted(
        destinations,
        key=lambda row: (row["trips"], row["nights"]),
        reverse=True,
    )[:10]
    trending_destinations = sorted(
        [row for row in destinations if row["last_30"]],
        key=lambda row: (row["change"], row["last_30"], row["trips"]),
        reverse=True,
    )[:10]
    popular_routes = [
        {"route": route, "trips": count}
        for route, count in route_counts.most_common(10)
    ]
    cheapest_trips = sorted(
        completed_trips,
        key=lambda row: row["daily_cost"],
    )[:10]

    total_nights = sum(trip.total_nights for trip in trips)
    total_cost = sum(trip.total_cost_gbp for trip in trips)
    returning_users = sum(1 for count in trips_by_user.values() if count > 1)
    product_summary = {
        "trips": len(trips),
        "travellers_with_trips": len(trips_by_user),
        "returning_users": returning_users,
        "returning_rate": (
            returning_users / len(trips_by_user) * 100 if trips_by_user else 0
        ),
        "average_nights": total_nights / len(trips) if trips else 0,
        "average_total_cost": total_cost / len(trips) if trips else 0,
        "average_daily_cost": total_cost / total_nights if total_nights else 0,
    }

    price_snapshots = (
        CityPriceSnapshot.query
        .options(joinedload(CityPriceSnapshot.city).joinedload(City.country))
        .order_by(
            CityPriceSnapshot.recorded_at.desc(),
            CityPriceSnapshot.id.desc(),
        )
        .limit(100)
        .all()
    )
    snapshot_groups = defaultdict(list)
    for snapshot in reversed(price_snapshots):
        snapshot_groups[snapshot.city_id].append(snapshot)

    price_movements = []
    for history in snapshot_groups.values():
        if len(history) < 2:
            continue
        oldest, newest = history[0], history[-1]
        old_cost = float(oldest.balanced_daily_cost)
        new_cost = float(newest.balanced_daily_cost)
        change_percent = ((new_cost - old_cost) / old_cost * 100) if old_cost else 0
        price_movements.append({
            "city": newest.city.name,
            "country": newest.city.country.name,
            "old_cost": old_cost,
            "new_cost": new_cost,
            "change_percent": change_percent,
            "from_date": oldest.recorded_at,
            "to_date": newest.recorded_at,
        })
    price_movements.sort(key=lambda row: abs(row["change_percent"]), reverse=True)

    top_destination = popular_destinations[0] if popular_destinations else None
    top_trending = trending_destinations[0] if trending_destinations else None
    top_route = popular_routes[0] if popular_routes else None
    cheapest_trip = cheapest_trips[0] if cheapest_trips else None

    content_signals = [
        {
            "label": "Most planned destination",
            "headline": top_destination["name"] if top_destination else "Waiting for trip data",
            "detail": (
                f'{top_destination["trips"]} saved trips · {top_destination["nights"]} nights'
                if top_destination else "This will appear as travellers save trips."
            ),
        },
        {
            "label": "Trending now",
            "headline": top_trending["name"] if top_trending else "No 30-day trend yet",
            "detail": (
                f'{top_trending["last_30"]} trips in the last 30 days '
                f'({top_trending["change"]:+d} vs previous 30)'
                if top_trending else "Needs recent and previous trip activity."
            ),
        },
        {
            "label": "Most repeated route",
            "headline": top_route["route"] if top_route else "Waiting for route data",
            "detail": (
                f'{top_route["trips"]} saved trip{"s" if top_route["trips"] != 1 else ""}'
                if top_route else "Multi-city routes will rank here."
            ),
        },
        {
            "label": "Cheapest saved trip",
            "headline": cheapest_trip["name"] if cheapest_trip else "Waiting for cost data",
            "detail": (
                f'£{cheapest_trip["daily_cost"]:.2f}/day · {cheapest_trip["nights"]} nights'
                if cheapest_trip else "Calculated from saved LeavePrints estimates."
            ),
        },
    ]

    recent_events = (
        AnalyticsEvent.query
        .order_by(AnalyticsEvent.created_at.desc(), AnalyticsEvent.id.desc())
        .limit(50)
        .all()
    )

    return render_template(
        "admin/analytics.html",
        content_signals=content_signals,
        product_summary=product_summary,
        popular_destinations=popular_destinations,
        trending_destinations=trending_destinations,
        popular_routes=popular_routes,
        cheapest_trips=cheapest_trips,
        style_counts=style_counts.most_common(),
        currency_counts=currency_counts.most_common(),
        price_snapshots=price_snapshots,
        price_movements=price_movements[:10],
        metric_cards=metric_cards,
        event_counts_all=event_counts_all,
        event_counts_30=event_counts_30,
        funnel=funnel,
        planner_activation=planner_activation,
        recent_events=recent_events,
        title="Content & Product Analytics | LeavePrints",
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