from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable

from runtime_paths import INSTANCE_DIR
from services.progression import (
    default_realm_labels,
    fixed_cultivation_xp,
    fixed_daily_xp,
    normalize_realm_labels,
)
from version import APP_VERSION
from workspace_profiles import DEFAULT_WORKSPACES, profile_for

DB_PATH = INSTANCE_DIR / "research_os.db"

DEFAULT_NAV_LABELS = {
    "dashboard": "主页",
    "daily": "每日任务",
    "cultivation": "修炼记录",
    "review": "温故知新",
    "plans": "近期计划",
    "projects": "课题推进",
    "career": "生涯罗盘",
    "retreat": "闭关计时",
    "trials": "秘境试炼",
    "achievements": "成就图鉴",
    "alchemy": "炼丹炉",
    "world": "我的洞府",
    "profile": "个人主页",
    "assistant": "AI 协作",
    "online": "联机扩展",
    "library": "知识库",
    "folders": "交付文件夹",
    "note_new": "写笔记",
    "upload": "上传资料",
    "search": "全库检索",
    "discover": "联网找论文",
    "workspaces": "工作区管理",
    "settings": "设置与备份",
    "group_cultivation": "今日修炼",
    "group_knowledge": "知识与交付",
    "group_workspaces": "我的工作区",
    "group_growth": "秘境与成长",
    "group_system": "协作与系统",
    "start": "开始修炼",
    "knowledge_export": "一键导出知识库",
    "backup": "完整备份",
}

NAV_GROUP_DEFAULT_ITEMS = {
    "cultivation": (
        "dashboard",
        "cultivation",
        "daily",
        "review",
        "plans",
        "projects",
        "retreat",
    ),
    "knowledge": (
        "library",
        "search",
        "note_new",
        "upload",
        "folders",
        "discover",
    ),
    "workspaces": (
        "workspace_shortcuts",
        "workspaces",
    ),
    "growth": (
        "career",
        "trials",
        "achievements",
        "alchemy",
        "world",
        "profile",
    ),
    "system": (
        "assistant",
        "online",
        "settings",
    ),
}

DEFAULT_NAV_LAYOUT = [
    {
        "key": group_key,
        "items": [
            {"key": item_key, "visible": True}
            for item_key in item_keys
        ],
    }
    for group_key, item_keys in NAV_GROUP_DEFAULT_ITEMS.items()
]

LEGACY_NAV_DEFAULTS = {
    "review": "昨日复盘",
    "online": "联机同步",
    "group_cultivation": "修炼与行动",
    "group_knowledge": "我的知识库",
    "group_system": "系统与工具",
}


def normalize_nav_labels(value: Any) -> dict[str, str]:
    labels = dict(DEFAULT_NAV_LABELS)
    if isinstance(value, dict):
        for key, default in DEFAULT_NAV_LABELS.items():
            candidate = str(value.get(key, "")).strip()[:24]
            if candidate and LEGACY_NAV_DEFAULTS.get(key) != candidate:
                labels[key] = candidate
            elif key not in value:
                labels[key] = default
    return labels


def _nav_visible(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "hidden"}
    if value is None:
        return False
    return bool(value)


