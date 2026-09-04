import pytest

from core import _normalise_database_url, create_app


def test_postgres_provider_url_uses_psycopg3():
    assert _normalise_database_url(
        "postgresql://user:pass@example/db"
    ) == "postgresql+psycopg://user:pass@example/db"

    assert _normalise_database_url(
        "postgres://user:pass@example/db"
    ) == "postgresql+psycopg://user:pass@example/db"


def test_sqlite_url_is_left_alone():
    assert _normalise_database_url("sqlite:///site.db") == "sqlite:///site.db"
