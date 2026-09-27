"""
Characterization tests for the Manufacturer Client Flask Server (`service.py`).

Strategy: patch function names *on the service module* (`service.build_upload_payload`,
`service.upload_with_mtls`, `service.history_with_mtls`). The route handlers read these
names via module-scope lookup, so patching at the service module fully isolates the
upstream mTLS layer without ever opening a TLS connection or binding a port.
"""

import io

import pytest

import service


# ---------------------------------------------------------------------------
# POST /internal/manufacturer/upload
# ---------------------------------------------------------------------------

def _upload_kwargs(firmware_bytes=b"FW", filename="fw.bin", firmware_version="v1", device_type="blink"):
    """Build data kwargs for a multipart upload.

    Pass `firmware_file=None` to omit the file entirely.
    Pass `filename=""` to simulate an empty filename.
    Pass `firmware_version=None` or `device_type=None` to omit that form field.
    """
    data = {}
    if firmware_file_bytes := firmware_bytes:
        file_tuple = (
            io.BytesIO(firmware_file_bytes) if firmware_file_bytes is not None else io.BytesIO(b""),
            filename,
        )
        data["firmware_file"] = file_tuple
    if firmware_version is not None:
        data["firmware_version"] = firmware_version
    if device_type is not None:
        data["device_type"] = device_type
    return data


class TestUploadValidation:
    """Request validation: 400 + exact error JSON, in the same order as production."""

    def test_missing_firmware_file(self, client, monkeypatch):
        def fake_build_payload(*a, **kw):
            raise AssertionError("build_upload_payload should not be called")
        def fake_upload(*a, **kw):
            raise AssertionError("upload_with_mtls should not be called")
        monkeypatch.setattr(service, "build_upload_payload", fake_build_payload)
        monkeypatch.setattr(service, "upload_with_mtls", fake_upload)

        resp = client.post("/internal/manufacturer/upload", content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "firmware_file is required"}

    def test_empty_firmware_file_filename(self, client, monkeypatch):
        monkeypatch.setattr(service, "build_upload_payload", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
        monkeypatch.setattr(service, "upload_with_mtls", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b""), ""),  # empty filename
                "firmware_version": "v1",
                "device_type": "blink",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "firmware_file is required"}

    def test_missing_firmware_version(self, client, monkeypatch):
        monkeypatch.setattr(service, "build_upload_payload", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
        monkeypatch.setattr(service, "upload_with_mtls", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))

        resp = client.post(
            "/internal/manufacturer/upload",
            data={"firmware_file": (io.BytesIO(b"FW"), "fw.bin"), "device_type": "blink"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "firmware_version is required"}

    @pytest.mark.parametrize("bad_version", ["", "   ", "\t", "\n"])
    def test_blank_firmware_version(self, client, monkeypatch, bad_version):
        monkeypatch.setattr(service, "build_upload_payload", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
        monkeypatch.setattr(service, "upload_with_mtls", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b"FW"), "fw.bin"),
                "firmware_version": bad_version,
                "device_type": "blink",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "firmware_version is required"}

    def test_missing_device_type(self, client, monkeypatch):
        monkeypatch.setattr(service, "build_upload_payload", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
        monkeypatch.setattr(service, "upload_with_mtls", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b"FW"), "fw.bin"),
                "firmware_version": "v1",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "device_type is required"}

    @pytest.mark.parametrize("bad_dt", ["", "   ", "\t", "\n"])
    def test_blank_device_type(self, client, monkeypatch, bad_dt):
        monkeypatch.setattr(service, "build_upload_payload", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
        monkeypatch.setattr(service, "upload_with_mtls", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b"FW"), "fw.bin"),
                "firmware_version": "v1",
                "device_type": bad_dt,
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "device_type is required"}


class TestUploadSuccess:
    def test_parameter_passing_to_upstream(self, client, monkeypatch):
        received = {}

        def fake_build(firmware_bytes, firmware_version, device_type):
            received["build_args"] = (firmware_bytes, firmware_version, device_type)
            return {"payload": "OK"}

        def fake_upload(payload):
            received["upload_args"] = payload
            from tests.conftest import FakeUpstreamResponse
            return FakeUpstreamResponse(status_code=201, json_data={"ok": True}, text="{}")

        monkeypatch.setattr(service, "build_upload_payload", fake_build)
        monkeypatch.setattr(service, "upload_with_mtls", fake_upload)

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b"ABC"), "fw.bin"),
                "firmware_version": "v1",
                "device_type": "blink",
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 201
        assert resp.get_json() == {"ok": True}
        assert received["build_args"] == (b"ABC", "v1", "blink")
        assert received["upload_args"] == {"payload": "OK"}

    def test_upstream_json_passthrough(self, client, monkeypatch):
        monkeypatch.setattr(service, "build_upload_payload", lambda *a: {"p": 1})
        monkeypatch.setattr(
            service,
            "upload_with_mtls",
            lambda payload: _fake_json_response(status_code=200, json_data={"received": True}),
        )

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b"X"), "fw.bin"),
                "firmware_version": "v1",
                "device_type": "blink",
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 200
        assert resp.get_json() == {"received": True}

    def test_upstream_non_200_status_passed_through(self, client, monkeypatch):
        monkeypatch.setattr(service, "build_upload_payload", lambda *a: {"p": 1})
        monkeypatch.setattr(
            service,
            "upload_with_mtls",
            lambda payload: _fake_json_response(status_code=422, json_data={"error": "upstream"}),
        )

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b"X"), "fw.bin"),
                "firmware_version": "v1",
                "device_type": "blink",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 422
        assert resp.get_json() == {"error": "upstream"}

    def test_upstream_json_value_error_falls_back_to_text(self, client, monkeypatch):
        monkeypatch.setattr(service, "build_upload_payload", lambda *a: {"p": 1})
        monkeypatch.setattr(
            service,
            "upload_with_mtls",
            lambda payload: _fake_text_response(status_code=200, text="plain text body"),
        )

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b"X"), "fw.bin"),
                "firmware_version": "v1",
                "device_type": "blink",
            },
            content_type="multipart/form-data",
        )

        # production wraps response.text via jsonify(response_data);
        # jsonify of a plain string is encoded as a JSON string value
        assert resp.status_code == 200
        assert resp.get_json() == "plain text body"


