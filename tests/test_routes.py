"""Integration tests for Flask HTTP routes."""

import json

import pytest


class TestIndexRoute:
    """GET / should serve the HTML template."""

    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"svs-to-ometiff" in resp.data


class TestInspectRoute:
    """GET /inspect validates the path parameter."""

    def test_inspect_missing_path_returns_400(self, client):
        resp = client.get("/inspect")
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data

    def test_inspect_empty_path_returns_400(self, client):
        resp = client.get("/inspect?path=")
        assert resp.status_code == 400

    def test_inspect_nonexistent_file_returns_404(self, client):
        resp = client.get("/inspect?path=/nonexistent/slide.svs")
        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert "not found" in data["error"].lower()


class TestConvertRoute:
    """POST /convert validates input before launching conversion."""

    def test_convert_missing_body_returns_400(self, client):
        resp = client.post(
            "/convert",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "input_path" in data["error"].lower() or "required" in data["error"].lower()

    def test_convert_nonexistent_file_returns_400(self, client):
        resp = client.post(
            "/convert",
            data=json.dumps({"input_path": "/fake/path/slide.svs"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "not found" in data["error"].lower()

    def test_convert_non_svs_extension_returns_400(self, client, tmp_svs):
        # Rename the tmp_svs to .tiff
        non_svs = tmp_svs.parent / "slide.tiff"
        tmp_svs.rename(non_svs)
        resp = client.post(
            "/convert",
            data=json.dumps({"input_path": str(non_svs)}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "svs" in data["error"].lower()

    def test_convert_invalid_tile_size_returns_400(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "tile_size": "abc",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]


class TestBatchConvertRoute:
    """POST /convert/batch validates inputs list."""

    def test_batch_empty_inputs_returns_400(self, client):
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": []}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_batch_missing_inputs_returns_400(self, client):
        resp = client.post(
            "/convert/batch",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_batch_nonexistent_file_returns_400(self, client):
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": ["/fake/slide1.svs"]}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_batch_non_svs_file_returns_400(self, client, tmp_svs):
        non_svs = tmp_svs.parent / "slide.tiff"
        tmp_svs.rename(non_svs)
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(non_svs)]}),
            content_type="application/json",
        )
        assert resp.status_code == 400
