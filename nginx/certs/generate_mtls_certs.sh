#!/usr/bin/env bash
# 從 thesis/ca/ 的 ECDSA CA 產生 mTLS server cert + key (CN=localhost, SAN=localhost)
# 供 nginx/certs/alias/server_cert.pem + server_key.pem 使用。
# 執行: bash nginx/certs/generate_mtls_certs.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)" 2>/dev/null || cd "$(dirname "$0")/../.."

A=nginx/certs/alias
CA_CERT=thesis/ca/certs/ecdsa_ca.pem
CA_KEY=thesis/ca/private/ecdsa_ca.key

mkdir -p "$A"

echo "Generating mTLS server cert (CN=localhost, SAN=DNS:localhost,IP:127.0.0.1)..."

# 產生 server key (ECDSA P-256)
openssl ecparam -genkey -name prime256v1 -noout -out "$A/server_key.pem" 2>/dev/null

# 產生 CSR
openssl req -new -key "$A/server_key.pem" \
  -subj "/C=TW/ST=Kaohsiung/L=Kaohsiung/O=ISU/OU=CSIE/CN=localhost" \
  -out "$A/server.csr" 2>/dev/null

# 用 CA 簽發, 加入 SAN
openssl x509 -req -in "$A/server.csr" \
  -CA "$CA_CERT" -CAkey "$CA_KEY" -CAcreateserial \
  -days 3650 -out "$A/server_cert.pem" 2>/dev/null \
  -extfile <(printf "subjectAltName=DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n")

# client_ca.pem = 同一支 CA cert (驗收 manufacturer client 憑證用)
cp "$CA_CERT" "$A/client_ca.pem"

# 清理 CSR
rm -f "$A/server.csr" "$CA_CERT.srl"

echo "OK: mTLS server cert + key + client_ca 已產出至 $A/"
openssl x509 -in "$A/server_cert.pem" -noout -subject -ext subjectAltName
echo "---"
openssl verify -CAfile "$CA_CERT" "$A/server_cert.pem"
