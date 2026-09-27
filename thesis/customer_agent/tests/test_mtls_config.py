"""mTLS / cert context tests — build ssl contexts from ephemeral certs.

No ports are bound and no real TLS connections are made; we only verify that
the context builders load the intended cert/key files and set the correct
verify_mode.
"""

import ssl
import socket
import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from datetime import datetime, timedelta

import run_customer_agent as rca


def _gen_key():
    return ec.generate_private_key(ec.SECP256R1())


def _make_cert(ca_key, ca_name, subject_key, subject_cn, is_ca=False):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_name)
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=2))
    )
    if is_ca:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
    return builder.sign(ca_key, hashes.SHA256())


def _write(path, data):
    path.write_bytes(data)
    return path


@pytest.fixture
def cert_bundle(tmp_path, monkeypatch):
    """Generate a throwaway CA + server key/cert and point rca at them."""
    ca_key = _gen_key()
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
    ca_cert = _make_cert(ca_key, ca_name, ca_key, "test-ca", is_ca=True)

    server_key = _gen_key()
    server_cert = _make_cert(ca_key, ca_name, server_key, "test-server")

    def pem(cert_or_key, is_key, key_obj=None):
        if is_key:
            return key_obj.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        return cert_or_key.public_bytes(serialization.Encoding.PEM)

    ca_pem = _write(tmp_path / "ca.pem", pem(ca_cert, False))
    cert_pem = _write(tmp_path / "server.pem", pem(server_cert, False))
    key_pem = _write(tmp_path / "server.key", pem(None, True, server_key))
    mfr_pem = _write(tmp_path / "mfr.pem", pem(server_cert, False))

    monkeypatch.setattr(rca, "CUSTOMER_CERT_PATH", cert_pem)
    monkeypatch.setattr(rca, "CUSTOMER_KEY_PATH", key_pem)
    monkeypatch.setattr(rca, "CA_CERT_PATH", ca_pem)
    monkeypatch.setattr(rca, "MANUFACTURER_CERT_PATH", mfr_pem)
    return {"ca": ca_pem, "cert": cert_pem, "key": key_pem, "mfr": mfr_pem}


class TestCreatePublicContext:
    def test_returns_ssl_context(self, cert_bundle):
        ctx = rca.create_public_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_loads_customer_cert_and_key_once(self, cert_bundle, monkeypatch):
        """create_public_context must load exactly the customer cert/key pair
        configured on the module, and exactly once."""
        calls = []
        orig_load = ssl.SSLContext.load_cert_chain
        def spy_load(self_ctx, certfile, keyfile=None, *a, **k):
            calls.append((str(certfile), str(keyfile)))
            return orig_load(self_ctx, certfile, keyfile, *a, **k)
        monkeypatch.setattr(ssl.SSLContext, "load_cert_chain", spy_load)
        rca.create_public_context()
        assert calls == [
            (str(cert_bundle["cert"]), str(cert_bundle["key"]))
        ]

    def test_missing_key_raises(self, cert_bundle, tmp_path, monkeypatch):
        monkeypatch.setattr(rca, "CUSTOMER_KEY_PATH", tmp_path / "does_not_exist.key")
        with pytest.raises(Exception):
            rca.create_public_context()


class TestCreateMtlsContext:
    def test_verify_mode_is_cert_required(self, cert_bundle):
        """create_mtls_context must enforce mutual auth — the peer cert is
        required, not optional."""
        ctx = rca.create_mtls_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_loads_customer_cert_key_and_trust_stores(self, cert_bundle, monkeypatch):
        """The mTLS context must load the customer cert/key AND add both
        trust anchors (CA cert + manufacturer cert) to its verification store."""
        cert_chain_calls = []
        verify_locations = []
        orig_load = ssl.SSLContext.load_cert_chain
        orig_locations = ssl.SSLContext.load_verify_locations
        def spy_load(self_ctx, certfile, keyfile=None, *a, **k):
            cert_chain_calls.append((str(certfile), str(keyfile)))
            return orig_load(self_ctx, certfile, keyfile, *a, **k)
        def spy_locations(self_ctx, *a, **k):
            verify_locations.append((a, k))
            return orig_locations(self_ctx, *a, **k)
        monkeypatch.setattr(ssl.SSLContext, "load_cert_chain", spy_load)
        monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", spy_locations)
        ctx = rca.create_mtls_context()

        # 1) customer cert + key loaded
        assert cert_chain_calls == [
            (str(cert_bundle["cert"]), str(cert_bundle["key"]))
        ]
        # 2) trust store: at least two CA load locations (CA cert + mfr cert)
        #    load_verify_locations is called with the CA cert and mfr cert.
        all_paths = []
        for args, kwargs in verify_locations:
            for p in args:
                all_paths.append(str(p))
        assert str(cert_bundle["ca"]) in all_paths
        assert str(cert_bundle["mfr"]) in all_paths
        # 3) mutual auth enforced
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_missing_ca_raises(self, cert_bundle, tmp_path, monkeypatch):
        monkeypatch.setattr(rca, "CA_CERT_PATH", tmp_path / "missing_ca.pem")
        with pytest.raises(Exception):
            rca.create_mtls_context()
