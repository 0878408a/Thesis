#!/usr/bin/env bash
# 產生 Nginx 對外入口所需的憑證 alias (學術用 .pem, 非 production secret)。
# 把 conf.d/manufacturer.conf / conf.d/customer.conf 引用的檔名, 對照到 thesis/ 實際的憑證路徑。
# 執行: bash nginx/certs/assemble_certs.sh   (產出在 nginx/certs/alias/)
set -euo pipefail
# 從 repo root 執行以讓 thesis/... 路徑有效; 同時處理從任意目錄呼叫的情況
cd "$(git rev-parse --show-toplevel)" 2>/dev/null || cd "$(dirname "$0")/../.."
A=nginx/certs/alias
mkdir -p "$A"
# --- customer 對外入口 (:443) ---
cp thesis/customer_agent/ecdsa_customer_public_cert.pem  "$A/customer_server_cert.pem"
cp thesis/customer_agent/ecdsa_customer_private_key.pem  "$A/customer_server_key.pem"
# --- manufacturer 對外入口 (:8443 mTLS) ---
# 產生 mTLS server cert (CN=localhost, SAN=DNS:localhost,IP:127.0.0.1) 由 CA 簽發
python -c "
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.x509.oid import NameOID
from cryptography import x509
from datetime import datetime, timedelta
from pathlib import Path
import ipaddress

A = Path('nginx/certs/alias')
CA_CERT = Path('thesis/ca/certs/ecdsa_ca.pem')
CA_KEY = Path('thesis/ca/private/ecdsa_ca.key')

ca_cert = x509.load_pem_x509_certificate(CA_CERT.read_bytes())
ca_key = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)

server_key = ec.generate_private_key(ec.SECP256R1())
(A / 'server_key.pem').write_bytes(server_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption()
))

subject = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, 'TW'),
    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, 'Kaohsiung'),
    x509.NameAttribute(NameOID.LOCALITY_NAME, 'Kaohsiung'),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'ISU'),
    x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, 'CSIE'),
    x509.NameAttribute(NameOID.COMMON_NAME, 'localhost'),
])

now = datetime.utcnow()
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(ca_cert.subject)
    .public_key(server_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(days=1))
    .not_valid_after(now + timedelta(days=3650))
    .add_extension(x509.SubjectAlternativeName([
        x509.DNSName('localhost'),
        x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
    ]), critical=False)
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .add_extension(x509.KeyUsage(
        digital_signature=True,
        content_commitment=False,
        key_encipherment=True,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=False,
        crl_sign=False,
        encipher_only=False,
        decipher_only=False,
    ), critical=True)
    .add_extension(x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    .sign(ca_key, hashes.SHA256())
)
(A / 'server_cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
(A / 'client_ca.pem').write_bytes(CA_CERT.read_bytes())
(A / 'ecdsa_ca.pem').write_bytes(CA_CERT.read_bytes())
print('mTLS server cert generated (CN=localhost)')
"
# 複製 manufacturer client 憑證 (mTLS client 端)
cp thesis/manufacturer_client/ecdsa_manufacturer_client_cert.pem "$A/manufacturer_client_cert.pem"
cp thesis/manufacturer_client/ecdsa_manufacturer_private_key.pem "$A/manufacturer_client_key.pem"
echo "OK: 憑證 alias 已組裝至 $A/"
ls -1 "$A"
