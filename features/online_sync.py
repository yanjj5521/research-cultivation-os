from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from db import connect, get_setting, now_iso, set_setting
from services.online_sync import best_effort_sync, cached_value, queue_event, sync_now
from services.economy import balances as local_balances

BASE_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = BASE_DIR / "storage" / "sync_exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _json_setting(key: str, fallback: Any) -> Any:
    try:
        return json.loads(get_setting(key, json.dumps(fallback, ensure_ascii=False)))
    except json.JSONDecodeError:
        return fallback


def _theme() -> dict[str, Any]:
    return {
        "accent": get_setting("ui_accent", "terracotta"),
        "density": get_setting("ui_density", "comfortable"),
        "scene": get_setting("ui_scene", "warm"),
        "home_motto": get_setting("ui_home_motto", "让科研更好玩一点"),
        "site_name": get_setting("site_name", "问道科研"),
        "realm_names": _json_setting("realm_names", []),
        "nav_labels": _json_setting("nav_labels", {}),
        "review_popup": get_setting("review_popup", "1"),
    }


def register_online_routes(app, templates, context: Callable[..., dict[str, Any]], flash: Callable[[Request, str, str], None]):
    router = APIRouter()

    @router.get("/online", response_class=HTMLResponse, name="online_page")
    def online_page(request: Request):
        with connect() as conn:
            queue_stats = dict(conn.execute(
                """SELECT COUNT(*) total,
                   SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) pending,
                   SUM(CASE WHEN status='synced' THEN 1 ELSE 0 END) synced
                   FROM online_sync_queue"""
            ).fetchone())
            recent = [dict(row) for row in conn.execute("SELECT * FROM online_sync_queue ORDER BY id DESC LIMIT 12")]
        return templates.TemplateResponse(
            request=request,
            name="online.html",
            context=context(
                request,
                "online",
                hub_url=get_setting("hub_url", ""),
                hub_token=get_setting("hub_api_token", ""),
                auto_sync=get_setting("hub_auto_sync", "1") == "1",
                theme=_theme(),
                queue_stats=queue_stats,
                recent=recent,
                last_sync=cached_value("last_sync", {}),
                last_error=cached_value("last_sync_error", {}),
                hub_state=cached_value("hub_state", {}),
                latest_release=cached_value("latest_release", None),
                local_version=get_setting("portable_version", "1.2.0"),
            ),
        )

    @router.post("/online/settings", name="online_settings_save")
    def online_settings_save(
        request: Request,
        hub_url: str = Form(""),
        hub_api_token: str = Form(""),
        auto_sync: str = Form(""),
    ):
        url = hub_url.strip().rstrip("/")
        if url and not (url.startswith("http://") or url.startswith("https://")):
            flash(request, "中心地址必须以 http:// 或 https:// 开头。", "error")
            return RedirectResponse(request.url_for("online_page"), status_code=303)
        set_setting("hub_url", url)
        set_setting("hub_api_token", hub_api_token.strip())
        set_setting("hub_auto_sync", "1" if auto_sync == "1" else "0")
        flash(request, "联机设置已保存。")
        return RedirectResponse(request.url_for("online_page"), status_code=303)

    @router.post("/online/connect", name="online_connect")
    def online_connect(request: Request):
        with connect() as conn:
            profile = dict(conn.execute("SELECT * FROM player_profile WHERE id=1").fetchone())
            claim_uuid = get_setting("hub_initial_claim_uuid", "").strip()
            if not claim_uuid:
                import uuid
                claim_uuid = uuid.uuid4().hex
                set_setting("hub_initial_claim_uuid", claim_uuid)
            inventory = [dict(row) for row in conn.execute(
                "SELECT item_key,item_type,quantity,level,equipped FROM inventory_items ORDER BY item_type,item_key"
            )]
            queue_event(conn, "initial_state_claim", {"balances": local_balances(conn), "inventory": inventory}, event_uuid=claim_uuid)
            queue_event(conn, "profile_updated", profile)
            queue_event(conn, "personalization_updated", _theme())
            conn.commit()
        result = sync_now()
        flash(request, result["message"], "success" if result["ok"] else "error")
        return RedirectResponse(request.url_for("online_page"), status_code=303)

    @router.post("/online/sync", name="online_sync_now")
    def online_sync_now(request: Request):
        result = sync_now()
        flash(request, f"{result['message']} 本次确认 {result.get('synced', 0)} 个事件。", "success" if result["ok"] else "error")
        return RedirectResponse(request.url_for("online_page"), status_code=303)

    @router.post("/online/theme", name="online_theme_save")
    def online_theme_save(
        request: Request,
        accent: str = Form("terracotta"), density: str = Form("comfortable"),
        scene: str = Form("warm"), home_motto: str = Form(""),
    ):
        allowed = {
            "accent": {"terracotta", "amber", "sage", "ink"},
            "density": {"comfortable", "compact"},
            "scene": {"warm", "forest", "paper", "night"},
        }
        values = {
            "accent": accent if accent in allowed["accent"] else "terracotta",
            "density": density if density in allowed["density"] else "comfortable",
            "scene": scene if scene in allowed["scene"] else "warm",
            "home_motto": home_motto.strip()[:80] or "让科研更好玩一点",
        }
        set_setting("ui_accent", values["accent"])
        set_setting("ui_density", values["density"])
        set_setting("ui_scene", values["scene"])
        set_setting("ui_home_motto", values["home_motto"])
        with connect() as conn:
            queue_event(conn, "personalization_updated", values)
            conn.commit()
        best_effort_sync()
        flash(request, "个性化方案已保存；新版本可直接导入。")
        return RedirectResponse(request.url_for("online_page"), status_code=303)

    @router.get("/online/personalization/export", name="online_personalization_export")
    def personalization_export():
        with connect() as conn:
            profile = dict(conn.execute("SELECT * FROM player_profile WHERE id=1").fetchone())
        payload = {
            "format": "research-cultivation-personalization-v2",
            "schema_version": 2,
            "exported_at": now_iso(),
            "theme": _theme(),
            "profile": {k: profile[k] for k in ("display_name", "title", "bio", "skills", "capabilities", "goals", "avatar_symbol")},
        }
        path = EXPORT_DIR / f"personalization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return FileResponse(path, filename=path.name, media_type="application/json")

    @router.post("/online/personalization/import", name="online_personalization_import")
    async def personalization_import(request: Request, file: UploadFile = File(...)):
        try:
            data = json.loads((await file.read()).decode("utf-8"))
            if data.get("format") not in {
                "research-cultivation-personalization-v1",
                "research-cultivation-personalization-v2",
            }:
                raise ValueError("不是受支持的个性化包")
            theme = data.get("theme", {})
            profile = data.get("profile", {})
            for source, key, default in [
                ("accent", "ui_accent", "terracotta"), ("density", "ui_density", "comfortable"),
                ("scene", "ui_scene", "warm"), ("home_motto", "ui_home_motto", "让科研更好玩一点"),
            ]:
                set_setting(key, str(theme.get(source, default)))
            if isinstance(theme.get("realm_names"), list):
                set_setting("realm_names", json.dumps(theme["realm_names"], ensure_ascii=False))
            if isinstance(theme.get("nav_labels"), dict):
                set_setting("nav_labels", json.dumps(theme["nav_labels"], ensure_ascii=False))
            if str(theme.get("site_name", "")).strip():
                set_setting("site_name", str(theme["site_name"]).strip()[:60])
            if str(theme.get("review_popup", "1")) in {"0", "1"}:
                set_setting("review_popup", str(theme.get("review_popup", "1")))
            with connect() as conn:
                conn.execute(
                    """UPDATE player_profile SET display_name=?,title=?,bio=?,skills=?,capabilities=?,goals=?,avatar_symbol=?,updated_at=? WHERE id=1""",
                    (
                        str(profile.get("display_name", "准研一修士")), str(profile.get("title", "")),
                        str(profile.get("bio", "")), str(profile.get("skills", "")),
                        str(profile.get("capabilities", "")), str(profile.get("goals", "")),
                        str(profile.get("avatar_symbol", "道"))[:2] or "道", now_iso(),
                    ),
                )
                queue_event(conn, "profile_updated", profile)
                queue_event(conn, "personalization_updated", theme)
                conn.commit()
            flash(request, "个性化包已导入。")
        except Exception as exc:
            flash(request, f"导入失败：{exc}", "error")
        return RedirectResponse(request.url_for("online_page"), status_code=303)

    app.include_router(router)
