"""Shared pytest fixtures for Customer Agent Backend tests.

This makes the top-level Customer Agent modules (webhook, db, query, verify,
telegram_notify, apply, run_customer_agent, config) importable by name, matching
how production code imports them (e.g. ``from db import ...``).

All external dependencies (MariaDB, IOTA, Telegram, ESP32, serial, real mTLS
connections) are isolated via mock / monkeypatch in the individual test files.
"""

import sys
from pathlib import Path

# Ensure the Customer Agent root (thesis/customer_agent) is importable.
_AGENT_ROOT = str(Path(__file__).resolve().parent.parent)
if _AGENT_ROOT not in sys.path:
    sys.path.insert(0, _AGENT_ROOT)


def pytest_configure(config):
    # No-op hook; sys.path setup is done at module import time above.
    pass
