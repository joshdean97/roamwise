from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort
)
from flask_login import login_required, current_user

from core.extensions import db
from core.models.country import Country
from ..decorators import admin_required


country_bp = Blueprint(
    "country",
    __name__,
    url_prefix="/country"
)



@country_bp.route("/all")
@login_required
@admin_required
def get_all_countries():
    countries = Country.query.order_by(
        Country.name
    ).all()

    return render_template(
        "country/all.html",
        countries=countries,
        title="All Countries"
    )


@country_bp.route("/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_country():
    if request.method == "POST":

        country = Country(
            name=request.form["name"].strip(),
            code=request.form["code"].strip().upper(),
            currency_code=request.form[
                "currency_code"
            ].strip().upper(),
            is_schengen=(
                request.form.get("is_schengen")
                == "on"
            )
        )

        db.session.add(country)
        db.session.commit()

        flash(
            f"{country.name} added.",
            "success"
        )

        return redirect(
            url_for(
                "country.get_all_countries"
            )
        )

    return render_template(
        "country/add.html",
        title="Add Country"
    )


@country_bp.route(
    "/<int:country_id>/edit",
    methods=["GET", "POST"]
)
@login_required
@admin_required
def edit_country(country_id):
    country = Country.query.get_or_404(
        country_id
    )

    if request.method == "POST":

        country.name = (
            request.form["name"].strip()
        )

        country.code = (
            request.form["code"]
            .strip()
            .upper()
        )

        country.currency_code = (
            request.form["currency_code"]
            .strip()
            .upper()
        )

        country.is_schengen = (
            request.form.get("is_schengen")
            == "on"
        )

        db.session.commit()

        flash(
            f"{country.name} updated.",
            "success"
        )

        return redirect(
            url_for(
                "country.get_all_countries"
            )
        )

    return render_template(
        "country/edit.html",
        country=country,
        title=f"Edit Country: {country.name}"
    )


@country_bp.route(
    "/<int:country_id>/delete",
    methods=["POST"]
)
@login_required
@admin_required
def delete_country(country_id):
    country = Country.query.get_or_404(
        country_id
    )

    if country.cities:
        flash(
            (
                f"Can't delete {country.name} "
                "because it still has cities."
            ),
            "error"
        )

        return redirect(
            url_for(
                "country.get_all_countries"
            )
        )

    db.session.delete(country)
    db.session.commit()

    flash(
        f"{country.name} deleted.",
        "success"
    )

    return redirect(
        url_for(
            "country.get_all_countries"
        )
    )