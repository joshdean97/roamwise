from core.models.user import User


def test_legal_pages_are_public(client):
    privacy = client.get("/privacy")
    terms = client.get("/terms")

    assert privacy.status_code == 200
    assert b"Privacy Policy" in privacy.data
    assert b"hello@leaveprints.com" in privacy.data
    assert terms.status_code == 200
    assert b"Terms of Use" in terms.data
    assert b"2026-09-05" in terms.data


def test_registration_requires_terms(client, app):
    response = client.post(
        "/auth/register",
        data={
            "username": "no-terms",
            "email": "no-terms@example.com",
            "password": "test-password",
            "confirm_password": "test-password",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Please agree to the Terms of Use" in response.data

    with app.app_context():
        assert User.query.filter_by(email="no-terms@example.com").first() is None
