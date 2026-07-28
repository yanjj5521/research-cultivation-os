from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from db import connect, now_iso
from runtime_paths import STORAGE_ROOT
from services.ai_provider import provider_status
from services.review_engine import add_or_increment_herb, generate_special_task

DELIVERY_DIR = STORAGE_ROOT / "deliveries"

HERB_GRADES = {
    1: {"label": "凡品", "name": "青露草", "icon": "♧"},
    2: {"label": "灵品", "name": "凝神花", "icon": "☘"},
    3: {"label": "玄品", "name": "玄脉芝", "icon": "⚘"},
    4: {"label": "地品", "name": "地心莲", "icon": "✿"},
    5: {"label": "天品", "name": "天衍果", "icon": "❋"},
}

RECIPES = {
    "clarity_pill": {
        "name": "清心丹",
        "desc": "使用后增加 10 修为，适合完成一次小复盘后收功。",
        "costs": {1: 2},
        "xp": 10,
    },
    "focus_pill": {
        "name": "凝元丹",
        "desc": "使用后增加 25 修为，象征把零散知识凝成方法。",
        "costs": {1: 1, 2: 2},
        "xp": 25,
    },
    "tribulation_pill": {
        "name": "渡劫丹",
        "desc": "只在金丹以上、修为达到下一大境界门槛时开启一次五问雷劫。",
        "costs": {3: 2, 4: 1},
        "xp": 0,
    },
}


def _safe_name(value: str) -> str:
    return re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", Path(value).name).strip("._")[:160] or "file"


def _pill_rows(conn) -> list[dict[str, Any]]:
    rows = {
        row["item_key"]: dict(row)
        for row in conn.execute("SELECT * FROM inventory_items WHERE item_type='pill'")
    }
    return [
        {"key": key, **spec, "quantity": int(rows.get(key, {}).get("quantity", 0))}
        for key, spec in RECIPES.items()
    ]


