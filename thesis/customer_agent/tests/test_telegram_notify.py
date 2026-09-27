"""Telegram notify tests — isolate external Telegram HTTP calls and DB reads."""

import json
import pytest

import telegram_notify


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


class TestSendTelegramMessage:
    def test_payload_with_button(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, **kwargs):
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse(200)

        monkeypatch.setattr(telegram_notify.requests, "post", fake_post)
        telegram_notify.send_telegram_message(
            "tok", "99", "hi", customer_id="cid", firmware_version="1.0", parse_mode="Markdown"
        )

        assert captured["url"] == "https://api.telegram.org/bottok/sendMessage"
        p = captured["payload"]
        assert p["chat_id"] == "99"
        assert p["text"] == "hi"
        assert p["parse_mode"] == "Markdown"
        kb = json.loads(p["reply_markup"])
        assert kb["inline_keyboard"][0][0]["callback_data"] == "install_fw:cid:1.0"
        assert kb["inline_keyboard"][0][0]["text"] == "下載並部署韌體版本: 1.0"

    def test_payload_without_button(self, monkeypatch):
        captured = {}

        def fake_post(url, json=None, **kwargs):
            captured["payload"] = json
            return FakeResponse(200)

        monkeypatch.setattr(telegram_notify.requests, "post", fake_post)
        telegram_notify.send_telegram_message("tok", "99", "hi")
        p = captured["payload"]
        assert "reply_markup" not in p
        assert "parse_mode" not in p

    def test_non_200_no_raise(self, monkeypatch):
        def fake_post(url, json=None, **kwargs):
            return FakeResponse(500, "err")

        monkeypatch.setattr(telegram_notify.requests, "post", fake_post)
        # Should not raise even on non-200
        telegram_notify.send_telegram_message("tok", "99", "hi")


class TestNotifyCustomers:
    def _metadata(self):
        return {
            "manufacturer_id": "m1",
            "device_type": "esp32",
            "firmware_version": "1.0",
            "release_date": "3854745600",  # NTP
            "firmware_size": 1024,
        }

    def test_no_customers_no_send(self, monkeypatch):
        monkeypatch.setattr(telegram_notify, "get_customers_by_firmware", lambda *a, **k: [])
        monkeypatch.setattr(telegram_notify, "get_manufacturer_name_by_id", lambda m: "Acme")
        sent = []
        monkeypatch.setattr(
            telegram_notify, "send_telegram_message",
            lambda **k: sent.append(k),
        )
        telegram_notify.notify_customers(self._metadata())
        assert sent == []

    def test_query_uses_metadata_fields(self, monkeypatch):
        """notify_customers must call get_customers_by_firmware with the
        metadata's manufacturer_id / device_type / firmware_version."""
        queried = []
        customers = [{"customer_id": "c1", "bot_token": "b1", "chatid": "91"}]
        monkeypatch.setattr(
            telegram_notify, "get_customers_by_firmware",
            lambda m, d, v: queried.append((m, d, v)) or customers,
        )
        monkeypatch.setattr(
            telegram_notify, "get_manufacturer_name_by_id", lambda m: "Acme"
        )
        sent = []
        monkeypatch.setattr(
            telegram_notify, "send_telegram_message",
            lambda **k: sent.append(k),
        )
        telegram_notify.notify_customers(self._metadata())
        assert queried == [("m1", "esp32", "1.0")]
        assert len(sent) == 1

    def test_notification_message_fields(self, monkeypatch):
        """The message contains device_type / manufacturer / version /
        NTP→Taipei release time / firmware size."""
        customers = [{"customer_id": "c1", "bot_token": "b1", "chatid": "91"}]
        monkeypatch.setattr(
            telegram_notify, "get_customers_by_firmware", lambda *a, **k: customers
        )
        monkeypatch.setattr(
            telegram_notify, "get_manufacturer_name_by_id", lambda m: "Acme"
        )
        sent = []
        monkeypatch.setattr(
            telegram_notify, "send_telegram_message",
            lambda **k: sent.append(k),
        )
        telegram_notify.notify_customers(self._metadata())
        message = sent[0]["message"]
        # Key fields present
        assert "esp32" in message
        assert "Acme" in message
        assert "1.0" in message
        assert "發佈時間" in message
        assert "1024 bytes" in message
        # NTP 3854745600 → 2022-02-25 02:40:00 UTC → 2022-02-25 10:40:00 Asia/Taipei
        assert "2022-02-25 10:40:00" in message

    def test_unknown_manufacturer_fallback(self, monkeypatch):
        customers = [
            {"customer_id": "c1", "bot_token": "b1", "chatid": "91"},
            {"customer_id": "c2", "bot_token": "b2", "chatid": "92"},
        ]
        monkeypatch.setattr(
            telegram_notify, "get_customers_by_firmware",
            lambda *a, **k: customers,
        )
        monkeypatch.setattr(
            telegram_notify, "get_manufacturer_name_by_id", lambda m: None
        )
        sent = []
        def fake_send(bot_token=None, chat_id=None, message=None, customer_id=None, firmware_version=None, **k):
            sent.append((chat_id, message, customer_id, firmware_version))
        monkeypatch.setattr(telegram_notify, "send_telegram_message", fake_send)

        telegram_notify.notify_customers(self._metadata())
        assert len(sent) == 2
        # Unknown manufacturer name fallback
        assert all("(未知製造商 m1)" in m for (_, m, _, _) in sent)
        # Per-customer callback data
        assert sent[0][2] == "c1"
        assert sent[1][2] == "c2"
        # NTP release time appears in message
        assert all("發佈時間" in m for (_, m, _, _) in sent)
