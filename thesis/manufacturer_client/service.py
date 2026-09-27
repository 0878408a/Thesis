from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from manufacturer_client.manufacturer_client import (
        build_upload_payload,
        upload_with_mtls,
        history_with_mtls,
    )
except ModuleNotFoundError:
    module_path = ROOT / "manufacturer_client" / "manufacturer_client.py"

    spec = importlib.util.spec_from_file_location(
        "manufacturer_client_module",
        module_path,
    )

    module = importlib.util.module_from_spec(spec)

    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)

    build_upload_payload = module.build_upload_payload
    upload_with_mtls = module.upload_with_mtls
    history_with_mtls = module.history_with_mtls


app = Flask(__name__)


@app.route("/internal/manufacturer/upload", methods=["POST"])
def upload_firmware_internal():
    firmware_file = request.files.get("firmware_file")
    firmware_version = request.form.get("firmware_version")
    device_type = request.form.get("device_type")

    if firmware_file is None or firmware_file.filename == "":
        return jsonify({"error": "firmware_file is required"}), 400

    if firmware_version is None or firmware_version.strip() == "":
        return jsonify({"error": "firmware_version is required"}), 400

    if device_type is None or device_type.strip() == "":
        return jsonify({"error": "device_type is required"}), 400

    try:
        firmware_bytes = firmware_file.read()

        payload = build_upload_payload(
            firmware_bytes,
            firmware_version,
            device_type,
        )

        upstream_response = upload_with_mtls(payload)

    except Exception:
        return jsonify({"error": "Manufacturer Client internal error"}), 500

    try:
        response_data = upstream_response.json()
    except ValueError:
        response_data = upstream_response.text

    return jsonify(response_data), upstream_response.status_code


@app.route("/internal/manufacturer/history/", methods=["GET"])
def firmware_history_internal():
    """透過 Manufacturer Client 的 mTLS 連線取得 Firmware History。"""

    # 前端傳來的 page 參數直接轉交給 Manufacturer Agent
    page = request.args.get("page", "1")

    try:
        upstream_response = history_with_mtls(page)

    except Exception:
        return jsonify({"error": "Manufacturer Client internal error"}), 500

    try:
        response_data = upstream_response.json()
    except ValueError:
        response_data = upstream_response.text

    return jsonify(response_data), upstream_response.status_code


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5002,
        debug=False,
    )

