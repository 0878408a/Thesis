"""query.run_query_pipeline tests — orchestration with all externals mocked."""

import pytest

import query
import db
import telegram_notify
import verify


def _make_event(object_id_hex, manufacturer_id, device_type, version):
    return {
        "object_id": object_id_hex,
        "manufacturer_id": manufacturer_id,
        "device_type": device_type,
        "firmware_version": version,
    }


class TestRunQueryPipeline:
    def test_full_happy_path(self, monkeypatch):
        devices = [{"manufacturer_id": "m1", "device_type": "esp32"}]
        events = [
            {
                "object_id": "0x0001",
                "manufacturer_id": "m1",
                "device_type": "esp32",
                "firmware_version": "1.0",
            }
        ]
        metadata = {"manufacturer_id": "m1", "firmware_version": "1.0",
                    "metadata_signature": b"sig", "firmware_size": 1,
                    "release_date": "20240101", "device_type": "esp32"}

        inserted = []
        notified = []
        monkeypatch.setattr(query, "get_all_devices", lambda: devices)
        monkeypatch.setattr(query, "query_events", lambda: events)
        monkeypatch.setattr(query, "firmware_exists", lambda *a: False)
        monkeypatch.setattr(query, "query_object_by_id", lambda oid: metadata)
        monkeypatch.setattr(query, "get_manufacturer_cert", lambda m: b"cert")
        monkeypatch.setattr(query, "verify_signature", lambda *a, **k: True)
        monkeypatch.setattr(
            query, "insert_firmware_metadata",
            lambda oid, md, fw=b"": inserted.append((oid, md)),
        )
        monkeypatch.setattr(
            query, "notify_customers", lambda md: notified.append(md)
        )

        query.run_query_pipeline()

        assert inserted == [("0x0001", metadata)]
        assert notified == [metadata]

    def test_no_matching_events_skips(self, monkeypatch):
        devices = [{"manufacturer_id": "m1", "device_type": "esp32"}]
        monkeypatch.setattr(query, "get_all_devices", lambda: devices)
        monkeypatch.setattr(query, "query_events", lambda: [])
        monkeypatch.setattr(query, "firmware_exists", lambda *a: False)

        inserted = []
        monkeypatch.setattr(
            query, "insert_firmware_metadata",
            lambda oid, md, fw=b"": inserted.append(oid),
        )
        query.run_query_pipeline()
        assert inserted == []

    def test_existing_firmware_skips(self, monkeypatch):
        devices = [{"manufacturer_id": "m1", "device_type": "esp32"}]
        events = [{"object_id": "0x1", "manufacturer_id": "m1",
                   "device_type": "esp32", "firmware_version": "1.0"}]
        monkeypatch.setattr(query, "get_all_devices", lambda: devices)
        monkeypatch.setattr(query, "query_events", lambda: events)
        monkeypatch.setattr(query, "firmware_exists", lambda *a: True)

        inserted = []
        monkeypatch.setattr(
            query, "insert_firmware_metadata",
            lambda oid, md, fw=b"": inserted.append(oid),
        )
        query.run_query_pipeline()
        assert inserted == []

    def test_missing_cert_skips(self, monkeypatch):
        devices = [{"manufacturer_id": "m1", "device_type": "esp32"}]
        events = [{"object_id": "0x1", "manufacturer_id": "m1",
                   "device_type": "esp32", "firmware_version": "1.0"}]
        monkeypatch.setattr(query, "get_all_devices", lambda: devices)
        monkeypatch.setattr(query, "query_events", lambda: events)
        monkeypatch.setattr(query, "firmware_exists", lambda *a: False)
        monkeypatch.setattr(query, "query_object_by_id", lambda oid: {"manufacturer_id": "m1"})
        monkeypatch.setattr(query, "get_manufacturer_cert", lambda m: None)

        inserted = []
        monkeypatch.setattr(
            query, "insert_firmware_metadata",
            lambda oid, md, fw=b"": inserted.append(oid),
        )
        query.run_query_pipeline()
        assert inserted == []

    def test_failed_signature_skips(self, monkeypatch):
        devices = [{"manufacturer_id": "m1", "device_type": "esp32"}]
        events = [{"object_id": "0x1", "manufacturer_id": "m1",
                   "device_type": "esp32", "firmware_version": "1.0"}]
        metadata = {"manufacturer_id": "m1", "firmware_version": "1.0",
                    "metadata_signature": b"x", "firmware_size": 1,
                    "release_date": "20240101", "device_type": "esp32"}
        monkeypatch.setattr(query, "get_all_devices", lambda: devices)
        monkeypatch.setattr(query, "query_events", lambda: events)
        monkeypatch.setattr(query, "firmware_exists", lambda *a: False)
        monkeypatch.setattr(query, "query_object_by_id", lambda oid: metadata)
        monkeypatch.setattr(query, "get_manufacturer_cert", lambda m: b"cert")
        monkeypatch.setattr(query, "verify_signature", lambda *a, **k: False)

        inserted = []
        monkeypatch.setattr(
            query, "insert_firmware_metadata",
            lambda oid, md, fw=b"": inserted.append(oid),
        )
        query.run_query_pipeline()
        assert inserted == []

    def test_multi_device_filtering_processes_only_matching_events(self, monkeypatch):
        """Two matching events (m1) are processed; two non-matching events
        (m2) are filtered out before cert lookup / signature / insert."""
        monkeypatch.setattr(query, "get_all_devices", lambda: [
            {"manufacturer_id": "m1", "device_type": "esp32"},
            {"manufacturer_id": "m1", "device_type": "raspberry"},
        ])
        events = [
            {"object_id": "0x0001", "manufacturer_id": "m1", "device_type": "esp32", "firmware_version": "1.0"},
            {"object_id": "0x0002", "manufacturer_id": "m1", "device_type": "raspberry", "firmware_version": "2.0"},
            {"object_id": "0x0003", "manufacturer_id": "m2", "device_type": "esp32", "firmware_version": "3.0"},
            {"object_id": "0x0004", "manufacturer_id": "m2", "device_type": "raspberry", "firmware_version": "4.0"},
        ]
        monkeypatch.setattr(query, "query_events", lambda: events)
        monkeypatch.setattr(query, "firmware_exists", lambda *a: False)

        metadata_map = {
            "0x0001": {"manufacturer_id": "m1", "device_type": "esp32", "firmware_version": "1.0",
                       "metadata_signature_algorithm": "ecdsa", "firmware_signature_algorithm": "ecdsa",
                       "metadata_signature": b"sig1", "firmware_signature": b"f1",
                       "firmware_size": 10, "release_date": "20250101"},
            "0x0002": {"manufacturer_id": "m1", "device_type": "raspberry", "firmware_version": "2.0",
                       "metadata_signature_algorithm": "ecdsa", "firmware_signature_algorithm": "ecdsa",
                       "metadata_signature": b"sig2", "firmware_signature": b"f2",
                       "firmware_size": 20, "release_date": "20250101"},
        }
        monkeypatch.setattr(
            query, "query_object_by_id",
            lambda oid: metadata_map[oid],
        )
        monkeypatch.setattr(query, "get_manufacturer_cert", lambda m: b"m1-cert")
        monkeypatch.setattr(query, "verify_signature", lambda *a, **k: True)

        inserted = []
        monkeypatch.setattr(
            query, "insert_firmware_metadata",
            lambda oid, md, fw=b"": inserted.append(oid),
        )
        notified = []
        monkeypatch.setattr(
            query, "notify_customers",
            lambda md: notified.append(md["firmware_version"]),
        )

        query.run_query_pipeline()

        # Only m1 events should have been inserted + notified
        assert inserted == ["0x0001", "0x0002"]
        assert notified == ["1.0", "2.0"]
