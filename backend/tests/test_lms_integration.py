"""The LMS risk-summary endpoint is server-to-server only: it needs the shared key and is off without it."""
import pytest
from fastapi import HTTPException

from config import settings
from routers import lms_integration


def test_disabled_when_no_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "LMS_INTEGRATION_KEY", "")
    with pytest.raises(HTTPException) as exc:
        lms_integration.require_integration_key("anything")
    assert exc.value.status_code == 503


@pytest.mark.parametrize("sent", [None, "", "wrong-key"])
def test_rejects_missing_or_wrong_key(monkeypatch, sent):
    monkeypatch.setattr(settings, "LMS_INTEGRATION_KEY", "the-shared-key")
    with pytest.raises(HTTPException) as exc:
        lms_integration.require_integration_key(sent)
    assert exc.value.status_code == 401


def test_accepts_the_shared_key(monkeypatch):
    monkeypatch.setattr(settings, "LMS_INTEGRATION_KEY", "the-shared-key")
    assert lms_integration.require_integration_key("the-shared-key") is None
