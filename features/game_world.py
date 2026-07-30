from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from db import connect, now_iso, total_xp
from services.economy import ASSETS, balance, balances, transact
from services.game_world import (
    ARTIFACTS,
    BUILDINGS,
    building_cost,
    building_level,
    equipped_artifact,
    inventory_map,
)
from services.online_sync import best_effort_sync, queue_event
from services.profile_media import (
    MAX_AVATAR_BYTES,
    current_avatar_filename,
    remove_avatar,
    save_avatar_bytes,
)


def register_game_routes(
    app,
    templates,
    context: Callable[..., dict[str, Any]],
    flash: Callable[[Request, str, str], None],
    current_realm: Callable[[int], dict[str, Any]],
):
    router = APIRouter()

    @router.get("/world", response_class=HTMLResponse, name="world_page")
    def world_page(request: Request):
        with connect() as conn:
            wallet = balances(conn)
            inventory = inventory_map(conn)
            building_cards = []
            for key, spec in BUILDINGS.items():
                level = building_level(conn, key)
                building_cards.append({"key": key, **spec, "level": level, "cost": building_cost(key, level)})
            artifact_cards = []
            for key, spec in ARTIFACTS.items():
                owned = inventory.get(key)
                level = int(owned["level"]) if owned else 0
                price = int(spec["price"])
                max_level = int(spec.get("max_level", 1))
                artifact_cards.append({
                    "key": key,
                    **spec,
                    "owned": bool(owned),
                    "equipped": bool(owned and owned["equipped"]),
                    "level": level,
                    "max_level": max_level,
                    "upgrade_cost": max(10, (price // 2) * max(level, 1)),
                    "can_afford": int(wallet["spirit_stone"]) >= price,
                    "shortfall": max(0, price - int(wallet["spirit_stone"])),
                })
            herb_specs = {
                1: {"label": "凡品", "name": "青露草", "icon": "♧"},
                2: {"label": "灵品", "name": "凝神花", "icon": "☘"},
                3: {"label": "玄品", "name": "玄脉芝", "icon": "⚘"},
                4: {"label": "地品", "name": "地心莲", "icon": "✿"},
                5: {"label": "天品", "name": "天衍果", "icon": "❋"},
            }
            quantities = {
                int(row["grade"]): int(row["quantity"])
                for row in conn.execute("SELECT grade,quantity FROM herb_inventory")
            }
            herbs = [
                {"grade": grade, **spec, "quantity": quantities.get(grade, 0)}
                for grade, spec in herb_specs.items()
            ]
            if herbs and all(item["quantity"] > 0 for item in herbs):
                conn.execute("UPDATE easter_eggs SET unlocked=1,discovered_at=COALESCE(discovered_at,?) WHERE egg_key='all_herbs'", (now_iso(),))
                conn.commit()
            eggs = [dict(row) for row in conn.execute("SELECT * FROM easter_eggs ORDER BY unlocked DESC,title")]
            profile = dict(conn.execute("SELECT * FROM player_profile WHERE id=1").fetchone())
            active_artifact = equipped_artifact(conn)
        return templates.TemplateResponse(
            request=request,
            name="world.html",
            context=context(request, "world", wallet=wallet, assets=ASSETS, buildings=building_cards,
                            artifacts=artifact_cards, herbs=herbs, eggs=eggs, profile=profile,
                            active_artifact=active_artifact,
                            egg_count=sum(1 for egg in eggs if egg["unlocked"])),
        )

    @router.post("/world/buildings/{building_key}/upgrade", name="world_building_upgrade")
    def world_building_upgrade(request: Request, building_key: str):
        if building_key not in BUILDINGS:
            raise HTTPException(status_code=404)
        with connect() as conn:
            level = building_level(conn, building_key)
            if level >= 9:
                flash(request, "该建筑已达到当前版本上限。", "error")
                return RedirectResponse(request.url_for("world_page"), status_code=303)
            spec = BUILDINGS[building_key]
            cost = building_cost(building_key, level)
            try:
                transact(conn, spec["asset"], -cost, f"升级建筑：{spec['name']}")
            except ValueError:
                flash(request, f"{ASSETS[spec['asset']]['name']}不足，还需要 {cost}。", "error")
                return RedirectResponse(request.url_for("world_page"), status_code=303)
            ts = now_iso()
            conn.execute(
                """INSERT INTO inventory_items(item_key,item_type,quantity,level,equipped,acquired_at,updated_at)
                   VALUES (?,?,1,1,0,?,?)
                   ON CONFLICT(item_key) DO UPDATE SET level=inventory_items.level+1,updated_at=excluded.updated_at""",
                (building_key, "building", ts, ts),
            )
            conn.execute("INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)", ("building_upgrade", 6, f"{spec['name']}升至 {level+1} 级", ts))
            queue_event(conn, "building_upgrade", {"item_key": building_key, "level": level + 1})
            conn.commit()
        best_effort_sync()
        flash(request, f"{spec['name']}已升至 {level+1} 级。", "success")
        return RedirectResponse(request.url_for("world_page"), status_code=303)

    @router.post("/world/artifacts/{artifact_key}/buy", name="world_artifact_buy")
    def world_artifact_buy(request: Request, artifact_key: str):
        if artifact_key not in ARTIFACTS:
            raise HTTPException(status_code=404)
        spec = ARTIFACTS[artifact_key]
        with connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM inventory_items WHERE item_key=? AND item_type='artifact'",
                (artifact_key,),
            ).fetchone():
                flash(request, "你已经拥有这件法器。", "error")
                return RedirectResponse(request.url_for("world_page"), status_code=303)
            try:
                transact(conn, "spirit_stone", -int(spec["price"]), f"购入法器：{spec['name']}")
            except ValueError:
                current = balance(conn, "spirit_stone")
                shortfall = max(0, int(spec["price"]) - current)
                flash(request, f"当前有 {current} 灵石，还差 {shortfall} 灵石才能购入。", "error")
                return RedirectResponse(request.url_for("world_page"), status_code=303)
            ts = now_iso()
            conn.execute(
                "INSERT INTO inventory_items(item_key,item_type,quantity,level,equipped,acquired_at,updated_at) VALUES (?,?,1,1,0,?,?)",
                (artifact_key, "artifact", ts, ts),
            )
            owned_count = int(
                conn.execute(
                    "SELECT COUNT(*) n FROM inventory_items WHERE item_type='artifact'"
                ).fetchone()["n"]
            )
            if owned_count >= 5:
                conn.execute(
                    """
                    UPDATE easter_eggs
                    SET unlocked=1,discovered_at=COALESCE(discovered_at,?)
                    WHERE egg_key='artifact_keeper'
                    """,
                    (ts,),
                )
            conn.execute(
                "INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)",
                ("artifact_buy", 3, f"获得法器：{spec['name']}", ts),
            )
            queue_event(conn, "artifact_buy", {"item_key": artifact_key})
            conn.commit()
        best_effort_sync()
        flash(request, f"已获得法器：{spec['name']}。", "success")
        return RedirectResponse(request.url_for("world_page"), status_code=303)

    @router.post("/world/artifacts/{artifact_key}/upgrade", name="world_artifact_upgrade")
    def world_artifact_upgrade(request: Request, artifact_key: str):
        if artifact_key not in ARTIFACTS:
            raise HTTPException(status_code=404)
        spec = ARTIFACTS[artifact_key]
        with connect() as conn:
            row = conn.execute("SELECT * FROM inventory_items WHERE item_key=? AND item_type='artifact'", (artifact_key,)).fetchone()
            if not row:
                flash(request, "请先购入这件法器。", "error")
                return RedirectResponse(request.url_for("world_page"), status_code=303)
            level = int(row["level"])
            max_level = int(spec.get("max_level", 1))
            if level >= max_level:
                flash(
                    request,
                    "这件法器的作用已经完整，无需继续淬炼。"
                    if max_level == 1
                    else "法器已达到当前版本上限。",
                    "error",
                )
                return RedirectResponse(request.url_for("world_page"), status_code=303)
            cost = max(10, (int(spec["price"]) // 2) * max(level, 1))
            try:
                transact(conn, "spirit_stone", -cost, f"淬炼法器：{spec['name']}")
            except ValueError:
                flash(request, f"灵石不足，淬炼需要 {cost} 灵石。", "error")
                return RedirectResponse(request.url_for("world_page"), status_code=303)
            conn.execute("UPDATE inventory_items SET level=level+1,updated_at=? WHERE item_key=?", (now_iso(), artifact_key))
            conn.execute("INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)", ("artifact_upgrade", 5, f"{spec['name']}淬炼至 {level+1} 级", now_iso()))
            queue_event(conn, "artifact_upgrade", {"item_key": artifact_key, "level": level + 1})
            conn.commit()
        best_effort_sync()
        flash(request, f"{spec['name']}已淬炼至 {level+1} 级。", "success")
        return RedirectResponse(request.url_for("world_page"), status_code=303)

    @router.post("/world/artifacts/{artifact_key}/equip", name="world_artifact_equip")
    def world_artifact_equip(request: Request, artifact_key: str):
        with connect() as conn:
            row = conn.execute("SELECT * FROM inventory_items WHERE item_key=? AND item_type='artifact'", (artifact_key,)).fetchone()
            if not row:
                flash(request, "尚未拥有这件法器。", "error")
                return RedirectResponse(request.url_for("world_page"), status_code=303)
            conn.execute("UPDATE inventory_items SET equipped=0 WHERE item_type='artifact'")
            conn.execute("UPDATE inventory_items SET equipped=1,updated_at=? WHERE item_key=?", (now_iso(), artifact_key))
            conn.execute("UPDATE player_profile SET featured_item_key=?,updated_at=? WHERE id=1", (artifact_key, now_iso()))
            queue_event(conn, "artifact_equip", {"item_key": artifact_key})
            conn.commit()
        best_effort_sync()
        effect = ARTIFACTS.get(artifact_key, {}).get("effect", "")
        flash(
            request,
            f"法器已佩戴。当前作用：{effect}" if effect else "法器已佩戴，并展示在个人主页。",
            "success",
        )
        return RedirectResponse(request.url_for("world_page"), status_code=303)

    @router.post("/world/eggs/moon-well", name="world_moon_well")
    def world_moon_well(request: Request):
        with connect() as conn:
            row = conn.execute("SELECT unlocked FROM easter_eggs WHERE egg_key='moon_well'").fetchone()
            if row and not row["unlocked"]:
                conn.execute("UPDATE easter_eggs SET unlocked=1,discovered_at=? WHERE egg_key='moon_well'", (now_iso(),))
                transact(conn, "spirit_stone", 3, "发现隐藏彩蛋：月影井")
                conn.commit()
                flash(request, "你在月影井边发现了 3 枚灵石。", "success")
            else:
                flash(request, "井水映出一句话：真正的问题，往往藏在你没有测量的地方。", "success")
        return RedirectResponse(request.url_for("world_page"), status_code=303)

    @router.get("/profile", response_class=HTMLResponse, name="profile_page")
    def profile_page(request: Request, edit: int = 0):
        with connect() as conn:
            profile = dict(conn.execute("SELECT * FROM player_profile WHERE id=1").fetchone())
            wallet = balances(conn)
            xp = total_xp(conn)
            realm = current_realm(xp)
            owned_artifacts = []
            for row in conn.execute("SELECT * FROM inventory_items WHERE item_type='artifact' ORDER BY acquired_at"):
                item = dict(row)
                item.update(ARTIFACTS.get(row["item_key"], {"name": row["item_key"], "icon": "◇", "desc": ""}))
                owned_artifacts.append(item)
            stats = {
                "deliveries": conn.execute("SELECT COUNT(*) n FROM mission_deliveries").fetchone()["n"],
                "documents": conn.execute("SELECT COUNT(*) n FROM entries WHERE kind='document'").fetchone()["n"],
                "notes": conn.execute("SELECT COUNT(*) n FROM entries WHERE kind IN ('note','question','idea','sop','failure')").fetchone()["n"],
                "datasets": conn.execute("SELECT COUNT(*) n FROM entries WHERE kind='dataset'").fetchone()["n"],
                "experiments": conn.execute("SELECT COUNT(*) n FROM experiments").fetchone()["n"],
                "simulations": conn.execute("SELECT COUNT(*) n FROM simulations").fetchone()["n"],
            }
        profile["skills_list"] = [x.strip() for x in profile["skills"].splitlines() if x.strip()]
        profile["capabilities_list"] = [x.strip() for x in profile["capabilities"].splitlines() if x.strip()]
        profile["avatar_file"] = current_avatar_filename()
        return templates.TemplateResponse(
            request=request, name="profile.html",
            context=context(request, "profile", profile=profile, wallet=wallet, xp=xp, realm=realm,
                            artifacts=owned_artifacts, stats=stats, herbs=[], edit_mode=bool(edit)),
        )

    @router.post("/profile", name="profile_save")
    def profile_save(
        request: Request,
        display_name: str = Form(...), title: str = Form(""), bio: str = Form(""),
        skills: str = Form(""), capabilities: str = Form(""), goals: str = Form(""), avatar_symbol: str = Form("道"),
    ):
        with connect() as conn:
            conn.execute(
                """UPDATE player_profile SET display_name=?,title=?,bio=?,skills=?,capabilities=?,goals=?,avatar_symbol=?,updated_at=? WHERE id=1""",
                (display_name.strip() or "修士", title.strip(), bio.strip(), skills.strip(), capabilities.strip(), goals.strip(), (avatar_symbol.strip() or "道")[:2], now_iso()),
            )
            conn.execute("INSERT INTO settings(key,value) VALUES ('researcher_name',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (display_name.strip() or "修士",))
            queue_event(
                conn,
                "profile_updated",
                {
                    "display_name": display_name.strip() or "修士",
                    "title": title.strip(), "bio": bio.strip(), "skills": skills.strip(),
                    "capabilities": capabilities.strip(), "goals": goals.strip(),
                    "avatar_symbol": (avatar_symbol.strip() or "道")[:2],
                },
            )
            conn.commit()
        best_effort_sync()
        flash(request, "个人主页已更新。", "success")
        return RedirectResponse(request.url_for("profile_page"), status_code=303)

    @router.post("/profile/avatar", name="profile_avatar_save")
    async def profile_avatar_save(
        request: Request,
        avatar_action: str = Form("symbol"),
        avatar_choice: str = Form("道"),
        avatar_custom: str = Form(""),
        avatar: UploadFile | None = File(default=None),
    ):
        symbol = (avatar_custom.strip() or avatar_choice.strip() or "道")[:2]
        try:
            if avatar_action == "upload":
                if not avatar or not avatar.filename:
                    raise ValueError("请先选择一张头像图片。")
                data = await avatar.read(MAX_AVATAR_BYTES + 1)
                save_avatar_bytes(data)
            elif avatar_action == "symbol":
                remove_avatar()
            else:
                raise ValueError("无法识别头像操作。")
            with connect() as conn:
                conn.execute(
                    "UPDATE player_profile SET avatar_symbol=?,updated_at=? WHERE id=1",
                    (symbol, now_iso()),
                )
                queue_event(conn, "profile_updated", {"avatar_symbol": symbol})
                conn.commit()
            best_effort_sync()
            message = "头像图片已更新。" if avatar_action == "upload" else "已改用字印头像。"
            flash(request, message, "success")
        except ValueError as exc:
            flash(request, str(exc), "error")
        return RedirectResponse(
            str(request.url_for("profile_page")) + "?edit=1",
            status_code=303,
        )

    app.include_router(router)
