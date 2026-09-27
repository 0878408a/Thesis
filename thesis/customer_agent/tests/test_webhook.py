"""Characterization tests for webhook Flask endpoints and pure helpers.

All DB functions and external services are mocked so these tests run without
MariaDB, IOTA, Telegram, or ESP32.
"""

import pytest

import webhook


@pytest.fixture
def client():
    """Flask test client for the webhook app."""
    return webhook.app.test_client()


# ---------------------------------------------------------------------------
# parse_callback_data (pure function)
# ---------------------------------------------------------------------------

class TestParseCallbackData:
    def test_valid(self):
        assert webhook.parse_callback_data("install_fw:cid1:1.2.3") == ("cid1", "1.2.3")

    def test_no_prefix(self):
        assert webhook.parse_callback_data("foo:cid:ver") == (None, None)

    def test_missing_fields(self):
        assert webhook.parse_callback_data("install_fw:onlyone") == (None, None)

    def test_empty_string(self):
        assert webhook.parse_callback_data("") == (None, None)


# ---------------------------------------------------------------------------
# trigger_download_and_apply (subprocess mock)
# ---------------------------------------------------------------------------

class TestTriggerDownloadAndApply:
    def test_success_calls_both_subprocesses(self, monkeypatch):
        """customer_id + firmware_version flow:
        [sys.executable, CUSTOMER_REQUEST_PATH, cid, ver]
        then
        [sys.executable, APPLY_PATH, cid, ver]
        both with cwd = config.CUSTOMER_AGENT_DIR.
        """
        import sys as _sys
        calls = []  # each entry: (cmd_list, kwargs)

        def fake_run(cmd, *args, **kwargs):
            calls.append((list(cmd), dict(kwargs)))
            return subprocess_result("done\n")

        monkeypatch.setattr(webhook.subprocess, "run", fake_run)
        status, text = webhook.trigger_download_and_apply("cid", "1.0")
        assert status == 200
        assert "韌體安裝完成" in text

        # Exactly two subprocess runs: request first, apply second
        assert len(calls) == 2

        # First call: customer_request.py with the right arguments
        req_cmd, req_kw = calls[0]
        assert req_cmd == [
            _sys.executable,
            str(webhook.CUSTOMER_REQUEST_PATH),
            "cid",
            "1.0",
        ]
        # Second call: apply.py with the same customer_id + version
        apply_cmd, apply_kw = calls[1]
        assert apply_cmd == [
            _sys.executable,
            str(webhook.APPLY_PATH),
            "cid",
            "1.0",
        ]
        # Both subprocesses run from CUSTOMER_AGENT_DIR so the scripts can
        # locate their mTLS certs; verify the important subprocess options.
        for kw in (req_kw, apply_kw):
            assert kw.get("cwd") == webhook.config.CUSTOMER_AGENT_DIR
            assert kw.get("check") is True
            assert kw.get("text") is True
            assert kw.get("stdout") == webhook.subprocess.PIPE
            assert kw.get("stderr") == webhook.subprocess.PIPE

    def test_failure_returns_500_with_stderr(self, monkeypatch):
        import subprocess as sp

        def fake_run(cmd, *args, **kwargs):
            raise sp.CalledProcessError(1, cmd, output="", stderr="boom")

        monkeypatch.setattr(webhook.subprocess, "run", fake_run)
        status, text = webhook.trigger_download_and_apply("cid", "1.0")
        assert status == 500
        assert text == "boom"

    def test_failure_with_empty_stderr_fallback(self, monkeypatch):
        import subprocess as sp

        def fake_run(cmd, *args, **kwargs):
            raise sp.CalledProcessError(1, cmd, output="", stderr="")

        monkeypatch.setattr(webhook.subprocess, "run", fake_run)
        status, text = webhook.trigger_download_and_apply("cid", "1.0")
        assert status == 500
        assert text == "執行失敗但無錯誤輸出"


def subprocess_result(stdout_text):
    class R:
        stdout = stdout_text
        stderr = ""
        returncode = 0
    return R()


# ---------------------------------------------------------------------------
# /register_device
# ---------------------------------------------------------------------------

