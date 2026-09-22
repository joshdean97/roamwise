from datetime import datetime
from decimal import Decimal

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from core.extensions import db
from core.models.city import City
from core.models.city_price_snapshot import CityPriceSnapshot
from core.models.country import Country
from ..decorators import admin_required

city_bp = Blueprint(
    "city",
    __name__,
    url_prefix="/city"
)

PRICE_CONFIDENCE_LEVELS = {"unverified", "low", "medium", "high"}


def apply_price_metadata(city):
    checked_value = (request.form.get("price_checked_at") or "").strip()
    city.price_checked_at = (
        datetime.strptime(checked_value, "%Y-%m-%d")
        if checked_value else None
    )
    city.price_source = (request.form.get("price_source") or "").strip()[:255] or None
    confidence = (request.form.get("price_confidence") or "unverified").strip().lower()
    city.price_confidence = (
        confidence if confidence in PRICE_CONFIDENCE_LEVELS else "unverified"
    )


@city_bp.route("/all")
@login_required
@admin_required
def get_all_cities():
    cities = City.query.order_by(City.name).all()

    return render_template(
        "city/all.html",
        cities=cities,
        title="All Cities"
    )


@city_bp.route("/<int:city_id>")
@login_required
@admin_required
def get_city(city_id):
    city = City.query.get_or_404(city_id)

    return render_template(
        "city/detail.html",
        city=city,
        title=f"City: {city.name}"
    )


@city_bp.route("/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_city():
    countries = Country.query.order_by(
        Country.name
    ).all()

    if request.method == "POST":

        city = City(
            name=request.form["name"],
            region=request.form.get("region"),
            country_id=request.form["country_id"],
            hostel_per_night=Decimal(request.form["hostel_per_night"]),
            monthly_living_cost=Decimal(request.form["monthly_living_cost"]),
        )
        apply_price_metadata(city)

        db.session.add(city)
        db.session.flush()
        CityPriceSnapshot.record(city, source="admin_create")
        db.session.commit()

        flash("City added.", "success")

        return redirect(
            url_for("city.get_all_cities")
        )

    return render_template(
        "city/add.html",
        countries=countries,
        title="Add City"
    )


@city_bp.route(
    "/<int:city_id>/update",
    methods=["GET", "POST"]
)
@login_required
@admin_required
def update_city(city_id):
    city = City.query.get_or_404(city_id)

    countries = Country.query.order_by(
        Country.name
    ).all()

    if request.method == "POST":

        old_prices = (
            float(city.hostel_per_night),
            float(city.monthly_living_cost),
        )

        city.name = request.form["name"]
        city.region = request.form.get("region")
        city.country_id = request.form["country_id"]

        city.hostel_per_night = Decimal(request.form["hostel_per_night"])

        city.monthly_living_cost = Decimal(request.form["monthly_living_cost"])
        apply_price_metadata(city)

        new_prices = (
            float(city.hostel_per_night),
            float(city.monthly_living_cost),
        )
        if new_prices != old_prices:
            CityPriceSnapshot.record(city)

        db.session.commit()

        flash("City updated.", "success")

        return redirect(
            url_for(
                "city.get_city",
                city_id=city.id
            )
        )

    return render_template(
        "city/edit.html",
        city=city,
        countries=countries,
        title=f"Edit City: {city.name}"
    )


@city_bp.route(
    "/<int:city_id>/delete",
    methods=["POST"]
)
@login_required
@admin_required
def delete_city(city_id):
    city = City.query.get_or_404(city_id)

    db.session.delete(city)
    db.session.commit()

    flash("City deleted.", "success")

    return redirect(
        url_for("city.get_all_cities")
    )
