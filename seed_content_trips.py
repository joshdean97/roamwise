from core import create_app
from core.content_seed import seed_reviewed_collection

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        print("Reviewed private content collection:", seed_reviewed_collection())
