"""DB layer tests — all connections are mocked (no real MariaDB).

We patch ``db.get_db_connection`` to return a fake context-manager connection
whose cursor returns canned rows.
"""

import contextlib
import pytest

import db


class FakeCursor:
    """Cursor supporting ``with`` + execute/fetchone/fetchall + rowcount."""

    def __init__(self, fetchone_result=None, fetchall_result=None, rowcount=1,
                 executed=None):
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result
        self.rowcount = rowcount
        self.executed = executed  # list to capture (sql, params)

    def execute(self, sql, params=None):
        if self.executed is not None:
            self.executed.append((sql, params))

    def fetchone(self):
        return self._fetchone_result

    def fetchall(self):
        return self._fetchall_result

    @contextlib.contextmanager
    def _unused(self):
        yield self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def make_conn(fetchone=None, fetchall=None, rowcount=1, executed=None):
    cur = FakeCursor(fetchone_result=fetchone, fetchall_result=fetchall,
                     rowcount=rowcount, executed=executed)
    return FakeConn(cur), cur


class TestFetchOneFunctions:
    def test_get_device_by_ip_returns_dict(self, monkeypatch):
        executed = []
        row = {"customer_id": "c", "manufacturer_id": "m", "device_type": "esp32"}
        conn, _ = make_conn(fetchone=row, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_device_by_ip("1.2.3.4") == row
        assert executed[0][1] == ("1.2.3.4",)

    def test_get_device_by_ip_none(self, monkeypatch):
        conn, _ = make_conn(fetchone=None)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_device_by_ip("1.2.3.4") is None

    def test_get_firmware_by_version_found(self, monkeypatch):
        executed = []
        row = {"firmware_data": b"data"}
        conn, _ = make_conn(fetchone=row, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_firmware_by_version("1.0") == row
        assert executed[0][1] == ("1.0",)

    def test_get_firmware_by_version_none(self, monkeypatch):
        conn, _ = make_conn(fetchone=None)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_firmware_by_version("1.0") is None

    def test_get_customer_chat_info(self, monkeypatch):
        executed = []
        row = {"customer_id": "c", "bot_token": "tok", "chatid": "9"}
        conn, _ = make_conn(fetchone=row, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_customer_chat_info("c") == row
        assert executed[0][1] == ("c",)

    def test_get_latest_firmware_version_found(self, monkeypatch):
        executed = []
        conn, _ = make_conn(fetchone={"firmware_version": "9.9"}, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_latest_firmware_version_for_device("esp32") == "9.9"
        assert executed[0][1] == ("esp32",)

    def test_get_latest_firmware_version_none(self, monkeypatch):
        conn, _ = make_conn(fetchone=None)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_latest_firmware_version_for_device("esp32") is None


class TestFirmwareExists:
    def test_true_when_row(self, monkeypatch):
        executed = []
        conn, _ = make_conn(fetchone={"1": 1}, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.firmware_exists("m", "esp32", "1.0") is True
        assert executed[0][1] == ("m", "esp32", "1.0")

    def test_false_when_none(self, monkeypatch):
        conn, _ = make_conn(fetchone=None)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.firmware_exists("m", "esp32", "1.0") is False


class TestFetchAllFunctions:
    def test_get_all_devices(self, monkeypatch):
        rows = [{"manufacturer_id": "m", "device_type": "esp32"}]
        conn, _ = make_conn(fetchall=rows)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_all_devices() == rows

    def test_get_devices_by_customer_and_version(self, monkeypatch):
        executed = []
        rows = [{"update_method": "https", "ip_address": "10.0.0.1"}]
        conn, _ = make_conn(fetchall=rows, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_devices_by_customer_and_version("c", "1.0") == rows
        assert executed[0][1] == ("c", "1.0")

    def test_get_devices_by_customer_and_version_empty(self, monkeypatch):
        conn, _ = make_conn(fetchall=[])
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_devices_by_customer_and_version("c", "1.0") == []

    def test_get_devices_by_customer_id(self, monkeypatch):
        executed = []
        rows = [
            {"update_method": "https", "ip_address": "10.0.0.1", "manufacturer_id": "m1"},
            {"update_method": "serial", "ip_address": None, "manufacturer_id": "m1"},
        ]
        conn, _ = make_conn(fetchall=rows, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_devices_by_customer_id("customer-123") == rows
        assert executed[0][1] == ("customer-123",)

    def test_get_devices_by_customer_id_empty(self, monkeypatch):
        conn, _ = make_conn(fetchall=[])
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_devices_by_customer_id("customer-123") == []


class TestUpdateFunctions:
    def test_update_device_ip_by_mac_commits(self, monkeypatch):
        executed = []
        conn, cur = make_conn(rowcount=1, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        db.update_device_ip_by_mac("aa:bb", "1.2.3.4")
        assert conn.committed is True
        # params are (ip, mac)
        assert executed[0][1] == ("1.2.3.4", "aa:bb")

    def test_mark_device_updated_commits(self, monkeypatch):
        executed = []
        conn, cur = make_conn(rowcount=1, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        db.mark_device_updated("c", "m", "esp32", "2.0")
        assert conn.committed is True
        assert executed[0][1] == ("2.0", "c", "m", "esp32")


class TestGetManufacturerName:
    def test_found(self, monkeypatch):
        executed = []
        conn, _ = make_conn(fetchone={"manufacturer_name": "Acme"}, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_manufacturer_name_by_id("m") == "Acme"
        assert executed[0][1] == ("m",)

    def test_not_found(self, monkeypatch):
        conn, _ = make_conn(fetchone=None)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_manufacturer_name_by_id("m") is None


class TestRemainingDbFunctions:
    """Cover the less-exercised db functions with the same fake-conn pattern."""

    def test_insert_firmware_metadata_commits(self, monkeypatch):
        executed = []
        conn, _ = make_conn(rowcount=1, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        metadata = {
            "metadata_signature": b"sig",
            "metadata_signature_algorithm": "ecdsa",
            "firmware_signature": b"sig",
            "firmware_signature_algorithm": "ecdsa",
            "firmware_size": 10,
            "release_date": "20240101",
            "manufacturer_id": "m",
            "device_type": "esp32",
            "firmware_version": "1.0",
        }
        db.insert_firmware_metadata("obj", metadata, b"firmware")
        assert conn.committed is True
        # params are 11 values; verify the full ordered tuple
        params = executed[0][1]
        assert params[0] == "obj"
        assert params[1] == b"sig"        # metadata_signature
        assert params[2] == "ecdsa"       # metadata_signature_algorithm
        assert params[3] == b"sig"        # firmware_signature
        assert params[4] == "ecdsa"       # firmware_signature_algorithm
        assert params[5] == 10            # firmware_size
        assert params[6] == "20240101"    # release_date
        assert params[7] == "m"           # manufacturer_id
        assert params[8] == "esp32"       # device_type
        assert params[9] == "1.0"         # firmware_version
        assert params[10] == b"firmware"  # firmware binary

    def test_customer_exists_true_when_row(self, monkeypatch):
        conn, _ = make_conn(fetchone={"1": 1})
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.customer_exists("c") is True

    def test_customer_exists_false_when_none(self, monkeypatch):
        conn, _ = make_conn(fetchone=None)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.customer_exists("c") is False

    def test_get_manufacturer_cert_found(self, monkeypatch):
        conn, _ = make_conn(fetchone={"manufacturer_cert": b"cert"})
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_manufacturer_cert("m") == b"cert"
        # conn.close() is in the finally block — must close on the happy path
        assert conn.closed is True

    def test_get_manufacturer_cert_none_raises(self, monkeypatch):
        conn, _ = make_conn(fetchone=None)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        with pytest.raises(ValueError):
            db.get_manufacturer_cert("m")
        # The second (winning) definition closes the connection in a
        # finally block, so it must be closed even on the ValueError path
        assert conn.closed is True

    def test_get_customers_by_firmware(self, monkeypatch):
        executed = []
        rows = [{"customer_id": "c", "bot_token": "b", "chatid": "1"}]
        conn, _ = make_conn(fetchall=rows, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_customers_by_firmware("m", "esp32", "1.0") == rows
        assert executed[0][1] == ("m", "esp32", "1.0")

    def test_get_firmware_metadata_by_customer_id(self, monkeypatch):
        executed = []
        row = {"manufacturer_id": "m", "device_type": "esp32", "firmware_version": "2.0"}
        conn, _ = make_conn(fetchone=row, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_firmware_metadata_by_customer_id("c") == row
        assert executed[0][1] == ("c",)

    def test_get_firmware_metadata_by_customer_id_none(self, monkeypatch):
        conn, _ = make_conn(fetchone=None)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_firmware_metadata_by_customer_id("c") is None

    def test_save_firmware_binary_commits(self, monkeypatch):
        executed = []
        conn, _ = make_conn(rowcount=1, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        db.save_firmware_binary("m", "esp32", "1.0", b"bin")
        assert conn.committed is True
        assert executed[0][1] == (b"bin", "m", "esp32", "1.0")

    def test_get_firmware_signature_metadata(self, monkeypatch):
        executed = []
        row = {"firmware_signature": b"x", "firmware_size": 5}
        conn, _ = make_conn(fetchone=row, executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_firmware_signature_metadata("m", "esp32", "1.0") == dict(row)
        assert executed[0][1] == ("m", "esp32", "1.0")

        conn2, _ = make_conn(fetchone=None)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn2)
        assert db.get_firmware_signature_metadata("m", "esp32", "1.0") is None

    def test_update_device_ip_by_mac_warns_on_no_rows(self, monkeypatch, capsys):
        conn, _ = make_conn(rowcount=0)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        db.update_device_ip_by_mac("unknown:mac", "1.2.3.4")
        out = capsys.readouterr().out
        assert "Unknown device MAC" in out


class TestFirmwareRecordsByCustomer:
    """Tests for get_firmware_records_by_customer_id (new, for the GET API)."""

    def test_returns_list_of_records(self, monkeypatch):
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
        conn, _ = make_conn(fetchall=rows)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        result = db.get_firmware_records_by_customer_id("c1")
        assert result == rows
        assert len(result) == 2
        assert result[0]["object_id"] == "0xabc"
        assert result[0]["manufacturer_name"] == "Acme"

    def test_returns_empty_list_when_no_rows(self, monkeypatch):
        conn, _ = make_conn(fetchall=[])
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        assert db.get_firmware_records_by_customer_id("c1") == []

    def test_params_is_customer_id(self, monkeypatch):
        executed = []
        conn, _ = make_conn(fetchall=[], executed=executed)
        monkeypatch.setattr(db, "get_db_connection", lambda: conn)
        db.get_firmware_records_by_customer_id("the-customer-id")
        assert executed[0][1] == ("the-customer-id",)
