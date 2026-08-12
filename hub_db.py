from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from runtime_paths import INSTANCE_DIR, STORAGE_ROOT
from version import APP_VERSION

HUB_DB_PATH = INSTANCE_DIR / "hub.db"
HUB_BACKUP_DIR = STORAGE_ROOT / "hub_backups"
HUB_RELEASE_DIR = STORAGE_ROOT / "hub_releases"
HUB_SECRET_PATH = INSTANCE_DIR / "hub_secret.txt"
HUB_ADMIN_PATH = INSTANCE_DIR / "HUB_ADMIN_CREDENTIALS.txt"

# These are deliberately only the light-weight, shared assets of a 同行会.
# They are not a mirror of a member's private local research database.
ASSET_KEYS = ("cultivation", "spirit_stone", "spirit_wood", "mystic_iron", "star_sand")
WELFARE_SINGLE_LIMITS = {
    "xp": 60,
    "spirit_stone": 50,
    "spirit_wood": 6,
    "mystic_iron": 6,
    "star_sand": 6,
}
WELFARE_DAILY_LIMITS = {
    "grants": 3,
    "xp": 120,
    "spirit_stone": 100,
    "spirit_wood": 12,
    "mystic_iron": 12,
    "star_sand": 12,
}


def _restrict_private_file(path: Path) -> None:
    """Use owner-only POSIX permissions where the host filesystem supports them."""
    try:
        path.chmod(0o600)
    except OSError:
        pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect_hub() -> sqlite3.Connection:
    HUB_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(HUB_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


@contextmanager
def hub_transaction() -> Iterable[sqlite3.Connection]:
    conn = connect_hub()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    _, candidate = _hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(candidate, digest_hex)


def set_password(conn: sqlite3.Connection, user_id: int, password: str) -> None:
    if len(password) < 8:
        raise ValueError("密码至少8位。")
    salt, digest = _hash_password(password)
    conn.execute(
        "UPDATE hub_users SET password_salt=?,password_hash=?,updated_at=? WHERE id=?",
        (salt, digest, now_iso(), user_id),
    )


def hub_secret() -> str:
    HUB_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if HUB_SECRET_PATH.exists():
        return HUB_SECRET_PATH.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    HUB_SECRET_PATH.write_text(value, encoding="utf-8")
    _restrict_private_file(HUB_SECRET_PATH)
    return value


def create_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    display_name: str,
    role: str = "member",
) -> tuple[int, str]:
    username = username.strip().lower()
    if not (3 <= len(username) <= 32) or not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("用户名需为3—32位字母、数字、下划线或短横线。")
    if len(password) < 8:
        raise ValueError("密码至少8位。")
    salt, digest = _hash_password(password)
    token = secrets.token_urlsafe(32)
    ts = now_iso()
    cur = conn.execute(
        """INSERT INTO hub_users(username,display_name,password_salt,password_hash,role,api_token,active,created_at,updated_at)
           VALUES (?,?,?,?,?,?,1,?,?)""",
        (username, display_name.strip() or username, salt, digest, role, token, ts, ts),
    )
    user_id = int(cur.lastrowid)
    conn.execute(
        """INSERT INTO hub_profiles(user_id,title,bio,skills,capabilities,goals,avatar_symbol,theme_json,public,revision,updated_at)
           VALUES (?,?,?,?,?,?,?,?,1,1,?)""",
        (
            user_id,
            "科研修士",
            "正在建立自己的科研体系。",
            "",
            "",
            "",
            "道",
            json.dumps({"accent": "terracotta", "density": "comfortable", "scene": "warm", "home_motto": "让科研更好玩一点", "home_poem": "纸上得来终觉浅，绝知此事要躬行。——陆游"}, ensure_ascii=False),
            ts,
        ),
    )
    for key, amount in {"cultivation": 100, "spirit_stone": 12, "spirit_wood": 4, "mystic_iron": 2, "star_sand": 2}.items():
        conn.execute(
            "INSERT INTO hub_asset_transactions(user_id,asset_key,amount,reason,created_at) VALUES (?,?,?,?,?)",
            (user_id, key, amount, "联机开宗礼包", ts),
        )
    return user_id, token


