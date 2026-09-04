from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from core.extensions import db
from core.models.city import City
from core.models.country import Country
from ..decorators import admin_required

city_bp = Blueprint(
    "city",
    __name__,
    url_prefix="/city"
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
            hostel_per_night=request.form["hostel_per_night"],
            monthly_living_cost=request.form["monthly_living_cost"]
        )

        db.session.add(city)
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

        city.name = request.form["name"]
        city.region = request.form.get("region")
        city.country_id = request.form["country_id"]

        city.hostel_per_night = (
            request.form["hostel_per_night"]
        )

        city.monthly_living_cost = (
            request.form["monthly_living_cost"]
        )

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