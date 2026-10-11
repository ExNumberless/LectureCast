import re

import pytest
from django.core import mail
from django.test import override_settings

from accounts.models import User


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_user_can_sign_in_with_an_email_code(client):
    user = User.objects.create_user(email="reader@example.com")
    assert not user.has_usable_password()

    response = client.post(
        "/api/auth/browser/v1/auth/code/request",
        {"email": user.email},
        content_type="application/json",
    )
    assert response.status_code == 401
    assert len(mail.outbox) == 1

    code = re.search(r"[BCDFGHJKLMNPQRSTVWXZ]+(?:-[BCDFGHJKLMNPQRSTVWXZ]+)+", mail.outbox[0].body)
    assert code
    response = client.post(
        "/api/auth/browser/v1/auth/code/confirm",
        {"code": code.group()},
        content_type="application/json",
    )
    assert response.status_code == 200

    response = client.get("/api/auth/browser/v1/auth/session")
    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == user.email


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_signup_creates_an_email_only_account(client):
    response = client.post(
        "/api/auth/browser/v1/auth/signup",
        {"email": "new-reader@example.com"},
        content_type="application/json",
    )
    assert response.status_code == 200
    user = User.objects.get(email="new-reader@example.com")
    assert not user.has_usable_password()
