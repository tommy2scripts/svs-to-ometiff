"""Integration tests for Flask HTTP routes."""

import json

from svs_to_ometiff_gui.serve import app


class DummyConversionService:
    """Minimal conversion service double for route-level job inspection tests."""

    is_active = False

    def __init__(self):
        self.job = None
        self.inputs = None
        self.output_dir = None

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

    def test_convert_rejects_zero_tile_size(self, client, tmp_svs):
        """tile_size=0 must be rejected — positive integer required."""
        resp = client.post(
            "/convert",
            data=json.dumps({"input_path": str(tmp_svs), "tile_size": 0}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]

    def test_convert_rejects_negative_tile_size(self, client, tmp_svs):
        """Negative tile_size must be rejected."""
        resp = client.post(
            "/convert",
            data=json.dumps({"input_path": str(tmp_svs), "tile_size": -16}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]

    def test_convert_accepts_tile_size_not_divisible_by_16(self, client, tmp_svs):
        """Route no longer validates tile_size divisibility by 16; 513 must be accepted."""
        service = DummyConversionService()
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = service
        try:
            resp = client.post(
                "/convert",
                data=json.dumps({"input_path": str(tmp_svs), "tile_size": 513}),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original
        assert resp.status_code == 200

    def test_convert_accepts_jpeg2000_compression_at_route_level(self, client, tmp_svs):
        """Route no longer validates compression; jpeg2000 must reach the queue."""
        service = DummyConversionService()
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = service
        try:
            resp = client.post(
                "/convert",
                data=json.dumps({"input_path": str(tmp_svs), "compression": "jpeg2000"}),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original
        assert resp.status_code == 200

    def test_convert_default_tile_size_is_512(self, client, tmp_svs):
        """When tile_size is omitted, route defaults to 512."""
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
        assert service.job.tile_size == 512

    def test_convert_default_num_levels_is_6(self, client, tmp_svs):
        """When num_levels is omitted, route defaults to 6."""
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
        assert service.job.num_levels == 6

    def test_convert_default_downsample_factor_is_2(self, client, tmp_svs):
        """When downsample_factor is omitted, route defaults to 2."""
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
        assert service.job.downsample_factor == 2

    def test_convert_default_edge_mode_is_crop(self, client, tmp_svs):
        """When edge_mode is omitted, route defaults to 'crop'."""
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
        assert service.job.edge_mode == "crop"

    def test_convert_rejects_invalid_num_levels(self, client, tmp_svs):
        """Non-integer num_levels must return 400."""
        resp = client.post(
            "/convert",
            data=json.dumps({"input_path": str(tmp_svs), "num_levels": "bad"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "num_levels" in data["error"]

    def test_convert_rejects_zero_num_levels(self, client, tmp_svs):
        """num_levels=0 must return 400 — must be positive."""
        resp = client.post(
            "/convert",
            data=json.dumps({"input_path": str(tmp_svs), "num_levels": 0}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "num_levels" in data["error"]

    def test_convert_rejects_invalid_downsample_factor(self, client, tmp_svs):
        """Non-integer downsample_factor must return 400."""
        resp = client.post(
            "/convert",
            data=json.dumps({"input_path": str(tmp_svs), "downsample_factor": "bad"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "downsample_factor" in data["error"]

    def test_convert_rejects_negative_downsample_factor(self, client, tmp_svs):
        """Negative downsample_factor must return 400."""
        resp = client.post(
            "/convert",
            data=json.dumps({"input_path": str(tmp_svs), "downsample_factor": -2}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "downsample_factor" in data["error"]


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

    def test_batch_rejects_invalid_tile_size(self, client, tmp_svs):
        """Non-integer tile_size in batch must return 400."""
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "tile_size": "abc"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]

    def test_batch_rejects_zero_tile_size(self, client, tmp_svs):
        """tile_size=0 in batch must return 400."""
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "tile_size": 0}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]

    def test_batch_rejects_negative_tile_size(self, client, tmp_svs):
        """Negative tile_size in batch must return 400."""
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "tile_size": -64}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_batch_rejects_invalid_num_levels(self, client, tmp_svs):
        """Non-integer num_levels in batch must return 400."""
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "num_levels": "bad"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "num_levels" in data["error"]

    def test_batch_rejects_invalid_downsample_factor(self, client, tmp_svs):
        """Non-integer downsample_factor in batch must return 400."""
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "downsample_factor": "xyz"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "downsample_factor" in data["error"]

    def test_batch_accepts_tile_size_not_divisible_by_16(self, client, tmp_svs):
        """Batch route does not enforce tile_size divisibility by 16; 513 must be accepted."""
        service = DummyConversionService()
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = service
        try:
            resp = client.post(
                "/convert/batch",
                data=json.dumps({"inputs": [str(tmp_svs)], "tile_size": 513}),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original
        assert resp.status_code == 200

    def test_batch_default_tile_size_is_512(self, client, tmp_svs):
        """When tile_size is omitted from batch, route defaults to 512."""
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
        assert service.job.tile_size == 512

    def test_batch_default_num_levels_is_6(self, client, tmp_svs):
        """When num_levels is omitted from batch, route defaults to 6."""
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
        assert service.job.num_levels == 6
