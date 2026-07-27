from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import date, timedelta

from fastapi.testclient import TestClient
from PIL import Image

import app
from db import connect, get_setting, now_iso, set_setting, total_xp
from services.progression import (
    REALM_STAGES,
    TRIBULATION_GATES,
    realm_state,
)


def _check_response(failures: list[str], label: str, response, expected: int = 200) -> None:
    if response.status_code != expected:
        failures.append(f"{label}: HTTP {response.status_code}")


def _run_integration(client: TestClient, failures: list[str]) -> None:
    """Exercise the complete v2.0.2 loop.

    This mode writes test records, so run it only against a disposable copy:
    `python self_test.py --integration`.
    """

    plan_text = """# 自检近期计划
> 用真实交付驱动复盘
## 修炼任务
- [进阶] 建立证据边界判断能力 | 验收：完成一张命题—反例—验证表 | 工作区：EG 实验
## Day 1 | 证据链
- [重点] 检查一条科研判断 | 20min | 999XP | 交付：一张证据卡 | 关联修炼：建立证据边界判断能力
## Day 2 | 修正
- [可选] 写出反例 | 15min | 888经验 | 交付：反例与验证办法
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
        cultivation_task = conn.execute(
            "SELECT * FROM quests WHERE title='建立证据边界判断能力' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not plan or not mission:
        failures.append("plan import did not create the expected mission")
        return
    if not cultivation_task or int(mission["quest_id"] or 0) != int(cultivation_task["id"]):
        failures.append("plan import did not keep cultivation and daily tasks separate but linked")
    if int(mission["xp"]) != 6:
        failures.append("imported XP was not ignored in favor of the fixed duration rule")
    if "999XP" in plan["source_text"] or "888经验" in plan["source_text"]:
        failures.append("custom reward fields were not removed from the normalized plan text")

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

    _check_response(
        failures,
        "knowledge attachment upload",
        client.post(
            "/upload",
            data={
                "title": "自检知识条目",
                "kind": "note",
                "domain": "电化学",
                "tags": "证据,自检",
                "summary": "用于验证 Markdown、JSON 与附件的一键导出。",
            },
            files={"files": ("evidence.txt", b"evidence-backed research note", "text/plain")},
        ),
    )
    _check_response(
        failures,
        "custom workspace create",
        client.post(
            "/workspaces/new",
            data={
                "name": "自检专题空间",
                "icon": "测",
                "module": "knowledge",
                "description": "验证每个人可拥有不同工作区。",
            },
        ),
    )
    with connect() as conn:
        workspace = conn.execute(
            "SELECT * FROM workspaces WHERE name='自检专题空间' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not workspace:
        failures.append("custom workspace was not created")
    else:
        _check_response(
            failures,
            "workspace attachment upload",
            client.post(
                "/upload",
                data={
                    "kind": "note",
                    "domain": "电化学",
                    "summary": "仅属于自检专题空间。",
                    "workspace_id": str(workspace["id"]),
                },
                files={"files": ("workspace-note.txt", b"workspace scoped note", "text/plain")},
            ),
        )
        workspace_page = client.get(f"/workspaces/{workspace['id']}")
        _check_response(failures, "custom workspace open", workspace_page)
        if "workspace-note" not in workspace_page.text:
            failures.append("custom workspace did not show its assigned knowledge entry")

    with connect() as conn:
        default_workspaces = {
            row["workspace_key"]: dict(row)
            for row in conn.execute(
                """
                SELECT * FROM workspaces
                WHERE workspace_key IN (
                    'eg-lab','lammps-lab','dataset-lab','ml-lab','md-lab','comsol-lab'
                )
                """
            )
        }
    workspace_modules = {
        "eg-lab": "experiments",
        "lammps-lab": "simulations",
        "dataset-lab": "datasets",
        "ml-lab": "ml",
        "md-lab": "md",
        "comsol-lab": "comsol",
    }
    for workspace_key, module in workspace_modules.items():
        workspace_item = default_workspaces.get(workspace_key)
        if not workspace_item:
            failures.append(f"default {workspace_key} workspace was not initialized")
            continue
        if workspace_item["module"] != module:
            failures.append(f"default {workspace_key} workspace used the wrong module")
        response = client.get(f"/workspaces/{workspace_item['id']}")
        _check_response(failures, f"{module} workspace open", response)
        if workspace_item["name"] not in response.text:
            failures.append(f"{module} workspace did not open its personalized module page")

    experiment_workspace = default_workspaces.get("eg-lab")
    simulation_workspace = default_workspaces.get("lammps-lab")
    dataset_workspace = default_workspaces.get("dataset-lab")
    if experiment_workspace:
        _check_response(
            failures,
            "workspace experiment create",
            client.post(
                "/experiments/save",
                data={
                    "sample_id": "SELFTEST-EG-01",
                    "title": "工作区实验",
                    "workspace_id": str(experiment_workspace["id"]),
                },
            ),
        )
    if simulation_workspace:
        _check_response(
            failures,
            "workspace simulation create",
            client.post(
                "/simulations/new",
                data={
                    "case_name": "SELFTEST-LAMMPS-01",
                    "workspace_id": str(simulation_workspace["id"]),
                },
            ),
        )
    if dataset_workspace:
        _check_response(
            failures,
            "workspace dataset create",
            client.post(
                "/upload",
                data={
                    "title": "自检工作区数据集",
                    "kind": "dataset",
                    "workspace_id": str(dataset_workspace["id"]),
                },
                files={"files": ("selftest.csv", b"x,y\n1,2\n", "text/csv")},
            ),
        )
    with connect() as conn:
        if experiment_workspace and conn.execute(
            "SELECT COUNT(*) n FROM experiments WHERE sample_id='SELFTEST-EG-01' AND workspace_id=?",
            (experiment_workspace["id"],),
        ).fetchone()["n"] != 1:
            failures.append("experiment record was not scoped to its personal workspace")
        if simulation_workspace and conn.execute(
            "SELECT COUNT(*) n FROM simulations WHERE case_name='SELFTEST-LAMMPS-01' AND workspace_id=?",
            (simulation_workspace["id"],),
        ).fetchone()["n"] != 1:
            failures.append("simulation record was not scoped to its personal workspace")
        if dataset_workspace and conn.execute(
            "SELECT COUNT(*) n FROM entries WHERE title='自检工作区数据集' AND workspace_id=?",
            (dataset_workspace["id"],),
        ).fetchone()["n"] != 1:
            failures.append("dataset record was not scoped to its personal workspace")

    dashboard = client.get("/")
    _check_response(failures, "pending review dashboard", dashboard)
    if "到了提取时间" not in dashboard.text:
        failures.append("dashboard did not surface the pending review")
    for marker in (
        "mountain-gate", "今日一诗", "gate-dual-search", "搜知识库", "联网找论文",
        "gate-shortcuts", "home-workbench-dock", "ML", "MD", "COMSOL", "本地优先 · 联机关闭",
    ):
        if marker not in dashboard.text:
            failures.append(f"light mountain-gate dashboard missed: {marker}")
    if 'formaction="http://testserver/search"' not in dashboard.text or 'formaction="http://testserver/discover"' not in dashboard.text:
        failures.append("homepage did not expose both local knowledge and online paper search")
    for removed_marker in ("dashboard-v2", "今日修行闭环", "今日论文卡", "每日一问", "闪念收集", "home-tool-dock"):
        if removed_marker in dashboard.text:
            failures.append(f"removed v2.0 dashboard block was still rendered: {removed_marker}")

    review_landing = client.get("/review")
    _check_response(failures, "review landing separation", review_landing)
    if 'value="beast"' in review_landing.text or 'value="tribulation"' in review_landing.text:
        failures.append("review page still contained independent challenge launch forms")
    trials_landing = client.get("/trials")
    _check_response(failures, "trials landing", trials_landing)
    if "万象秘境" not in trials_landing.text or "五问雷劫" not in trials_landing.text:
        failures.append("independent trials page did not expose both trial types")

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

    first_gate = TRIBULATION_GATES[0]
    target_xp = next(
        stage.threshold for stage in REALM_STAGES if stage.key == first_gate.to_key
    )
    with connect() as conn:
        missing_xp = max(0, target_xp - total_xp(conn))
        if missing_xp:
            conn.execute(
                "INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)",
                ("selftest_realm_setup", missing_xp, "只用于一次性迁移与雷劫自检", now_iso()),
            )
        conn.execute(
            """
            INSERT INTO inventory_items(
                item_key,item_type,quantity,level,equipped,acquired_at,updated_at
            ) VALUES ('tribulation_pill','pill',1,1,0,?,?)
            ON CONFLICT(item_key) DO UPDATE SET
                item_type='pill',quantity=quantity+1,updated_at=excluded.updated_at
            """,
            (now_iso(), now_iso()),
        )
        conn.commit()
    locked_realm = app.current_realm(target_xp)
    if not locked_realm["tribulation_required"]:
        failures.append("reaching a major threshold did not activate the tribulation gate")
    _check_response(
        failures,
        "tribulation start at breakthrough",
        client.post("/review/start", data={"mode": "tribulation"}),
    )
    with connect() as conn:
        tribulation_session = conn.execute(
            "SELECT * FROM review_sessions WHERE mode='tribulation' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not tribulation_session:
        failures.append("eligible tribulation did not create a session")
    else:
        tribulation_questions = json.loads(tribulation_session["questions_json"])
        for index, question in enumerate(tribulation_questions):
            _check_response(
                failures,
                f"tribulation answer {index}",
                client.post(
                    f"/review/sessions/{tribulation_session['id']}/answer",
                    data={
                        "question_index": str(index),
                        "answer": str(question.get("evidence", "")),
                    },
                ),
            )
        with connect() as conn:
            attempt = conn.execute(
                "SELECT * FROM realm_tribulations WHERE session_id=?",
                (tribulation_session["id"],),
            ).fetchone()
        if not attempt or attempt["status"] != "passed":
            failures.append("high-evidence tribulation answers did not unlock the gate")
        elif app.current_realm(total_xp())["key"] != first_gate.to_key:
            failures.append("passed tribulation did not advance the visible realm")

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

    realm_names = "\n".join(["mortal=见习研究者", "body_early=证据学徒"])
    nav_labels = "\n".join(["dashboard=科研台", "alchemy=实验炼丹房", "group_workspaces=我的实验空间"])
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
                "poem_pool": "问渠那得清如许？为有源头活水来。——朱熹\n纸上得来终觉浅，绝知此事要躬行。——陆游",
            },
        ),
    )
    if get_setting("site_name") != "自检科研系统":
        failures.append("site personalization was not saved")
    saved_nav = json.loads(get_setting("nav_labels", "{}"))
    if saved_nav.get("dashboard") != "科研台" or saved_nav.get("alchemy") != "实验炼丹房":
        failures.append("navigation personalization was not saved")

    avatar_buffer = io.BytesIO()
    Image.new("RGB", (96, 96), "#8b654d").save(avatar_buffer, format="PNG")
    _check_response(
        failures,
        "avatar upload",
        client.post(
            "/profile/avatar",
            data={
                "avatar_action": "upload",
                "avatar_choice": "研",
                "avatar_custom": "",
            },
            files={"avatar": ("avatar.png", avatar_buffer.getvalue(), "image/png")},
        ),
    )
    avatar_file = get_setting("avatar_file", "")
    if not avatar_file or not (app.PROFILE_DIR / avatar_file).is_file():
        failures.append("avatar upload did not create a portable profile image")

    package_response = client.get("/online/personalization/export")
    _check_response(failures, "personalization export", package_response)
    try:
        package = json.loads(package_response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        package = {}
        failures.append("personalization export was not valid JSON")
    if package.get("format") != "research-cultivation-personalization-v5":
        failures.append("personalization export did not use the v5 format")
    if len(package.get("theme", {}).get("realm_names", {})) != 39:
        failures.append("personalization export did not include the full realm map")
    if not package.get("workspaces"):
        failures.append("personalization export did not include workspace definitions")
    if not package.get("avatar_image", {}).get("data_base64"):
        failures.append("personalization export did not include the uploaded avatar")
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

    legacy_package = {
        "format": "research-cultivation-personalization-v1",
        "theme": {
            "realm_names": [
                "旧包凡人", "旧包炼气一层", "旧包炼气中期", "旧包炼气圆满",
                "旧包筑基初期", "旧包筑基圆满", "旧包金丹初成", "旧包金丹圆满",
                "旧包元婴", "旧包化神", "旧包炼虚", "旧包合体", "旧包大乘", "旧包渡劫",
            ],
            "nav_labels": {"dashboard": "旧包首页"},
        },
        "profile": package.get("profile", {}),
    }
    _check_response(
        failures,
        "legacy personalization import",
        client.post(
            "/online/personalization/import",
            files={
                "file": (
                    "personalization-v1.json",
                    json.dumps(legacy_package, ensure_ascii=False).encode("utf-8"),
                    "application/json",
                )
            },
        ),
    )
    imported_legacy_realms = json.loads(get_setting("realm_names", "{}"))
    imported_legacy_nav = json.loads(get_setting("nav_labels", "{}"))
    if len(imported_legacy_realms) != 39 or imported_legacy_realms.get("mortal") != "旧包凡人":
        failures.append("legacy realm labels were not expanded without losing custom names")
    if imported_legacy_nav.get("dashboard") != "旧包首页" or "group_workspaces" not in imported_legacy_nav:
        failures.append("legacy navigation labels were not merged with new customizable items")
    _check_response(
        failures,
        "restore current personalization",
        client.post(
            "/online/personalization/import",
            files={
                "file": (
                    "personalization-v5.json",
                    json.dumps(package, ensure_ascii=False).encode("utf-8"),
                    "application/json",
                )
            },
        ),
    )

    portable_knowledge = client.get("/knowledge/export")
    _check_response(failures, "portable knowledge export", portable_knowledge)
    try:
        with zipfile.ZipFile(io.BytesIO(portable_knowledge.content)) as archive:
            names = archive.namelist()
        if not any(name.startswith("entries/") and name.endswith(".md") for name in names):
            failures.append("knowledge export did not create Markdown entries")
        if not any(name.startswith("attachments/") for name in names):
            failures.append("knowledge export did not include original attachments")
    except zipfile.BadZipFile:
        failures.append("portable knowledge export was not a valid ZIP")


def main() -> None:
    integration = "--integration" in sys.argv
    client = TestClient(app.app)
    pages = [
        "/", "/cultivation", "/daily", "/review", "/trials", "/retreat", "/alchemy", "/world", "/profile", "/plans",
        "/foundation", "/assistant", "/notes/new", "/library", "/search", "/discover", "/workspaces", "/settings", "/online",
    ]
    failures = []
    for page in pages:
        response = client.get(page)
        _check_response(failures, page, response)
    daily_navigation = client.get("/daily")
    navigation_groups = [
        "今日修炼",
        "知识与交付",
        "我的工作区",
        "秘境与成长",
        "协作与系统",
    ]
    group_positions = [daily_navigation.text.find(label) for label in navigation_groups]
    if any(position < 0 for position in group_positions):
        failures.append("expanded navigation did not show every expected category")
    elif group_positions != sorted(group_positions):
        failures.append("navigation categories were not ordered by expected frequency")
    if "nav-more" in daily_navigation.text:
        failures.append("desktop navigation still rendered a collapsed tools section")
    capabilities = client.get("/api/sync/capabilities")
    _check_response(failures, "sync capability interface", capabilities)
    if capabilities.status_code == 200:
        capability_data = capabilities.json()
        if capability_data.get("active_backend", {}).get("enabled"):
            failures.append("scale-ready sync interface was not disabled by default")
        if capability_data.get("data_policy", {}).get("cloud_v2_implemented"):
            failures.append("reserved cloud backend incorrectly reported as implemented")
        reliability = capability_data.get("reliability_policy", {})
        expected_reliability = {
            "auto_timeout_seconds": 1.5,
            "failure_threshold": 3,
            "circuit_pause_seconds": 300,
            "dead_letter_attempts": 6,
            "respects_retry_after": True,
        }
        for key, expected in expected_reliability.items():
            if reliability.get(key) != expected:
                failures.append(f"sync reliability policy mismatch for {key}")
    knowledge_export = client.get("/knowledge/export")
    _check_response(failures, "knowledge export", knowledge_export)
    try:
        with zipfile.ZipFile(io.BytesIO(knowledge_export.content)) as archive:
            names = set(archive.namelist())
        if not {"README.md", "manifest.json", "knowledge.json"}.issubset(names):
            failures.append("knowledge export missed its portable index files")
    except zipfile.BadZipFile:
        failures.append("knowledge export was not a valid ZIP")
    with connect() as conn:
        required_tables = {
            "mission_deliveries", "mission_delivery_files", "asset_transactions", "inventory_items",
            "player_profile", "easter_eggs", "track_growth", "online_sync_queue", "online_sync_cache",
            "review_sources", "review_sessions", "review_session_sources", "review_answers",
            "review_snoozes", "realm_tribulations", "special_tasks", "herb_inventory",
            "workspaces",
        }
        found = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(required_tables - found)
        if missing:
            failures.append("missing tables: " + ", ".join(missing))
        if conn.execute("SELECT COUNT(*) n FROM study_plans").fetchone()["n"] < 1:
            failures.append("no study plan")
        if conn.execute("SELECT COUNT(*) n FROM daily_missions").fetchone()["n"] < 1:
            failures.append("no daily missions")
        default_keys = {
            row["workspace_key"]
            for row in conn.execute(
                """
                SELECT workspace_key FROM workspaces
                WHERE workspace_key IN (
                    'eg-lab','lammps-lab','dataset-lab','ml-lab','md-lab','comsol-lab'
                )
                """
            )
        }
        if default_keys != {
            "eg-lab", "lammps-lab", "dataset-lab", "ml-lab", "md-lab", "comsol-lab",
        }:
            failures.append("six default workspaces were not initialized")
    if get_setting("portable_version") != "2.0.2":
        failures.append("portable version was not migrated to 2.0.2")
    if len(REALM_STAGES) != 39:
        failures.append(f"realm system expected 39 stages, got {len(REALM_STAGES)}")
    requirements = [stage.required_xp for stage in REALM_STAGES[1:]]
    if len(requirements) != len(set(requirements)):
        failures.append("realm XP requirements were not unique per stage")
    if not TRIBULATION_GATES:
        failures.append("no major breakthrough gates were defined")
    else:
        first_gate = TRIBULATION_GATES[0]
        target_xp = next(
            stage.threshold for stage in REALM_STAGES if stage.key == first_gate.to_key
        )
        locked = realm_state(target_xp, passed_gate_keys=())
        unlocked = realm_state(target_xp, passed_gate_keys={first_gate.key})
        if not locked["tribulation_required"] or locked["key"] != first_gate.from_key:
            failures.append("Golden-Core-plus breakthrough was not locked before tribulation")
        if unlocked["key"] != first_gate.to_key:
            failures.append("passed tribulation did not unlock the target realm")
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
        print("Core pages, v2.0.2 light mountain-gate dashboard, six workspaces, sync guardrails, knowledge export and local database are ready.")


if __name__ == "__main__":
    main()
