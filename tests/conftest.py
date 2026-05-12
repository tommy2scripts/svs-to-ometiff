"""Shared test fixtures for svs-to-ometiff GUI tests."""

import pytest

from svs_to_ometiff_gui.serve import app


@pytest.fixture()
def client():
    """Create a Flask test client for integration tests."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def tmp_svs(tmp_path):
    """Create a fake .svs file for path-resolution tests.

    This is NOT a valid SVS — it only tests path lookup logic,
    not actual image conversion.
    """
    fake = tmp_path / "test_slide.svs"
    fake.write_bytes(b"FAKE_SVS_HEADER")
    return fake
