from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from db import normalize_nav_labels
from hub_db import (
    HUB_ADMIN_PATH,
    HUB_BACKUP_DIR,
    HUB_DB_PATH,
    HUB_RELEASE_DIR,
    backup_hub_db,
    balances,
    connect_hub,
    create_user,
    get_hub_setting,
    get_user_by_token,
    hub_secret,
    hub_transaction,
    init_hub_db,
    now_iso,
    set_password,
    transact_asset,
    verify_password,
)
from services.game_world import ARTIFACTS, BUILDINGS
from services.progression import normalize_realm_labels

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "hub_templates"
STATIC_DIR = BASE_DIR / "hub_static"
VERSION = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip() if (BASE_DIR / "VERSION").exists() else "2.0.2"

app = FastAPI(title="问道科研同行会", docs_url=None, redoc_url=None)
HUB_HTTPS_ONLY = os.getenv("HUB_HTTPS_ONLY", "0").strip() == "1"
HUB_TRUST_PROXY = os.getenv("HUB_TRUST_PROXY", "0").strip() == "1"
app.add_middleware(SessionMiddleware, secret_key=hub_secret(), same_site="lax", https_only=HUB_HTTPS_ONLY)
_allowed_hosts = [x.strip() for x in os.getenv("HUB_ALLOWED_HOSTS", "").split(",") if x.strip()]
if _allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

_LOGIN_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    if request.url.path.startswith("/api/") or request.url.path in {"/login", "/register", "/me"}:
        response.headers["Cache-Control"] = "no-store"
    return response


def client_ip(request: Request) -> str:
    if HUB_TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def login_allowed(ip: str) -> bool:
    now = time.time()
    queue = _LOGIN_ATTEMPTS[ip]
    while queue and now - queue[0] > 600:
        queue.popleft()
    return len(queue) < 8


def record_login_failure(ip: str) -> None:
    _LOGIN_ATTEMPTS[ip].append(time.time())


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["csrf"] = token
    return token


def verify_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf", "")
    if not expected or not secrets.compare_digest(expected, token or ""):
        raise HTTPException(status_code=403, detail="请求校验失败，请刷新页面重试。")


def flash(request: Request, message: str, category: str = "success") -> None:
    request.session.setdefault("flashes", []).append({"message": message, "category": category})


def current_user(request: Request) -> dict[str, Any] | None:
    user_id = request.session.get("hub_user_id")
    if not user_id:
        return None
    with connect_hub() as conn:
        row = conn.execute("SELECT * FROM hub_users WHERE id=? AND active=1", (int(user_id),)).fetchone()
        return dict(row) if row else None


def require_user(request: Request, admin: bool = False) -> dict[str, Any]:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    if admin and user["role"] != "admin":
        raise HTTPException(status_code=403)
    return user


def hub_context(request: Request, active: str, **extra: Any) -> dict[str, Any]:
    user = current_user(request)
    base = {
        "request": request,
        "user": user,
        "active": active,
        "csrf": csrf_token(request),
        "flashes": request.session.pop("flashes", []),
        "version": VERSION,
        "site_name": "问道科研 · 同行会",
    }
    if user:
        with connect_hub() as conn:
            base["nav_balances"] = balances(conn, int(user["id"]))
    base.update(extra)
    return base


def api_user(request: Request) -> dict[str, Any]:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少API Token")
    token = auth.split(" ", 1)[1].strip()
    with connect_hub() as conn:
        row = get_user_by_token(conn, token)
        if not row:
            raise HTTPException(status_code=401, detail="API Token无效")
        conn.execute("UPDATE hub_users SET last_seen_at=?,updated_at=? WHERE id=?", (now_iso(), now_iso(), row["id"]))
        conn.commit()
        return dict(row)


def profile_payload(conn, user_id: int) -> dict[str, Any]:
    user = dict(conn.execute("SELECT id,username,display_name,role,updated_at,last_seen_at FROM hub_users WHERE id=?", (user_id,)).fetchone())
    profile = dict(conn.execute("SELECT * FROM hub_profiles WHERE user_id=?", (user_id,)).fetchone())
    try:
        theme = json.loads(profile.pop("theme_json") or "{}")
    except json.JSONDecodeError:
        theme = {}
    inventory = [dict(row) for row in conn.execute("SELECT item_key,item_type,quantity,level,equipped,updated_at FROM hub_inventory WHERE user_id=? ORDER BY item_type,item_key", (user_id,))]
    latest = conn.execute("SELECT version,title,notes,file_size,sha256,created_at FROM hub_releases WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "user": user,
        "profile": profile,
        "theme": theme,
        "balances": balances(conn, user_id),
        "inventory": inventory,
        "latest_release": dict(latest) if latest else None,
        "hub_version": VERSION,
    }


def audit(conn, user_id: int | None, action: str, detail: str, request: Request | None = None) -> None:
    conn.execute(
        "INSERT INTO hub_audit_log(user_id,action,detail,ip,created_at) VALUES (?,?,?,?,?)",
        (user_id, action, detail[:500], client_ip(request) if request else "", now_iso()),
    )