def register_alchemy_routes(
    app,
    templates,
    context: Callable[..., dict[str, Any]],
    flash: Callable[[Request, str, str], None],
):
    router = APIRouter()

    @router.get("/alchemy", response_class=HTMLResponse, name="alchemy_page")
    def alchemy_page(request: Request):
        with connect() as conn:
            tasks = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM special_tasks
                    WHERE status IN ('offered','active')
                    ORDER BY status='active' DESC,id DESC
                    """
                )
            ]
            completed = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM special_tasks WHERE status='completed' ORDER BY completed_at DESC LIMIT 8"
                )
            ]
            quantities = {
                int(row["grade"]): int(row["quantity"])
                for row in conn.execute("SELECT grade,quantity FROM herb_inventory")
            }
            herbs = [
                {"grade": grade, **spec, "quantity": quantities.get(grade, 0)}
                for grade, spec in HERB_GRADES.items()
            ]
            pills = _pill_rows(conn)
        recipes = []
        for key, spec in RECIPES.items():
            costs = [
                f"{HERB_GRADES[grade]['label']}{HERB_GRADES[grade]['name']}×{amount}"
                for grade, amount in spec["costs"].items()
            ]
            recipes.append({"key": key, **spec, "cost_text": " + ".join(costs)})
        return templates.TemplateResponse(
            request=request,
            name="alchemy.html",
            context=context(
                request,
                "alchemy",
                tasks=tasks,
                completed=completed,
                herbs=herbs,
                pills=pills,
                recipes=recipes,
                grades=HERB_GRADES,
                ai_status=provider_status(),
            ),
        )

    @router.post("/alchemy/tasks/generate", name="alchemy_task_generate")
    def task_generate(
        request: Request,
        difficulty: int = Form(2),
        focus: str = Form(""),
    ):
        difficulty = max(1, min(int(difficulty), 5))
        with connect() as conn:
            recent = [
                dict(row)
                for row in conn.execute(
                    "SELECT title,source_text FROM review_sources ORDER BY source_date DESC,id DESC LIMIT 6"
                )
            ]
            active = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT title,deliverable FROM daily_missions
                    WHERE completed=0 ORDER BY id DESC LIMIT 5
                    """
                )
            ]
        context_text = "\n".join(
            [f"用户指定：{focus.strip()}"] if focus.strip() else []
        )
        context_text += "\n" + "\n".join(f"{row['title']}：{row['source_text']}" for row in recent)
        context_text += "\n" + "\n".join(f"近期任务：{row['title']}；交付={row['deliverable']}" for row in active)
        task, provider, fallback_reason = generate_special_task(context_text, difficulty)
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO special_tasks(
                    title,description,deliverable,why_it_matters,difficulty,status,
                    provider,fallback_reason,created_at
                ) VALUES (?,?,?,?,?,'offered',?,?,?)
                """,
                (
                    task["title"],
                    task["description"],
                    task["deliverable"],
                    task["why_it_matters"],
                    difficulty,
                    provider,
                    fallback_reason[:1000],
                    now_iso(),
                ),
            )
            conn.commit()
        flash(request, f"已生成 {HERB_GRADES[difficulty]['label']} 特殊任务。", "success")
        return RedirectResponse(request.url_for("alchemy_page"), status_code=303)

    @router.post("/alchemy/tasks/{task_id}/accept", name="alchemy_task_accept")
    def task_accept(request: Request, task_id: int):
        with connect() as conn:
            active = conn.execute("SELECT COUNT(*) n FROM special_tasks WHERE status='active'").fetchone()["n"]
            if active:
                flash(request, "先完成或放弃当前特殊任务，再接下一项。", "error")
                return RedirectResponse(request.url_for("alchemy_page"), status_code=303)
            conn.execute(
                "UPDATE special_tasks SET status='active',accepted_at=? WHERE id=? AND status='offered'",
                (now_iso(), task_id),
            )
            conn.commit()
        flash(request, "特殊任务已接取。完成真实交付后才能获得灵草。", "success")
        return RedirectResponse(request.url_for("alchemy_page"), status_code=303)

    @router.post("/alchemy/tasks/{task_id}/abandon", name="alchemy_task_abandon")
    def task_abandon(request: Request, task_id: int):
        with connect() as conn:
            conn.execute(
                "UPDATE special_tasks SET status='abandoned' WHERE id=? AND status IN ('offered','active')",
                (task_id,),
            )
            conn.commit()
        flash(request, "任务已放下，不扣资源，也不形成补课债务。", "success")
        return RedirectResponse(request.url_for("alchemy_page"), status_code=303)

    @router.post("/alchemy/tasks/{task_id}/complete", name="alchemy_task_complete")
    def task_complete(
        request: Request,
        task_id: int,
        evidence: str = Form(...),
        review_text: str = Form(...),
        files: list[UploadFile] = File(default=[]),
    ):
        evidence = evidence.strip()
        review_text = review_text.strip()
        if not evidence or not review_text:
            flash(request, "请同时填写交付说明和复盘关键文本。", "error")
            return RedirectResponse(request.url_for("alchemy_page"), status_code=303)
        with connect() as conn:
            task = conn.execute("SELECT * FROM special_tasks WHERE id=? AND status='active'", (task_id,)).fetchone()
        if not task:
            raise HTTPException(status_code=404)

        storage_key = f"special_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        root = DELIVERY_DIR / storage_key
        root.mkdir(parents=True, exist_ok=True)
        try:
            (root / "交付说明.txt").write_text(evidence, encoding="utf-8")
            (root / "复盘关键文本.txt").write_text(review_text, encoding="utf-8")
            for upload in [item for item in files if item.filename]:
                target = root / _safe_name(upload.filename or "file")
                with target.open("wb") as output:
                    shutil.copyfileobj(upload.file, output)
            ts = now_iso()
            with connect() as conn:
                conn.execute(
                    """
                    UPDATE special_tasks
                    SET status='completed',evidence=?,review_text=?,storage_key=?,completed_at=?
                    WHERE id=? AND status='active'
                    """,
                    (evidence, review_text, storage_key, ts, task_id),
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO review_sources(
                        source_type,source_id,title,source_text,storage_key,source_date,created_at
                    ) VALUES ('special_task',?,?,?,?,?,?)
                    """,
                    (
                        task_id,
                        task["title"],
                        review_text,
                        storage_key,
                        ts[:10],
                        ts,
                    ),
                )
                add_or_increment_herb(conn, int(task["difficulty"]))
                conn.execute(
                    "INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)",
                    (
                        "special_task",
                        10 + int(task["difficulty"]) * 5,
                        f"完成特殊任务：{task['title']}",
                        ts,
                    ),
                )
                conn.commit()
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
        herb = HERB_GRADES[int(task["difficulty"])]
        flash(request, f"交付成立，获得 {herb['label']}{herb['name']} ×1。", "success")
        return RedirectResponse(request.url_for("alchemy_page"), status_code=303)

    @router.post("/alchemy/craft/{recipe_key}", name="alchemy_craft")
    def alchemy_craft(request: Request, recipe_key: str):
        recipe = RECIPES.get(recipe_key)
        if not recipe:
            raise HTTPException(status_code=404)
        with connect() as conn:
            quantities = {
                int(row["grade"]): int(row["quantity"])
                for row in conn.execute("SELECT grade,quantity FROM herb_inventory")
            }
            missing = [
                grade
                for grade, amount in recipe["costs"].items()
                if quantities.get(grade, 0) < amount
            ]
            if missing:
                flash(request, "灵草不足，先完成对应等级的特殊任务。", "error")
                return RedirectResponse(request.url_for("alchemy_page"), status_code=303)
            ts = now_iso()
            for grade, amount in recipe["costs"].items():
                conn.execute(
                    "UPDATE herb_inventory SET quantity=quantity-?,updated_at=? WHERE grade=?",
                    (amount, ts, grade),
                )
            conn.execute("DELETE FROM herb_inventory WHERE quantity<=0")
            conn.execute(
                """
                INSERT INTO inventory_items(
                    item_key,item_type,quantity,level,equipped,acquired_at,updated_at
                ) VALUES (?,'pill',1,1,0,?,?)
                ON CONFLICT(item_key) DO UPDATE SET
                    quantity=inventory_items.quantity+1,updated_at=excluded.updated_at
                """,
                (recipe_key, ts, ts),
            )
            conn.commit()
        flash(request, f"{recipe['name']}炼制成功。", "success")
        return RedirectResponse(request.url_for("alchemy_page"), status_code=303)

    @router.post("/alchemy/pills/{pill_key}/use", name="alchemy_pill_use")
    def pill_use(request: Request, pill_key: str):
        recipe = RECIPES.get(pill_key)
        if not recipe or not int(recipe["xp"]):
            flash(request, "这枚丹药不能在这里直接使用。", "error")
            return RedirectResponse(request.url_for("alchemy_page"), status_code=303)
        with connect() as conn:
            row = conn.execute(
                "SELECT quantity FROM inventory_items WHERE item_key=? AND item_type='pill'",
                (pill_key,),
            ).fetchone()
            if not row or int(row["quantity"]) < 1:
                flash(request, "你还没有这枚丹药。", "error")
                return RedirectResponse(request.url_for("alchemy_page"), status_code=303)
            ts = now_iso()
            conn.execute(
                "UPDATE inventory_items SET quantity=quantity-1,updated_at=? WHERE item_key=?",
                (ts, pill_key),
            )
            conn.execute("DELETE FROM inventory_items WHERE item_key=? AND quantity<=0", (pill_key,))
            conn.execute(
                "INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)",
                ("pill_use", int(recipe["xp"]), f"服用{recipe['name']}", ts),
            )
            conn.commit()
        flash(request, f"服用{recipe['name']}，增加 {recipe['xp']} 修为。", "success")
        return RedirectResponse(request.url_for("alchemy_page"), status_code=303)

    app.include_router(router)