def normalize_nav_layout(value: Any) -> list[dict[str, Any]]:
    """Return a complete, forward-compatible navigation layout.

    Groups and items use stable keys. Unknown values are discarded, duplicate
    items are kept only once, and newly introduced items are appended to their
    default group without changing a user's existing order or visibility.
    """

    source = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    seen_groups: set[str] = set()

    for raw_group in source:
        if not isinstance(raw_group, dict):
            continue
        group_key = str(raw_group.get("key", "")).strip()
        if group_key not in NAV_GROUP_DEFAULT_ITEMS or group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        allowed_items = NAV_GROUP_DEFAULT_ITEMS[group_key]
        seen_items: set[str] = set()
        items: list[dict[str, Any]] = []
        raw_items = raw_group.get("items", [])
        if isinstance(raw_items, list):
            for raw_item in raw_items:
                if isinstance(raw_item, str):
                    item_key = raw_item.strip()
                    visible = True
                elif isinstance(raw_item, dict):
                    item_key = str(raw_item.get("key", "")).strip()
                    visible = _nav_visible(raw_item.get("visible", True))
                else:
                    continue
                if item_key not in allowed_items or item_key in seen_items:
                    continue
                seen_items.add(item_key)
                items.append({"key": item_key, "visible": visible})
        for item_key in allowed_items:
            if item_key not in seen_items:
                items.append({"key": item_key, "visible": True})
        normalized.append({"key": group_key, "items": items})

    for group_key, item_keys in NAV_GROUP_DEFAULT_ITEMS.items():
        if group_key in seen_groups:
            continue
        normalized.append(
            {
                "key": group_key,
                "items": [
                    {"key": item_key, "visible": True}
                    for item_key in item_keys
                ],
            }
        )
    return normalized


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