def parse_theme(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            data = {}
    else:
        data = value or {}
    allowed = {
        "accent": {"terracotta", "amber", "sage", "ink"},
        "density": {"comfortable", "compact"},
        "scene": {"warm", "forest", "paper", "night"},
    }
    result = {
        "accent": data.get("accent", "terracotta"),
        "density": data.get("density", "comfortable"),
        "scene": data.get("scene", "warm"),
        "home_motto": str(data.get("home_motto", "让科研更好玩一点"))[:80],
        "home_poem": str(data.get("home_poem", "纸上得来终觉浅，绝知此事要躬行。——陆游"))[:120],
        "site_name": str(data.get("site_name", "问道科研"))[:60],
        "review_popup": "1" if str(data.get("review_popup", "1")) == "1" else "0",
    }
    result["realm_names"] = normalize_realm_labels(data.get("realm_names", {}))
    nav_labels = data.get("nav_labels", {})
    result["nav_labels"] = normalize_nav_labels(nav_labels)
    for key, values in allowed.items():
        if result[key] not in values:
            result[key] = next(iter(values))
    return result


def apply_event(conn, user_id: int, event: dict[str, Any]) -> dict[str, Any]:
    event_uuid = str(event.get("event_uuid", ""))[:80]
    event_type = str(event.get("event_type", ""))[:60]
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if not event_uuid or not event_type:
        return {"event_uuid": event_uuid, "status": "rejected", "message": "缺少事件编号或类型"}
    existing = conn.execute("SELECT result_json FROM hub_sync_events WHERE event_uuid=?", (event_uuid,)).fetchone()
    if existing:
        try:
            result = json.loads(existing["result_json"] or "{}")
        except json.JSONDecodeError:
            result = {}
        return {"event_uuid": event_uuid, "status": "duplicate", **result}

    result: dict[str, Any] = {"message": "已记录", "rewards": {}}
    rewarded = 0
    today = datetime.now().astimezone().date().isoformat()
    if event_type == "initial_state_claim":
        prior = conn.execute(
            "SELECT COUNT(*) n FROM hub_sync_events WHERE user_id=? AND event_type='initial_state_claim' AND rewarded=1",
            (user_id,),
        ).fetchone()["n"]
        if prior:
            result = {"message": "初始状态已经迁移过", "rewards": {}}
        else:
            requested_balances = payload.get("balances") if isinstance(payload.get("balances"), dict) else {}
            limits = {"spirit_stone": 100000, "spirit_wood": 10000, "mystic_iron": 10000, "star_sand": 10000}
            current_balances = balances(conn, user_id)
            for key, upper in limits.items():
                target = max(0, min(int(requested_balances.get(key, current_balances.get(key, 0)) or 0), upper))
                delta = target - int(current_balances.get(key, 0))
                if delta:
                    transact_asset(conn, user_id, key, delta, "首次联机迁移", event_uuid)
            requested_inventory = payload.get("inventory") if isinstance(payload.get("inventory"), list) else []
            allowed_items = set(ARTIFACTS) | set(BUILDINGS)
            for raw in requested_inventory[:100]:
                if not isinstance(raw, dict):
                    continue
                key = str(raw.get("item_key", ""))
                if key not in allowed_items:
                    continue
                item_type = "artifact" if key in ARTIFACTS else "building"
                conn.execute(
                    """INSERT INTO hub_inventory(user_id,item_key,item_type,quantity,level,equipped,updated_at)
                       VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id,item_key) DO UPDATE SET
                       quantity=MAX(hub_inventory.quantity,excluded.quantity),
                       level=MAX(hub_inventory.level,excluded.level),
                       equipped=excluded.equipped,updated_at=excluded.updated_at""",
                    (user_id,key,item_type,max(1,min(int(raw.get("quantity",1) or 1),99)),max(1,min(int(raw.get("level",1) or 1),99)),int(bool(raw.get("equipped",0))),now_iso()),
                )
            result = {"message": "本地初始资产已迁移", "rewards": {}}
            rewarded = 1
    elif event_type == "mission_completed":
        rewarded_today = conn.execute(
            """SELECT COUNT(*) n FROM hub_sync_events
               WHERE user_id=? AND event_type='mission_completed' AND rewarded=1 AND substr(created_at,1,10)=?""",
            (user_id, today),
        ).fetchone()["n"]
        if rewarded_today < 4:
            requested = payload.get("rewards") if isinstance(payload.get("rewards"), dict) else {}
            stone_amount = max(1, min(int(requested.get("spirit_stone", 8) or 8), 40))
            reward_asset = next((key for key in ("spirit_wood", "mystic_iron", "star_sand") if int(requested.get(key, 0) or 0) > 0), "spirit_wood")
            material_amount = max(1, min(int(requested.get(reward_asset, 1) or 1), 3))
            transact_asset(conn, user_id, "spirit_stone", stone_amount, "联机任务交付", event_uuid)
            transact_asset(conn, user_id, reward_asset, material_amount, "联机任务交付", event_uuid)
            result = {"message": "交付已同步", "rewards": {"spirit_stone": stone_amount, reward_asset: material_amount}}
            rewarded = 1
        else:
            result = {"message": "已记录；今日联机奖励达到4次上限", "rewards": {}}
    elif event_type == "day_cleared":
        transact_asset(conn, user_id, "spirit_stone", 5, "联机通关奖励", event_uuid)
        result = {"message": "通关已同步", "rewards": {"spirit_stone": 5}}
        rewarded = 1
    elif event_type == "mission_postponed":
        try:
            transact_asset(conn, user_id, "spirit_stone", -2, "联机任务推迟", event_uuid)
            result = {"message": "推迟已同步", "rewards": {"spirit_stone": -2}}
            rewarded = 1
        except ValueError:
            result = {"message": "联机灵石不足，中心未扣款", "rewards": {}}
    elif event_type == "profile_updated":
        display_name = str(payload.get("display_name", ""))[:40].strip()
        if display_name:
            conn.execute("UPDATE hub_users SET display_name=?,updated_at=? WHERE id=?", (display_name, now_iso(), user_id))
        conn.execute(
            """UPDATE hub_profiles SET title=?,bio=?,skills=?,capabilities=?,goals=?,avatar_symbol=?,revision=revision+1,updated_at=? WHERE user_id=?""",
            (
                str(payload.get("title", ""))[:100], str(payload.get("bio", ""))[:1000],
                str(payload.get("skills", ""))[:2000], str(payload.get("capabilities", ""))[:3000],
                str(payload.get("goals", ""))[:1500], str(payload.get("avatar_symbol", "道"))[:2] or "道",
                now_iso(), user_id,
            ),
        )
        result = {"message": "个人信息已同步", "rewards": {}}
    elif event_type == "personalization_updated":
        theme = parse_theme(payload)
        conn.execute("UPDATE hub_profiles SET theme_json=?,revision=revision+1,updated_at=? WHERE user_id=?", (json.dumps(theme, ensure_ascii=False), now_iso(), user_id))
        result = {"message": "个性化配置已同步", "rewards": {}}
    elif event_type in {"artifact_buy", "artifact_upgrade", "artifact_equip", "building_upgrade"}:
        item_key = str(payload.get("item_key", ""))
        if event_type.startswith("artifact"):
            spec = ARTIFACTS.get(item_key)
            item_type = "artifact"
        else:
            spec = BUILDINGS.get(item_key)
            item_type = "building"
        if not spec:
            result = {"message": "未知物品，未同步", "rewards": {}}
        else:
            row = conn.execute("SELECT * FROM hub_inventory WHERE user_id=? AND item_key=?", (user_id, item_key)).fetchone()
            if event_type == "artifact_buy":
                if row:
                    result = {"message": "已拥有该法器", "rewards": {}}
                else:
                    try:
                        transact_asset(conn, user_id, "spirit_stone", -int(spec["price"]), f"购入{spec['name']}", event_uuid)
                        conn.execute("INSERT INTO hub_inventory(user_id,item_key,item_type,quantity,level,equipped,updated_at) VALUES (?,?,?,1,1,0,?)", (user_id,item_key,item_type,now_iso()))
                        result = {"message": "法器已同步", "rewards": {"spirit_stone": -int(spec["price"])}}
                        rewarded = 1
                    except ValueError:
                        result = {"message": "联机灵石不足，购买未同步", "rewards": {}}
            elif event_type == "artifact_upgrade":
                if not row:
                    result = {"message": "中心尚无该法器", "rewards": {}}
                else:
                    level = int(row["level"])
                    cost = max(10, (int(spec["price"]) // 2) * max(level, 1))
                    try:
                        transact_asset(conn, user_id, "spirit_stone", -cost, f"淬炼{spec['name']}", event_uuid)
                        conn.execute("UPDATE hub_inventory SET level=level+1,updated_at=? WHERE user_id=? AND item_key=?", (now_iso(),user_id,item_key))
                        result = {"message": "法器等级已同步", "rewards": {"spirit_stone": -cost}}
                        rewarded = 1
                    except ValueError:
                        result = {"message": "联机灵石不足，淬炼未同步", "rewards": {}}
            elif event_type == "artifact_equip":
                if row:
                    conn.execute("UPDATE hub_inventory SET equipped=0 WHERE user_id=? AND item_type='artifact'", (user_id,))
                    conn.execute("UPDATE hub_inventory SET equipped=1,updated_at=? WHERE user_id=? AND item_key=?", (now_iso(),user_id,item_key))
                    result = {"message": "佩戴状态已同步", "rewards": {}}
                else:
                    result = {"message": "中心尚无该法器", "rewards": {}}
            else:
                level = int(row["level"]) if row else 0
                asset_key = spec["asset"]
                cost = int(spec["base_cost"] * max(1, level + 1))
                try:
                    transact_asset(conn, user_id, asset_key, -cost, f"升级{spec['name']}", event_uuid)
                    conn.execute(
                        """INSERT INTO hub_inventory(user_id,item_key,item_type,quantity,level,equipped,updated_at)
                           VALUES (?,?,?,1,1,0,?) ON CONFLICT(user_id,item_key) DO UPDATE SET level=hub_inventory.level+1,updated_at=excluded.updated_at""",
                        (user_id,item_key,item_type,now_iso()),
                    )
                    result = {"message": "建筑等级已同步", "rewards": {asset_key: -cost}}
                    rewarded = 1
                except ValueError:
                    result = {"message": "联机资材不足，升级未同步", "rewards": {}}
    else:
        result = {"message": "该事件仅留存，不参与结算", "rewards": {}}

    conn.execute(
        "INSERT INTO hub_sync_events(user_id,event_uuid,event_type,payload_json,rewarded,result_json,created_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, event_uuid, event_type, json.dumps(payload, ensure_ascii=False), rewarded, json.dumps(result, ensure_ascii=False), now_iso()),
    )
    return {"event_uuid": event_uuid, "status": "applied", **result}


@app.on_event("startup")
def startup() -> None:
    init_hub_db()
    try:
        backup_hub_db()
    except Exception:
        pass

    def periodic_backup() -> None:
        while True:
            time.sleep(24 * 3600)
            try:
                backup_hub_db()
            except Exception:
                pass

    threading.Thread(target=periodic_backup, daemon=True).start()


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        with connect_hub() as conn:
            conn.execute("SELECT 1").fetchone()
            active_members = int(
                conn.execute("SELECT COUNT(*) n FROM hub_users WHERE active=1").fetchone()["n"]
            )
        backups = sorted(
            HUB_BACKUP_DIR.glob("hub_*.db"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return {
            "status": "ok",
            "version": VERSION,
            "database": "ready",
            "active_members": active_members,
            "latest_backup": backups[0].name if backups else None,
        }
    except Exception:
        return JSONResponse(
            {
                "status": "degraded",
                "version": VERSION,
                "database": "unavailable",
                "detail": "中心数据库暂不可用。",
            },
            status_code=503,
            headers={"Retry-After": "30"},
        )


@app.get("/", response_class=HTMLResponse, name="hub_home")
def home(request: Request):
    user = current_user(request)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context=hub_context(request, "login"))
    with connect_hub() as conn:
        profile = dict(conn.execute("SELECT * FROM hub_profiles WHERE user_id=?", (user["id"],)).fetchone())
        members = []
        for row in conn.execute(
            """SELECT u.id,u.username,u.display_name,u.last_seen_at,p.title,p.bio,p.avatar_symbol,p.skills,p.capabilities
               FROM hub_users u JOIN hub_profiles p ON p.user_id=u.id WHERE u.active=1 AND p.public=1 ORDER BY u.role='admin' DESC,u.display_name"""
        ):
            item = dict(row)
            item["skills_list"] = [x.strip() for x in item["skills"].splitlines() if x.strip()][:5]
            members.append(item)
        release = conn.execute("SELECT * FROM hub_releases WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
        recent = [dict(row) for row in conn.execute(
            """SELECT e.event_type,e.created_at,u.display_name FROM hub_sync_events e JOIN hub_users u ON u.id=e.user_id
               ORDER BY e.id DESC LIMIT 12"""
        )]
        resource_cards = [dict(row) for row in conn.execute(
            """SELECT c.id,c.title,c.summary,c.tags,c.source_url,c.created_at,u.display_name,p.avatar_symbol
               FROM hub_resource_cards c JOIN hub_users u ON u.id=c.user_id JOIN hub_profiles p ON p.user_id=u.id
               WHERE u.active=1 AND c.visibility='team' ORDER BY c.id DESC LIMIT 6"""
        )]
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=hub_context(request, "home", profile=profile, members=members, latest_release=dict(release) if release else None, recent=recent, resource_cards=resource_cards),
    )


@app.post("/login", name="hub_login")
def login(request: Request, username: str = Form(...), password: str = Form(...), csrf_value: str = Form(..., alias="_csrf")):
    verify_csrf(request, csrf_value)
    ip = client_ip(request)
    if not login_allowed(ip):
        flash(request, "登录尝试过多，请10分钟后再试。", "error")
        response = RedirectResponse("/", status_code=303)
        response.headers["Retry-After"] = "600"
        return response
    with connect_hub() as conn:
        row = conn.execute("SELECT * FROM hub_users WHERE username=? AND active=1", (username.strip().lower(),)).fetchone()
        if not row or not verify_password(password, row["password_salt"], row["password_hash"]):
            record_login_failure(ip)
            audit(conn, int(row["id"]) if row else None, "login_failed", username, request)
            conn.commit()
            flash(request, "用户名或密码不正确。", "error")
            return RedirectResponse("/", status_code=303)
        request.session["hub_user_id"] = int(row["id"])
        conn.execute("UPDATE hub_users SET last_seen_at=?,updated_at=? WHERE id=?", (now_iso(), now_iso(), row["id"]))
        audit(conn, int(row["id"]), "login", "网页登录", request)
        conn.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/register", response_class=HTMLResponse, name="hub_register")
def register_page(request: Request, invite: str = ""):
    return templates.TemplateResponse(request=request, name="register.html", context=hub_context(request, "register", invite=invite))


@app.post("/register", name="hub_register_submit")
def register_submit(
    request: Request,
    invite: str = Form(...),
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_value: str = Form(..., alias="_csrf"),
):
    verify_csrf(request, csrf_value)
    if password != password_confirm:
        flash(request, "两次密码不一致。", "error")
        return RedirectResponse(f"/register?invite={invite}", status_code=303)
    with hub_transaction() as conn:
        max_members = int(get_hub_setting(conn, "max_members", "10"))
        if conn.execute("SELECT COUNT(*) n FROM hub_users WHERE active=1").fetchone()["n"] >= max_members:
            flash(request, "同行会成员已达到当前上限。", "error")
            return RedirectResponse("/register", status_code=303)
        row = conn.execute("SELECT * FROM hub_invites WHERE code=?", (invite.strip(),)).fetchone()
        if not row or int(row["uses_remaining"]) <= 0:
            flash(request, "邀请码无效或已用完。", "error")
            return RedirectResponse("/register", status_code=303)
        if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) < datetime.now().astimezone():
            flash(request, "邀请码已过期。", "error")
            return RedirectResponse("/register", status_code=303)
        try:
            user_id, _ = create_user(conn, username, password, display_name)
        except (ValueError, Exception) as exc:
            if "UNIQUE constraint" in str(exc):
                flash(request, "用户名已经存在。", "error")
            else:
                flash(request, str(exc), "error")
            return RedirectResponse(f"/register?invite={invite}", status_code=303)
        conn.execute("UPDATE hub_invites SET uses_remaining=uses_remaining-1 WHERE code=?", (invite.strip(),))
        audit(conn, user_id, "register", "邀请码注册", request)
        request.session["hub_user_id"] = user_id
    return RedirectResponse("/me", status_code=303)


@app.post("/logout", name="hub_logout")
def logout(request: Request, csrf_value: str = Form(..., alias="_csrf")):
    verify_csrf(request, csrf_value)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.get("/members", response_class=HTMLResponse, name="hub_members")
def members_page(request: Request):
    require_user(request)
    with connect_hub() as conn:
        members = []
        for row in conn.execute(
            """SELECT u.id,u.username,u.display_name,u.role,u.last_seen_at,p.title,p.bio,p.skills,p.capabilities,p.avatar_symbol
               FROM hub_users u JOIN hub_profiles p ON p.user_id=u.id WHERE u.active=1 AND p.public=1 ORDER BY u.display_name"""
        ):
            item = dict(row)
            item["skills_list"] = [x.strip() for x in item["skills"].splitlines() if x.strip()]
            item["capabilities_list"] = [x.strip() for x in item["capabilities"].splitlines() if x.strip()]
            members.append(item)
    return templates.TemplateResponse(request=request, name="members.html", context=hub_context(request, "members", members=members))


@app.get("/resources", response_class=HTMLResponse, name="hub_resources")
def resources_page(request: Request, q: str = ""):
    require_user(request)
    query = q.strip()[:100]
    with connect_hub() as conn:
        if query:
            like = f"%{query}%"
            rows = conn.execute(
                """SELECT c.*,u.display_name,u.username,p.avatar_symbol
                   FROM hub_resource_cards c
                   JOIN hub_users u ON u.id=c.user_id
                   JOIN hub_profiles p ON p.user_id=u.id
                   WHERE u.active=1 AND c.visibility='team'
                     AND (c.title LIKE ? OR c.summary LIKE ? OR c.tags LIKE ?)
                   ORDER BY c.id DESC LIMIT 100""",
                (like, like, like),
            )
        else:
            rows = conn.execute(
                """SELECT c.*,u.display_name,u.username,p.avatar_symbol
                   FROM hub_resource_cards c
                   JOIN hub_users u ON u.id=c.user_id
                   JOIN hub_profiles p ON p.user_id=u.id
                   WHERE u.active=1 AND c.visibility='team'
                   ORDER BY c.id DESC LIMIT 100"""
            )
        cards = [dict(row) for row in rows]
    for card in cards:
        card["tag_list"] = [x.strip() for x in re.split(r"[,，;；\n]", card.get("tags", "")) if x.strip()][:8]
    return templates.TemplateResponse(
        request=request, name="resources.html",
        context=hub_context(request, "resources", cards=cards, query=query),
    )


@app.get("/me", response_class=HTMLResponse, name="hub_me")
def me_page(request: Request):
    user = require_user(request)
    with connect_hub() as conn:
        payload = profile_payload(conn, int(user["id"]))
        token = conn.execute("SELECT api_token FROM hub_users WHERE id=?", (user["id"],)).fetchone()["api_token"]
        cards = [dict(row) for row in conn.execute("SELECT * FROM hub_resource_cards WHERE user_id=? ORDER BY id DESC", (user["id"],))]
    return templates.TemplateResponse(request=request, name="me.html", context=hub_context(request, "me", data=payload, api_token=token, cards=cards))


@app.post("/me/profile", name="hub_profile_save")
def profile_save(
    request: Request,
    display_name: str = Form(...), title: str = Form(""), bio: str = Form(""), skills: str = Form(""),
    capabilities: str = Form(""), goals: str = Form(""), avatar_symbol: str = Form("道"), public: str = Form(""),
    csrf_value: str = Form(..., alias="_csrf"),
):
    user = require_user(request)
    verify_csrf(request, csrf_value)
    with hub_transaction() as conn:
        conn.execute("UPDATE hub_users SET display_name=?,updated_at=? WHERE id=?", (display_name.strip()[:40] or user["username"], now_iso(), user["id"]))
        conn.execute(
            """UPDATE hub_profiles SET title=?,bio=?,skills=?,capabilities=?,goals=?,avatar_symbol=?,public=?,revision=revision+1,updated_at=? WHERE user_id=?""",
            (title[:100],bio[:1000],skills[:2000],capabilities[:3000],goals[:1500],avatar_symbol[:2] or "道",int(public=="1"),now_iso(),user["id"]),
        )
        audit(conn, int(user["id"]), "profile_update", "网页更新个人主页", request)
    flash(request, "个人主页已保存，并可被本地节点同步。")
    return RedirectResponse("/me", status_code=303)


@app.post("/me/theme", name="hub_theme_save")
def theme_save(request: Request, accent: str = Form("terracotta"), density: str = Form("comfortable"), scene: str = Form("warm"), home_motto: str = Form(""), home_poem: str = Form(""), csrf_value: str = Form(..., alias="_csrf")):
    user = require_user(request)
    verify_csrf(request, csrf_value)
    with hub_transaction() as conn:
        row = conn.execute("SELECT theme_json FROM hub_profiles WHERE user_id=?", (user["id"],)).fetchone()
        try:
            existing = json.loads(row["theme_json"] or "{}") if row else {}
        except json.JSONDecodeError:
            existing = {}
        existing.update({"accent":accent,"density":density,"scene":scene,"home_motto":home_motto,"home_poem":home_poem})
        theme = parse_theme(existing)
        conn.execute("UPDATE hub_profiles SET theme_json=?,revision=revision+1,updated_at=? WHERE user_id=?", (json.dumps(theme,ensure_ascii=False),now_iso(),user["id"]))
        audit(conn, int(user["id"]), "theme_update", json.dumps(theme,ensure_ascii=False), request)
    flash(request, "个性化配置已保存。")
    return RedirectResponse("/me", status_code=303)


@app.get("/me/export", name="hub_me_export")
def me_export(request: Request):
    user = require_user(request)
    with connect_hub() as conn:
        data = profile_payload(conn, int(user["id"]))
        data["resource_cards"] = [dict(row) for row in conn.execute("SELECT title,summary,tags,source_url,visibility,created_at,updated_at FROM hub_resource_cards WHERE user_id=?", (user["id"],))]
    path = HUB_BACKUP_DIR / f"user_{user['username']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    return FileResponse(path, filename=path.name, media_type="application/json")


@app.post("/me/token/regenerate", name="hub_token_regenerate")
def token_regenerate(request: Request, csrf_value: str = Form(..., alias="_csrf")):
    user = require_user(request)
    verify_csrf(request, csrf_value)
    token = secrets.token_urlsafe(32)
    with hub_transaction() as conn:
        conn.execute("UPDATE hub_users SET api_token=?,updated_at=? WHERE id=?", (token,now_iso(),user["id"]))
        audit(conn, int(user["id"]), "token_regenerate", "重新生成API Token", request)
    flash(request, "API Token已重新生成，旧Token立即失效。")
    return RedirectResponse("/me", status_code=303)


@app.post("/me/password", name="hub_password_change")
def password_change(request: Request, current_password: str = Form(...), new_password: str = Form(...), new_password_confirm: str = Form(...), csrf_value: str = Form(..., alias="_csrf")):
    user = require_user(request)
    verify_csrf(request, csrf_value)
    if new_password != new_password_confirm:
        flash(request, "两次新密码不一致。", "error")
        return RedirectResponse("/me", status_code=303)
    with hub_transaction() as conn:
        row = conn.execute("SELECT * FROM hub_users WHERE id=?", (user["id"],)).fetchone()
        if not verify_password(current_password, row["password_salt"], row["password_hash"]):
            flash(request, "当前密码不正确。", "error")
            return RedirectResponse("/me", status_code=303)
        try:
            set_password(conn, int(user["id"]), new_password)
        except ValueError as exc:
            flash(request, str(exc), "error")
            return RedirectResponse("/me", status_code=303)
        audit(conn, int(user["id"]), "password_change", "修改密码", request)
    credentials_retired = False
    if user["role"] == "admin" and HUB_ADMIN_PATH.exists():
        HUB_ADMIN_PATH.unlink(missing_ok=True)
        credentials_retired = True
    flash(
        request,
        "密码已修改；首次一次性凭据文件已销毁，API Token 仍可在本页查看。"
        if credentials_retired
        else "密码已修改。",
    )
    return RedirectResponse("/me", status_code=303)


@app.post("/me/cards", name="hub_card_create")
def card_create(request: Request, title: str = Form(...), summary: str = Form(""), tags: str = Form(""), source_url: str = Form(""), csrf_value: str = Form(..., alias="_csrf")):
    user = require_user(request)
    verify_csrf(request, csrf_value)
    if source_url and not re.match(r"^https?://", source_url.strip(), re.I):
        flash(request, "来源链接必须以http://或https://开头。", "error")
        return RedirectResponse("/me", status_code=303)
    with hub_transaction() as conn:
        ts=now_iso()
        conn.execute("INSERT INTO hub_resource_cards(user_id,title,summary,tags,source_url,created_at,updated_at) VALUES (?,?,?,?,?,?,?)", (user["id"],title[:160],summary[:1000],tags[:300],source_url[:500],ts,ts))
        audit(conn,int(user["id"]),"resource_card_create",title,request)
    flash(request,"共享资料卡已发布；原文件仍留在你自己的电脑。")
    return RedirectResponse("/me",status_code=303)


@app.post("/me/cards/{card_id}/delete", name="hub_card_delete")
def card_delete(request: Request, card_id: int, csrf_value: str = Form(..., alias="_csrf")):
    user=require_user(request); verify_csrf(request,csrf_value)
    with hub_transaction() as conn:
        conn.execute("DELETE FROM hub_resource_cards WHERE id=? AND user_id=?",(card_id,user["id"]))
    flash(request,"资料卡已删除。")
    return RedirectResponse("/me",status_code=303)


@app.get("/releases", response_class=HTMLResponse, name="hub_releases")
def releases_page(request: Request):
    require_user(request)
    with connect_hub() as conn:
        releases=[dict(row) for row in conn.execute("SELECT * FROM hub_releases WHERE active=1 ORDER BY id DESC")]
    return templates.TemplateResponse(request=request,name="releases.html",context=hub_context(request,"releases",releases=releases))


@app.get("/releases/{release_id}/download", name="hub_release_download")
def release_download(request: Request, release_id: int):
    require_user(request)
    with connect_hub() as conn:
        row=conn.execute("SELECT * FROM hub_releases WHERE id=? AND active=1",(release_id,)).fetchone()
    if not row: raise HTTPException(status_code=404)
    target=(BASE_DIR/row["file_path"]).resolve()
    if not target.exists() or HUB_RELEASE_DIR.resolve() not in target.parents: raise HTTPException(status_code=404)
    return FileResponse(target,filename=target.name,media_type="application/zip")


@app.get("/admin", response_class=HTMLResponse, name="hub_admin")
def admin_page(request: Request):
    user=require_user(request,admin=True)
    with connect_hub() as conn:
        users=[dict(row) for row in conn.execute("SELECT id,username,display_name,role,active,created_at,last_seen_at FROM hub_users ORDER BY id")]
        invites=[dict(row) for row in conn.execute("SELECT * FROM hub_invites ORDER BY created_at DESC")]
        releases=[dict(row) for row in conn.execute("SELECT * FROM hub_releases ORDER BY id DESC")]
        audits=[dict(row) for row in conn.execute("SELECT a.*,u.display_name FROM hub_audit_log a LEFT JOIN hub_users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 30")]
    backup_files = sorted(HUB_BACKUP_DIR.glob("hub_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context=hub_context(
            request,
            "admin",
            users=users,
            invites=invites,
            releases=releases,
            audits=audits,
            admin_credentials_path=str(HUB_ADMIN_PATH),
            admin_credentials_exists=HUB_ADMIN_PATH.exists(),
            backup_count=len(backup_files),
            last_backup=backup_files[0].name if backup_files else "尚无",
        ),
    )


@app.post("/admin/invites", name="hub_invite_create")
def invite_create(request:Request,uses:int=Form(1),days:int=Form(14),csrf_value:str=Form(..., alias="_csrf")):
    user=require_user(request,admin=True); verify_csrf(request,csrf_value)
    code=secrets.token_urlsafe(8)
    expires=(datetime.now().astimezone()+timedelta(days=max(1,min(days,90)))).isoformat(timespec="seconds")
    with hub_transaction() as conn:
        conn.execute("INSERT INTO hub_invites(code,uses_remaining,expires_at,created_by,created_at) VALUES (?,?,?,?,?)",(code,max(1,min(uses,10)),expires,user["id"],now_iso()))
        audit(conn,int(user["id"]),"invite_create",code,request)
    flash(request,f"邀请码已生成：{code}")
    return RedirectResponse("/admin",status_code=303)


@app.post("/admin/users/{user_id}/toggle", name="hub_user_toggle")
def user_toggle(request:Request,user_id:int,csrf_value:str=Form(..., alias="_csrf")):
    admin=require_user(request,admin=True); verify_csrf(request,csrf_value)
    if int(admin["id"])==user_id:
        flash(request,"不能停用当前管理员。","error"); return RedirectResponse("/admin",status_code=303)
    with hub_transaction() as conn:
        conn.execute("UPDATE hub_users SET active=CASE active WHEN 1 THEN 0 ELSE 1 END,updated_at=? WHERE id=?",(now_iso(),user_id))
        audit(conn,int(admin["id"]),"user_toggle",str(user_id),request)
    return RedirectResponse("/admin",status_code=303)


@app.post("/admin/releases", name="hub_release_upload")
def release_upload(request:Request,version:str=Form(...),title:str=Form(...),notes:str=Form(""),file:UploadFile=File(...),csrf_value:str=Form(..., alias="_csrf")):
    admin=require_user(request,admin=True); verify_csrf(request,csrf_value)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        flash(request,"版本包必须为ZIP。","error"); return RedirectResponse("/admin",status_code=303)
    safe_version=re.sub(r"[^0-9A-Za-z._-]+","_",version.strip())[:40]
    if not safe_version:
        flash(request,"版本号无效。","error"); return RedirectResponse("/admin",status_code=303)
    target=HUB_RELEASE_DIR/f"ResearchCultivationOS_{safe_version}.zip"
    h=hashlib.sha256(); size=0
    max_size = 500 * 1024 * 1024
    with target.open("wb") as out:
        while chunk:=file.file.read(1024*1024):
            size += len(chunk)
            if size > max_size:
                out.close(); target.unlink(missing_ok=True)
                flash(request, "版本包超过500MB，请精简后重新发布。", "error")
                return RedirectResponse("/admin", status_code=303)
            h.update(chunk); out.write(chunk)
    rel=target.relative_to(BASE_DIR).as_posix()
    try:
        with hub_transaction() as conn:
            conn.execute("INSERT INTO hub_releases(version,title,notes,file_path,file_size,sha256,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",(safe_version,title[:160],notes[:4000],rel,size,h.hexdigest(),admin["id"],now_iso()))
            audit(conn,int(admin["id"]),"release_upload",safe_version,request)
    except Exception as exc:
        target.unlink(missing_ok=True)
        flash(request,f"版本发布失败：{exc}","error"); return RedirectResponse("/admin",status_code=303)
    flash(request,f"v{safe_version} 已发布。")
    return RedirectResponse("/admin",status_code=303)


@app.post("/admin/backup", name="hub_backup")
def admin_backup(request:Request,csrf_value:str=Form(..., alias="_csrf")):
    require_user(request,admin=True); verify_csrf(request,csrf_value)
    path=backup_hub_db(); flash(request,f"联机数据库已备份：{path.name}")
    return RedirectResponse("/admin",status_code=303)


@app.get("/api/v1/ping")
def api_ping():
    return {"status": "ok", "version": VERSION, "mode": "coordination-hub"}


@app.get("/api/v1/bootstrap")
def api_bootstrap(request:Request):
    user=api_user(request)
    with connect_hub() as conn: return profile_payload(conn,int(user["id"]))


@app.post("/api/v1/events")
async def api_events(request:Request):
    user=api_user(request)
    body=await request.json()
    events=body.get("events",[]) if isinstance(body,dict) else []
    if not isinstance(events,list) or len(events)>100: raise HTTPException(status_code=400,detail="事件列表无效")
    results=[]
    with hub_transaction() as conn:
        for event in events: results.append(apply_event(conn,int(user["id"]),event if isinstance(event,dict) else {}))
        audit(conn,int(user["id"]),"api_sync",f"{len(events)} events",request)
        payload=profile_payload(conn,int(user["id"]))
    return {"results":results,"state":payload}


@app.post("/api/v1/personalization")
async def api_personalization(request:Request):
    user=api_user(request); body=await request.json(); theme=parse_theme(body if isinstance(body,dict) else {})
    with hub_transaction() as conn:
        conn.execute("UPDATE hub_profiles SET theme_json=?,revision=revision+1,updated_at=? WHERE user_id=?",(json.dumps(theme,ensure_ascii=False),now_iso(),user["id"]))
    return {"ok":True,"theme":theme}


@app.get("/api/v1/releases/latest")
def api_latest_release(request:Request):
    api_user(request)
    with connect_hub() as conn:
        row=conn.execute("SELECT id,version,title,notes,file_size,sha256,created_at FROM hub_releases WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    return {"release":dict(row) if row else None}


@app.get("/api/v1/releases/{release_id}/download")
def api_release_download(request:Request,release_id:int):
    api_user(request)
    with connect_hub() as conn: row=conn.execute("SELECT * FROM hub_releases WHERE id=? AND active=1",(release_id,)).fetchone()
    if not row: raise HTTPException(status_code=404)
    target=(BASE_DIR/row["file_path"]).resolve()
    if not target.exists() or HUB_RELEASE_DIR.resolve() not in target.parents:
        raise HTTPException(status_code=404)
    return FileResponse(target,filename=target.name,media_type="application/zip")