class TestRegisterDevice:
    def test_ok(self, client, monkeypatch):
        spy = {"called": None}

        def fake_update(mac, ip):
            spy["called"] = (mac, ip)

        monkeypatch.setattr(webhook, "update_device_ip_by_mac", fake_update)
        resp = client.post("/register_device", json={"mac_address": "AB:CD:EF:01:23:45"})
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}
        assert spy["called"] == ("ab:cd:ef:01:23:45", "127.0.0.1")

    def test_missing_mac(self, client):
        resp = client.post("/register_device", json={})
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "missing mac_address"}

    def test_db_error_returns_500(self, client, monkeypatch):
        def fake_update(mac, ip):
            raise RuntimeError("db down")

        monkeypatch.setattr(webhook, "update_device_ip_by_mac", fake_update)
        resp = client.post("/register_device", json={"mac_address": "aa:bb:cc"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "register failed"}


# ---------------------------------------------------------------------------
# /report_update
# ---------------------------------------------------------------------------

class TestReportUpdate:
    def test_ok(self, client, monkeypatch):
        device = {"customer_id": "c1", "manufacturer_id": "m1", "device_type": "esp32"}
        marked = {"called": None}

        monkeypatch.setattr(
            webhook, "get_device_by_ip", lambda ip: device
        )
        def fake_mark(cid, mid, dt, ver):
            marked["called"] = (cid, mid, dt, ver)

        monkeypatch.setattr(webhook, "mark_device_updated", fake_mark)
        resp = client.post("/report_update", json={"version": "2.0"})
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}
        assert marked["called"] == ("c1", "m1", "esp32", "2.0")

    def test_missing_version(self, client):
        resp = client.post("/report_update", json={})
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "missing version"}

    def test_device_not_found(self, client, monkeypatch):
        monkeypatch.setattr(webhook, "get_device_by_ip", lambda ip: None)
        resp = client.post("/report_update", json={"version": "2.0"})
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "device not found"}

    def test_db_error_returns_500(self, client, monkeypatch):
        def fake_get(ip):
            raise RuntimeError("db down")

        monkeypatch.setattr(webhook, "get_device_by_ip", fake_get)
        resp = client.post("/report_update", json={"version": "2.0"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "failed"}


# ---------------------------------------------------------------------------
# /download_firmware
# ---------------------------------------------------------------------------

class TestDownloadFirmware:
    def test_found(self, client, monkeypatch):
        fw = {"firmware_data": b"\x01\x02bin"}
        monkeypatch.setattr(webhook, "get_firmware_by_version", lambda v: fw)
        resp = client.get("/download_firmware?version=1.0")
        assert resp.status_code == 200
        assert resp.data == b"\x01\x02bin"
        assert resp.headers["Content-Type"] == "application/octet-stream"
        assert resp.headers["Content-Disposition"] == "attachment; filename=fw_1.0.bin"

    def test_not_found(self, client, monkeypatch):
        monkeypatch.setattr(webhook, "get_firmware_by_version", lambda v: None)
        resp = client.get("/download_firmware?version=9.9")
        assert resp.status_code == 404
        assert resp.get_data(as_text=True) == "not found"


# ---------------------------------------------------------------------------
# /webhook (telegram)
# ---------------------------------------------------------------------------

class TestTelegramWebhook:
    def test_no_callback_query(self, client):
        resp = client.post("/webhook", json={"message": {"text": "hi"}})
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}

    def test_bad_callback_data(self, client):
        update = {"callback_query": {"data": "garbage"}}
        resp = client.post("/webhook", json=update)
        assert resp.status_code == 400
        assert resp.get_json() == {"ok": False, "error": "callback_data 格式錯誤"}

    def test_user_not_found(self, client, monkeypatch):
        update = {"callback_query": {"data": "install_fw:cid:1.0"}}
        monkeypatch.setattr(webhook, "get_chat_info_by_customer", lambda cid: None)
        resp = client.post("/webhook", json=update)
        assert resp.status_code == 404
        assert resp.get_json() == {"ok": False, "error": "找不到對應用戶"}

    def test_success_sends_telegram(self, client, monkeypatch):
        """On success the callback's customer_id + firmware_version must reach
        trigger_download_and_apply, and its response text must reach the
        Telegram sender with the chat info from the DB lookup."""
        update = {"callback_query": {"data": "install_fw:cid:1.0"}}
        monkeypatch.setattr(
            webhook, "get_chat_info_by_customer",
            lambda cid: {"chatid": "99", "bot_token": "tok"},
        )
        triggered = []
        def fake_trigger(c, v):
            triggered.append((c, v))
            return 200, "done"
        monkeypatch.setattr(webhook, "trigger_download_and_apply", fake_trigger)
        sent = {"called": None}

        def fake_send(token, chat, text, *a, **k):
            sent["called"] = (token, chat, text)

        monkeypatch.setattr(webhook, "send_telegram_message", fake_send)
        resp = client.post("/webhook", json=update)
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}
        # The parsed callback fields flow into the trigger call
        assert triggered == [("cid", "1.0")]
        assert sent["called"] == ("tok", "99", "done")

    def test_processing_error_returns_500(self, client, monkeypatch):
        update = {"callback_query": {"data": "install_fw:cid:1.0"}}
        monkeypatch.setattr(
            webhook, "get_chat_info_by_customer",
            lambda cid: {"chatid": "99", "bot_token": "tok"},
        )
        def fake_trigger(c, v):
            raise RuntimeError("explode")

        monkeypatch.setattr(webhook, "trigger_download_and_apply", fake_trigger)
        resp = client.post("/webhook", json=update)
        assert resp.status_code == 500
        assert resp.get_json() == {"ok": False, "error": "webhook 發生例外錯誤"}

    def test_failed_trigger_calls_handle_error(self, client, monkeypatch):
        update = {"callback_query": {"data": "install_fw:cid:1.0"}}
        monkeypatch.setattr(
            webhook, "get_chat_info_by_customer",
            lambda cid: {"chatid": "99", "bot_token": "tok"},
        )
        monkeypatch.setattr(
            webhook, "trigger_download_and_apply", lambda c, v: (500, "boom")
        )
        handled = []
        monkeypatch.setattr(
            webhook, "handle_error",
            lambda token, chat, msg, error=None: handled.append((token, chat, msg)),
        )
        monkeypatch.setattr(webhook, "send_telegram_message", lambda *a, **k: None)
        resp = client.post("/webhook", json=update)
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}
        assert len(handled) == 1
        assert "安裝請求失敗" in handled[0][2]


