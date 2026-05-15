"""Integration tests for Flask HTTP routes."""

import json



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

    def test_batch_invalid_tile_size_string_returns_400(self, client, tmp_svs):
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "tile_size": "abc"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]

    def test_batch_zero_tile_size_returns_400(self, client, tmp_svs):
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "tile_size": 0}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]

    def test_batch_negative_tile_size_returns_400(self, client, tmp_svs):
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "tile_size": -1}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]

    def test_batch_zero_num_levels_returns_400(self, client, tmp_svs):
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "num_levels": 0}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "num_levels" in data["error"]

    def test_batch_invalid_downsample_factor_string_returns_400(self, client, tmp_svs):
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "downsample_factor": "x"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "downsample_factor" in data["error"]

    def test_batch_error_message_uses_short_form(self, client, tmp_svs):
        """Batch endpoint uses 'must be positive int' (shorter than single route)."""
        resp = client.post(
            "/convert/batch",
            data=json.dumps({"inputs": [str(tmp_svs)], "tile_size": 0}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "positive int" in data["error"]


class TestConvertInlineValidation:
    """Tests for the new inline validation added in the PR (no ConvertConfig delegation)."""

    def test_convert_rejects_tile_size_not_divisible_by_16(self, client, tmp_svs):
        """Route validates with ConvertConfig before queueing background work."""
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "tile_size": 513,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "divisible" in json.loads(resp.data).get("error", "")

    def test_convert_rejects_jpeg2000_compression_at_route_level(self, client, tmp_svs):
        """Route rejects unsupported compression before queueing background work."""
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "compression": "jpeg2000",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "jpeg2000" in json.loads(resp.data).get("error", "")

    def test_convert_rejects_zero_tile_size(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "tile_size": 0,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]

    def test_convert_rejects_negative_tile_size(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "tile_size": -16,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "tile_size" in data["error"]

    def test_convert_rejects_zero_num_levels(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "num_levels": 0,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "num_levels" in data["error"]

    def test_convert_rejects_negative_num_levels(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "num_levels": -3,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "num_levels" in data["error"]

    def test_convert_rejects_invalid_num_levels_string(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "num_levels": "bad",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "num_levels" in data["error"]

    def test_convert_rejects_zero_downsample_factor(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "downsample_factor": 0,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "downsample_factor" in data["error"]

    def test_convert_rejects_invalid_downsample_factor_string(self, client, tmp_svs):
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "downsample_factor": "two",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "downsample_factor" in data["error"]

    def test_convert_error_message_uses_long_form(self, client, tmp_svs):
        """Single /convert endpoint uses 'must be a positive integer' (longer form)."""
        resp = client.post(
            "/convert",
            data=json.dumps({
                "input_path": str(tmp_svs),
                "tile_size": 0,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "positive integer" in data["error"]

    def test_convert_valid_omitted_optional_params_are_accepted(self, client, tmp_svs):
        """Omitting optional params should not trigger validation errors."""
        class CapturingService:
            is_active = False
            progress_queues = {}
            latest_events = {}

            def start_conversion(self, job):
                return "req-id"

            def inspect_slide(self, path):
                return {}

            def cleanup_job(self, request_id):
                pass

        from svs_to_ometiff_gui.serve import app
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = CapturingService()
        try:
            resp = client.post(
                "/convert",
                data=json.dumps({"input_path": str(tmp_svs)}),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original

        assert resp.status_code == 200


class TestConvertJobDefaults:
    """Verify the default values used in ConversionJob construction after PR changes."""

    def test_convert_defaults_match_public_profile(self, client, tmp_svs):
        """Default single-conversion settings match the public profile."""
        captured_jobs = []

        class CapturingService:
            is_active = False
            progress_queues = {}
            latest_events = {}

            def start_conversion(self, job):
                captured_jobs.append(job)
                return "req-id"

            def inspect_slide(self, path):
                return {}

            def cleanup_job(self, request_id):
                pass

        from svs_to_ometiff_gui.serve import app
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = CapturingService()
        try:
            resp = client.post(
                "/convert",
                data=json.dumps({"input_path": str(tmp_svs)}),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original

        assert resp.status_code == 200
        assert len(captured_jobs) == 1
        assert captured_jobs[0].tile_size == 1024
        assert captured_jobs[0].compression == "zlib"
        assert captured_jobs[0].num_levels == 6
        assert captured_jobs[0].downsample_factor == 2
        assert captured_jobs[0].edge_mode == "crop"

    def test_convert_default_edge_mode_is_crop(self, client, tmp_svs):
        """Default edge_mode should be 'crop'."""
        captured_jobs = []

        class CapturingService:
            is_active = False
            progress_queues = {}
            latest_events = {}

            def start_conversion(self, job):
                captured_jobs.append(job)
                return "req-id"

            def inspect_slide(self, path):
                return {}

            def cleanup_job(self, request_id):
                pass

        from svs_to_ometiff_gui.serve import app
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = CapturingService()
        try:
            resp = client.post(
                "/convert",
                data=json.dumps({"input_path": str(tmp_svs)}),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original

        assert resp.status_code == 200
        assert captured_jobs[0].edge_mode == "crop"

    def test_convert_includes_temp_dir_when_provided(self, client, tmp_svs, tmp_path):
        """Single route carries the GUI temp directory into the job."""
        captured_jobs = []

        class CapturingService:
            is_active = False
            progress_queues = {}
            latest_events = {}

            def start_conversion(self, job):
                captured_jobs.append(job)
                return "req-id"

            def inspect_slide(self, path):
                return {}

            def cleanup_job(self, request_id):
                pass

        from svs_to_ometiff_gui.serve import app
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = CapturingService()
        temp_dir = tmp_path / "local_temp"
        try:
            resp = client.post(
                "/convert",
                data=json.dumps({
                    "input_path": str(tmp_svs),
                    "temp_dir": str(temp_dir),
                }),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original

        assert resp.status_code == 200
        assert captured_jobs[0].temp_dir == str(temp_dir)

    def test_batch_defaults_match_public_profile(self, client, tmp_svs):
        """Batch route defaults match the public profile."""
        captured_templates = []

        class CapturingService:
            is_active = False
            progress_queues = {}
            latest_events = {}

            def start_batch_conversion(self, inputs, output_dir, job_template):
                captured_templates.append(job_template)
                return "batch-req-id"

            def inspect_slide(self, path):
                return {}

            def cleanup_job(self, request_id):
                pass

        from svs_to_ometiff_gui.serve import app
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = CapturingService()
        try:
            resp = client.post(
                "/convert/batch",
                data=json.dumps({"inputs": [str(tmp_svs)]}),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original

        assert resp.status_code == 200
        assert len(captured_templates) == 1
        assert captured_templates[0].tile_size == 1024
        assert captured_templates[0].compression == "zlib"
        assert captured_templates[0].num_levels == 6
        assert captured_templates[0].downsample_factor == 2
        assert captured_templates[0].edge_mode == "crop"

    def test_batch_includes_temp_dir_when_provided(self, client, tmp_svs, tmp_path):
        """Batch route carries the GUI temp directory into the job template."""
        captured_templates = []

        class CapturingService:
            is_active = False
            progress_queues = {}
            latest_events = {}

            def start_batch_conversion(self, inputs, output_dir, job_template):
                captured_templates.append(job_template)
                return "batch-req-id"

            def inspect_slide(self, path):
                return {}

            def cleanup_job(self, request_id):
                pass

        from svs_to_ometiff_gui.serve import app
        original = app.config["CONVERSION_SERVICE"]
        app.config["CONVERSION_SERVICE"] = CapturingService()
        temp_dir = tmp_path / "local_temp"
        try:
            resp = client.post(
                "/convert/batch",
                data=json.dumps({
                    "inputs": [str(tmp_svs)],
                    "temp_dir": str(temp_dir),
                }),
                content_type="application/json",
            )
        finally:
            app.config["CONVERSION_SERVICE"] = original

        assert resp.status_code == 200
        assert captured_templates[0].temp_dir == str(temp_dir)
