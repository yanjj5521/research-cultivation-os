from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.request
from typing import Any

from db import connect, get_setting, now_iso, set_setting
from services.economy import balances as local_balances
from services.game_world import ARTIFACTS, BUILDINGS


def queue_event(conn, event_type: str, payload: dict[str, Any] | None = None, event_uuid: str | None = None) -> str:
    event_uuid = event_uuid or uuid.uuid4().hex
    conn.execute(
        """INSERT OR IGNORE INTO online_sync_queue(event_uuid,event_type,payload_json,status,created_at)
           VALUES (?,?,?,'pending',?)""",
        (event_uuid, event_type, json.dumps(payload or {}, ensure_ascii=False), now_iso()),
    )
    return event_uuid


def online_configured() -> bool:
    return bool(get_setting("hub_url", "").strip() and get_setting("hub_api_token", "").strip())


def _request_json(method: str, url: str, token: str, body: dict[str, Any] | None = None, timeout: float = 5.0) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "ResearchCultivationOS/1.3"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _cache(conn, key: str, value: Any) -> None:
    conn.execute(
        """INSERT INTO online_sync_cache(key,value,updated_at) VALUES (?,?,?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
        (key, json.dumps(value, ensure_ascii=False), now_iso()),
    )


def apply_state(conn, state: dict[str, Any]) -> None:
    central_balances = state.get("balances") if isinstance(state.get("balances"), dict) else {}
    current = local_balances(conn)
    for key in ("spirit_stone", "spirit_wood", "mystic_iron", "star_sand"):
        target = int(central_balances.get(key, current.get(key, 0)) or 0)
        difference = target - int(current.get(key, 0))
        if difference:
            conn.execute(
                "INSERT INTO asset_transactions(asset_key,amount,reason,created_at) VALUES (?,?,?,?)",
                (key, difference, "联机中心校准", now_iso()),
            )

    central_items = state.get("inventory") if isinstance(state.get("inventory"), list) else []
    central_keys = {str(item.get("item_key", "")) for item in central_items if item.get("item_key")}
    managed_keys = set(ARTIFACTS) | set(BUILDINGS)
    for key in managed_keys - central_keys:
        conn.execute("DELETE FROM inventory_items WHERE item_key=?", (key,))
    for item in central_items:
        key = str(item.get("item_key", ""))
        if not key:
            continue
        conn.execute(
            """INSERT INTO inventory_items(item_key,item_type,quantity,level,equipped,acquired_at,updated_at)
               VALUES (?,?,?,?,?,?,?) ON CONFLICT(item_key) DO UPDATE SET
               item_type=excluded.item_type,quantity=excluded.quantity,level=excluded.level,
               equipped=excluded.equipped,updated_at=excluded.updated_at""",
            (
                key, str(item.get("item_type", "artifact")), int(item.get("quantity", 1)),
                int(item.get("level", 1)), int(item.get("equipped", 0)), now_iso(), now_iso(),
            ),
        )

    user = state.get("user") if isinstance(state.get("user"), dict) else {}
    profile = state.get("profile") if isinstance(state.get("profile"), dict) else {}
    if user or profile:
        conn.execute(
            """UPDATE player_profile SET display_name=?,title=?,bio=?,skills=?,capabilities=?,goals=?,avatar_symbol=?,updated_at=? WHERE id=1""",
            (
                str(user.get("display_name", "准研一修士")), str(profile.get("title", "")),
                str(profile.get("bio", "")), str(profile.get("skills", "")),
                str(profile.get("capabilities", "")), str(profile.get("goals", "")),
                str(profile.get("avatar_symbol", "道"))[:2] or "道", now_iso(),
            ),
        )
        conn.execute(
            "INSERT INTO settings(key,value) VALUES ('researcher_name',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(user.get("display_name", "准研一修士")),),
        )

    theme = state.get("theme") if isinstance(state.get("theme"), dict) else {}
    mapping = {
        "accent": "ui_accent",
        "density": "ui_density",
        "scene": "ui_scene",
        "home_motto": "ui_home_motto",
        "home_poem": "ui_home_poem",
        "site_name": "site_name",
        "review_popup": "review_popup",
    }
    for source, setting_key in mapping.items():
        if source in theme:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (setting_key, str(theme[source])),
            )
    if isinstance(theme.get("realm_names"), list):
        conn.execute(
            "INSERT INTO settings(key,value) VALUES ('realm_names',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps(theme["realm_names"], ensure_ascii=False),),
        )
    if isinstance(theme.get("nav_labels"), dict):
        conn.execute(
            "INSERT INTO settings(key,value) VALUES ('nav_labels',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps(theme["nav_labels"], ensure_ascii=False),),
        )
    _cache(conn, "hub_state", state)
    if state.get("latest_release") is not None:
        _cache(conn, "latest_release", state.get("latest_release"))


def sync_now(timeout: float = 5.0) -> dict[str, Any]:
    hub_url = get_setting("hub_url", "").strip().rstrip("/")
    token = get_setting("hub_api_token", "").strip()
    if not hub_url or not token:
        return {"ok": False, "message": "尚未配置联机中心。", "synced": 0}
    with connect() as conn:
        pending = [dict(row) for row in conn.execute(
            "SELECT * FROM online_sync_queue WHERE status!='synced' ORDER BY id LIMIT 100"
        )]
    events = []
    for row in pending:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        events.append({"event_uuid": row["event_uuid"], "event_type": row["event_type"], "payload": payload})
    try:
        if events:
            response = _request_json("POST", f"{hub_url}/api/v1/events", token, {"events": events}, timeout=timeout)
            results = response.get("results", [])
            state = response.get("state", {})
        else:
            state = _request_json("GET", f"{hub_url}/api/v1/bootstrap", token, timeout=timeout)
            results = []
        accepted = {r.get("event_uuid") for r in results if r.get("status") in {"applied", "duplicate"}}
        with connect() as conn:
            for row in pending:
                if row["event_uuid"] in accepted:
                    conn.execute("UPDATE online_sync_queue SET status='synced',attempts=attempts+1,last_error='',synced_at=? WHERE id=?", (now_iso(), row["id"]))
                else:
                    conn.execute("UPDATE online_sync_queue SET attempts=attempts+1,last_error=? WHERE id=?", ("中心未确认该事件", row["id"]))
            apply_state(conn, state)
            _cache(conn, "last_sync", {"at": now_iso(), "results": results})
            conn.commit()
        return {"ok": True, "message": "联机状态已同步。", "synced": len(accepted), "state": state, "results": results}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        message = f"中心返回 HTTP {exc.code}: {detail}"
    except Exception as exc:
        message = f"暂时无法连接联机中心：{exc}"
    with connect() as conn:
        for row in pending:
            conn.execute("UPDATE online_sync_queue SET attempts=attempts+1,last_error=? WHERE id=?", (message[:500], row["id"]))
        _cache(conn, "last_sync_error", {"at": now_iso(), "message": message})
        conn.commit()
    return {"ok": False, "message": message, "synced": 0}


def best_effort_sync() -> None:
    if get_setting("hub_auto_sync", "1") != "1" or not online_configured():
        return
    try:
        sync_now(timeout=2.5)
    except Exception:
        pass


def cached_value(key: str, default: Any = None) -> Any:
    with connect() as conn:
        row = conn.execute("SELECT value FROM online_sync_cache WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return default