def _add_column(conn: sqlite3.Connection, table: str, definition: str) -> bool:
    name = definition.split()[0]
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
        return True
    return False


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
                workspace_id INTEGER,
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
                deliverable TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL DEFAULT '',
                difficulty INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'planned',
                workspace_id INTEGER,
                xp_awarded INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                updated_at TEXT
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
                workspace_id INTEGER,
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
                workspace_id INTEGER,
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

            CREATE TABLE IF NOT EXISTS research_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                research_question TEXT NOT NULL DEFAULT '',
                rationale TEXT NOT NULL DEFAULT '',
                target_outcome TEXT NOT NULL DEFAULT '',
                success_criteria TEXT NOT NULL DEFAULT '',
                current_state TEXT NOT NULL DEFAULT '',
                constraints_text TEXT NOT NULL DEFAULT '',
                search_query TEXT NOT NULL DEFAULT '',
                workspace_id INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                target_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS project_workspaces (
                project_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT '',
                is_primary INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY(project_id,workspace_id),
                FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE,
                FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS project_milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                stage_key TEXT NOT NULL DEFAULT 'custom',
                title TEXT NOT NULL,
                criterion TEXT NOT NULL DEFAULT '',
                deliverable TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planned',
                due_date TEXT,
                evidence TEXT NOT NULL DEFAULT '',
                decision TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS project_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                provider TEXT NOT NULL DEFAULT 'Crossref',
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                authors TEXT NOT NULL DEFAULT '',
                publication_year INTEGER,
                source TEXT NOT NULL DEFAULT '',
                doi TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                cited_by INTEGER NOT NULL DEFAULT 0,
                relation TEXT NOT NULL DEFAULT 'unclassified',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(project_id,provider,external_id),
                FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS project_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                update_type TEXT NOT NULL DEFAULT 'checkin',
                summary TEXT NOT NULL,
                evidence TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL DEFAULT '',
                confidence INTEGER NOT NULL DEFAULT 50,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS career_moments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                moment_type TEXT NOT NULL DEFAULT 'decision',
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL DEFAULT '',
                project_id INTEGER,
                occurred_on TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES research_projects(id) ON DELETE SET NULL
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

            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                icon TEXT NOT NULL DEFAULT '研',
                module TEXT NOT NULL DEFAULT 'knowledge',
                description TEXT NOT NULL DEFAULT '',
                accent TEXT NOT NULL DEFAULT 'clay',
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                pinned_home INTEGER NOT NULL DEFAULT 0,
                objective TEXT NOT NULL DEFAULT '',
                workflow_json TEXT NOT NULL DEFAULT '[]',
                toolset_json TEXT NOT NULL DEFAULT '[]',
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
                quest_id INTEGER,
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
                display_name TEXT NOT NULL DEFAULT '修士',
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

            CREATE TABLE IF NOT EXISTS realm_tribulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gate_key TEXT NOT NULL,
                from_stage_key TEXT NOT NULL,
                to_stage_key TEXT NOT NULL,
                session_id INTEGER NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                score INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(session_id) REFERENCES review_sessions(id) ON DELETE CASCADE
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
            CREATE INDEX IF NOT EXISTS idx_research_projects_status ON research_projects(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_project_milestones_project ON project_milestones(project_id, sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_project_cases_project ON project_cases(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_project_updates_project ON project_updates(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_project_workspaces_workspace ON project_workspaces(workspace_id,project_id);
            CREATE INDEX IF NOT EXISTS idx_career_moments_date ON career_moments(occurred_on DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_career_moments_project ON career_moments(project_id, occurred_on DESC);
            CREATE INDEX IF NOT EXISTS idx_research_tracks_order ON research_tracks(sort_order, id);
            CREATE INDEX IF NOT EXISTS idx_workspaces_order ON workspaces(active, sort_order, id);
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
            CREATE INDEX IF NOT EXISTS idx_realm_tribulations_gate ON realm_tribulations(gate_key, status, id);
            CREATE INDEX IF NOT EXISTS idx_special_tasks_status ON special_tasks(status, created_at DESC);
            """
        )

        # Upgrade older databases in place.
        _add_column(conn, "entries", "analysis_json TEXT NOT NULL DEFAULT '{}'")
        _add_column(conn, "entries", "indexed_at TEXT")
        _add_column(conn, "entries", "extract_status TEXT NOT NULL DEFAULT 'pending'")
        _add_column(conn, "entries", "content_format TEXT NOT NULL DEFAULT 'plain'")
        _add_column(conn, "entries", "workspace_id INTEGER")
        _add_column(conn, "experiments", "workspace_id INTEGER")
        _add_column(conn, "simulations", "workspace_id INTEGER")
        _add_column(conn, "daily_missions", "track_id INTEGER")
        _add_column(conn, "daily_missions", "quest_id INTEGER")
        _add_column(conn, "daily_missions", "workspace_id INTEGER")
        _add_column(conn, "daily_missions", "project_id INTEGER")
        _add_column(conn, "daily_missions", "stones_awarded INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "daily_missions", "materials_awarded INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "daily_missions", "postponed_count INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "mission_deliveries", "review_text TEXT NOT NULL DEFAULT ''")
        _add_column(conn, "mission_deliveries", "review_source TEXT NOT NULL DEFAULT 'manual'")
        _add_column(conn, "quests", "deliverable TEXT NOT NULL DEFAULT ''")
        _add_column(conn, "quests", "evidence TEXT NOT NULL DEFAULT ''")
        _add_column(conn, "quests", "difficulty INTEGER NOT NULL DEFAULT 1")
        _add_column(conn, "quests", "status TEXT NOT NULL DEFAULT 'planned'")
        _add_column(conn, "quests", "workspace_id INTEGER")
        _add_column(conn, "quests", "xp_awarded INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "quests", "updated_at TEXT")
        _add_column(conn, "online_sync_queue", "schema_version INTEGER NOT NULL DEFAULT 1")
        _add_column(conn, "online_sync_queue", "aggregate_type TEXT NOT NULL DEFAULT ''")
        _add_column(conn, "online_sync_queue", "aggregate_id TEXT NOT NULL DEFAULT ''")
        _add_column(conn, "online_sync_queue", "sequence_no INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "online_sync_queue", "next_attempt_at TEXT")
        _add_column(conn, "online_sync_queue", "dead_letter INTEGER NOT NULL DEFAULT 0")
        pinned_home_added = _add_column(conn, "workspaces", "pinned_home INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "workspaces", "objective TEXT NOT NULL DEFAULT ''")
        _add_column(conn, "workspaces", "workflow_json TEXT NOT NULL DEFAULT '[]'")
        _add_column(conn, "workspaces", "toolset_json TEXT NOT NULL DEFAULT '[]'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_workspace ON entries(workspace_id, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_experiments_workspace ON experiments(workspace_id, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_simulations_workspace ON simulations(workspace_id, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quests_workspace ON quests(workspace_id, completed, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_missions_workspace ON daily_missions(workspace_id,completed,day_index)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_missions_project ON daily_missions(project_id,completed,day_index)")

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

        had_sync_provider = conn.execute(
            "SELECT 1 FROM settings WHERE key='sync_provider'"
        ).fetchone() is not None
        defaults = {
            "site_name": "科研系统",
            "researcher_name": "修士",
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
            "portable_version": APP_VERSION,
            "foundation_master_text": "",
            "hub_url": "",
            "hub_api_token": "",
            "hub_auto_sync": "0",
            "sync_provider": "disabled",
            "sync_contract_version": "2026-07-27",
            "ui_accent": "terracotta",
            "ui_density": "comfortable",
            "ui_scene": "warm",
            "ui_motion": "balanced",
            "ui_geometry": "soft",
            "ui_font_scale": "normal",
            "ui_home_effect": "orbits",
            "ui_home_motto": "让科研更好玩一点",
            "ui_home_poem": "纸上得来终觉浅，绝知此事要躬行。——陆游",
            "ui_poem_pool": "[]",
            "avatar_file": "",
            "review_popup": "1",
            "career_phase": "foundation",
            "career_focus": "把当前学习转化为可复用、可验证的科研能力。",
            "career_boundary": "不为尚未确定的长期主线提前承诺，只推进当前证据最需要的一步。",
            "career_success_signal": "能独立解释、复现或用证据修正一个关键判断。",
            "career_review_date": "",
            "realm_names": json.dumps(default_realm_labels(), ensure_ascii=False),
            "nav_labels": json.dumps(DEFAULT_NAV_LABELS, ensure_ascii=False),
            "nav_layout": json.dumps(DEFAULT_NAV_LAYOUT, ensure_ascii=False),
        }
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        if not had_sync_provider:
            legacy_hub = conn.execute(
                "SELECT value FROM settings WHERE key='hub_url'"
            ).fetchone()
            legacy_token = conn.execute(
                "SELECT value FROM settings WHERE key='hub_api_token'"
            ).fetchone()
            if (
                legacy_hub
                and legacy_token
                and str(legacy_hub["value"]).strip()
                and str(legacy_token["value"]).strip()
            ):
                conn.execute(
                    "UPDATE settings SET value='legacy_hub' WHERE key='sync_provider'"
                )
                conn.execute(
                    "UPDATE settings SET value='1' WHERE key='hub_auto_sync'"
                )
            else:
                conn.execute(
                    "UPDATE settings SET value='0' WHERE key='hub_auto_sync'"
                )
        realm_row = conn.execute("SELECT value FROM settings WHERE key='realm_names'").fetchone()
        try:
            realm_value = json.loads(realm_row["value"]) if realm_row else {}
        except json.JSONDecodeError:
            realm_value = {}
        conn.execute(
            "UPDATE settings SET value=? WHERE key='realm_names'",
            (json.dumps(normalize_realm_labels(realm_value), ensure_ascii=False),),
        )
        nav_row = conn.execute("SELECT value FROM settings WHERE key='nav_labels'").fetchone()
        try:
            nav_value = json.loads(nav_row["value"]) if nav_row else {}
        except json.JSONDecodeError:
            nav_value = {}
        conn.execute(
            "UPDATE settings SET value=? WHERE key='nav_labels'",
            (json.dumps(normalize_nav_labels(nav_value), ensure_ascii=False),),
        )
        nav_layout_row = conn.execute(
            "SELECT value FROM settings WHERE key='nav_layout'"
        ).fetchone()
        try:
            nav_layout_value = json.loads(nav_layout_row["value"]) if nav_layout_row else []
        except json.JSONDecodeError:
            nav_layout_value = []
        conn.execute(
            "UPDATE settings SET value=? WHERE key='nav_layout'",
            (
                json.dumps(
                    normalize_nav_layout(nav_layout_value),
                    ensure_ascii=False,
                ),
            ),
        )
        conn.execute(
            "UPDATE settings SET value=? WHERE key='portable_version'",
            (APP_VERSION,),
        )
        conn.execute(
            "UPDATE settings SET value='科研系统' WHERE key='site_name' AND trim(value)='问道科研'"
        )
        ts = now_iso()
        for workspace in DEFAULT_WORKSPACES:
            profile = profile_for(workspace["module"])
            conn.execute(
                """
                INSERT OR IGNORE INTO workspaces(
                    workspace_key,name,icon,module,description,accent,sort_order,active,pinned_home,
                    objective,workflow_json,toolset_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,1,1,?,?,?,?,?)
                """,
                (
                    workspace["workspace_key"],
                    workspace["name"],
                    workspace["icon"],
                    workspace["module"],
                    workspace["description"],
                    workspace["accent"],
                    workspace["sort_order"],
                    profile["objective"],
                    json.dumps(profile["workflow"], ensure_ascii=False),
                    json.dumps(profile["tools"], ensure_ascii=False),
                    ts,
                    ts,
                ),
            )
            conn.execute(
                """
                UPDATE workspaces
                SET objective=CASE WHEN trim(objective)='' THEN ? ELSE objective END,
                    workflow_json=CASE WHEN trim(workflow_json) IN ('','[]') THEN ? ELSE workflow_json END,
                    toolset_json=CASE WHEN trim(toolset_json) IN ('','[]') THEN ? ELSE toolset_json END
                WHERE workspace_key=?
                """,
                (
                    profile["objective"],
                    json.dumps(profile["workflow"], ensure_ascii=False),
                    json.dumps(profile["tools"], ensure_ascii=False),
                    workspace["workspace_key"],
                ),
            )
        if pinned_home_added:
            conn.execute(
                """
                UPDATE workspaces SET pinned_home=1
                WHERE workspace_key IN (
                    'eg-lab','lammps-lab','dataset-lab','ml-lab','md-lab','comsol-lab'
                )
                """
            )
        workspace_ids = {
            row["workspace_key"]: int(row["id"])
            for row in conn.execute("SELECT id,workspace_key FROM workspaces")
        }
        conn.execute(
            """
            INSERT OR IGNORE INTO project_workspaces(
                project_id,workspace_id,role,is_primary,created_at
            )
            SELECT id,workspace_id,'主要工作区',1,COALESCE(created_at,?)
            FROM research_projects
            WHERE workspace_id IS NOT NULL
            """,
            (ts,),
        )
        if workspace_ids.get("eg-lab"):
            conn.execute(
                "UPDATE experiments SET workspace_id=? WHERE workspace_id IS NULL",
                (workspace_ids["eg-lab"],),
            )
        if workspace_ids.get("lammps-lab"):
            conn.execute(
                "UPDATE simulations SET workspace_id=? WHERE workspace_id IS NULL",
                (workspace_ids["lammps-lab"],),
            )
        if workspace_ids.get("dataset-lab"):
            conn.execute(
                "UPDATE entries SET workspace_id=? WHERE kind='dataset' AND workspace_id IS NULL",
                (workspace_ids["dataset-lab"],),
            )
        for mission in conn.execute("SELECT id,duration_minutes FROM daily_missions"):
            conn.execute(
                "UPDATE daily_missions SET xp=? WHERE id=?",
                (fixed_daily_xp(int(mission["duration_minutes"] or 30)), int(mission["id"])),
            )
        for quest in conn.execute("SELECT id,completed,difficulty FROM quests"):
            difficulty = max(1, min(int(quest["difficulty"] or 1), 3))
            conn.execute(
                """
                UPDATE quests
                SET difficulty=?,xp=?,status=?,xp_awarded=CASE WHEN completed=1 THEN 1 ELSE xp_awarded END,
                    updated_at=COALESCE(updated_at,created_at,?)
                WHERE id=?
                """,
                (
                    difficulty,
                    fixed_cultivation_xp(difficulty),
                    "done" if int(quest["completed"] or 0) else "planned",
                    ts,
                    int(quest["id"]),
                ),
            )
        conn.execute(
            "INSERT OR IGNORE INTO player_profile(id,display_name,title,bio,skills,capabilities,goals,avatar_symbol,updated_at) VALUES (1,?,?,?,?,?,?,?,?)",
            (
                "修士", "水泥基能源材料探索者",
                "正在用方向判断、近期行动、真实交付和持续复盘建立能够陪伴整个科研生涯的成长系统。",
                "电化学基础\n水泥基材料\n膨胀石墨实验\nLAMMPS入门\nPython数据处理",
                "能复现基础案例\n能建立实验台账\n能拆解论文图表\n能用GPT辅助学习与排错",
                "让每一次学习、试错、决策和成果都沉淀为下一阶段可调用的科研能力", "道", ts,
            ),
        )
        conn.execute(
            "UPDATE settings SET value='修士' WHERE key='researcher_name' AND trim(value)='准研一修士'"
        )
        conn.execute(
            "UPDATE player_profile SET display_name='修士',updated_at=? WHERE id=1 AND trim(display_name)='准研一修士'",
            (ts,),
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
            ("balanced_plan", "七日有度", "一份近期计划既照顾眼前卡点，也为每天留下了可完成的交付。"),
            ("many_workspaces", "诸域同参", "一个课题第一次同时连接多个工作区，实验、计算与写作开始共享同一问题。"),
            ("ai_handoff", "借智留痕", "你没有让 AI 对话随窗口消失，而是把结论、证据与下一步重新收进系统。"),
            ("evidence_gate", "一证破关", "第一个证据闸门不是靠感觉，而是凭证据与决策理由通过。"),
            ("failure_alchemy", "败中炼金", "一次失败被写成可复用的预防规则，损失开始转化为方法。"),
            ("constellation", "几何星图", "你在山门的几何轨道里找到了隐藏节点。连接本身，也是一种发现。"),
            ("artifact_keeper", "百器归心", "你收集了五件法器，也开始理解工具只有在真实工作中生效才有意义。"),
            ("trial_triad", "三境同游", "你完成了三种不同目的的秘境：回忆、迁移与反证开始互相支撑。"),
            ("review_scribe", "十简成卷", "十次交付留下了可复盘关键文本，个人题库开始拥有连续性。"),
            ("career_witness", "回望有迹", "生涯罗盘记录了第一个重要节点，未来的你能够看见为何转向。"),
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
                ("建立第一张论文证据卡", "上传一篇与你当前问题直接相关的论文，并写清它证明了什么。", "论文条目 + 证据摘要", 1, None),
                ("形成第一个可证伪问题", "把模糊想法改写为变量、机制、结果和判断边界。", "问题—假设—证据—下一步卡片", 1, None),
                ("建立第一个数据集档案", "上传 CSV 或 XLSX，并补充变量、单位和来源说明。", "可检索数据集 + 数据字典", 2, "dataset-lab"),
                ("完成一次失败复盘", "记录一次实验或代码失败，并明确下次如何更早发现。", "失败现象—根因—修正—预防记录", 2, None),
                ("建立第一个实验批次", "把配比、成型、几何尺寸、测试边界和结果录入实验台账。", "一个字段完整的实验批次", 2, "eg-lab"),
                ("归档第一个可复现模拟案例", "保存输入、日志、轨迹、版本、命令和判定结果。", "可复现案例目录或 ZIP", 2, "lammps-lab"),
            ]
            for title, description, deliverable, difficulty, workspace_key in starter_quests:
                conn.execute(
                    """
                    INSERT INTO quests(
                        title,description,deliverable,difficulty,xp,status,workspace_id,created_at,updated_at
                    ) VALUES (?,?,?,?,?,'planned',?,?,?)
                    """,
                    (
                        title,
                        description,
                        deliverable,
                        difficulty,
                        fixed_cultivation_xp(difficulty),
                        workspace_ids.get(workspace_key) if workspace_key else None,
                        ts,
                        ts,
                    ),
                )


def get_setting(key: str, default: str = "") -> str:
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


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
