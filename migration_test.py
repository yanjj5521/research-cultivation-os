from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="research-os-v220-upgrade-") as root:
        os.environ["RESEARCH_OS_DATA_DIR"] = root

        import db
        from runtime_paths import STORAGE_ROOT
        from version import APP_VERSION

        db.init_db()
        ts = db.now_iso()
        upload = STORAGE_ROOT / "uploads" / "v220-preserved-result.txt"
        upload.parent.mkdir(parents=True, exist_ok=True)
        upload.write_bytes(b"v2.2 research evidence must survive an in-place upgrade\n")

        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO entries(
                    title,kind,domain,tags,summary,content,file_path,original_name,
                    mime_type,file_size,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "v2.2 保留资料",
                    "document",
                    "电化学",
                    "升级,证据",
                    "旧版原始附件",
                    "不要在升级时覆盖",
                    upload.name,
                    upload.name,
                    "text/plain",
                    upload.stat().st_size,
                    ts,
                    ts,
                ),
            )
            project_id = conn.execute(
                """
                INSERT INTO research_projects(
                    title,research_question,rationale,target_outcome,success_criteria,
                    current_state,constraints_text,search_query,status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "v2.2 真实旧课题",
                    "旧数据库升级后证据链是否保留？",
                    "版本迁移验证",
                    "数据原样保留",
                    "表、记录、附件与配置全部不丢",
                    "已有旧版记录",
                    "不能依赖人工复制",
                    "database migration evidence",
                    "active",
                    ts,
                    ts,
                ),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO project_milestones(
                    project_id,stage_key,title,criterion,deliverable,status,sort_order,
                    created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    project_id,
                    "problem",
                    "旧版证据闸门",
                    "原位升级后仍可读取",
                    "迁移报告",
                    "active",
                    10,
                    ts,
                    ts,
                ),
            )
            conn.execute(
                """
                INSERT INTO inventory_items(
                    item_key,item_type,quantity,level,equipped,acquired_at,updated_at
                ) VALUES ('qingxin_slip','artifact',1,3,1,?,?)
                ON CONFLICT(item_key) DO UPDATE SET
                    item_type='artifact',quantity=1,level=3,equipped=1,updated_at=excluded.updated_at
                """,
                (ts, ts),
            )
            conn.execute(
                "UPDATE workspaces SET name='旧版材料模拟空间',objective='保留旧工作区个性化' "
                "WHERE workspace_key='md-lab'"
            )
            conn.execute(
                "INSERT INTO settings(key,value) VALUES ('site_name','旧版科研生涯站') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )
            conn.execute(
                "INSERT INTO settings(key,value) VALUES ('sync_provider','disabled') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )
            conn.execute(
                "INSERT INTO settings(key,value) VALUES ('researcher_name','准研一修士') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )
            conn.execute(
                "UPDATE player_profile SET display_name='准研一修士',bio='旧版个人简介' WHERE id=1"
            )
            conn.execute(
                "INSERT INTO settings(key,value) VALUES ('portable_version','2.2.0') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )
            conn.execute("DROP TABLE career_moments")
            snapshot = {
                table: int(
                    conn.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]
                )
                for table in (
                    "study_plans",
                    "daily_missions",
                    "entries",
                    "research_projects",
                    "project_milestones",
                    "workspaces",
                    "asset_transactions",
                    "inventory_items",
                )
            }
            conn.commit()

        db.init_db()

        with db.connect() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert "career_moments" in tables
            for table, expected in snapshot.items():
                actual = int(
                    conn.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]
                )
                assert actual == expected, f"{table} changed from {expected} to {actual}"
            assert db.get_setting("portable_version") == APP_VERSION
            assert db.get_setting("site_name") == "旧版科研生涯站"
            assert db.get_setting("sync_provider") == "disabled"
            assert db.get_setting("researcher_name") == "修士"
            profile = conn.execute(
                "SELECT display_name,bio FROM player_profile WHERE id=1"
            ).fetchone()
            assert profile["display_name"] == "修士"
            assert profile["bio"] == "旧版个人简介"
            project = conn.execute(
                "SELECT * FROM research_projects WHERE title='v2.2 真实旧课题'"
            ).fetchone()
            assert project and project["status"] == "active"
            artifact = conn.execute(
                "SELECT level,equipped FROM inventory_items WHERE item_key='qingxin_slip'"
            ).fetchone()
            assert artifact and int(artifact["level"]) == 3 and int(artifact["equipped"]) == 1
            workspace = conn.execute(
                "SELECT name,objective FROM workspaces WHERE workspace_key='md-lab'"
            ).fetchone()
            assert workspace["name"] == "旧版材料模拟空间"
            assert workspace["objective"] == "保留旧工作区个性化"
            nav_layout = db.normalize_nav_layout(
                json.loads(db.get_setting("nav_layout", "[]"))
            )
            assert len(nav_layout) == 5
            assert nav_layout[0]["key"] == "cultivation"
            assert any(
                item["key"] == "workspace_shortcuts"
                for group in nav_layout
                for item in group["items"]
            )

        assert upload.read_bytes() == b"v2.2 research evidence must survive an in-place upgrade\n"

        custom_layout = db.normalize_nav_layout(
            [
                {
                    "key": "system",
                    "items": [
                        {"key": "online", "visible": True},
                        {"key": "assistant", "visible": False},
                        {"key": "settings", "visible": False},
                    ],
                }
            ]
        )
        db.set_setting(
            "nav_layout",
            json.dumps(custom_layout, ensure_ascii=False),
        )
        db.init_db()
        preserved_layout = json.loads(db.get_setting("nav_layout", "[]"))
        assert preserved_layout[0]["key"] == "system"
        assert {
            item["key"]: item["visible"]
            for item in preserved_layout[0]["items"]
        }["assistant"] is False

        with db.connect() as conn:
            conn.execute(
                "UPDATE settings SET value='林同学' WHERE key='researcher_name'"
            )
            conn.execute(
                "UPDATE player_profile SET display_name='林同学' WHERE id=1"
            )
            conn.commit()
        db.init_db()
        assert db.get_setting("researcher_name") == "林同学"
        with db.connect() as conn:
            assert conn.execute(
                "SELECT display_name FROM player_profile WHERE id=1"
            ).fetchone()["display_name"] == "林同学"

    print("V2.2.0 IN-PLACE MIGRATION TEST PASS")
    print("Plans, projects, evidence, attachments, customization, artifacts and custom names survived.")


if __name__ == "__main__":
    main()
