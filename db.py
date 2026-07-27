from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "research_os.db"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction() -> Iterable[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _add_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db() -> None:
    with transaction() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'document',
                domain TEXT NOT NULL DEFAULT '未分类',
                tags TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                file_path TEXT,
                original_name TEXT,
                mime_type TEXT,
                file_size INTEGER NOT NULL DEFAULT 0,
                dataset_rows INTEGER,
                dataset_columns INTEGER,
                dataset_schema TEXT NOT NULL DEFAULT '[]',
                dataset_preview TEXT NOT NULL DEFAULT '[]',
                favorite INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                entry_id INTEGER,
                xp INTEGER NOT NULL DEFAULT 0,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                xp INTEGER NOT NULL DEFAULT 10,
                completed INTEGER NOT NULL DEFAULT 0,
                recurring TEXT NOT NULL DEFAULT 'once',
                due_date TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id TEXT NOT NULL UNIQUE,
                experiment_date TEXT,
                title TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planned',
                eg_content REAL,
                eg_unit TEXT NOT NULL DEFAULT 'wt%',
                water_cement_ratio REAL,
                compaction_pressure REAL,
                compaction_unit TEXT NOT NULL DEFAULT 'MPa',
                thickness_cm REAL,
                area_cm2 REAL,
                electrolyte TEXT NOT NULL DEFAULT '',
                voltage_min REAL,
                voltage_max REAL,
                scan_rate REAL,
                scan_rate_unit TEXT NOT NULL DEFAULT 'mV/s',
                specific_capacitance REAL,
                capacitance_unit TEXT NOT NULL DEFAULT 'F/g',
                conductivity REAL,
                conductivity_unit TEXT NOT NULL DEFAULT 'S/m',
                compressive_strength REAL,
                strength_unit TEXT NOT NULL DEFAULT 'MPa',
                hypothesis TEXT NOT NULL DEFAULT '',
                observations TEXT NOT NULL DEFAULT '',
                conclusion TEXT NOT NULL DEFAULT '',
                next_step TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                attachment_entry_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(attachment_entry_id) REFERENCES entries(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS simulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_name TEXT NOT NULL,
                project_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'NEW',
                engine TEXT NOT NULL DEFAULT 'LAMMPS',
                engine_version TEXT NOT NULL DEFAULT '',
                ensemble TEXT NOT NULL DEFAULT '',
                forcefield TEXT NOT NULL DEFAULT '',
                atoms INTEGER,
                steps INTEGER,
                temperature REAL,
                timestep REAL,
                last_step INTEGER,
                last_temp REAL,
                last_etotal REAL,
                warnings INTEGER NOT NULL DEFAULT 0,
                errors INTEGER NOT NULL DEFAULT 0,
                run_command TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                folder_path TEXT NOT NULL DEFAULT '',
                summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS simulation_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'other',
                file_path TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(simulation_id) REFERENCES simulations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS research_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                icon TEXT NOT NULL DEFAULT '◇',
                objective TEXT NOT NULL DEFAULT '',
                current_stage TEXT NOT NULL DEFAULT '',
                next_focus TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_plan_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                deliverable TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planned',
                priority TEXT NOT NULL DEFAULT 'normal',
                due_date TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(track_id) REFERENCES research_tracks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS research_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                storage_key TEXT NOT NULL UNIQUE,
                file_count INTEGER NOT NULL DEFAULT 0,
                total_size INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(track_id) REFERENCES research_tracks(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS research_folder_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL,
                relative_path TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                original_name TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(folder_id) REFERENCES research_folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS study_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                current_day INTEGER NOT NULL DEFAULT 1,
                total_days INTEGER NOT NULL DEFAULT 30,
                status TEXT NOT NULL DEFAULT 'active',
                source_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_missions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                day_index INTEGER NOT NULL,
                category TEXT NOT NULL DEFAULT '主线',
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                deliverable TEXT NOT NULL DEFAULT '',
                duration_minutes INTEGER NOT NULL DEFAULT 30,
                xp INTEGER NOT NULL DEFAULT 10,
                optional INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0,
                xp_awarded INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(plan_id) REFERENCES study_plans(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS daily_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                day_index INTEGER NOT NULL,
                mood TEXT NOT NULL DEFAULT 'steady',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(plan_id, day_index),
                FOREIGN KEY(plan_id) REFERENCES study_plans(id) ON DELETE CASCADE
            );



            CREATE TABLE IF NOT EXISTS mission_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                storage_key TEXT NOT NULL UNIQUE,
                file_count INTEGER NOT NULL DEFAULT 0,
                total_size INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(mission_id) REFERENCES daily_missions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS mission_delivery_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                delivery_id INTEGER NOT NULL,
                relative_path TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                original_name TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(delivery_id) REFERENCES mission_deliveries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS asset_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_key TEXT NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                mission_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(mission_id) REFERENCES daily_missions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS inventory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_key TEXT NOT NULL UNIQUE,
                item_type TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                level INTEGER NOT NULL DEFAULT 1,
                equipped INTEGER NOT NULL DEFAULT 0,
                acquired_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS player_profile (
                id INTEGER PRIMARY KEY CHECK (id=1),
                display_name TEXT NOT NULL DEFAULT '准研一修士',
                title TEXT NOT NULL DEFAULT '水泥基能源材料探索者',
                bio TEXT NOT NULL DEFAULT '',
                skills TEXT NOT NULL DEFAULT '',
                capabilities TEXT NOT NULL DEFAULT '',
                goals TEXT NOT NULL DEFAULT '',
                avatar_symbol TEXT NOT NULL DEFAULT '道',
                featured_item_key TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS easter_eggs (
                egg_key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                unlocked INTEGER NOT NULL DEFAULT 0,
                discovered_at TEXT
            );

            CREATE TABLE IF NOT EXISTS track_growth (
                track_id INTEGER PRIMARY KEY,
                bonus_points INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(track_id) REFERENCES research_tracks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS online_sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_uuid TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                synced_at TEXT
            );

            CREATE TABLE IF NOT EXISTS online_sync_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS review_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                source_text TEXT NOT NULL,
                storage_key TEXT NOT NULL DEFAULT '',
                source_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(source_type, source_id)
            );

            CREATE TABLE IF NOT EXISTS review_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL DEFAULT 'yesterday',
                title TEXT NOT NULL,
                source_date TEXT NOT NULL DEFAULT '',
                questions_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                provider TEXT NOT NULL DEFAULT '离线规则',
                fallback_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS review_session_sources (
                session_id INTEGER NOT NULL,
                review_source_id INTEGER NOT NULL,
                PRIMARY KEY(session_id, review_source_id),
                FOREIGN KEY(session_id) REFERENCES review_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(review_source_id) REFERENCES review_sources(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS review_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                question_index INTEGER NOT NULL,
                answer TEXT NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0,
                level TEXT NOT NULL DEFAULT 'needs_review',
                feedback TEXT NOT NULL DEFAULT '',
                evidence_quote TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0,
                provider TEXT NOT NULL DEFAULT '',
                self_rating TEXT NOT NULL DEFAULT '',
                next_due TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(session_id, question_index),
                FOREIGN KEY(session_id) REFERENCES review_sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS review_snoozes (
                review_day TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS special_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                deliverable TEXT NOT NULL DEFAULT '',
                why_it_matters TEXT NOT NULL DEFAULT '',
                difficulty INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'offered',
                provider TEXT NOT NULL DEFAULT '离线规则',
                fallback_reason TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL DEFAULT '',
                review_text TEXT NOT NULL DEFAULT '',
                storage_key TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                accepted_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS herb_inventory (
                grade INTEGER PRIMARY KEY,
                herb_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_entries_kind ON entries(kind);
            CREATE INDEX IF NOT EXISTS idx_entries_domain ON entries(domain);
            CREATE INDEX IF NOT EXISTS idx_entries_updated ON entries(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_activities_created ON activities(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_experiments_date ON experiments(experiment_date DESC);
            CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);
            CREATE INDEX IF NOT EXISTS idx_simulations_updated ON simulations(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_research_tracks_order ON research_tracks(sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_research_plan_track ON research_plan_items(track_id, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_research_folders_track ON research_folders(track_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_research_folder_files_folder ON research_folder_files(folder_id, relative_path);
            CREATE INDEX IF NOT EXISTS idx_daily_missions_plan_day ON daily_missions(plan_id, day_index, sort_order);
            CREATE INDEX IF NOT EXISTS idx_study_plans_status ON study_plans(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_mission_deliveries_mission ON mission_deliveries(mission_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_delivery_files_delivery ON mission_delivery_files(delivery_id, relative_path);
            CREATE INDEX IF NOT EXISTS idx_asset_transactions_key ON asset_transactions(asset_key, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_online_sync_status ON online_sync_queue(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_review_sources_date ON review_sources(source_date DESC, id);
            CREATE INDEX IF NOT EXISTS idx_review_sessions_status ON review_sessions(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_review_answers_due ON review_answers(next_due, self_rating);
            CREATE INDEX IF NOT EXISTS idx_special_tasks_status ON special_tasks(status, created_at DESC);
            """
        )

        # Upgrade older databases in place.
        _add_column(conn, "entries", "analysis_json TEXT NOT NULL DEFAULT '{}'")
        _add_column(conn, "entries", "indexed_at TEXT")
        _add_column(conn, "entries", "extract_status TEXT NOT NULL DEFAULT 'pending'")
        _add_column(conn, "entries", "content_format TEXT NOT NULL DEFAULT 'plain'")
        _add_column(conn, "daily_missions", "track_id INTEGER")
        _add_column(conn, "daily_missions", "stones_awarded INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "daily_missions", "materials_awarded INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "daily_missions", "postponed_count INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "mission_deliveries", "review_text TEXT NOT NULL DEFAULT ''")
        _add_column(conn, "mission_deliveries", "review_source TEXT NOT NULL DEFAULT 'manual'")

        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                    title, summary, content, tags, domain,
                    content='entries', content_rowid='id',
                    tokenize='unicode61 remove_diacritics 2'
                )
                """
            )
            conn.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
                    INSERT INTO entries_fts(rowid, title, summary, content, tags, domain)
                    VALUES (new.id, new.title, new.summary, new.content, new.tags, new.domain);
                END;
                CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
                    INSERT INTO entries_fts(entries_fts, rowid, title, summary, content, tags, domain)
                    VALUES ('delete', old.id, old.title, old.summary, old.content, old.tags, old.domain);
                END;
                CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
                    INSERT INTO entries_fts(entries_fts, rowid, title, summary, content, tags, domain)
                    VALUES ('delete', old.id, old.title, old.summary, old.content, old.tags, old.domain);
                    INSERT INTO entries_fts(rowid, title, summary, content, tags, domain)
                    VALUES (new.id, new.title, new.summary, new.content, new.tags, new.domain);
                END;
                """
            )
        except sqlite3.OperationalError:
            pass

        defaults = {
            "site_name": "问道科研",
            "researcher_name": "准研一修士",
            "domains": json.dumps(
                [
                    "电化学", "超级电容器", "水泥基能源材料", "膨胀石墨", "分子动力学",
                    "机器学习", "实验方法", "英语与雅思", "科研写作", "未分类",
                ],
                ensure_ascii=False,
            ),
            "ai_mode": "offline",
            "ai_endpoint": "http://127.0.0.1:11434/api/generate",
            "ai_model": "qwen2.5:7b",
            "portable_version": "1.3.0",
            "foundation_master_text": "",
            "hub_url": "",
            "hub_api_token": "",
            "hub_auto_sync": "1",
            "ui_accent": "terracotta",
            "ui_density": "comfortable",
            "ui_scene": "warm",
            "ui_home_motto": "让科研更好玩一点",
            "ui_home_poem": "纸上得来终觉浅，绝知此事要躬行。——陆游",
            "avatar_file": "",
            "review_popup": "1",
            "realm_names": json.dumps(
                [
                    "凡人", "炼气一层", "炼气中期", "炼气圆满", "筑基初期", "筑基圆满",
                    "金丹初成", "金丹圆满", "元婴境", "化神境", "炼虚境", "合体境", "大乘境", "渡劫境",
                ],
                ensure_ascii=False,
            ),
            "nav_labels": json.dumps(
                {
                    "dashboard": "主页", "daily": "每日任务", "review": "昨日复盘",
                    "plans": "近期计划", "retreat": "闭关计时", "alchemy": "炼丹炉", "world": "我的洞府",
                    "profile": "个人主页", "assistant": "AI 协作", "online": "联机同步",
                    "library": "知识库", "folders": "交付文件夹", "note_new": "写笔记",
                    "upload": "上传资料", "search": "全库检索", "discover": "联网找论文",
                    "datasets": "数据集", "experiments": "EG 实验", "simulations": "LAMMPS",
                    "cultivation": "修炼记录", "settings": "设置与备份",
                },
                ensure_ascii=False,
            ),
        }
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        conn.execute("UPDATE settings SET value='1.3.0' WHERE key='portable_version'")
        ts = now_iso()
        conn.execute(
            "INSERT OR IGNORE INTO player_profile(id,display_name,title,bio,skills,capabilities,goals,avatar_symbol,updated_at) VALUES (1,?,?,?,?,?,?,?,?)",
            (
                "准研一修士", "水泥基能源材料探索者",
                "正在用近期计划、真实交付和持续复盘建立自己的科研系统。",
                "电化学基础\n水泥基材料\n膨胀石墨实验\nLAMMPS入门\nPython数据处理",
                "能复现基础案例\n能建立实验台账\n能拆解论文图表\n能用GPT辅助学习与排错",
                "让当前学习留下可复用、可验证、可持续升级的科研资产", "道", ts,
            ),
        )
        if conn.execute("SELECT COUNT(*) n FROM asset_transactions").fetchone()["n"] == 0:
            conn.execute("INSERT INTO asset_transactions(asset_key,amount,reason,created_at) VALUES (?,?,?,?)", ("spirit_stone", 12, "正式版开宗礼包", ts))
            conn.execute("INSERT INTO asset_transactions(asset_key,amount,reason,created_at) VALUES (?,?,?,?)", ("spirit_wood", 4, "正式版开宗礼包", ts))
            conn.execute("INSERT INTO asset_transactions(asset_key,amount,reason,created_at) VALUES (?,?,?,?)", ("mystic_iron", 2, "正式版开宗礼包", ts))
            conn.execute("INSERT INTO asset_transactions(asset_key,amount,reason,created_at) VALUES (?,?,?,?)", ("star_sand", 2, "正式版开宗礼包", ts))
        starter_eggs = [
            ("moon_well", "月影井", "你在洞府角落找到了一口井。科研中的空白，有时比答案更值得凝视。"),
            ("first_delivery", "第一枚玉简", "你第一次用真实交付证明：今天不是只看懂了，而是留下了可复用的痕迹。"),
            ("seven_deliveries", "七日炼心", "七次交付后，你开始从‘知道’走向‘能够稳定做到’。"),
            ("image_note", "画中有道", "一张图进入笔记，文字与视觉开始共同承担思考。"),
            ("all_herbs", "百草同春", "所有方向都萌芽了。广度不是分散，而是让不同能力开始互相供养。"),
        ]
        for egg_key, title, description in starter_eggs:
            conn.execute("INSERT OR IGNORE INTO easter_eggs(egg_key,title,description) VALUES (?,?,?)", (egg_key,title,description))

        # Backfill review sources when an upgraded database already contains
        # deliveries with manually written review text.
        for row in conn.execute(
            """
            SELECT d.id,d.review_text,d.storage_key,d.created_at,m.title
            FROM mission_deliveries d
            JOIN daily_missions m ON m.id=d.mission_id
            WHERE trim(d.review_text)!=''
            """
        ):
            conn.execute(
                """
                INSERT OR IGNORE INTO review_sources(
                    source_type,source_id,title,source_text,storage_key,source_date,created_at
                ) VALUES ('mission_delivery',?,?,?,?,?,?)
                """,
                (
                    row["id"], row["title"], row["review_text"], row["storage_key"],
                    row["created_at"][:10], row["created_at"],
                ),
            )

        track_count = conn.execute("SELECT COUNT(*) AS n FROM research_tracks").fetchone()["n"]
        if track_count == 0:
            starter_tracks = [
                ("电化学", "⚡", "建立电荷—电势—能量—输运的完整概念链，并能独立解释 CV、GCD 与 EIS。", "基础概念与曲线判读", "完成一套可复用的电化学测试与解读模板"),
                ("超级电容器", "◫", "掌握器件结构、性能指标、测试边界与机制表达，形成水泥基体系的评价框架。", "EDLC、赝电容与核心指标", "建立水泥基超级电容器评价清单"),
                ("水泥基能源材料", "▦", "理解水泥孔结构、含水状态、导电相与力学性能之间的耦合。", "水泥材料基础与能源分类", "形成材料—结构—输运—性能地图"),
                ("膨胀石墨", "◆", "围绕 EG 的网络构筑、润湿、压实与界面行为形成主线判断。", "材料特性与预实验", "明确第一篇论文的核心变量与实验矩阵"),
                ("分子动力学", "◎", "从可复现案例起步，逐步建立能回答实验机制问题的模拟能力。", "LAMMPS 基线与后处理", "将一个模拟问题与 EG 实验变量对齐"),
                ("机器学习", "⌘", "围绕结构化实验数据建立清洗、建模、解释和版本管理能力。", "Python 数据处理与特征表", "建立可持续扩展的实验数据集"),
                ("科研写作", "✎", "训练问题提出、证据链、图表叙事和审稿式表达。", "论文拆解与 Figure 叙事", "形成一套自己的论文与汇报模板"),
                ("英语与雅思", "A", "以科研阅读和稳定词汇输入为主，兼顾雅思所需能力。", "词汇与论文局部精读", "建立低负担、长期可持续的英语节奏"),
            ]
            ts = now_iso()
            for order, (name, icon, objective, stage, focus) in enumerate(starter_tracks):
                cur = conn.execute(
                    "INSERT INTO research_tracks(name,icon,objective,current_stage,next_focus,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (name, icon, objective, stage, focus, order, ts, ts),
                )
                track_id = cur.lastrowid
                starter_items = [
                    (f"推进{name}当前主线", "围绕当前阶段持续推进，不设置固定30天截止。", "形成一份可以复用或验证的具体交付", "active", "high", 0),
                    (f"记录{name}关键问题", "只记录会影响下一步决策的问题、异常和判断。", "至少沉淀一个问题—假设—验证闭环", "planned", "normal", 1),
                ]
                for title, desc, deliverable, status, priority, item_order in starter_items:
                    conn.execute(
                        "INSERT INTO research_plan_items(track_id,title,description,deliverable,status,priority,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (track_id, title, desc, deliverable, status, priority, item_order, ts, ts),
                    )

        quest_count = conn.execute("SELECT COUNT(*) AS n FROM quests").fetchone()["n"]
        if quest_count == 0:
            starter_quests = [
                ("录入第一篇核心论文", "上传一篇与你当前方向直接相关的论文，并补充标签。", 25),
                ("写下第一个科研问题", "创建一条问题笔记：现象、可能原因、下一步验证。", 20),
                ("建立第一个数据集档案", "上传 CSV 或 XLSX，并补充变量说明。", 35),
                ("完成一次失败复盘", "记录一次实验或代码失败，以及以后如何避免。", 30),
                ("建立第一个EG实验批次", "把配比、压实、几何尺寸与电化学窗口录入实验模块。", 35),
                ("归档第一个LAMMPS案例", "上传一个包含输入、日志和轨迹的可复现案例。", 40),
            ]
            for title, description, xp in starter_quests:
                conn.execute(
                    "INSERT INTO quests(title, description, xp, created_at) VALUES (?, ?, ?, ?)",
                    (title, description, xp, now_iso()),
                )


def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def log_activity(action: str, xp: int, detail: str = "", entry_id: int | None = None) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO activities(action, entry_id, xp, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (action, entry_id, xp, detail, now_iso()),
        )


def total_xp(conn: sqlite3.Connection | None = None) -> int:
    owns = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT COALESCE(SUM(xp), 0) AS xp FROM activities").fetchone()
        return int(row["xp"])
    finally:
        if owns:
            conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None
