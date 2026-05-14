"""Integration tests for Flask HTTP routes."""

import json

from svs_to_ometiff_gui.serve import app


class DummyConversionService:
    """Minimal conversion service double for route-level job tests."""

    is_active = False

    def __init__(self):
        self.job = None

    def start_conversion(self, job):
        self.job = job
        return "single-request"

    def start_batch_conversion(self, inputs, output_dir, job_template):
        self.inputs = inputs
        self.output_dir = output_dir
        self.job = job_template
        return "batch-request"



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

    def test_convert_rejects_tile_size_not_divisible_by_16(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "tile_size": 513,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "divisible by 16" in data["error"]

    def test_convert_rejects_invalid_compression(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "compression": "jpeg2000",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "jpeg2000" in data["error"]

    def test_convert_defaults_match_gui_config(self, client, tmp_svs):
        service = DummyConversionService()
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = service
        try:
            resp = client.post(
                "/convert",
                data=json.dumps({"input_path": str(tmp_svs)}),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original

        assert resp.status_code == 200
        assert service.job.tile_size == 1024
        assert service.job.compression == "zlib"
        assert service.job.num_levels == 6
        assert service.job.downsample_factor == 2
        assert service.job.edge_mode == "crop"


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

    def test_batch_defaults_match_gui_config(self, client, tmp_svs):
        service = DummyConversionService()
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = service
        try:
            resp = client.post(
                "/convert/batch",
                data=json.dumps({"inputs": [str(tmp_svs)]}),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original

        assert resp.status_code == 200
        assert service.job.tile_size == 1024
        assert service.job.compression == "zlib"
        assert service.job.num_levels == 6
        assert service.job.downsample_factor == 2
        assert service.job.edge_mode == "crop"
