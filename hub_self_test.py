from __future__ import annotations

from fastapi.testclient import TestClient

import hub_app
from hub_db import connect_hub, get_hub_setting, init_hub_db


def main() -> None:
    init_hub_db()
    client = TestClient(hub_app.app)
    failures: list[str] = []
    for path in ("/health", "/api/v1/ping", "/register"):
        response = client.get(path)
        if response.status_code != 200:
            failures.append(f"{path}: HTTP {response.status_code}")
    with connect_hub() as conn:
        required = {
            "hub_users", "hub_profiles", "hub_asset_transactions", "hub_inventory",
            "hub_sync_events", "hub_invites", "hub_releases", "hub_resource_cards", "hub_audit_log",
        }
        found = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(required - found)
        if missing:
            failures.append("missing tables: " + ", ".join(missing))
        if conn.execute("SELECT COUNT(*) n FROM hub_users WHERE role='admin'").fetchone()["n"] != 1:
            failures.append("admin account not initialized")
        if get_hub_setting(conn, "version") != "1.5.0":
            failures.append("hub version was not migrated to 1.5.0")
    if failures:
        print("HUB SELF TEST FAILED")
        for item in failures:
            print("-", item)
        raise SystemExit(1)
    print("HUB SELF TEST PASS")
    print("Health endpoint, registration page and central tables are ready.")


if __name__ == "__main__":
    main()
