import importlib.util
from pathlib import Path

from core import create_app
from core.extensions import db
from core.models.city import City


def _load_importer():
    path = Path(__file__).with_name("extract-data.py")
    spec = importlib.util.spec_from_file_location("roamwise_city_importer", path)

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load city importer from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.import_data


app = create_app()

with app.app_context():
    try:
        existing_city = db.session.query(City.id).limit(1).scalar()

        if existing_city is not None:
            print("City data already present; seed skipped.")
        else:
            print("No city data found; importing city-database.csv...")
            _load_importer()()
    except Exception:
        db.session.rollback()
        raise
