"""Pure-function tests for query.py (no network / IOTA calls)."""

import query


class TestVectorU8ToHexString:
    def test_encode(self):
        assert query.vector_u8_to_hex_string([0x00, 0x08, 0xab]) == "0x0008ab"

    def test_single_byte(self):
        assert query.vector_u8_to_hex_string([0xff]) == "0xff"

    def test_empty(self):
        assert query.vector_u8_to_hex_string([]) == "0x"

    def test_each_byte_is_two_hex_digits_lowercase(self):
        result = query.vector_u8_to_hex_string([0, 1, 255])
        assert result == "0x0001ff"

    def test_object_id_round_trip(self):
        # 64-char hex object_id, as returned by IOTA
        raw = list(range(32))
        result = query.vector_u8_to_hex_string(raw)
        assert result.startswith("0x")
        assert result == "0x" + "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"


class TestVectorU8ToString:
    def test_valid_utf8(self):
        assert query.vector_u8_to_string([118, 49, 46, 49]) == "v1.1"

    def test_invalid_utf8(self):
        # 0xff 0xfe is not valid UTF-8
        assert query.vector_u8_to_string([0xff, 0xfe]) == "<invalid utf-8>"


class TestQueryEventsParsing:
    """query_events() parses raw JSON-RPC responses; no real IOTA calls."""

    class _FakeResponse:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    def test_paired_events_with_valid_utf8(self, monkeypatch):
        data = {
            "result": {
                "data": [
                    {
                        "parsedJson": {
                            "object_id": [0, 1],
                            "manufacturer_id": [109, 49],  # "m1"
                            "device_type": [101, 115, 112, 51, 50],  # "esp32"
                            "firmware_version": [49, 46, 48],  # "1.0"
                        }
                    }
                ]
            }
        }
        monkeypatch.setattr(
            query.requests, "post",
            lambda url, **kw: self._FakeResponse(data),
        )
        result = query.query_events()
        assert result == [
            {
                "object_id": "0x0001",
                "manufacturer_id": "m1",
                "device_type": "esp32",
                "firmware_version": "1.0",
            }
        ]

    def test_missing_result_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(
            query.requests, "post",
            lambda url, **kw: self._FakeResponse({"error": "nope"}),
        )
        assert query.query_events() == []

    def test_invalid_utf8_field_uses_placeholder(self, monkeypatch):
        data = {
            "result": {
                "data": [
                    {
                        "parsedJson": {
                            "object_id": [0x01],
                            "manufacturer_id": [0xff, 0xfe],  # invalid UTF-8
                            "device_type": [101, 115, 112, 51, 50],
                            "firmware_version": [49, 46, 48],
                        }
                    }
                ]
            }
        }
        monkeypatch.setattr(
            query.requests, "post",
            lambda url, **kw: self._FakeResponse(data),
        )
        result = query.query_events()
        assert result[0]["manufacturer_id"] == "<invalid utf-8>"
        assert result[0]["device_type"] == "esp32"


class TestQueryObjectById:
    """query_object_by_id() parses IoTa object metadata; mock requests.post."""

    def _fake_post(self, fields):
        class FakeResp:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        return lambda url, **kw: FakeResp({
            "result": {"data": {"content": {"fields": fields}}}
        })

    def test_happy_path_decodes_all_fields(self, monkeypatch):
        fields = {
            "firmware_version": [118, 49, 46, 49],       # "v1.1"
            "device_type": [101, 115, 112, 51, 50],      # "esp32"
            "manufacturer_id": [109, 49],                 # "m1"
            "metadata_signature_algorithm": [101, 99, 100, 115, 97],  # "ecdsa"
            "firmware_signature_algorithm": [101, 99, 100, 115, 97],
            "metadata_signature": [1, 2, 3],
            "firmware_signature": [4, 5, 6],
            "firmware_size": 40960,
            "release_date": 3998805834,
        }
        monkeypatch.setattr(query.requests, "post", self._fake_post(fields))
        result = query.query_object_by_id("0xabc123")

        assert result["firmware_version"] == "v1.1"
        assert result["device_type"] == "esp32"
        assert result["manufacturer_id"] == "m1"
        assert result["metadata_signature"] == b"\x01\x02\x03"
        assert result["firmware_signature"] == b"\x04\x05\x06"
        assert result["firmware_size"] == 40960
        assert result["release_date"] == 3998805834

    def test_uses_correct_jsonrpc_params(self, monkeypatch):
        captured = []

        def spy_post(url, **kw):
            captured.append((url, kw.get("json")))
            class FR:
                def __init__(self, d): self._d = d
                def json(self): return self._d
            return FR({"result": {"data": {"content": {"fields": self._empty_fields()}}}})

        monkeypatch.setattr(query.requests, "post", spy_post)
        query.query_object_by_id("0xdeadbeef")

        url, payload = captured[0]
        assert payload["method"] == "iota_getObject"
        assert payload["params"][0] == "0xdeadbeef"
        assert payload["params"][1]["showType"] is True
        assert payload["params"][1]["showContent"] is True

    def _empty_fields(self):
        return {
            "firmware_version": [], "device_type": [], "manufacturer_id": [],
            "metadata_signature_algorithm": [], "firmware_signature_algorithm": [],
            "metadata_signature": [], "firmware_signature": [],
            "firmware_size": 0, "release_date": 0,
        }

    def test_error_response_returns_empty_dict(self, monkeypatch):
        class FR:
            def json(self):
                return {"error": "object not found"}
        monkeypatch.setattr(query.requests, "post", lambda url, **kw: FR())
        assert query.query_object_by_id("0xdeadbeef") == {}

    def test_missing_data_returns_empty_dict(self, monkeypatch):
        class FR:
            def json(self):
                return {"result": {}}
        monkeypatch.setattr(query.requests, "post", lambda url, **kw: FR())
        assert query.query_object_by_id("0xdeadbeef") == {}
