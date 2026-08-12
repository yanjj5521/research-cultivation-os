from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import urllib.request
import webbrowser
from datetime import date
from pathlib import Path

from launchers.server import run_server

HOST = "127.0.0.1"
START_PORT = 5000


def preconfigure_runtime() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--mode", choices=("personal", "team"), default="personal")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--pet", action="store_true", help="Run the detachable, animated research companion.")
    parser.add_argument("--no-pet", action="store_true", help="Do not start the desktop companion with the main window.")
    parser.add_argument("--portable", action="store_true", help="Keep data beside the executable.")
    parser.add_argument("--data-dir", default="", help="Use an explicit data directory.")
    parser.add_argument("--open-data", action="store_true", help="Open the active data directory.")
    parser.add_argument("--self-check", action="store_true", help="Initialize the app and exit.")
    args = parser.parse_args()
    if args.portable:
        executable_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        os.environ["RESEARCH_OS_PORTABLE"] = "1"
        os.environ["RESEARCH_OS_DATA_DIR"] = str(executable_root / "user_data")
    elif args.data_dir:
        os.environ["RESEARCH_OS_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    elif args.self_check:
        # A manual self-check must never add test plans to the user's real data.
        os.environ["RESEARCH_OS_DATA_DIR"] = tempfile.mkdtemp(prefix="research-os-self-check-")
    return args


def is_research_os(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/stats", timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
            return True
        except OSError:
            return False


def choose_port() -> tuple[int, bool]:
    for port in range(START_PORT, START_PORT + 20):
        if is_research_os(port):
            return port, True
        if port_available(port):
            return port, False
    raise RuntimeError("No free local port was found between 5000 and 5019.")


def safe_print(message: str) -> None:
    stream = sys.stdout
    if stream is None:
        return
    try:
        print(message, file=stream)
    except UnicodeEncodeError:
        encoding = stream.encoding or "ascii"
        escaped = message.encode(encoding, errors="backslashreplace").decode(encoding)
        print(escaped, file=stream)


if __name__ == "__main__":
    args = preconfigure_runtime()
    from runtime_paths import DATA_ROOT, ensure_data_layout

    ensure_data_layout()
    if args.pet:
        from desktop_pet import run_pet

        run_pet()
        raise SystemExit(0)
    if args.open_data:
        try:
            os.startfile(DATA_ROOT)  # type: ignore[attr-defined]
        except AttributeError:
            webbrowser.open(DATA_ROOT.as_uri())
        raise SystemExit(0)

    if args.mode == "team":
        if args.self_check:
            from run_hub import packaged_self_check

            packaged_self_check()
            raise SystemExit(0)
        from launchers.team import run_team

        raise SystemExit(
            run_team(
                data_root=DATA_ROOT,
                preferred_port=args.port or 5050,
                host=args.host or "0.0.0.0",
                no_browser=args.no_browser,
                report=safe_print,
            )
        )

    from app import app as web_app
    if args.self_check:
        from fastapi.testclient import TestClient
        from db import connect
        from version import APP_VERSION

        with TestClient(web_app) as client:
            for path in (
                "/",
                "/projects",
                "/career",
                "/world",
                "/workspaces",
                "/settings",
                "/online",
                "/literature-report",
                "/api/stats",
            ):
                response = client.get(path)
                if response.status_code != 200:
                    raise SystemExit(
                        f"Packaged self-check failed: {path} returned HTTP {response.status_code}."
                    )
            homepage = client.get("/").text
            if "gate-dual-search" not in homepage or "data-living-scene" not in homepage:
                raise SystemExit("Packaged self-check failed: the homepage template is incomplete.")
            settings_page = client.get("/settings").text
            if (
                "data-nav-layout-editor" not in settings_page
                or "data-nav-reset" not in settings_page
                or "调整导航" not in settings_page
            ):
                raise SystemExit(
                    "Packaged self-check failed: the navigation editor is incomplete."
                )
            world = client.get("/world")
            if world.status_code != 200 or "购入 · 12 灵石" not in world.text:
                raise SystemExit("Packaged self-check failed: the starter artifact is not affordable.")
            client.post("/world/artifacts/qingxin_slip/buy")
            client.post("/world/artifacts/qingxin_slip/buy")
            client.post("/world/artifacts/measuring_ruler/buy")
            with connect() as conn:
                starter_artifact = conn.execute(
                    "SELECT COUNT(*) n FROM inventory_items WHERE item_key='qingxin_slip'"
                ).fetchone()["n"]
                unavailable_artifact = conn.execute(
                    "SELECT 1 FROM inventory_items WHERE item_key='measuring_ruler'"
                ).fetchone()
                stone_balance = conn.execute(
                    "SELECT COALESCE(SUM(amount),0) n FROM asset_transactions "
                    "WHERE asset_key='spirit_stone'"
                ).fetchone()["n"]
            if starter_artifact != 1 or unavailable_artifact or int(stone_balance) != 0:
                raise SystemExit(
                    "Packaged self-check failed: artifact purchase safeguards are incomplete."
                )
            career_focus = client.post(
                "/career/focus",
                data={
                    "phase": "validate",
                    "focus": "形成可以复核的证据链。",
                    "boundary": "不把单次相关性当作机制。",
                    "success_signal": "至少两类独立证据支持同一判断。",
                    "review_date": "",
                },
            )
            career_moment = client.post(
                "/career/moments/new",
                data={
                    "moment_type": "decision",
                    "title": "打包自检生涯节点",
                    "summary": "验证长期科研记忆可写入。",
                    "evidence": "打包后表单链路",
                    "project_id": "0",
                    "occurred_on": date.today().isoformat(),
                },
            )
            if career_focus.status_code != 200 or career_moment.status_code != 200:
                raise SystemExit("Packaged self-check failed: career compass forms are incomplete.")
            with connect() as conn:
                phase = conn.execute(
                    "SELECT value FROM settings WHERE key='career_phase'"
                ).fetchone()
                moment = conn.execute(
                    "SELECT 1 FROM career_moments WHERE title='打包自检生涯节点'"
                ).fetchone()
            if not phase or phase["value"] != "validate" or not moment:
                raise SystemExit("Packaged self-check failed: career memory was not persisted.")
            plans_page = client.get("/plans")
            if "planImportForm" not in plans_page.text or "导入并立即进入 Day 1" not in plans_page.text:
                raise SystemExit("Packaged self-check failed: plan import controls are incomplete.")
            with connect() as conn:
                original = conn.execute(
                    "SELECT id FROM study_plans WHERE status='active' ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
            copied_plan = """电化学资产化入门计划
用5天形成可复用的电化学资产
修炼任务
• [进阶] 建立电化学最小概念与计算资产 | 验收：概念表与计算模板
第一天｜量纲起点
• [重点] 完成 Q-I-V-C-E-P 概念图 | 45分钟 | 交付：概念图
第二天｜CV 判读
• [可选] 判读一张 CV 曲线 | 20min | 交付：三句话判读
"""
            imported = client.post("/plans/import", data={"plan_text": copied_plan})
            if imported.status_code != 200 or "电化学资产化入门计划" not in imported.text:
                raise SystemExit("Packaged self-check failed: a copied plan could not be imported.")
            with connect() as conn:
                active = conn.execute(
                    "SELECT id,name FROM study_plans WHERE status='active'"
                ).fetchall()
            if len(active) != 1 or active[0]["name"] != "电化学资产化入门计划":
                raise SystemExit("Packaged self-check failed: imported plan was not activated.")
            client.post("/plans/999999999/activate")
            with connect() as conn:
                after_invalid = conn.execute(
                    "SELECT id FROM study_plans WHERE status='active'"
                ).fetchall()
            if len(after_invalid) != 1 or int(after_invalid[0]["id"]) != int(active[0]["id"]):
                raise SystemExit("Packaged self-check failed: invalid activation changed the current plan.")
            if original:
                client.post(f"/plans/{original['id']}/activate")
                with connect() as conn:
                    restored = conn.execute(
                        "SELECT id FROM study_plans WHERE status='active'"
                    ).fetchall()
                if len(restored) != 1 or int(restored[0]["id"]) != int(original["id"]):
                    raise SystemExit("Packaged self-check failed: archived plan activation failed.")
            created = client.post(
                "/projects/new",
                data={
                    "title": "打包自检课题",
                    "research_question": "变量 A 是否在约束 C 下改变结果 B？",
                    "rationale": "验证课题推进的真实表单链路。",
                    "target_outcome": "形成可审查结论。",
                    "success_criteria": "至少三次重复且效应达到预设阈值。",
                    "current_state": "已有一组预实验。",
                    "constraints_text": "样品有限。",
                    "search_query": "",
                },
                follow_redirects=False,
            )
            if created.status_code != 303:
                raise SystemExit("Packaged self-check failed: a research project could not be created.")
            with connect() as conn:
                project = conn.execute(
                    "SELECT id FROM research_projects WHERE title='打包自检课题' ORDER BY id DESC LIMIT 1"
                ).fetchone()
                gates = (
                    conn.execute(
                        "SELECT id,title,criterion,deliverable,status FROM project_milestones "
                        "WHERE project_id=? ORDER BY sort_order,id",
                        (project["id"],),
                    ).fetchall()
                    if project
                    else []
                )
            if not project or len(gates) != 5 or gates[0]["status"] != "active":
                raise SystemExit("Packaged self-check failed: project evidence gates are incomplete.")
            client.post(
                f"/projects/{project['id']}/milestones/{gates[0]['id']}/save",
                data={
                    "title": gates[0]["title"],
                    "criterion": gates[0]["criterion"],
                    "deliverable": gates[0]["deliverable"],
                    "status": "passed",
                },
            )
            with connect() as conn:
                rejected = conn.execute(
                    "SELECT status FROM project_milestones WHERE id=?", (gates[0]["id"],)
                ).fetchone()
            if not rejected or rejected["status"] != "active":
                raise SystemExit("Packaged self-check failed: an empty evidence gate was accepted.")
            client.post(
                f"/projects/{project['id']}/milestones/{gates[0]['id']}/save",
                data={
                    "title": gates[0]["title"],
                    "criterion": gates[0]["criterion"],
                    "deliverable": gates[0]["deliverable"],
                    "status": "passed",
                    "evidence": "问题卡已保存，对照与边界均已写明。",
                    "decision": "Go：进入先例检索。",
                },
            )
            with connect() as conn:
                states = [
                    row["status"]
                    for row in conn.execute(
                        "SELECT status FROM project_milestones WHERE project_id=? ORDER BY sort_order,id",
                        (project["id"],),
                    )
                ]
            if states[:2] != ["passed", "active"]:
                raise SystemExit("Packaged self-check failed: the next evidence gate was not activated.")
            project_plan = client.get(f"/projects/{project['id']}/plan")
            if project_plan.status_code != 200 or "导入并立即进入 Day 1" not in project_plan.text:
                raise SystemExit("Packaged self-check failed: the project plan bridge is incomplete.")
        safe_print(f"问道科研 {APP_VERSION} self-check PASS")
        safe_print(f"Data: {DATA_ROOT}")
        raise SystemExit(0)

    port, already_running = (
        (args.port, False) if args.port and port_available(args.port) else choose_port()
    )
    url = f"http://{HOST}:{port}"
    if args.no_browser:
        if already_running:
            safe_print(f"问道科研 is already running: {url}")
            raise SystemExit(0)
        safe_print("\n问道科研")
        safe_print(f"Open: {url}")
        safe_print(f"Data: {DATA_ROOT}")
        safe_print("Close this window or press Ctrl+C to stop the local server.\n")
        run_server(
            web_app,
            host=HOST,
            port=port,
            data_root=DATA_ROOT,
        )
        raise SystemExit(0)

    from desktop_shell import open_desktop_window, start_local_service, wait_until_ready

    pet_process = None
    if not args.no_pet:
        pet_command = [sys.executable]
        if not getattr(sys, "frozen", False):
            pet_command.append(str(Path(__file__).resolve()))
        pet_command.append("--pet")
        startup = getattr(subprocess, "STARTUPINFO", lambda: None)()
        if startup is not None:
            startup.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        try:
            pet_process = subprocess.Popen(
                pet_command,
                startupinfo=startup,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            pet_process = None

    server = None
    if already_running:
        safe_print(f"问道科研 desktop window: {url}")
    else:
        server, _thread = start_local_service(web_app, host=HOST, port=port, data_root=DATA_ROOT)
        if not wait_until_ready(lambda: is_research_os(port)):
            server.should_exit = True
            raise SystemExit("问道科研本地服务启动失败，请查看数据目录中的 logs。")
    try:
        open_desktop_window(url)
    finally:
        if server is not None:
            server.should_exit = True
        if pet_process is not None and pet_process.poll() is None:
            pet_process.terminate()
