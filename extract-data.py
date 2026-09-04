import csv
from decimal import Decimal
from pathlib import Path

from app import create_app
from core.extensions import db
from core.models.country import Country
from core.models.city import City


CSV_FILE = Path(__file__).parent / "city-database.csv"


# ============================================================
# Currency codes
# ============================================================

CURRENCY_CODES = {
    "Albania": "ALL",
    "Armenia": "AMD",
    "Austria": "EUR",
    "Belgium": "EUR",
    "Bosnia & Herzegovina": "BAM",
    "Bulgaria": "EUR",
    "Croatia": "EUR",
    "Czechia": "CZK",
    "Denmark": "DKK",
    "Estonia": "EUR",
    "Finland": "EUR",
    "France": "EUR",
    "Georgia": "GEL",
    "Germany": "EUR",
    "Greece": "EUR",
    "Hungary": "HUF",
    "Iceland": "ISK",
    "Ireland": "EUR",
    "Italy": "EUR",
    "Kosovo": "EUR",
    "Latvia": "EUR",
    "Lithuania": "EUR",
    "Moldova": "MDL",
    "Montenegro": "EUR",
    "Morocco": "MAD",
    "Netherlands": "EUR",
    "North Macedonia": "MKD",
    "Norway": "NOK",
    "Poland": "PLN",
    "Portugal": "EUR",
    "Romania": "RON",
    "Serbia": "RSD",
    "Slovakia": "EUR",
    "Slovenia": "EUR",
    "Spain": "EUR",
    "Sweden": "SEK",
    "Switzerland": "CHF",
    "Turkey": "TRY",
    "Ukraine": "UAH",
    "United Kingdom": "GBP",
    "Uzbekistan": "UZS",
}

COUNTRY_CODES = {
    "Albania": "AL",
    "Armenia": "AM",
    "Austria": "AT",
    "Belgium": "BE",
    "Bosnia & Herzegovina": "BA",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Czechia": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Georgia": "GE",
    "Germany": "DE",
    "Greece": "GR",
    "Hungary": "HU",
    "Iceland": "IS",
    "Ireland": "IE",
    "Italy": "IT",
    "Kosovo": "XK",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Moldova": "MD",
    "Montenegro": "ME",
    "Morocco": "MA",
    "Netherlands": "NL",
    "North Macedonia": "MK",
    "Norway": "NO",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Serbia": "RS",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Turkey": "TR",
    "Ukraine": "UA",
    "United Kingdom": "GB",
    "Uzbekistan": "UZ",
}

# ============================================================
# Conversion helpers
# ============================================================

def yes_no(value):
    """
    Convert CSV Yes/No values to Python booleans.
    """

    value = value.strip().lower()

    if value == "yes":
        return True

    if value == "no":
        return False

    raise ValueError(
        f"Expected Yes or No but got: {value!r}"
    )


def money(value):
    """
    Convert values such as:

        £30
        £968
        £1,037

    into Decimal values suitable for db.Numeric.
    """

    value = (
        value.strip()
        .replace("£", "")
        .replace(",", "")
    )

    if not value:
        raise ValueError("Missing required monetary value")

    return Decimal(value)


# ============================================================
# Load CSV
# ============================================================

