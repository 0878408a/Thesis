"""Shared pytest fixtures for Manufacturer Client Flask Server tests."""
import sys
from pathlib import Path

import pytest

# 把 thesis/manufacturer_client 加入 sys.path，確保能 import service / manufacturer_client
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


@pytest.fixture
def client():
    """Flask test client for service.app."""
    import service

    service.app.config["TESTING"] = True
    with service.app.test_client() as c:
        yield c


class FakeUpstreamResponse:
    """Fake requests.Response: 只含 status_code / json() / text。"""

    def __init__(self, status_code: int = 200, json_data=None, text: str = "", raise_json_value_error: bool = False):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._raise_json_value_error = raise_json_value_error

    def json(self):
        if self._raise_json_value_error:
            raise ValueError("No JSON object could be decoded")
        return self._json_data

    @property
    def ok(self):
        return 200 <= self.status_code < 300


@pytest.fixture
def make_upstream_response():
    return FakeUpstreamResponse