class TestUploadException:
    def test_build_upload_payload_raises(self, client, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("boom")
        monkeypatch.setattr(service, "build_upload_payload", boom)
        monkeypatch.setattr(service, "upload_with_mtls", lambda *a: (_ for _ in ()).throw(AssertionError("should not call")))

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b"X"), "fw.bin"),
                "firmware_version": "v1",
                "device_type": "blink",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Manufacturer Client internal error"}

    def test_upload_with_mtls_raises(self, client, monkeypatch):
        monkeypatch.setattr(service, "build_upload_payload", lambda *a: {"p": 1})

        def boom(payload):
            raise RuntimeError("boom")
        monkeypatch.setattr(service, "upload_with_mtls", boom)

        resp = client.post(
            "/internal/manufacturer/upload",
            data={
                "firmware_file": (io.BytesIO(b"X"), "fw.bin"),
                "firmware_version": "v1",
                "device_type": "blink",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Manufacturer Client internal error"}


# ---------------------------------------------------------------------------
# GET /internal/manufacturer/history/
# ---------------------------------------------------------------------------

class TestHistorySuccess:
    def test_default_page_is_1(self, client, monkeypatch):
        captured = {}

        def fake_history(page):
            captured["page"] = page
            return _fake_json_response(status_code=200, json_data={"items": []})

        monkeypatch.setattr(service, "history_with_mtls", fake_history)
        resp = client.get("/internal/manufacturer/history/")
        assert resp.status_code == 200
        assert resp.get_json() == {"items": []}
        assert captured["page"] == "1"

    def test_explicit_page_is_passed_through(self, client, monkeypatch):
        captured = {}

        def fake_history(page):
            captured["page"] = page
            return _fake_json_response(status_code=200, json_data={"items": [1]})

        monkeypatch.setattr(service, "history_with_mtls", fake_history)
        resp = client.get("/internal/manufacturer/history/", query_string={"page": "2"})
        assert resp.status_code == 200
        assert resp.get_json() == {"items": [1]}
        assert captured["page"] == "2"

    def test_arbitrary_page_string_is_passed_verbatim(self, client, monkeypatch):
        captured = {}

        def fake_history(page):
            captured["page"] = page
            return _fake_json_response(status_code=200, json_data={"items": []})

        monkeypatch.setattr(service, "history_with_mtls", fake_history)
        # no parsing / no validation: the server forwards the raw string
        resp = client.get("/internal/manufacturer/history/", query_string={"page": "abc-def"})
        assert resp.status_code == 200
        assert captured["page"] == "abc-def"

    def test_upstream_json_passthrough(self, client, monkeypatch):
        monkeypatch.setattr(
            service,
            "history_with_mtls",
            lambda page: _fake_json_response(status_code=200, json_data={"history": []}),
        )
        resp = client.get("/internal/manufacturer/history/")
        assert resp.status_code == 200
        assert resp.get_json() == {"history": []}

    def test_upstream_non_200_status_passed_through(self, client, monkeypatch):
        monkeypatch.setattr(
            service,
            "history_with_mtls",
            lambda page: _fake_json_response(status_code=503, json_data={"error": "upstream"}),
        )
        resp = client.get("/internal/manufacturer/history/")
        assert resp.status_code == 503
        assert resp.get_json() == {"error": "upstream"}

    def test_upstream_json_value_error_falls_back_to_text(self, client, monkeypatch):
        monkeypatch.setattr(
            service,
            "history_with_mtls",
            lambda page: _fake_text_response(status_code=200, text="plain text body"),
        )
        resp = client.get("/internal/manufacturer/history/")
        assert resp.status_code == 200
        assert resp.get_json() == "plain text body"


class TestHistoryException:
    def test_history_with_mtls_raises(self, client, monkeypatch):
        def boom(page):
            raise RuntimeError("boom")
        monkeypatch.setattr(service, "history_with_mtls", boom)

        resp = client.get("/internal/manufacturer/history/")
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Manufacturer Client internal error"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_json_response(status_code: int, json_data):
    from tests.conftest import FakeUpstreamResponse
    return FakeUpstreamResponse(status_code=status_code, json_data=json_data, text="")


def _fake_text_response(status_code: int, text: str):
    from tests.conftest import FakeUpstreamResponse
    return FakeUpstreamResponse(status_code=status_code, json_data=None, text=text, raise_json_value_error=True)