def balances(conn: sqlite3.Connection, user_id: int) -> dict[str, int]:
    result = {key: 0 for key in ASSET_KEYS}
    for row in conn.execute(
        "SELECT asset_key,COALESCE(SUM(amount),0) amount FROM hub_asset_transactions WHERE user_id=? GROUP BY asset_key",
        (user_id,),
    ):
        result[row["asset_key"]] = int(row["amount"])
    return result


def transact_asset(conn: sqlite3.Connection, user_id: int, asset_key: str, amount: int, reason: str, event_uuid: str | None = None) -> None:
    if asset_key not in ASSET_KEYS:
        raise ValueError("未知资产")
    if amount < 0 and balances(conn, user_id).get(asset_key, 0) + amount < 0:
        raise ValueError("资产不足")
    conn.execute(
        "INSERT INTO hub_asset_transactions(user_id,asset_key,amount,reason,event_uuid,created_at) VALUES (?,?,?,?,?,?)",
        (user_id, asset_key, int(amount), reason, event_uuid, now_iso()),
    )


def normalize_welfare_values(values: dict[str, object]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, upper in WELFARE_SINGLE_LIMITS.items():
        try:
            amount = int(values.get(key, 0) or 0)
        except (TypeError, ValueError):
            amount = 0
        if amount < 0 or amount > upper:
            raise ValueError(f"{key} 单次只能发放 0—{upper}。")
        result[key] = amount
    if not any(result.values()):
        raise ValueError("至少填写一项福利。")
    return result


def enforce_welfare_daily_limits(conn: sqlite3.Connection, recipient_id: int, values: dict[str, int]) -> None:
    today = datetime.now().astimezone().date().isoformat()
    row = conn.execute(
        """SELECT COUNT(*) grants,COALESCE(SUM(xp),0) xp,COALESCE(SUM(spirit_stone),0) spirit_stone,
                  COALESCE(SUM(spirit_wood),0) spirit_wood,COALESCE(SUM(mystic_iron),0) mystic_iron,
                  COALESCE(SUM(star_sand),0) star_sand
           FROM hub_welfare_grants WHERE recipient_id=? AND substr(created_at,1,10)=?""",
        (recipient_id, today),
    ).fetchone()
    if int(row["grants"] or 0) >= WELFARE_DAILY_LIMITS["grants"]:
        raise ValueError("该成员今日已达到 3 次福利上限。")
    for key, upper in WELFARE_DAILY_LIMITS.items():
        if key == "grants":
            continue
        if int(row[key] or 0) + int(values[key]) > upper:
            raise ValueError(f"该成员今日 {key} 福利上限为 {upper}。")


def backup_hub_db(keep: int = 14) -> Path:
    HUB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = HUB_BACKUP_DIR / f"hub_{stamp}.db"
    source = connect_hub()
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    backups = sorted(HUB_BACKUP_DIR.glob("hub_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[keep:]:
        old.unlink(missing_ok=True)
    return target


def init_hub_db() -> None:
    HUB_RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    HUB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with hub_transaction() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hub_users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                api_token TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT
            );
            CREATE TABLE IF NOT EXISTS hub_profiles(
                user_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                bio TEXT NOT NULL DEFAULT '',
                skills TEXT NOT NULL DEFAULT '',
                capabilities TEXT NOT NULL DEFAULT '',
                goals TEXT NOT NULL DEFAULT '',
                avatar_symbol TEXT NOT NULL DEFAULT '道',
                theme_json TEXT NOT NULL DEFAULT '{}',
                public INTEGER NOT NULL DEFAULT 1,
                revision INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_asset_transactions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                asset_key TEXT NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                event_uuid TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_inventory(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                item_type TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                level INTEGER NOT NULL DEFAULT 1,
                equipped INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id,item_key),
                FOREIGN KEY(user_id) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_sync_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_uuid TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                rewarded INTEGER NOT NULL DEFAULT 0,
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_invites(
                code TEXT PRIMARY KEY,
                uses_remaining INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(created_by) REFERENCES hub_users(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS hub_releases(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                sha256 TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(created_by) REFERENCES hub_users(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS hub_welfare_grants(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id INTEGER NOT NULL,
                granted_by INTEGER NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                spirit_stone INTEGER NOT NULL DEFAULT 0,
                spirit_wood INTEGER NOT NULL DEFAULT 0,
                mystic_iron INTEGER NOT NULL DEFAULT 0,
                star_sand INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                claimed_at TEXT,
                FOREIGN KEY(recipient_id) REFERENCES hub_users(id) ON DELETE CASCADE,
                FOREIGN KEY(granted_by) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_resource_cards(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'team',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_forum_posts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_forum_replies(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(post_id) REFERENCES hub_forum_posts(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_chat_messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_social_transfers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                offer_asset TEXT NOT NULL,
                offer_amount INTEGER NOT NULL,
                request_asset TEXT NOT NULL DEFAULT '',
                request_amount INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(sender_id) REFERENCES hub_users(id) ON DELETE CASCADE,
                FOREIGN KEY(recipient_id) REFERENCES hub_users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS hub_audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                ip TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES hub_users(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS hub_settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hub_events_user_created ON hub_sync_events(user_id,created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_hub_assets_user_created ON hub_asset_transactions(user_id,created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_hub_releases_created ON hub_releases(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_hub_welfare_recipient ON hub_welfare_grants(recipient_id,created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_hub_forum_posts_created ON hub_forum_posts(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_hub_forum_replies_post ON hub_forum_replies(post_id,created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_hub_chat_created ON hub_chat_messages(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_hub_social_recipient ON hub_social_transfers(recipient_id,status,created_at DESC);
            """
        )
        defaults = {
            "site_name": "科研系统 · 同行会",
            "version": APP_VERSION,
            "registration_mode": "invite",
            "max_members": "10",
        }
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO hub_settings(key,value) VALUES (?,?)", (key, value))
        conn.execute(
            "UPDATE hub_settings SET value=? WHERE key='version'",
            (APP_VERSION,),
        )
        # Existing v3.5 team centres receive one small, virtual social balance.
        # It is intentionally separate from local XP and never uploads research files.
        for row in conn.execute("SELECT id FROM hub_users WHERE active=1"):
            user_id = int(row["id"])
            has_cultivation = conn.execute(
                "SELECT 1 FROM hub_asset_transactions WHERE user_id=? AND asset_key='cultivation' LIMIT 1",
                (user_id,),
            ).fetchone()
            if not has_cultivation:
                conn.execute(
                    "INSERT INTO hub_asset_transactions(user_id,asset_key,amount,reason,created_at) VALUES (?,?,?,?,?)",
                    (user_id, "cultivation", 100, "同行会社交启用礼包", now_iso()),
                )
        conn.execute(
            """
            UPDATE hub_settings SET value='科研系统 · 同行会'
            WHERE key='site_name' AND trim(value)='问道科研 · 同行会'
            """
        )
        admin = conn.execute("SELECT id FROM hub_users WHERE role='admin' LIMIT 1").fetchone()
        if not admin:
            password = secrets.token_urlsafe(10)
            user_id, token = create_user(conn, "admin", password, "洞府主人", role="admin")
            HUB_ADMIN_PATH.write_text(
                f"科研系统 v{APP_VERSION} 轻量联机中心管理员凭据\n"
                "================================\n"
                f"用户名: admin\n密码: {password}\nAPI Token: {token}\n\n"
                "首次登录后请立即修改密码。修改成功后系统会销毁这份一次性凭据文件；\n"
                "API Token 仍可在“我的联机主页”查看或重新生成。\n",
                encoding="utf-8",
            )
            _restrict_private_file(HUB_ADMIN_PATH)
            invite = secrets.token_urlsafe(8)
            conn.execute(
                "INSERT INTO hub_invites(code,uses_remaining,expires_at,created_by,created_at) VALUES (?,?,?,?,?)",
                (invite, 9, (datetime.now().astimezone() + timedelta(days=30)).isoformat(timespec="seconds"), user_id, now_iso()),
            )


def get_user_by_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM hub_users WHERE api_token=? AND active=1", (token,)).fetchone()


def get_hub_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM hub_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default
