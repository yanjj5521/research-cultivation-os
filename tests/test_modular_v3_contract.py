from __future__ import annotations

import ast
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent


def route_manifest(paths: list[Path]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    not isinstance(decorator, ast.Call)
                    or not isinstance(decorator.func, ast.Attribute)
                    or decorator.func.attr not in {"get", "post", "put", "delete", "patch"}
                    or not decorator.args
                    or not isinstance(decorator.args[0], ast.Constant)
                    or not isinstance(decorator.args[0].value, str)
                ):
                    continue
                name = node.name
                for keyword in decorator.keywords:
                    if (
                        keyword.arg == "name"
                        and isinstance(keyword.value, ast.Constant)
                        and isinstance(keyword.value.value, str)
                    ):
                        name = keyword.value.value
                items.append(
                    {
                        "method": decorator.func.attr.upper(),
                        "path": decorator.args[0].value,
                        "name": name,
                    }
                )
    return sorted(items, key=lambda item: (item["path"], item["method"], item["name"]))


class ModularV3ContractTests(unittest.TestCase):
    def test_learning_first_surface_is_present(self) -> None:
        # v3.5 used a frozen pixel-surface manifest, which made intentional
        # usability improvements fail CI.  Keep durable product contracts
        # instead: the learning-first tools must remain reachable and the
        # obsolete ChatGPT jump-out must not reappear.
        for relative in (
            "templates/dashboard.html",
            "templates/workbench.html",
            "templates/literature_report.html",
            "templates/idle.html",
            "static/style.css",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        dashboard = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
        workbench = (ROOT / "templates" / "workbench.html").read_text(encoding="utf-8")
        idle = (ROOT / "templates" / "idle.html").read_text(encoding="utf-8")
        self.assertIn("literature_report_page", dashboard)
        self.assertIn("英文精读", workbench)
        self.assertIn("多面板图", workbench)
        self.assertIn("我的壁纸", idle)
        self.assertNotIn("打开 ChatGPT", dashboard + workbench)

    def test_v3_route_contract_is_unchanged(self) -> None:
        expected = json.loads(
            (TESTS / "v3_route_manifest.json").read_text(encoding="utf-8")
        )
        paths = sorted((ROOT / "web" / "routes").glob("*.py"))
        paths += sorted((ROOT / "features").glob("*.py"))
        self.assertEqual(route_manifest(paths), expected)

    def test_team_social_routes_and_safety_boundaries_are_present(self) -> None:
        hub = (ROOT / "hub_app.py").read_text(encoding="utf-8")
        database = (ROOT / "hub_db.py").read_text(encoding="utf-8")
        for marker in (
            'name="hub_forum"',
            'name="hub_chat"',
            'name="hub_market"',
            'name="hub_red_packet_send"',
            'name="hub_trade_accept"',
            "verify_csrf(request, csrf_value)",
            "SOCIAL_TRANSFER_LIMITS",
        ):
            self.assertIn(marker, hub)
        for marker in (
            "CREATE TABLE IF NOT EXISTS hub_forum_posts",
            "CREATE TABLE IF NOT EXISTS hub_chat_messages",
            "CREATE TABLE IF NOT EXISTS hub_social_transfers",
            '"cultivation"',
        ):
            self.assertIn(marker, database)
        for template in ("forum.html", "chat.html", "market.html"):
            self.assertTrue((ROOT / "hub_templates" / template).is_file(), template)

    def test_application_and_database_are_domain_modules(self) -> None:
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        db_source = (ROOT / "db.py").read_text(encoding="utf-8")
        self.assertLessEqual(len(app_source.splitlines()), 20)
        self.assertLessEqual(len(db_source.splitlines()), 45)
        self.assertIn("from web.app import app", app_source)
        self.assertIn("from core.database import", db_source)

        route_modules = {
            path.stem for path in (ROOT / "web" / "routes").glob("*.py")
        }
        self.assertTrue(
            {
                "home",
                "library",
                "settings",
                "analysis",
                "research_tools",
                "foundation",
            }.issubset(route_modules)
        )

    def test_no_old_database_compatibility_code_remains(self) -> None:
        checked = [
            ROOT / "db.py",
            ROOT / "runtime_paths.py",
            ROOT / "run_local.py",
            *sorted((ROOT / "core").glob("*.py")),
        ]
        forbidden = (
            "ALTER TABLE",
            "_add_column",
            "migrate_legacy_data",
            "migrate_adjacent_legacy_data",
            'INSTANCE_DIR / "research_os.db"',
        )
        combined = "\n".join(path.read_text(encoding="utf-8") for path in checked)
        for marker in forbidden:
            self.assertNotIn(marker, combined)
        self.assertIn('DATABASE_FILENAME = "wendao-v3-clean.db"', combined)
        self.assertIn('PRODUCT_DIR_NAME = "WendaoResearchV3"', combined)

    def test_clean_database_is_seeded_once_and_rejects_old_schema(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wendao-v3-db-test-") as temp_dir:
            environment = dict(os.environ)
            environment["RESEARCH_OS_DATA_DIR"] = temp_dir
            environment["PYTHONPATH"] = str(ROOT)
            script = """
from db import DB_PATH, connect, init_db
init_db()
init_db()
with connect() as connection:
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM research_tracks").fetchone()[0] == 8
    assert connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 6
    assert connection.execute("SELECT COUNT(*) FROM quests").fetchone()[0] == 6
    assert connection.execute("SELECT value FROM settings WHERE key='site_name'").fetchone()[0] == "问道科研"
print(DB_PATH.name)
"""
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(result.stdout.strip(), "wendao-v3-clean.db")

        with tempfile.TemporaryDirectory(prefix="wendao-old-db-test-") as temp_dir:
            environment = dict(os.environ)
            environment["RESEARCH_OS_DATA_DIR"] = temp_dir
            environment["PYTHONPATH"] = str(ROOT)
            script = """
import sqlite3
from runtime_paths import INSTANCE_DIR
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
old = INSTANCE_DIR / "wendao-v3-clean.db"
with sqlite3.connect(old) as connection:
    connection.execute("CREATE TABLE old_data(id INTEGER PRIMARY KEY)")
from db import init_db
try:
    init_db()
except RuntimeError:
    print("rejected")
else:
    raise SystemExit("old schema was accepted")
"""
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(result.stdout.strip(), "rejected")

    def test_current_motion_layer_is_isolated(self) -> None:
        base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
        motion = (ROOT / "static" / "motion-vnext.css").read_text(encoding="utf-8")
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("motion-vnext.css", base)
        self.assertIn("vnext-ambient-orbit", base)
        self.assertIn("@keyframes vnext-drift", motion)
        self.assertIn("body.motion-reduced .vnext-ambient", motion)
        self.assertIn("livingScene.addEventListener('pointermove'", javascript)
        self.assertNotIn("requestAnimationFrame", javascript)

    def test_windowed_server_has_no_console_dependency(self) -> None:
        from launchers import server

        with tempfile.TemporaryDirectory(prefix="wendao-v3-log-test-") as temp_dir:
            try:
                with patch.object(server.uvicorn, "run") as run:
                    with patch.object(sys, "stdout", None), patch.object(
                        sys, "stderr", None
                    ):
                        server.run_server(
                            object(),
                            host="127.0.0.1",
                            port=5000,
                            data_root=Path(temp_dir),
                        )
                kwargs = run.call_args.kwargs
                self.assertIsNone(kwargs["log_config"])
                self.assertFalse(kwargs["access_log"])
                self.assertTrue(
                    (Path(temp_dir) / "logs" / "wendao-v3.log").exists()
                )
            finally:
                for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
                    logger = logging.getLogger(name)
                    for handler in logger.handlers[:]:
                        logger.removeHandler(handler)
                        handler.close()

    def test_safe_print_survives_cp1252_console(self) -> None:
        import io

        from run_local import safe_print

        output = io.BytesIO()
        console = io.TextIOWrapper(output, encoding="cp1252", errors="strict")
        with patch.object(sys, "stdout", console):
            safe_print("问道科研 3.6.1 self-check PASS")
            console.flush()
        self.assertEqual(
            output.getvalue().decode("cp1252").strip(),
            r"\u95ee\u9053\u79d1\u7814 3.6.1 self-check PASS",
        )

    def test_release_shell_is_single_program_and_clean_identity(self) -> None:
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "3.6.1")
        spec = (ROOT / "packaging" / "WendaoResearchV3.spec").read_text(
            encoding="utf-8"
        )
        build = (ROOT / "tools" / "build.py").read_text(encoding="utf-8")
        workflow = (
            ROOT / ".github" / "workflows" / "build-v3-modular.yml"
        ).read_text(encoding="utf-8")
        android = (ROOT / "mobile" / "android" / "app" / "build.gradle").read_text(
            encoding="utf-8"
        )
        self.assertIn('name="WendaoResearchV3"', spec)
        self.assertIn("console=False", spec)
        self.assertIn('"portable.flag", "使用说明.txt"', build)
        self.assertNotIn('"启动团队中心.cmd", portable_root', build)
        self.assertIn("Team-Update.zip", build)
        self.assertIn('applicationId "cn.wendao.research.v3.mobile"', android)
        self.assertIn("python tools/build.py --assemble --output out", workflow)
        self.assertIn('$PSNativeCommandUseErrorActionPreference = $true', workflow)
        self.assertIn("Start-Process -FilePath $exe", workflow)
        self.assertIn('"--mode", "team"', workflow)
        self.assertIn("motion-vnext.css", workflow)
        self.assertIn("cn.wendao.research.v3.mobile", workflow)
        self.assertIn("Team-Update.zip", workflow)
        for obsolete in (
            ".github/workflows/release-windows.yml",
            ".github/workflows/validate-development.yml",
            "Restore_Data.cmd",
            "Safe_Update_From_Zip.cmd",
            "restore_data.py",
            "safe_update.py",
            "migration_test.py",
            "packaging/ResearchOS.spec",
            "packaging/ResearchHub.spec",
            "packaging/windows/迁移旧版数据.cmd",
        ):
            self.assertFalse((ROOT / obsolete).exists())


if __name__ == "__main__":
    unittest.main()
