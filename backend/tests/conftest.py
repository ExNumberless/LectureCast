from collections import deque

import pytest
from django.core.files.storage import default_storage
from django.utils.functional import empty

from accounts.models import User
from courses.models import Course
from pipeline import tasks


@pytest.fixture(autouse=True)
def local_storage(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    }
    # default_storage is cached: reset it so the override takes effect.
    default_storage._wrapped = empty
    yield
    default_storage._wrapped = empty


@pytest.fixture
def queue(monkeypatch):
    """Capture Celery dispatches instead of sending them to a broker."""
    dispatched = deque()

    def apply_async(args, queue):
        dispatched.append((args[0], queue))

    monkeypatch.setattr(tasks.execute_stage_run, "apply_async", apply_async)
    return dispatched


@pytest.fixture
def user(db):
    return User.objects.create_user(email="owner@example.com")


@pytest.fixture
def course(user):
    return Course.objects.create(
        owner=user, title="Algorithms", provider=Course.Provider.WEBSITE, source_url="https://example.com/course"
    )


@pytest.fixture
def api(client, user):
    client.force_login(user)
    return client