def load_rows():
    """
    Load city-database.csv.

    The CSV contains introductory rows before the actual
    column headers, so we locate the header row first.
    """

    with open(
        CSV_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        rows = list(csv.reader(file))

    header_index = None

    # --------------------------------------------------------
    # Find the real header row
    # --------------------------------------------------------

    for index, row in enumerate(rows):

        cleaned = [
            column.strip()
            for column in row
        ]

        if "City" in cleaned and "Country" in cleaned:
            header_index = index
            break

    if header_index is None:
        raise RuntimeError(
            "Could not find the City/Country header row"
        )

    header = rows[header_index]

    # The first column in the spreadsheet is blank.
    # Give any blank headers a harmless internal name.

    header = [
        column.strip()
        if column.strip()
        else f"_unused_{index}"

        for index, column in enumerate(header)
    ]

    data = []

    # --------------------------------------------------------
    # Convert rows into dictionaries
    # --------------------------------------------------------

    for row in rows[header_index + 1:]:

        # Make sure short rows still line up with the header
        row += [""] * (len(header) - len(row))

        record = dict(zip(header, row))

        city_name = record.get("City", "").strip()

        if not city_name:
            continue

        data.append(record)

    return data


# ============================================================
# Import
# ============================================================

def import_data():

    rows = load_rows()

    print()
    print("=" * 60)
    print(f"Found {len(rows)} cities in CSV")
    print("=" * 60)

    # Dictionary used to connect cities to their countries
    countries = {}

    # ========================================================
    # STEP 1 — COUNTRIES
    # ========================================================

    print()
    print("IMPORTING COUNTRIES")
    print("-" * 60)

    for row in rows:

        country_name = row["Country"].strip()

        if not country_name:
            raise ValueError(
                f"City {row['City']} has no country"
            )

        # We've already processed this country during this run
        if country_name in countries:
            continue

        currency_code = CURRENCY_CODES.get(country_name)
        country_code = COUNTRY_CODES.get(country_name)

        if currency_code is None:
            raise ValueError(
                f"No currency code configured for {country_name}"
            )

        if country_code is None:
            raise ValueError(
                f"No country code configured for {country_name}"
            )
        is_schengen = yes_no(
            row["Schengen Area?"]
        )

        visa_buffer = yes_no(
            row["Non-Schengen (visa buffer)?"]
        )

        region = row["Region"].strip() or None

        # ----------------------------------------------------
        # Check whether country already exists
        # ----------------------------------------------------

        country = Country.query.filter_by(
            name=country_name
        ).first()

        if country:
            country.code = country_code
            country.currency_code = currency_code
            country.region = region
            country.is_schengen = is_schengen
            country.visa_buffer = visa_buffer

            print(
                f"UPDATE COUNTRY: "
                f"{country_name} ({country_code}, {currency_code})"
            )
        else:
            country = Country(
                name=country_name,
                code=country_code,
                currency_code=currency_code,
                region=region,
                is_schengen=is_schengen,
                visa_buffer=visa_buffer,
            )

            db.session.add(country)

            print(
                f"ADD COUNTRY: "
                f"{country_name} ({country_code}, {currency_code})"
            )
        countries[country_name] = country

    # --------------------------------------------------------
    # Flush countries first
    #
    # This assigns IDs to newly-created countries without
    # committing the transaction yet.
    # --------------------------------------------------------

    db.session.flush()

    print()
    print(
        f"{len(countries)} countries processed."
    )

    # ========================================================
    # STEP 2 — CITIES
    # ========================================================

    print()
    print("IMPORTING CITIES")
    print("-" * 60)

    cities_added = 0
    cities_updated = 0

    for row in rows:

        city_name = row["City"].strip()
        country_name = row["Country"].strip()
        region = row["Region"].strip() or None

        country = countries.get(country_name)

        if country is None:
            raise RuntimeError(
                f"Country not loaded for city "
                f"{city_name}: {country_name}"
            )

        hostel_per_night = money(
            row["Hostel dorm £/night"]
        )

        monthly_living_cost = money(
            row["Living cost £/mo (excl. accom.)"]
        )

        # ----------------------------------------------------
        # Check existing city
        # ----------------------------------------------------

        city = City.query.filter_by(
            name=city_name,
            country_id=country.id,
        ).first()

        if city:

            # Update values from latest CSV

            city.region = region
            city.hostel_per_night = hostel_per_night
            city.monthly_living_cost = (
                monthly_living_cost
            )

            cities_updated += 1

            print(
                f"UPDATE CITY: "
                f"{city_name}, {country_name}"
            )

        else:

            city = City(
                name=city_name,
                region=region,
                country_id=country.id,
                hostel_per_night=hostel_per_night,
                monthly_living_cost=monthly_living_cost,
            )

            db.session.add(city)

            cities_added += 1

            print(
                f"ADD CITY: "
                f"{city_name}, {country_name}"
            )

    # ========================================================
    # COMMIT
    # ========================================================

    db.session.commit()

    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)

    print(
        f"Countries processed: {len(countries)}"
    )

    print(
        f"Cities added:       {cities_added}"
    )

    print(
        f"Cities updated:     {cities_updated}"
    )

    print(
        f"Total cities:       {len(rows)}"
    )

    print("=" * 60)
    print()


# ============================================================
# Run script
# ============================================================

if __name__ == "__main__":

    app = create_app()

    with app.app_context():

        try:

            import_data()

        except Exception as error:

            db.session.rollback()

            print()
            print("=" * 60)
            print("IMPORT FAILED")
            print("=" * 60)
            print(error)
            print("=" * 60)
            print()

            raise