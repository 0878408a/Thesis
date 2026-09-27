"""Signature verification tests using ephemeral (in-memory) certs.

No real .pem files are read; certificates and keys are generated at runtime
with ``cryptography``.
"""

import base64
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from datetime import datetime, timedelta
import uuid

import verify


def _make_ecdsa():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


def _make_rsa():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _cert_for_public(public_key):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=1))
        .sign(_SIGNER, hashes.SHA256())
    )
    return cert


# A single self-signed key used to issue test certs. We only read the subject
# public key out of each cert, so any valid issuing key works.
_SIGNER = ec.generate_private_key(ec.SECP256R1())


# ---------------------------------------------------------------------------
# verify_signature (metadata_signature)
# ---------------------------------------------------------------------------

class TestVerifySignatureMetadata:
    def test_ecdsa_correct(self):
        priv, pub = _make_ecdsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)

        metadata = {
            "firmware_size": 123,
            "release_date": "20240101",
            "manufacturer_id": "m1",
            "device_type": "esp32",
            "firmware_version": "1.0",
            "metadata_signature_algorithm": "ecdsa",
        }
        raw = f"{metadata['firmware_size']}{metadata['release_date']}{metadata['manufacturer_id']}{metadata['device_type']}{metadata['firmware_version']}".encode()
        sig = priv.sign(raw, ec.ECDSA(hashes.SHA256()))
        assert verify.verify_signature(metadata, cert_pem, "metadata_signature", sig) is True

    def test_ecdsa_wrong_sig(self):
        priv, pub = _make_ecdsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        metadata = {
            "firmware_size": 1, "release_date": "20240101",
            "manufacturer_id": "m1", "device_type": "esp32",
            "firmware_version": "1.0", "metadata_signature_algorithm": "ecdsa",
        }
        assert verify.verify_signature(metadata, cert_pem, "metadata_signature", b"junk") is False

    def test_unsupported_algorithm(self):
        priv, pub = _make_ecdsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        metadata = {
            "firmware_size": 1, "release_date": "20240101",
            "manufacturer_id": "m1", "device_type": "esp32",
            "firmware_version": "1.0", "metadata_signature_algorithm": "md5",
        }
        assert verify.verify_signature(metadata, cert_pem, "metadata_signature", b"x") is False

    def test_unsupported_field(self):
        priv, pub = _make_ecdsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        metadata = {"metadata_signature_algorithm": "ecdsa"}
        assert verify.verify_signature(metadata, cert_pem, "bogus_field", b"x") is False

    def test_rsa_correct(self):
        priv, pub = _make_rsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        metadata = {
            "firmware_size": 1, "release_date": "20240101",
            "manufacturer_id": "m1", "device_type": "esp32",
            "firmware_version": "1.0", "metadata_signature_algorithm": "rsa",
        }
        raw = b"120240101m1esp321.0"
        sig = priv.sign(raw, padding.PKCS1v15(), hashes.SHA256())
        assert verify.verify_signature(metadata, cert_pem, "metadata_signature", sig) is True


# ---------------------------------------------------------------------------
# verify_response_signature
# ---------------------------------------------------------------------------

class TestVerifyResponseSignature:
    def test_ecdsa_correct(self):
        priv, pub = _make_ecdsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        raw_payload = "1|https://x|msg|".encode()
        sig = base64.b64encode(priv.sign(raw_payload, ec.ECDSA(hashes.SHA256())))
        assert verify.verify_response_signature("https://x", "msg", sig, cert_pem, "ecdsa") is True

    def test_ecdsa_wrong(self):
        priv, pub = _make_ecdsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        sig = base64.b64encode(b"garbage")
        assert verify.verify_response_signature("https://x", "msg", sig, cert_pem, "ecdsa") is False

    def test_unsupported_algo(self):
        priv, pub = _make_ecdsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        sig = base64.b64encode(b"junk")
        assert verify.verify_response_signature("https://x", "msg", sig, cert_pem, "md5") is False

    def test_optional_params_included_in_payload(self):
        """error_code + upload_result must be folded into the signed payload:
        raw = f"{upload_result}|{url}|{message}|{error_code}".encode()
        (production uses str(error_code); None → empty string)."""
        priv, pub = _make_ecdsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        raw_payload = "0|https://x|msg|500".encode()
        sig = base64.b64encode(priv.sign(raw_payload, ec.ECDSA(hashes.SHA256())))
        assert verify.verify_response_signature(
            "https://x", "msg", sig, cert_pem, "ecdsa",
            error_code=500, upload_result=0,
        ) is True

    def test_wrong_optional_params_rejects_valid_signature(self):
        """A signature made over error_code=500/upload_result=0 must FAIL
        when the verifier is called with the default parameters — proves the
        optional values are actually part of the payload, not ignored."""
        priv, pub = _make_ecdsa()
        cert = _cert_for_public(pub)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        raw_payload = "0|https://x|msg|500".encode()
        sig = base64.b64encode(priv.sign(raw_payload, ec.ECDSA(hashes.SHA256())))
        # Defaults: upload_result=1, error_code=None → "1|https://x|msg|"
        assert verify.verify_response_signature(
            "https://x", "msg", sig, cert_pem, "ecdsa",
        ) is False
