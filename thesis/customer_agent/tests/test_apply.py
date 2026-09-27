"""apply.py tests — isolate ESP32 https/serial deployment and DB reads."""

import pytest

import apply


class FakeResp:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


class TestUpdateDeviceDispatch:
    def test_https(self, monkeypatch):
        called = []
        monkeypatch.setattr(apply, "update_https", lambda ip, v: called.append(("https", ip, v)) or True)
        assert apply.update_device("https", "10.0.0.1", "1.0") is True
        assert called == [("https", "10.0.0.1", "1.0")]

    def test_serial(self, monkeypatch):
        called = []
        monkeypatch.setattr(apply, "update_serial", lambda port, fw: called.append(("serial", port)) or True)
        assert apply.update_device("serial", "COM3", b"fw") is True
        assert called == [("serial", "COM3")]

    def test_unsupported(self, monkeypatch):
        # Ensure it does not call the two handlers
        def boom(*a, **k):
            raise AssertionError("should not be called")
        monkeypatch.setattr(apply, "update_https", boom)
        monkeypatch.setattr(apply, "update_serial", boom)
        assert apply.update_device("bluetooth", "x", "1.0") is False


class TestUpdateHttps:
    def test_success_200(self, monkeypatch):
        captured = {}
        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return FakeResp(200)
        monkeypatch.setattr(apply.requests, "post", fake_post)
        assert apply.update_https("10.0.0.1", "1.0") is True
        # IP + version compose the exact HTTP request to the ESP32
        assert captured["url"] == "http://10.0.0.1:80/trigger_update"
        assert captured["json"] == {"version": "1.0"}
        assert captured["timeout"] == 10

    def test_non_200(self, monkeypatch):
        monkeypatch.setattr(apply.requests, "post", lambda url, json=None, timeout=None: FakeResp(500, "err"))
        assert apply.update_https("10.0.0.1", "1.0") is False

    def test_exception(self, monkeypatch):
        def fake_post(*a, **k):
            raise ConnectionError("nope")
        monkeypatch.setattr(apply.requests, "post", fake_post)
        assert apply.update_https("10.0.0.1", "1.0") is False


class TestUpdateSerial:
    def test_ok_response(self, monkeypatch):
        """BEGIN\n → firmware bytes → END\n write order, with sleep mocked."""
        writes = []
        serial_ctor_args = []
        class FakeSerial:
            def __init__(self, port, baud, timeout):
                serial_ctor_args.append((port, baud, timeout))
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def write(self, data):
                writes.append(data)
            def read(self, n):
                return b"OK"

        monkeypatch.setattr(apply.serial, "Serial", FakeSerial, raising=False)
        slept = []
        monkeypatch.setattr(apply.time, "sleep", lambda s: slept.append(s))
        assert apply.update_serial("COM3", b"fw") is True
        # Handshake protocol: BEGIN marker, firmware payload, END marker
        assert writes == [b"BEGIN\n", b"fw", b"END\n"]
        # Serial constructor uses the documented port/baud/timeout
        assert serial_ctor_args == [("COM3", 115200, 10)]
        # Both sleeps actually happened (unit test mocked them — no real wait)
        assert slept == [1, 0.5]

    def test_no_ok_response(self, monkeypatch):
        class FakeSerial:
            def __init__(self, *a, **k):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def write(self, data):
                pass
            def read(self, n):
                return b"NO"

        monkeypatch.setattr(apply.serial, "Serial", lambda *a, **k: FakeSerial(), raising=False)
        monkeypatch.setattr(apply.time, "sleep", lambda s: None)
        assert apply.update_serial("COM3", b"fw") is False

    def test_serial_exception(self, monkeypatch):
        def fake_serial(*a, **k):
            raise OSError("no port")
        monkeypatch.setattr(apply.serial, "Serial", fake_serial, raising=False)
        monkeypatch.setattr(apply.time, "sleep", lambda s: None)
        assert apply.update_serial("COM3", b"fw") is False


class TestDeployToDevices:
    def test_no_devices_returns_false(self, monkeypatch):
        queried = []
        monkeypatch.setattr(
            apply, "get_devices_by_customer_and_version",
            lambda c, v: queried.append((c, v)) or [],
        )
        assert apply.deploy_to_devices("c", "1.0") is False
        # The DB query receives the exact customer_id + firmware_version
        assert queried == [("c", "1.0")]

    def test_calls_update_device_per_device(self, monkeypatch):
        devices = [
            {"update_method": "https", "ip_address": "10.0.0.1", "manufacturer_id": "m1", "device_type": "esp32"},
            {"update_method": "https", "ip_address": "10.0.0.2", "manufacturer_id": "m1", "device_type": "esp32"},
        ]
        monkeypatch.setattr(
            apply, "get_devices_by_customer_and_version",
            lambda c, v: devices,
        )
        called = []
        monkeypatch.setattr(
            apply, "update_device",
            lambda method, address, firmware_version: called.append(
                (method, address, firmware_version)
            ) or True,
        )
        assert apply.deploy_to_devices("c", "1.0") is True
        # Each device gets (method, address) from its row + the firmware_version
        assert called == [
            ("https", "10.0.0.1", "1.0"),
            ("https", "10.0.0.2", "1.0"),
        ]

    def test_update_failure_still_returns_true(self, monkeypatch):
        """Locks current production behavior: deploy_to_devices returns True
        even when update_device fails for a device (the failure is only
        logged, not propagated). This test documents the behavior so that
        any future change to return False on failure must be a deliberate,
        reviewed decision."""
        devices = [
            {"update_method": "https", "ip_address": "10.0.0.1", "manufacturer_id": "m1", "device_type": "esp32"},
        ]
        monkeypatch.setattr(
            apply, "get_devices_by_customer_and_version",
            lambda c, v: devices,
        )
        failures = []
        monkeypatch.setattr(
            apply, "update_device",
            lambda method, address, firmware_version: failures.append(address) or False,
        )
        # update_device returned False (OTA trigger failed for this device)
        assert apply.deploy_to_devices("c", "1.0") is True
        assert failures == ["10.0.0.1"]
