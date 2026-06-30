# Implementation of Secure Firmware Update System for IoT by Using Blockchain

This project implements a secure firmware OTA (Over-the-Air) update system featuring:

* ✅ **Metadata signature verification** (RSA / ECDSA)
* ✅ **mTLS authentication**
* ✅ **DLT firmware metadata storage** (IOTA Move)
* ⚠️ **Optional DID / VC support** (Planned, not yet implemented)

## 📄 Thesis Reference
This project is based on the following research:
🔗 [https://hdl.handle.net/11296/zzwz8z](https://hdl.handle.net/11296/zzwz8z)

---

## 🧩 System Architecture

```text
Manufacturer Client
        │
        │ (mTLS + signed metadata)
        ▼
Manufacturer Agent (Django)
        │
        │ (verify signature)
        ▼
DLT (IOTA Move)
        │
        ▼
Customer Agent
        │
        ▼
Device (ESP32 OTA)
```

---

## 🚀 Features
* **Firmware integrity verification**: Ensures the code hasn't been tampered with.
* **Metadata signature validation**: Confirms the source of the update.
* **Secure upload via mTLS**: Mutual TLS for encrypted and authenticated communication.
* **DLT immutability**: Uses IOTA to ensure firmware metadata cannot be altered.
* **Replay / version protection**: Prevents rolling back to insecure older versions.

---

## ⚙️ Environment Setup

### 1️⃣ Clone Repository
```bash
git clone <your-repo-url>
cd your-project
```

### 2️⃣ Python Environment
```bash
pip install -r requirements.txt
```

### 3️⃣ Node.js (for IOTA interaction)
Install Node.js from [nodejs.org](https://nodejs.org/).
Check version:
```bash
node -v
npm -v
```

### 4️⃣ Install tsx (run TypeScript directly)
```bash
npm install -g tsx
```

### 5️⃣ IOTA Rebased Environment Setup
This project uses **IOTA Rebased** (Move-based chain).

* **Install IOTA SDK dependencies:**
    ```bash
    npm install @iota/iota-sdk @iota/bcs
    ```

* **Configure `.env`:**
    Create `.env` from `.env.example`:
    ```bash
    cp .env.example .env
    ```
    Fill in your credentials:
    ```ini
    IOTA_NETWORK=testnet
    IOTA_PRIVATE_KEY_BASE64=YOUR_PRIVATE_KEY
    PACKAGE_ID=YOUR_MOVE_PACKAGE_ID
    MOVE_MODULE=firmware_module
    MOVE_FUNCTION=publish
    ```

### 6️⃣ Deploy Move Smart Contract
```bash
cd firmware_module/
iota move build
iota move publish
```
After deployment, copy the generated `PACKAGE_ID` into your `.env` file.

### 7️⃣ Database Setup (MySQL)
Create the database:
```sql
CREATE DATABASE mydatabase;
```
Import schemas from:
* `manufacturer_agent_db/`
* `customer_agent_db/`

### 8️⃣ Run Django Server
```bash
python manage.py migrate
python manage.py runserver
```
**With HTTPS (mTLS):**
```bash
python manage.py runserver_plus \
  --cert-file <cert.pem> \
  --key-file <key.pem>
```

---

## 📦 Usage Flow

1.  **Manufacturer Client Upload**
    `python manufacturer_client.py`
    * Signs firmware & metadata.
    * Sends to Manufacturer Agent via mTLS.

2.  **Manufacturer Agent**
    * Validates metadata & verifies signatures.
    * Stores info in DB.
    * Executes `submit_firmware.ts` to upload metadata to IOTA DLT.

3.  **Customer Agent**
    * Queries IOTA DLT.
    * Verifies metadata & downloads firmware.
    * Triggers ESP32 OTA update.

---

## 🔐 Security Design

| Component | Protection |
| :--- | :--- |
| **Firmware** | Signature verification |
| **Metadata** | Signature verification |
| **Transport** | mTLS |
| **Storage** | IOTA DLT immutability |

---

## ⚠️ Optional DID / VC Support (Planned)
🚧 **Status: Not implemented yet (future work)**

### Planned Features:
* DID-based manufacturer identity (stored on-chain).
* VC (Verifiable Credential) for customer authorization.
* Replacement of traditional X.509 trust models.

| Feature | Status |
| :--- | :--- |
| DID Document | ❌ Not implemented |
| VC issuance | ❌ Not implemented |
| DID verification | ❌ Not implemented |

---

## 📁 .env.example

```ini
# --- Manufacturer Configuration ---
IOTA_NETWORK=testnet
IOTA_PRIVATE_KEY_BASE64=YOUR_PRIVATE_KEY
PACKAGE_ID=YOUR_PACKAGE_ID
MOVE_MODULE=firmware_module
MOVE_FUNCTION=publish

DB_ENGINE=django.db.backends.mysql
DB_NAME=mydatabase
DB_USER=root
DB_PASSWORD=your_password
DB_HOST=127.0.0.1
DB_PORT=3306

DJANGO_SECRET_KEY=your_secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# --- Customer Configuration ---
CUSTOMER_DB_NAME=customer_database
```

---

## 📌 Git Notes

* **Should be committed:** `.gitignore`, `.gitattributes`, `.env.example`, source code, Move contracts.
* **Should NOT be committed:** `.env`, `__pycache__/`, `node_modules/`, production private keys.

## 🧪 Experimental Assets
This repository includes test firmware (`.ino`, `.bin`) and self-signed certificates for research and demonstration purposes only.

## 👨‍💻 Author
This project is part of an academic research implementation.
```