from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from fastapi.testclient import TestClient

import app
from db import connect, get_setting, now_iso, set_setting


def _check_response(failures: list[str], label: str, response, expected: int = 200) -> None:
    if response.status_code != expected:
        failures.append(f"{label}: HTTP {response.status_code}")


def _run_integration(client: TestClient, failures: list[str]) -> None:
    """Exercise the complete v1.2 loop.

    This mode writes test records, so run it only against a disposable copy:
    `python self_test.py --integration`.
    """

    plan_text = """# 自检近期计划
> 用真实交付驱动复盘
## Day 1 | 证据链
- [重点] 检查一条科研判断 | 20min | 12XP | 交付：一张证据卡
## Day 2 | 修正
- [可选] 写出反例 | 15min | 8XP | 交付：反例与验证办法
"""
    _check_response(
        failures,
        "plan import",
        client.post("/plans/import", data={"plan_text": plan_text}),
    )
    with connect() as conn:
        plan = conn.execute(
            "SELECT * FROM study_plans WHERE name='自检近期计划' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        mission = conn.execute(
            "SELECT * FROM daily_missions WHERE plan_id=? AND day_index=1 ORDER BY id LIMIT 1",
            (plan["id"],),
        ).fetchone() if plan else None
    if not plan or not mission:
        failures.append("plan import did not create the expected mission")
        return

    _check_response(
        failures,
        "delivery",
        client.post(
            f"/daily/missions/{mission['id']}/deliver",
            data={
                "view_day": "1",
                "note": "已提交证据卡。",
                "review_text": "科研判断必须说明证据、适用边界和可能反例。因果关系需要可验证，而不是只看相关性。",
                "folder_paths": "[]",
            },
        ),
    )
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    with connect() as conn:
        delivery = conn.execute(
            "SELECT * FROM mission_deliveries WHERE mission_id=? ORDER BY id DESC LIMIT 1",
            (mission["id"],),
        ).fetchone()
        source = conn.execute(
            "SELECT * FROM review_sources WHERE source_type='mission_delivery' AND source_id=?",
            (delivery["id"],),
        ).fetchone() if delivery else None
        if source:
            conn.execute("UPDATE review_sources SET source_date=? WHERE id=?", (yesterday, source["id"]))
            conn.commit()
    if not delivery or not source:
        failures.append("delivery did not create a review source")
        return

    dashboard = client.get("/")
    _check_response(failures, "pending review dashboard", dashboard)
    if "昨日复盘" not in dashboard.text:
        failures.append("dashboard did not surface the pending review")

    _check_response(
        failures,
        "review start",
        client.post("/review/start", data={"mode": "yesterday"}),
    )
    with connect() as conn:
        session = conn.execute(
            "SELECT * FROM review_sessions WHERE mode='yesterday' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not session:
        failures.append("review start did not create a session")
        return
    questions = json.loads(session["questions_json"])
    if len(questions) != 3:
        failures.append(f"review session expected 3 questions, got {len(questions)}")
    for index, question in enumerate(questions):
        answer = f"我的回答依据是：{question.get('evidence', '')}"
        _check_response(
            failures,
            f"review answer {index}",
            client.post(
                f"/review/sessions/{session['id']}/answer",
                data={"question_index": str(index), "answer": answer},
            ),
        )
    _check_response(
        failures,
        "review self rating",
        client.post(
            f"/review/sessions/{session['id']}/rate",
            data={"question_index": "0", "self_rating": "partial"},
        ),
    )
    with connect() as conn:
        finished = conn.execute("SELECT status FROM review_sessions WHERE id=?", (session["id"],)).fetchone()
        answers = conn.execute(
            "SELECT COUNT(*) n FROM review_answers WHERE session_id=?", (session["id"],)
        ).fetchone()["n"]
        rating = conn.execute(
            "SELECT self_rating,next_due FROM review_answers WHERE session_id=? AND question_index=0",
            (session["id"],),
        ).fetchone()
    if not finished or finished["status"] != "completed" or answers != len(questions):
        failures.append("review session did not complete")
    if not rating or rating["self_rating"] != "partial" or not rating["next_due"]:
        failures.append("review self rating was not scheduled")

    _check_response(
        failures,
        "special task generate",
        client.post(
            "/alchemy/tasks/generate",
            data={"difficulty": "2", "focus": "检查科研判断的证据边界"},
        ),
    )
    with connect() as conn:
        task = conn.execute(
            "SELECT * FROM special_tasks WHERE status='offered' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not task:
        failures.append("special task generation failed")
        return
    _check_response(
        failures,
        "special task accept",
        client.post(f"/alchemy/tasks/{task['id']}/accept"),
    )
    _check_response(
        failures,
        "special task complete",
        client.post(
            f"/alchemy/tasks/{task['id']}/complete",
            data={
                "evidence": "完成了一张命题—反例—验证办法表。",
                "review_text": "反例用于检查结论的适用边界；验证办法必须对应可观测量。",
            },
        ),
    )
    with connect() as conn:
        completed = conn.execute("SELECT status FROM special_tasks WHERE id=?", (task["id"],)).fetchone()
        herb = conn.execute("SELECT quantity FROM herb_inventory WHERE grade=2").fetchone()
        ts = now_iso()
        conn.execute(
            """
            INSERT INTO herb_inventory(grade,herb_name,quantity,updated_at)
            VALUES (1,'青露草',2,?)
            ON CONFLICT(grade) DO UPDATE SET quantity=quantity+2,updated_at=excluded.updated_at
            """,
            (ts,),
        )
        conn.commit()
    if not completed or completed["status"] != "completed" or not herb or herb["quantity"] < 1:
        failures.append("special task did not award the expected herb")

    _check_response(failures, "alchemy craft", client.post("/alchemy/craft/clarity_pill"))
    with connect() as conn:
        pill = conn.execute(
            "SELECT quantity FROM inventory_items WHERE item_key='clarity_pill'"
        ).fetchone()
    if not pill or pill["quantity"] < 1:
        failures.append("alchemy did not create a clarity pill")
    _check_response(
        failures,
        "alchemy pill use",
        client.post("/alchemy/pills/clarity_pill/use"),
    )

    realm_names = "\n".join(["见习研究者", "证据学徒"])
    nav_labels = "\n".join(["dashboard=科研台", "alchemy=实验炼丹房"])
    _check_response(
        failures,
        "personalization settings",
        client.post(
            "/settings",
            data={
                "site_name": "自检科研系统",
                "researcher_name": "自检用户",
                "domains": "电化学\n未分类",
                "ai_mode": "offline",
                "ai_endpoint": "http://127.0.0.1:11434/api/generate",
                "ai_model": "qwen2.5:7b",
                "realm_names": realm_names,
                "nav_labels": nav_labels,
                "review_popup": "1",
            },
        ),
    )
    if get_setting("site_name") != "自检科研系统":
        failures.append("site personalization was not saved")
    saved_nav = json.loads(get_setting("nav_labels", "{}"))
    if saved_nav.get("dashboard") != "科研台" or saved_nav.get("alchemy") != "实验炼丹房":
        failures.append("navigation personalization was not saved")

    package_response = client.get("/online/personalization/export")
    _check_response(failures, "personalization export", package_response)
    try:
        package = json.loads(package_response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        package = {}
        failures.append("personalization export was not valid JSON")
    if package.get("format") != "research-cultivation-personalization-v2":
        failures.append("personalization export did not use the v2 format")
    if "hub_api_token" in json.dumps(package, ensure_ascii=False):
        failures.append("personalization export leaked the hub token field")
    set_setting("site_name", "临时改名")
    _check_response(
        failures,
        "personalization import",
        client.post(
            "/online/personalization/import",
            files={
                "file": (
                    "personalization.json",
                    json.dumps(package, ensure_ascii=False).encode("utf-8"),
                    "application/json",
                )
            },
        ),
    )
    if get_setting("site_name") != "自检科研系统":
        failures.append("personalization import did not restore the site name")


def main() -> None:
    integration = "--integration" in sys.argv
    client = TestClient(app.app)
    pages = [
        "/", "/daily", "/review", "/alchemy", "/world", "/profile", "/plans",
        "/foundation", "/assistant", "/notes/new", "/library", "/settings", "/online",
    ]
    failures = []
    for page in pages:
        response = client.get(page)
        _check_response(failures, page, response)
    with connect() as conn:
        required_tables = {
            "mission_deliveries", "mission_delivery_files", "asset_transactions", "inventory_items",
            "player_profile", "easter_eggs", "track_growth", "online_sync_queue", "online_sync_cache",
            "review_sources", "review_sessions", "review_session_sources", "review_answers",
            "review_snoozes", "special_tasks", "herb_inventory",
        }
        found = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(required_tables - found)
        if missing:
            failures.append("missing tables: " + ", ".join(missing))
        if conn.execute("SELECT COUNT(*) n FROM study_plans").fetchone()["n"] < 1:
            failures.append("no study plan")
        if conn.execute("SELECT COUNT(*) n FROM daily_missions").fetchone()["n"] < 1:
            failures.append("no daily missions")
    if integration:
        _run_integration(client, failures)
    if failures:
        print("SELF TEST FAILED")
        for failure in failures:
            print("-", failure)
        raise SystemExit(1)
    print("SELF TEST PASS")
    if integration:
        print("Plans, deliveries, evidence-based review, challenge grading, alchemy and personalization are ready.")
    else:
        print("Core pages, v1.2 tables, daily plan, online queue and local database are ready.")


if __name__ == "__main__":
    main()