# ---------------------------------------------------------------------------
# /api/customer/<customer_id>/firmware  (GET, for Customer Frontend)
# ---------------------------------------------------------------------------

class TestCustomerFirmwareGetApi:
    """GET /api/customer/<customer_id>/firmware — firmware metadata / history."""

    def test_returns_firmware_records_json(self, client, monkeypatch):
        rows = [
            {
                "object_id": "0xabc",
                "manufacturer_id": "m1",
                "manufacturer_name": "Acme",
                "device_type": "esp32",
                "firmware_version": "v1.12",
                "firmware_size": 40960,
                "release_date": 3820540800,
            },
            {
                "object_id": "0xdef",
                "manufacturer_id": "m1",
                "manufacturer_name": "Acme",
                "device_type": "esp32",
                "firmware_version": "v1.11",
                "firmware_size": 40500,
                "release_date": 3820454400,
            },
        ]
        called = {"cid": None}

        def fake_records(customer_id):
            called["cid"] = customer_id
            return rows

        monkeypatch.setattr(webhook, "customer_exists", lambda cid: True)
        monkeypatch.setattr(
            webhook, "get_firmware_records_by_customer_id", fake_records
        )

        resp = client.get("/api/customer/the-cid/firmware")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "application/json"
        body = resp.get_json()
        assert called["cid"] == "the-cid"
        assert body["customer_id"] == "the-cid"
        assert body["device_type"] == "esp32"
        # Full payload check (not just length): the response must be the
        # rows returned by the DB function, unchanged.
        assert body["firmwares"] == rows
        # 保留 manufacturer_name（JOIN 結果），且每筆含 object_id
        assert body["firmwares"][0]["manufacturer_name"] == "Acme"
        assert body["firmwares"][0]["object_id"] == "0xabc"

    def test_empty_firmware_list_is_200(self, client, monkeypatch):
        monkeypatch.setattr(webhook, "customer_exists", lambda cid: True)
        monkeypatch.setattr(
            webhook, "get_firmware_records_by_customer_id", lambda cid: []
        )
        resp = client.get("/api/customer/c1/firmware")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["customer_id"] == "c1"
        assert body["firmwares"] == []
        # 無 device 時 device_type 為 None
        assert body["device_type"] is None

    def test_unknown_customer_returns_404_json(self, client, monkeypatch):
        monkeypatch.setattr(webhook, "customer_exists", lambda cid: False)
        monkeypatch.setattr(
            webhook, "get_firmware_records_by_customer_id", lambda cid: []
        )
        resp = client.get("/api/customer/missing/firmware")
        assert resp.status_code == 404
        assert resp.headers["Content-Type"] == "application/json"
        assert "error" in resp.get_json()

    def test_db_error_returns_500_json(self, client, monkeypatch):
        monkeypatch.setattr(webhook, "customer_exists", lambda cid: True)

        def boom(cid):
            raise RuntimeError("db down")

        monkeypatch.setattr(
            webhook, "get_firmware_records_by_customer_id", boom
        )
        resp = client.get("/api/customer/c1/firmware")
        assert resp.status_code == 500
        assert resp.headers["Content-Type"] == "application/json"
        assert "error" in resp.get_json()


# ---------------------------------------------------------------------------
# /api/customer/<customer_id>/devices  (GET, for Customer Frontend)
# ---------------------------------------------------------------------------

class TestCustomerDevicesGetApi:
    """GET /api/customer/<customer_id>/devices — customer's device list."""

    def test_returns_device_list_json(self, client, monkeypatch):
        rows = [
            {
                "manufacturer_id": "m1",
                "manufacturer_name": "Acme Inc",
                "device_type": "esp32",
                "current_firmware_version": "v1.11",
                "update_method": "https",
            },
            {
                "manufacturer_id": "m2",
                "manufacturer_name": "Beta Corp",
                "device_type": "esp32",
                "current_firmware_version": "v1.10",
                "update_method": "http",
            },
        ]
        called = {"cid": None}

        def fake_devices(customer_id):
            called["cid"] = customer_id
            return rows

        monkeypatch.setattr(webhook, "customer_exists", lambda cid: True)
        monkeypatch.setattr(webhook, "get_devices_by_customer_id", fake_devices)
        resp = client.get("/api/customer/the-cid/devices")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "application/json"
        body = resp.get_json()
        assert called["cid"] == "the-cid"
        assert body["customer_id"] == "the-cid"
        # Full payload check (not just length): the response must be the
        # rows returned by the DB function, unchanged.
        assert body["devices"] == rows
        # 確認包含 manufacturer_name（JOIN 結果）
        assert body["devices"][0]["manufacturer_name"] == "Acme Inc"
        assert body["devices"][1]["manufacturer_name"] == "Beta Corp"

    def test_customer_without_devices_returns_empty_array(self, client, monkeypatch):
        monkeypatch.setattr(webhook, "customer_exists", lambda cid: True)
        monkeypatch.setattr(
            webhook, "get_devices_by_customer_id", lambda cid: []
        )
        resp = client.get("/api/customer/empty-cust/devices")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["customer_id"] == "empty-cust"
        assert body["devices"] == []

    def test_unknown_customer_returns_404_json(self, client, monkeypatch):
        monkeypatch.setattr(webhook, "customer_exists", lambda cid: False)
        monkeypatch.setattr(
            webhook, "get_devices_by_customer_id", lambda cid: []
        )
        resp = client.get("/api/customer/missing-cust/devices")
        assert resp.status_code == 404
        assert resp.headers["Content-Type"] == "application/json"
        assert resp.get_json() == {"error": "customer not found"}

    def test_db_error_returns_500_json(self, client, monkeypatch):
        monkeypatch.setattr(webhook, "customer_exists", lambda cid: True)

        def boom(cid):
            raise RuntimeError("db down")

        monkeypatch.setattr(webhook, "get_devices_by_customer_id", boom)
        resp = client.get("/api/customer/c1/devices")
        assert resp.status_code == 500
        assert resp.headers["Content-Type"] == "application/json"
        assert resp.get_json() == {"error": "failed to load devices"}

    def test_returns_devices_for_requested_customer(self, client, monkeypatch):
        """The requested customer_id is passed to get_devices_by_customer_id,
        and each request returns only that customer's rows. (Not a DB
        security-isolation proof — the DB layer is mocked here.)"""
        devices_by_cid = {
            "cust-A": [
                {
                    "manufacturer_id": "mA",
                    "manufacturer_name": "Acme",
                    "device_type": "esp32",
                    "current_firmware_version": "v1.11",
                    "update_method": "https",
                }
            ],
            "cust-B": [
                {
                    "manufacturer_id": "mB",
                    "manufacturer_name": "Beta",
                    "device_type": "esp32",
                    "current_firmware_version": "v1.10",
                    "update_method": "http",
                }
            ],
        }

        def fake_devices(customer_id):
            return devices_by_cid.get(customer_id, [])

        monkeypatch.setattr(webhook, "customer_exists", lambda cid: True)
        monkeypatch.setattr(webhook, "get_devices_by_customer_id", fake_devices)

        resp_a = client.get("/api/customer/cust-A/devices")
        resp_b = client.get("/api/customer/cust-B/devices")
        # A 的回應只含 A 的裝置
        assert all(
            d["manufacturer_id"] == "mA" for d in resp_a.get_json()["devices"]
        )
        # B 的回應只含 B 的裝置
        assert all(
            d["manufacturer_id"] == "mB" for d in resp_b.get_json()["devices"]
        )
