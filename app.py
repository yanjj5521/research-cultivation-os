from __future__ import annotations

import csv
import io
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import bleach

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from db import DB_PATH, connect, get_setting, init_db, log_activity, now_iso, set_setting, total_xp
from extractors import extract_file
from research_tools import find_lammps_files, offline_paper_summary, parse_lammps_log, summary_to_markdown, unpack_lammps_bundle
from services.economy import balances as asset_balances
from services.backups import register_backup_jobs
from services.ai_provider import provider_status
from services.review_engine import pending_review_group

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
BACKUP_DIR = BASE_DIR / "storage" / "backups"
SIMULATION_DIR = BASE_DIR / "storage" / "simulations"
FOUNDATION_DIR = BASE_DIR / "storage" / "research_foundation"
DELIVERY_DIR = BASE_DIR / "storage" / "deliveries"
NOTE_IMAGE_DIR = BASE_DIR / "storage" / "note_images"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
SIMULATION_DIR.mkdir(parents=True, exist_ok=True)
FOUNDATION_DIR.mkdir(parents=True, exist_ok=True)
DELIVERY_DIR.mkdir(parents=True, exist_ok=True)
NOTE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024

KINDS = {
    "document": ("文献/文档", "📚"),
    "note": ("科研笔记", "📝"),
    "question": ("科学问题", "❓"),
    "experiment": ("实验记录", "🧪"),
    "dataset": ("数据集", "📊"),
    "image": ("图片/图谱", "🖼️"),
    "code": ("代码/模拟", "💻"),
    "sop": ("SOP/方法", "🧭"),
    "failure": ("失败复盘", "🔥"),
    "idea": ("灵感假设", "💡"),
    "other": ("其他", "📦"),
}



def secure_filename(name: str) -> str:
    base = Path(name).name
    safe = re.sub(r"[^\w.\-]+", "_", base, flags=re.UNICODE).strip("._")
    return safe[:180] or "file"

REALMS = [
    (0, "凡人", "尚未踏入科研仙途"),
    (80, "炼气一层", "开始积累基础知识"),
    (180, "炼气中期", "形成稳定输入与输出"),
    (350, "炼气圆满", "能够独立复现基础工作"),
    (600, "筑基初期", "建立自己的研究体系"),
    (950, "筑基圆满", "能够提出并验证科学问题"),
    (1450, "金丹初成", "拥有可复用的方法与数据资产"),
    (2200, "金丹圆满", "形成结构—机制—性能闭环"),
    (3200, "元婴境", "可以稳定推进多条研究支线"),
    (4600, "化神境", "形成鲜明科研判断与学术表达"),
    (6500, "炼虚境", "能够构建团队级科研基础设施"),
    (9000, "合体境", "知识、数据、方法高度协同"),
    (12000, "大乘境", "能够定义问题并引领方向"),
    (16000, "渡劫境", "成果、方法与传承体系成熟"),
]

DEFAULT_NAV_LABELS = {
    "dashboard": "主页",
    "daily": "每日任务",
    "review": "昨日复盘",
    "plans": "近期计划",
    "alchemy": "炼丹炉",
    "world": "我的洞府",
    "profile": "个人主页",
    "assistant": "AI 协作",
    "online": "联机同步",
    "library": "资料库",
    "folders": "交付文件夹",
    "note_new": "写笔记",
    "upload": "上传资料",
    "search": "本地检索",
    "discover": "联网找论文",
    "datasets": "数据集",
    "experiments": "EG 实验",
    "simulations": "LAMMPS",
    "cultivation": "修炼记录",
    "settings": "设置与备份",
}

app = FastAPI(title="问道科研", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("RESEARCH_OS_SECRET", "local-research-os-change-me"),
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/media/note-images", StaticFiles(directory=NOTE_IMAGE_DIR), name="note_images")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def filesize_filter(size: int | None) -> str:
    size = int(size or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def date_filter(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


templates.env.filters["filesize"] = filesize_filter
templates.env.filters["datecn"] = date_filter


def configured_realm_names() -> list[str]:
    try:
        custom_names = json.loads(get_setting("realm_names", "[]"))
    except json.JSONDecodeError:
        custom_names = []
    if not isinstance(custom_names, list):
        custom_names = []
    return [
        str(custom_names[index]).strip()[:30] or name
        if index < len(custom_names)
        else name
        for index, (_, name, _) in enumerate(REALMS)
    ]


def current_realm(xp: int) -> dict[str, Any]:
    custom_names = configured_realm_names()
    realms = [
        (threshold, custom_names[index], description)
        for index, (threshold, name, description) in enumerate(REALMS)
    ]
    current_index = 0
    for i, item in enumerate(realms):
        if xp >= item[0]:
            current_index = i
        else:
            break
    threshold, name, description = realms[current_index]
    if current_index + 1 < len(realms):
        next_threshold, next_name, _ = realms[current_index + 1]
        progress = int((xp - threshold) / max(next_threshold - threshold, 1) * 100)
        remaining = max(next_threshold - xp, 0)
    else:
        next_threshold, next_name, progress, remaining = threshold, "已至巅峰", 100, 0
    return {
        "name": name,
        "description": description,
        "threshold": threshold,
        "next_threshold": next_threshold,
        "next_name": next_name,
        "progress": max(0, min(progress, 100)),
        "remaining": remaining,
    }


def domains() -> list[str]:
    try:
        return json.loads(get_setting("domains", "[]"))
    except json.JSONDecodeError:
        return ["未分类"]


def navigation_labels() -> dict[str, str]:
    try:
        custom = json.loads(get_setting("nav_labels", "{}"))
    except json.JSONDecodeError:
        custom = {}
    if not isinstance(custom, dict):
        custom = {}
    return {
        key: str(custom.get(key, default)).strip()[:24] or default
        for key, default in DEFAULT_NAV_LABELS.items()
    }


def infer_kind(filename: str, selected: str) -> str:
    if selected and selected != "auto":
        return selected
    suffix = Path(filename).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".svg"}:
        return "image"
    if suffix in {".csv", ".xlsx", ".xlsm", ".json", ".parquet", ".tsv", ".sav", ".h5", ".hdf5"}:
        return "dataset"
    if suffix in {".py", ".ipynb", ".r", ".m", ".cpp", ".c", ".h", ".java", ".sh", ".bat", ".yaml", ".yml"}:
        return "code"
    return "document"


def xp_for_kind(kind: str) -> int:
    return {
        "document": 12,
        "note": 10,
        "question": 15,
        "experiment": 18,
        "dataset": 25,
        "image": 8,
        "code": 16,
        "sop": 22,
        "failure": 20,
        "idea": 12,
        "other": 6,
    }.get(kind, 8)


def parse_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except json.JSONDecodeError:
        return fallback


def entry_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["schema"] = parse_json(item.get("dataset_schema", "[]"), [])
    item["analysis"] = parse_json(item.get("analysis_json", "{}"), {})
    item["preview"] = parse_json(item.get("dataset_preview", "[]"), [])
    item["kind_label"], item["kind_icon"] = KINDS.get(item["kind"], KINDS["other"])
    item["tags_list"] = [x.strip() for x in re.split(r"[,，;；#]+", item.get("tags", "")) if x.strip()]
    return item


def activity_streak(conn) -> int:
    rows = conn.execute("SELECT DISTINCT substr(created_at, 1, 10) AS day FROM activities ORDER BY day DESC").fetchall()
    days = {row["day"] for row in rows}
    cursor = date.today()
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def achievements(conn) -> list[dict[str, Any]]:
    counts = {row["kind"]: row["n"] for row in conn.execute("SELECT kind, COUNT(*) n FROM entries GROUP BY kind")}
    total = sum(counts.values())
    domain_count = conn.execute("SELECT COUNT(DISTINCT domain) n FROM entries WHERE domain != '未分类'").fetchone()["n"]
    tagged = conn.execute("SELECT COUNT(*) n FROM entries WHERE trim(tags) != ''").fetchone()["n"]
    return [
        {"name": "初入仙途", "desc": "建立第一条科研资产", "unlocked": total >= 1, "icon": "🌱"},
        {"name": "藏经阁弟子", "desc": "收录10份文献或文档", "unlocked": counts.get("document", 0) >= 10, "icon": "📚"},
        {"name": "问道者", "desc": "记录10个科学问题", "unlocked": counts.get("question", 0) >= 10, "icon": "❓"},
        {"name": "百炼成钢", "desc": "完成10次实验或失败复盘", "unlocked": counts.get("experiment", 0) + counts.get("failure", 0) >= 10, "icon": "🔥"},
        {"name": "数据炼丹师", "desc": "建立5个数据集档案", "unlocked": counts.get("dataset", 0) >= 5, "icon": "📊"},
        {"name": "法门传承者", "desc": "沉淀5份SOP", "unlocked": counts.get("sop", 0) >= 5, "icon": "🧭"},
        {"name": "贯通诸域", "desc": "覆盖6个研究领域", "unlocked": domain_count >= 6, "icon": "🌌"},
        {"name": "秩序建立者", "desc": "为50条资料添加标签", "unlocked": tagged >= 50, "icon": "🏛️"},
    ]


RICH_TAGS = ["p","br","strong","b","em","i","u","ul","ol","li","h2","h3","blockquote","a","img","code","pre","hr"]
RICH_ATTRS = {"a": ["href","title","target"], "img": ["src","alt","title"]}


def sanitize_rich_content(value: str) -> str:
    return bleach.clean(value or "", tags=RICH_TAGS, attributes=RICH_ATTRS, protocols=["http","https"], strip=True)


def flash(request: Request, message: str, category: str = "success") -> None:
    request.session.setdefault("flashes", []).append({"category": category, "message": message})


def context(request: Request, active_page: str, **extra: Any) -> dict[str, Any]:
    xp = total_xp()
    with connect() as _asset_conn:
        _balances = asset_balances(_asset_conn)
    base = {
        "request": request,
        "site_name": get_setting("site_name", "问道科研"),
        "researcher_name": get_setting("researcher_name", "准研一修士"),
        "nav_xp": xp,
        "nav_realm": current_realm(xp),
        "nav_assets": _balances,
        "kinds": KINDS,
        "domains": domains(),
        "current_year": datetime.now().year,
        "active_page": active_page,
        "flashes": request.session.pop("flashes", []),
        "ui_accent": get_setting("ui_accent", "terracotta"),
        "ui_density": get_setting("ui_density", "comfortable"),
        "ui_scene": get_setting("ui_scene", "warm"),
        "ui_home_motto": get_setting("ui_home_motto", "让科研更好玩一点"),
        "nav_labels": navigation_labels(),
        "hub_configured": bool(get_setting("hub_url", "").strip() and get_setting("hub_api_token", "").strip()),
    }
    base.update(extra)
    return base


def redirect(name: str, request: Request, **path_params: Any) -> RedirectResponse:
    return RedirectResponse(url=request.url_for(name, **path_params), status_code=303)


@app.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request):
    with connect() as conn:
        stats = {
            "total": conn.execute("SELECT COUNT(*) n FROM entries").fetchone()["n"],
            "documents": conn.execute("SELECT COUNT(*) n FROM entries WHERE kind='document'").fetchone()["n"],
            "notes": conn.execute("SELECT COUNT(*) n FROM entries WHERE kind IN ('note','question','idea','failure','sop')").fetchone()["n"],
            "datasets": conn.execute("SELECT COUNT(*) n FROM entries WHERE kind='dataset'").fetchone()["n"],
            "experiments": conn.execute("SELECT COUNT(*) n FROM entries WHERE kind='experiment'").fetchone()["n"],
        }
        recent = [entry_dict(row) for row in conn.execute("SELECT * FROM entries ORDER BY updated_at DESC LIMIT 8")]
        activities = conn.execute(
            "SELECT a.*, e.title AS entry_title FROM activities a LEFT JOIN entries e ON e.id=a.entry_id ORDER BY a.created_at DESC LIMIT 12"
        ).fetchall()
        quests = conn.execute("SELECT * FROM quests ORDER BY completed ASC, created_at DESC LIMIT 8").fetchall()
        active_plan = conn.execute("SELECT * FROM study_plans WHERE status='active' ORDER BY updated_at DESC LIMIT 1").fetchone()
        today_missions = []
        today_progress = 0
        if active_plan:
            today_missions = [dict(row) for row in conn.execute(
                "SELECT * FROM daily_missions WHERE plan_id=? AND day_index=? ORDER BY optional,sort_order,id",
                (active_plan["id"], active_plan["current_day"]),
            )]
            required = [m for m in today_missions if not m["optional"]]
            today_progress = round(sum(int(m["completed"]) for m in required) / len(required) * 100) if required else 0
        xp = total_xp(conn)
        realm = current_realm(xp)
        streak = activity_streak(conn)
        domain_rows = conn.execute(
            """
            SELECT domain, COUNT(*) AS total,
                   SUM(CASE WHEN kind='dataset' THEN 1 ELSE 0 END) AS datasets,
                   SUM(CASE WHEN kind IN ('note','question','idea','failure','sop') THEN 1 ELSE 0 END) AS notes,
                   SUM(CASE WHEN trim(tags) != '' THEN 1 ELSE 0 END) AS tagged
            FROM entries GROUP BY domain ORDER BY total DESC
            """
        ).fetchall()
        knowledge = []
        for row in domain_rows:
            score = min(100, row["total"] * 7 + row["datasets"] * 10 + row["notes"] * 5 + row["tagged"] * 2)
            knowledge.append({"domain": row["domain"], "score": score, "total": row["total"]})
        data = context(
            request,
            "dashboard",
            stats=stats,
            recent=recent,
            activities=activities,
            quests=quests,
            xp=xp,
            realm=realm,
            streak=streak,
            knowledge=knowledge,
            achievements=achievements(conn),
            active_plan=dict(active_plan) if active_plan else None,
            today_missions=today_missions,
            today_progress=today_progress,
            pending_review=pending_review_group(conn) if get_setting("review_popup", "1") == "1" else None,
        )
    return templates.TemplateResponse(request=request, name="dashboard.html", context=data)


@app.get("/library", response_class=HTMLResponse, name="library")
def library(request: Request, kind: str = "", domain: str = "", favorite: str = ""):
    sql = "SELECT * FROM entries WHERE status='active'"
    params: list[Any] = []
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    if domain:
        sql += " AND domain=?"
        params.append(domain)
    if favorite == "1":
        sql += " AND favorite=1"
    sql += " ORDER BY favorite DESC, updated_at DESC LIMIT 300"
    with connect() as conn:
        entries = [entry_dict(row) for row in conn.execute(sql, params)]
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context=context(request, "library", entries=entries, selected_kind=kind, selected_domain=domain, favorite=favorite),
    )


@app.get("/datasets", response_class=HTMLResponse, name="datasets_page")
def datasets_page(request: Request):
    with connect() as conn:
        entries = [entry_dict(row) for row in conn.execute("SELECT * FROM entries WHERE kind='dataset' ORDER BY updated_at DESC LIMIT 300")]
    return templates.TemplateResponse(request=request, name="datasets.html", context=context(request, "datasets", entries=entries))


@app.get("/upload", response_class=HTMLResponse, name="upload")
def upload_get(request: Request):
    return templates.TemplateResponse(request=request, name="upload.html", context=context(request, "upload"))


@app.post("/upload", name="upload_post")
def upload_post(
    request: Request,
    files: list[UploadFile] = File(...),
    title: str = Form(""),
    kind: str = Form("auto"),
    domain: str = Form("未分类"),
    tags: str = Form(""),
    summary: str = Form(""),
    source: str = Form(""),
):
    files = [item for item in files if item.filename]
    if not files:
        flash(request, "请选择至少一个文件。", "error")
        return redirect("upload", request)
    created_ids: list[int] = []
    saved_paths: list[Path] = []
    with connect() as conn:
        try:
            for upload in files:
                original_name = upload.filename or "unnamed"
                safe_name = secure_filename(original_name) or f"file_{uuid.uuid4().hex}"
                stored_name = f"{uuid.uuid4().hex}_{safe_name}"
                stored_path = UPLOAD_DIR / stored_name
                with stored_path.open("wb") as output:
                    shutil.copyfileobj(upload.file, output)
                saved_paths.append(stored_path)
                if stored_path.stat().st_size > MAX_UPLOAD_BYTES:
                    raise ValueError(f"文件 {original_name} 超过 1 GB")
                extracted = extract_file(stored_path)
                inferred_kind = infer_kind(original_name, kind)
                entry_title = title.strip() if title.strip() and len(files) == 1 else Path(original_name).stem
                item_summary = summary.strip()
                if extracted.get("error"):
                    item_summary = (item_summary + "\n" + extracted["error"]).strip()
                ts = now_iso()
                cursor = conn.execute(
                    """
                    INSERT INTO entries(
                        title, kind, domain, tags, summary, content, file_path, original_name,
                        mime_type, file_size, dataset_rows, dataset_columns, dataset_schema,
                        dataset_preview, source, created_at, updated_at, extract_status, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_title,
                        inferred_kind,
                        domain.strip() or "未分类",
                        tags.strip(),
                        item_summary,
                        extracted.get("content", ""),
                        stored_name,
                        original_name,
                        extracted.get("mime_type", upload.content_type or "application/octet-stream"),
                        stored_path.stat().st_size,
                        extracted.get("rows"),
                        extracted.get("columns"),
                        json.dumps(extracted.get("schema", []), ensure_ascii=False),
                        json.dumps(extracted.get("preview", []), ensure_ascii=False, default=str),
                        source.strip(),
                        ts,
                        ts,
                        "ok" if extracted.get("content") else ("error" if extracted.get("error") else "no_text"),
                        ts,
                    ),
                )
                entry_id = int(cursor.lastrowid)
                created_ids.append(entry_id)
                conn.execute(
                    "INSERT INTO activities(action, entry_id, xp, detail, created_at) VALUES (?, ?, ?, ?, ?)",
                    ("upload", entry_id, xp_for_kind(inferred_kind), f"收录：{entry_title}", ts),
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            for path in saved_paths:
                path.unlink(missing_ok=True)
            flash(request, f"上传失败：{exc}", "error")
            return redirect("upload", request)
    flash(request, f"成功收录 {len(created_ids)} 项科研资料，修为已增长。")
    return redirect("entry_view", request, entry_id=str(created_ids[-1]))


@app.get("/notes/new", response_class=HTMLResponse, name="note_new")
def note_new_get(request: Request):
    return templates.TemplateResponse(request=request, name="editor.html", context=context(request, "note_new", entry=None))


@app.post("/notes/new", name="note_new_post")
def note_new_post(
    request: Request,
    title: str = Form(...),
    kind: str = Form("note"),
    domain: str = Form("未分类"),
    tags: str = Form(""),
    summary: str = Form(""),
    content: str = Form(""),
    source: str = Form(""),
):
    title = title.strip()
    if not title:
        flash(request, "标题不能为空。", "error")
        return redirect("note_new", request)
    if kind not in KINDS:
        kind = "note"
    ts = now_iso()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO entries(title, kind, domain, tags, summary, content, source, created_at, updated_at, content_format)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'html')
            """,
            (title, kind, domain.strip() or "未分类", tags.strip(), summary.strip(), sanitize_rich_content(content), source.strip(), ts, ts),
        )
        entry_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO activities(action, entry_id, xp, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            ("create", entry_id, xp_for_kind(kind), f"新建：{title}", ts),
        )
        conn.commit()
    flash(request, "记录已保存，并转化为你的科研资产。")
    return redirect("entry_view", request, entry_id=str(entry_id))


@app.post("/notes/paste-image", name="note_paste_image")
def note_paste_image(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        return JSONResponse({"ok": False, "error": "只能粘贴图片"}, status_code=400)
    suffix = Path(file.filename or "pasted.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        suffix = ".png"
    name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:10]}{suffix}"
    target = NOTE_IMAGE_DIR / name
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    if target.stat().st_size > 25 * 1024 * 1024:
        target.unlink(missing_ok=True)
        return JSONResponse({"ok": False, "error": "图片不能超过25MB"}, status_code=400)
    with connect() as conn:
        row = conn.execute("SELECT unlocked FROM easter_eggs WHERE egg_key='image_note'").fetchone()
        if row and not row["unlocked"]:
            conn.execute("UPDATE easter_eggs SET unlocked=1,discovered_at=? WHERE egg_key='image_note'", (now_iso(),))
            conn.commit()
    return {"ok": True, "url": f"/media/note-images/{name}"}


@app.get("/entry/{entry_id}", response_class=HTMLResponse, name="entry_view")
def entry_view(request: Request, entry_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        entry = entry_dict(row)
        related = [
            entry_dict(r)
            for r in conn.execute(
                "SELECT * FROM entries WHERE id != ? AND (domain=? OR kind=?) ORDER BY updated_at DESC LIMIT 6",
                (entry_id, entry["domain"], entry["kind"]),
            )
        ]
    return templates.TemplateResponse(
        request=request,
        name="entry.html",
        context=context(request, "entry", entry=entry, related=related),
    )


@app.get("/entry/{entry_id}/edit", response_class=HTMLResponse, name="entry_edit")
def entry_edit_get(request: Request, entry_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="editor.html",
        context=context(request, "entry", entry=entry_dict(row)),
    )


@app.post("/entry/{entry_id}/edit", name="entry_edit_post")
def entry_edit_post(
    request: Request,
    entry_id: int,
    title: str = Form(...),
    kind: str = Form("note"),
    domain: str = Form("未分类"),
    tags: str = Form(""),
    summary: str = Form(""),
    content: str = Form(""),
    source: str = Form(""),
    file: UploadFile | None = File(None),
):
    with connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        entry = entry_dict(row)
        title = title.strip()
        if not title:
            flash(request, "标题不能为空。", "error")
            return redirect("entry_edit", request, entry_id=str(entry_id))
        fields: dict[str, Any] = {
            "title": title,
            "kind": kind if kind in KINDS else entry["kind"],
            "domain": domain.strip() or "未分类",
            "tags": tags.strip(),
            "summary": summary.strip(),
            "content": sanitize_rich_content(content),
            "content_format": "html",
            "source": source.strip(),
            "updated_at": now_iso(),
        }
        old_path: Path | None = None
        new_path: Path | None = None
        try:
            if file and file.filename:
                original_name = file.filename
                safe_name = secure_filename(original_name) or f"file_{uuid.uuid4().hex}"
                stored_name = f"{uuid.uuid4().hex}_{safe_name}"
                new_path = UPLOAD_DIR / stored_name
                with new_path.open("wb") as output:
                    shutil.copyfileobj(file.file, output)
                if new_path.stat().st_size > MAX_UPLOAD_BYTES:
                    raise ValueError("替换文件超过 1 GB")
                extracted = extract_file(new_path)
                old_path = UPLOAD_DIR / entry["file_path"] if entry.get("file_path") else None
                fields.update(
                    {
                        "file_path": stored_name,
                        "original_name": original_name,
                        "mime_type": extracted.get("mime_type", file.content_type or "application/octet-stream"),
                        "file_size": new_path.stat().st_size,
                        "content": extracted.get("content", "") or sanitize_rich_content(content),
                        "content_format": "plain" if extracted.get("content") else "html",
                        "dataset_rows": extracted.get("rows"),
                        "dataset_columns": extracted.get("columns"),
                        "dataset_schema": json.dumps(extracted.get("schema", []), ensure_ascii=False),
                        "dataset_preview": json.dumps(extracted.get("preview", []), ensure_ascii=False, default=str),
                    }
                )
            assignments = ", ".join(f"{key}=?" for key in fields)
            conn.execute(f"UPDATE entries SET {assignments} WHERE id=?", [*fields.values(), entry_id])
            conn.execute(
                "INSERT INTO activities(action, entry_id, xp, detail, created_at) VALUES (?, ?, ?, ?, ?)",
                ("edit", entry_id, 4, f"完善：{title}", now_iso()),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            if new_path:
                new_path.unlink(missing_ok=True)
            flash(request, f"更新失败：{exc}", "error")
            return redirect("entry_edit", request, entry_id=str(entry_id))
    if old_path and old_path.exists():
        old_path.unlink(missing_ok=True)
    flash(request, "条目已更新，知识结构更加完整。")
    return redirect("entry_view", request, entry_id=str(entry_id))


@app.post("/entry/{entry_id}/delete", name="entry_delete")
def entry_delete(request: Request, entry_id: int):
    with connect() as conn:
        row = conn.execute("SELECT title, file_path FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))
        conn.execute(
            "INSERT INTO activities(action, entry_id, xp, detail, created_at) VALUES (?, NULL, ?, ?, ?)",
            ("delete", 0, f"删除：{row['title']}", now_iso()),
        )
        conn.commit()
    if row["file_path"]:
        (UPLOAD_DIR / row["file_path"]).unlink(missing_ok=True)
    flash(request, "条目已删除。")
    return redirect("library", request)


@app.post("/entry/{entry_id}/favorite", name="entry_favorite")
def entry_favorite(request: Request, entry_id: int):
    with connect() as conn:
        row = conn.execute("SELECT favorite FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        conn.execute("UPDATE entries SET favorite=?, updated_at=? WHERE id=?", (0 if row["favorite"] else 1, now_iso(), entry_id))
        conn.commit()
    referer = request.headers.get("referer")
    return RedirectResponse(url=referer or str(request.url_for("entry_view", entry_id=entry_id)), status_code=303)


@app.get("/search", response_class=HTMLResponse, name="search")
def search(request: Request, q: str = "", kind: str = "", domain: str = ""):
    q = q.strip()
    entries: list[dict[str, Any]] = []
    used_mode = "关键词模糊检索"
    with connect() as conn:
        if q:
            terms = [term for term in re.split(r"\s+", q) if term]
            fts_terms = [term.replace('"', "") for term in terms if term.replace('"', "")]
            if fts_terms:
                try:
                    match = " AND ".join(f'"{term}"*' for term in fts_terms)
                    sql = (
                        "SELECT e.*, bm25(entries_fts) AS rank FROM entries_fts "
                        "JOIN entries e ON e.id=entries_fts.rowid WHERE entries_fts MATCH ?"
                    )
                    params: list[Any] = [match]
                    if kind:
                        sql += " AND e.kind=?"
                        params.append(kind)
                    if domain:
                        sql += " AND e.domain=?"
                        params.append(domain)
                    sql += " ORDER BY rank LIMIT 100"
                    entries = [entry_dict(row) for row in conn.execute(sql, params)]
                    if entries:
                        used_mode = "SQLite FTS5 全文检索"
                except Exception:
                    entries = []
            if not entries:
                conditions = []
                params = []
                searchable = "lower(title || ' ' || summary || ' ' || content || ' ' || tags || ' ' || domain || ' ' || source)"
                for term in terms:
                    conditions.append(f"{searchable} LIKE ?")
                    params.append(f"%{term.lower()}%")
                sql = "SELECT * FROM entries WHERE " + " AND ".join(conditions or ["1=1"])
                if kind:
                    sql += " AND kind=?"
                    params.append(kind)
                if domain:
                    sql += " AND domain=?"
                    params.append(domain)
                sql += " ORDER BY favorite DESC, updated_at DESC LIMIT 100"
                entries = [entry_dict(row) for row in conn.execute(sql, params)]
        else:
            sql = "SELECT * FROM entries WHERE 1=1"
            params = []
            if kind:
                sql += " AND kind=?"
                params.append(kind)
            if domain:
                sql += " AND domain=?"
                params.append(domain)
            sql += " ORDER BY updated_at DESC LIMIT 100"
            entries = [entry_dict(row) for row in conn.execute(sql, params)]
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context=context(
            request,
            "search",
            entries=entries,
            q=q,
            selected_kind=kind,
            selected_domain=domain,
            used_mode=used_mode,
        ),
    )


@app.get("/files/{entry_id}", name="entry_file")
def entry_file(request: Request, entry_id: int, inline: int = 0):
    with connect() as conn:
        row = conn.execute("SELECT file_path, original_name, mime_type FROM entries WHERE id=?", (entry_id,)).fetchone()
    if not row or not row["file_path"]:
        raise HTTPException(status_code=404)
    path = UPLOAD_DIR / row["file_path"]
    if not path.exists():
        raise HTTPException(status_code=404)
    safe_inline = (row["mime_type"] or "").startswith("image/") or row["mime_type"] == "application/pdf"
    disposition = "inline" if inline == 1 and safe_inline else "attachment"
    return FileResponse(
        path,
        media_type=row["mime_type"] or mimetypes.guess_type(row["original_name"])[0],
        filename=row["original_name"],
        content_disposition_type=disposition,
    )


@app.post("/quests/new", name="quest_new")
def quest_new(request: Request, title: str = Form(...), description: str = Form(""), xp: int = Form(15)):
    title = title.strip()
    if not title:
        flash(request, "任务标题不能为空。", "error")
        return redirect("dashboard", request)
    xp = max(1, min(xp, 200))
    with connect() as conn:
        conn.execute(
            "INSERT INTO quests(title, description, xp, created_at) VALUES (?, ?, ?, ?)",
            (title, description.strip(), xp, now_iso()),
        )
        conn.commit()
    flash(request, "新任务已加入修炼清单。")
    return RedirectResponse(url=str(request.url_for("dashboard")) + "#quests", status_code=303)


@app.post("/quests/{quest_id}/toggle", name="quest_toggle")
def quest_toggle(request: Request, quest_id: int):
    with connect() as conn:
        quest = conn.execute("SELECT * FROM quests WHERE id=?", (quest_id,)).fetchone()
        if not quest:
            raise HTTPException(status_code=404)
        completing = not bool(quest["completed"])
        conn.execute(
            "UPDATE quests SET completed=?, completed_at=? WHERE id=?",
            (1 if completing else 0, now_iso() if completing else None, quest_id),
        )
        if completing:
            conn.execute(
                "INSERT INTO activities(action, xp, detail, created_at) VALUES (?, ?, ?, ?)",
                ("quest", quest["xp"], f"完成任务：{quest['title']}", now_iso()),
            )
        else:
            conn.execute(
                "INSERT INTO activities(action, xp, detail, created_at) VALUES (?, ?, ?, ?)",
                ("quest_reopen", -quest["xp"], f"重新开启任务：{quest['title']}", now_iso()),
            )
        conn.commit()
    return RedirectResponse(url=request.headers.get("referer") or str(request.url_for("dashboard")), status_code=303)


@app.post("/quests/{quest_id}/delete", name="quest_delete")
def quest_delete(request: Request, quest_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM quests WHERE id=?", (quest_id,))
        conn.commit()
    return RedirectResponse(url=request.headers.get("referer") or str(request.url_for("dashboard")), status_code=303)


@app.get("/settings", response_class=HTMLResponse, name="settings_page")
def settings_get(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context=context(
            request,
            "settings",
            current_site_name=get_setting("site_name", "问道科研"),
            current_researcher_name=get_setting("researcher_name", "准研一修士"),
            domain_text="\n".join(domains()),
            ai_mode=get_setting("ai_mode", "offline"),
            ai_endpoint=get_setting("ai_endpoint", "http://127.0.0.1:11434/api/generate"),
            ai_model=get_setting("ai_model", "qwen2.5:7b"),
            ai_status=provider_status(),
            realm_names_text="\n".join(configured_realm_names()),
            nav_labels_text="\n".join(f"{key}={value}" for key, value in navigation_labels().items()),
            review_popup=get_setting("review_popup", "1") == "1",
            portable_version=get_setting("portable_version", "1.2.0"),
        ),
    )


@app.post("/settings", name="settings_post")
def settings_post(
    request: Request,
    site_name: str = Form("问道科研"),
    researcher_name: str = Form("准研一修士"),
    domains_text: str = Form("", alias="domains"),
    ai_mode: str = Form("offline"),
    ai_endpoint: str = Form("http://127.0.0.1:11434/api/generate"),
    ai_model: str = Form("qwen2.5:7b"),
    realm_names: str = Form(""),
    nav_labels: str = Form(""),
    review_popup: str = Form(""),
):
    domain_list = [x.strip() for x in domains_text.splitlines() if x.strip()]
    if "未分类" not in domain_list:
        domain_list.append("未分类")
    set_setting("site_name", site_name.strip() or "问道科研")
    set_setting("researcher_name", researcher_name.strip() or "准研一修士")
    set_setting("domains", json.dumps(list(dict.fromkeys(domain_list)), ensure_ascii=False))
    set_setting("ai_mode", ai_mode if ai_mode in {"offline", "ollama", "openai"} else "offline")
    set_setting("ai_endpoint", ai_endpoint.strip() or "http://127.0.0.1:11434/api/generate")
    set_setting("ai_model", ai_model.strip() or "qwen2.5:7b")
    custom_realms = [line.strip()[:30] for line in realm_names.splitlines() if line.strip()]
    default_realm_names = [name for _, name, _ in REALMS]
    merged_realms = [
        custom_realms[index] if index < len(custom_realms) else default
        for index, default in enumerate(default_realm_names)
    ]
    set_setting("realm_names", json.dumps(merged_realms, ensure_ascii=False))
    parsed_nav = dict(DEFAULT_NAV_LABELS)
    for line in nav_labels.splitlines():
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if key in parsed_nav and value:
            parsed_nav[key] = value[:24]
    set_setting("nav_labels", json.dumps(parsed_nav, ensure_ascii=False))
    set_setting("review_popup", "1" if review_popup == "1" else "0")
    flash(request, "设置已保存。")
    return redirect("settings_page", request)


@app.get("/export/json", name="export_json")
def export_json(request: Request):
    with connect() as conn:
        entries = [dict(row) for row in conn.execute("SELECT * FROM entries ORDER BY id")]
        activities = [dict(row) for row in conn.execute("SELECT * FROM activities ORDER BY id")]
        quests = [dict(row) for row in conn.execute("SELECT * FROM quests ORDER BY id")]
        experiments = [dict(row) for row in conn.execute("SELECT * FROM experiments ORDER BY id")]
        simulations = [dict(row) for row in conn.execute("SELECT * FROM simulations ORDER BY id")]
        simulation_files = [dict(row) for row in conn.execute("SELECT * FROM simulation_files ORDER BY id")]
        research_tracks = [dict(row) for row in conn.execute("SELECT * FROM research_tracks ORDER BY sort_order,id")]
        research_plan_items = [dict(row) for row in conn.execute("SELECT * FROM research_plan_items ORDER BY track_id,sort_order,id")]
        research_folders = [dict(row) for row in conn.execute("SELECT * FROM research_folders ORDER BY id")]
        research_folder_files = [dict(row) for row in conn.execute("SELECT * FROM research_folder_files ORDER BY folder_id,relative_path")]
        mission_deliveries = [dict(row) for row in conn.execute("SELECT * FROM mission_deliveries ORDER BY id")]
        mission_delivery_files = [dict(row) for row in conn.execute("SELECT * FROM mission_delivery_files ORDER BY delivery_id,relative_path")]
        asset_transactions = [dict(row) for row in conn.execute("SELECT * FROM asset_transactions ORDER BY id")]
        inventory_items = [dict(row) for row in conn.execute("SELECT * FROM inventory_items ORDER BY id")]
        player_profile = [dict(row) for row in conn.execute("SELECT * FROM player_profile ORDER BY id")]
        easter_eggs = [dict(row) for row in conn.execute("SELECT * FROM easter_eggs ORDER BY egg_key")]
        review_sources = [dict(row) for row in conn.execute("SELECT * FROM review_sources ORDER BY id")]
        review_sessions = [dict(row) for row in conn.execute("SELECT * FROM review_sessions ORDER BY id")]
        review_answers = [dict(row) for row in conn.execute("SELECT * FROM review_answers ORDER BY id")]
        special_tasks = [dict(row) for row in conn.execute("SELECT * FROM special_tasks ORDER BY id")]
        herb_inventory = [dict(row) for row in conn.execute("SELECT * FROM herb_inventory ORDER BY grade")]
        settings_rows = [dict(row) for row in conn.execute("SELECT key,value FROM settings WHERE key NOT IN ('hub_api_token') ORDER BY key")]
    path = BACKUP_DIR / f"research_os_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    payload = {
        "entries": entries, "activities": activities, "quests": quests, "experiments": experiments,
        "simulations": simulations, "simulation_files": simulation_files,
        "research_tracks": research_tracks, "research_plan_items": research_plan_items,
        "research_folders": research_folders, "research_folder_files": research_folder_files,
        "mission_deliveries": mission_deliveries, "mission_delivery_files": mission_delivery_files,
        "asset_transactions": asset_transactions, "inventory_items": inventory_items,
        "player_profile": player_profile, "easter_eggs": easter_eggs,
        "review_sources": review_sources, "review_sessions": review_sessions,
        "review_answers": review_answers, "special_tasks": special_tasks,
        "herb_inventory": herb_inventory, "settings": settings_rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/backup", name="backup")
def backup(request: Request):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stage = BACKUP_DIR / f"research_os_backup_{timestamp}"
    stage.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        source_conn = connect()
        destination_conn = sqlite3.connect(stage / DB_PATH.name)
        try:
            source_conn.backup(destination_conn)
        finally:
            destination_conn.close()
            source_conn.close()
    storage_stage = stage / "storage"
    storage_stage.mkdir(exist_ok=True)
    for name, source in (("uploads", UPLOAD_DIR), ("simulations", SIMULATION_DIR), ("research_foundation", FOUNDATION_DIR), ("deliveries", DELIVERY_DIR), ("note_images", NOTE_IMAGE_DIR)):
        target = storage_stage / name
        if source.exists():
            shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".gitkeep"))
        else:
            target.mkdir(parents=True, exist_ok=True)
    manifest = {"version": get_setting("portable_version", "1.2.0"), "created_at": now_iso(), "database": DB_PATH.name}
    (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = shutil.make_archive(str(stage), "zip", root_dir=stage)
    shutil.rmtree(stage, ignore_errors=True)
    log_activity("backup", 5, "完成本地知识库备份")
    return FileResponse(archive, media_type="application/zip", filename=Path(archive).name)




def _number(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ollama_card(title: str, content: str) -> dict[str, Any]:
    endpoint = get_setting("ai_endpoint", "http://127.0.0.1:11434/api/generate")
    model = get_setting("ai_model", "qwen2.5:7b")
    prompt = f"""你是一名严谨的科研助理。根据论文文本生成中文结构化研读卡，只输出JSON，字段为 research_question、method、key_points(数组)、takeaway、keywords(数组)、relevance、limitations_prompt、next_actions(数组)。不得杜撰，信息不足写‘原文未明确说明’。论文题目：{title}\n论文文本：{content[:45000]}"""
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))
    raw = payload.get("response", "{}")
    card = json.loads(raw)
    card["title"] = title
    card["mode"] = f"本地 Ollama · {model}"
    return card


@app.post("/entry/{entry_id}/analyze", name="entry_analyze")
def entry_analyze(request: Request, entry_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        if not row["content"]:
            flash(request, "该条目没有可分析文本。扫描版 PDF 需要先 OCR。", "error")
            return redirect("entry_view", request, entry_id=str(entry_id))
        mode = get_setting("ai_mode", "offline")
        try:
            card = _ollama_card(row["title"], row["content"]) if mode == "ollama" else offline_paper_summary(row["title"], row["content"])
        except Exception as exc:
            card = offline_paper_summary(row["title"], row["content"])
            card["fallback_reason"] = str(exc)
            flash(request, "本地模型不可用，已自动改用离线规则摘要。", "error")
        conn.execute(
            "UPDATE entries SET analysis_json=?, updated_at=? WHERE id=?",
            (json.dumps(card, ensure_ascii=False), now_iso(), entry_id),
        )
        conn.execute(
            "INSERT INTO activities(action, entry_id, xp, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            ("analyze", entry_id, 12, f"生成研读卡：{row['title']}", now_iso()),
        )
        conn.commit()
    flash(request, "论文研读卡已生成。")
    return redirect("entry_view", request, entry_id=str(entry_id))


@app.post("/entry/{entry_id}/analysis-to-note", name="analysis_to_note")
def analysis_to_note(request: Request, entry_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        card = parse_json(row["analysis_json"], {})
        if not card:
            flash(request, "请先生成论文研读卡。", "error")
            return redirect("entry_view", request, entry_id=str(entry_id))
        ts = now_iso()
        cur = conn.execute(
            "INSERT INTO entries(title,kind,domain,tags,summary,content,source,created_at,updated_at,extract_status,indexed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"研读卡｜{row['title']}", "note", row["domain"], row["tags"], "由论文条目自动生成，可继续人工修订。", summary_to_markdown(card), f"关联条目 #{entry_id}", ts, ts, "generated", ts),
        )
        note_id = int(cur.lastrowid)
        conn.execute("INSERT INTO activities(action,entry_id,xp,detail,created_at) VALUES (?,?,?,?,?)", ("analysis_note", note_id, 10, f"沉淀研读卡：{row['title']}", ts))
        conn.commit()
    flash(request, "研读卡已转为可编辑笔记。")
    return redirect("entry_view", request, entry_id=str(note_id))


@app.post("/entry/{entry_id}/reindex", name="entry_reindex")
def entry_reindex(request: Request, entry_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row or not row["file_path"]:
            raise HTTPException(status_code=404)
        path = UPLOAD_DIR / row["file_path"]
        if not path.exists():
            flash(request, "原文件不存在，无法重新建立索引。", "error")
            return redirect("entry_view", request, entry_id=str(entry_id))
        extracted = extract_file(path)
        status = "ok" if extracted.get("content") else ("error" if extracted.get("error") else "no_text")
        conn.execute(
            "UPDATE entries SET content=?, mime_type=?, dataset_rows=?, dataset_columns=?, dataset_schema=?, dataset_preview=?, extract_status=?, indexed_at=?, updated_at=? WHERE id=?",
            (extracted.get("content", ""), extracted.get("mime_type", row["mime_type"]), extracted.get("rows"), extracted.get("columns"), json.dumps(extracted.get("schema", []), ensure_ascii=False), json.dumps(extracted.get("preview", []), ensure_ascii=False, default=str), status, now_iso(), now_iso(), entry_id),
        )
        conn.execute("INSERT INTO activities(action,entry_id,xp,detail,created_at) VALUES (?,?,?,?,?)", ("reindex", entry_id, 5, f"重建全文索引：{row['title']}", now_iso()))
        conn.commit()
    flash(request, "全文索引已重新建立。")
    return redirect("entry_view", request, entry_id=str(entry_id))


@app.get("/experiments", response_class=HTMLResponse, name="experiments_page")
def experiments_page(request: Request, edit: int = 0, status: str = ""):
    with connect() as conn:
        params: list[Any] = []
        sql = "SELECT * FROM experiments WHERE 1=1"
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY experiment_date DESC, updated_at DESC"
        items = [dict(row) for row in conn.execute(sql, params)]
        edit_row = conn.execute("SELECT * FROM experiments WHERE id=?", (edit,)).fetchone() if edit else None
        editing = dict(edit_row) if edit_row else None
        docs = [dict(row) for row in conn.execute("SELECT id,title FROM entries ORDER BY updated_at DESC LIMIT 300")]
    return templates.TemplateResponse(request=request, name="experiments.html", context=context(request, "experiments", items=items, editing=editing, selected_status=status, documents=docs))


@app.post("/experiments/save", name="experiment_save")
def experiment_save(
    request: Request,
    experiment_id: int = Form(0), sample_id: str = Form(...), experiment_date: str = Form(""), title: str = Form(""), status: str = Form("planned"),
    eg_content: str = Form(""), water_cement_ratio: str = Form(""), compaction_pressure: str = Form(""), thickness_cm: str = Form(""), area_cm2: str = Form(""),
    electrolyte: str = Form(""), voltage_min: str = Form(""), voltage_max: str = Form(""), scan_rate: str = Form(""), specific_capacitance: str = Form(""),
    conductivity: str = Form(""), compressive_strength: str = Form(""), hypothesis: str = Form(""), observations: str = Form(""), conclusion: str = Form(""),
    next_step: str = Form(""), tags: str = Form(""), attachment_entry_id: str = Form(""),
):
    sample_id = sample_id.strip()
    if not sample_id:
        flash(request, "样品编号不能为空。", "error")
        return redirect("experiments_page", request)
    values = (
        sample_id, experiment_date or None, title.strip(), status, _number(eg_content), _number(water_cement_ratio), _number(compaction_pressure), _number(thickness_cm), _number(area_cm2),
        electrolyte.strip(), _number(voltage_min), _number(voltage_max), _number(scan_rate), _number(specific_capacitance), _number(conductivity), _number(compressive_strength),
        hypothesis.strip(), observations.strip(), conclusion.strip(), next_step.strip(), tags.strip(), int(attachment_entry_id) if attachment_entry_id.isdigit() else None, now_iso(),
    )
    with connect() as conn:
        try:
            if experiment_id:
                conn.execute("""UPDATE experiments SET sample_id=?,experiment_date=?,title=?,status=?,eg_content=?,water_cement_ratio=?,compaction_pressure=?,thickness_cm=?,area_cm2=?,electrolyte=?,voltage_min=?,voltage_max=?,scan_rate=?,specific_capacitance=?,conductivity=?,compressive_strength=?,hypothesis=?,observations=?,conclusion=?,next_step=?,tags=?,attachment_entry_id=?,updated_at=? WHERE id=?""", values + (experiment_id,))
                action, xp = "experiment_update", 4
            else:
                conn.execute("""INSERT INTO experiments(sample_id,experiment_date,title,status,eg_content,water_cement_ratio,compaction_pressure,thickness_cm,area_cm2,electrolyte,voltage_min,voltage_max,scan_rate,specific_capacitance,conductivity,compressive_strength,hypothesis,observations,conclusion,next_step,tags,attachment_entry_id,updated_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values + (now_iso(),))
                action, xp = "experiment_create", 28
            conn.execute("INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)", (action, xp, f"EG实验：{sample_id}", now_iso()))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            flash(request, "样品编号已存在，请换一个编号。", "error")
            return redirect("experiments_page", request)
    flash(request, "实验记录已保存。")
    return redirect("experiments_page", request)


@app.post("/experiments/{experiment_id}/delete", name="experiment_delete")
def experiment_delete(request: Request, experiment_id: int):
    with connect() as conn:
        row = conn.execute("SELECT sample_id FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        conn.execute("DELETE FROM experiments WHERE id=?", (experiment_id,))
        conn.commit()
    flash(request, f"已删除实验记录：{row['sample_id'] if row else experiment_id}")
    return redirect("experiments_page", request)


@app.get("/experiments/export.csv", name="experiments_export")
def experiments_export():
    with connect() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM experiments ORDER BY experiment_date, id")]
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
    path = BACKUP_DIR / f"eg_experiments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    path.write_text("\ufeff" + output.getvalue(), encoding="utf-8")
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/simulations", response_class=HTMLResponse, name="simulations_page")
def simulations_page(request: Request):
    with connect() as conn:
        items = []
        for row in conn.execute("SELECT * FROM simulations ORDER BY updated_at DESC"):
            item = dict(row); item["summary"] = parse_json(item.get("summary_json", "{}"), {})
            item["files"] = [dict(x) for x in conn.execute("SELECT * FROM simulation_files WHERE simulation_id=? ORDER BY role,original_name", (row["id"],))]
            items.append(item)
    return templates.TemplateResponse(request=request, name="simulations.html", context=context(request, "simulations", items=items))


@app.post("/simulations/new", name="simulation_new")
def simulation_new(
    request: Request, case_name: str = Form(...), project_name: str = Form(""), ensemble: str = Form(""), forcefield: str = Form(""),
    temperature: str = Form(""), timestep: str = Form(""), run_command: str = Form(""), notes: str = Form(""), tags: str = Form(""), files: list[UploadFile] = File(default=[]),
):
    case_name = case_name.strip()
    if not case_name:
        flash(request, "案例名称不能为空。", "error")
        return redirect("simulations_page", request)
    folder_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{secure_filename(case_name)}"
    folder = SIMULATION_DIR / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    all_paths: list[Path] = []
    try:
        for upload in [f for f in files if f.filename]:
            target = folder / secure_filename(upload.filename or "file")
            with target.open("wb") as out:
                shutil.copyfileobj(upload.file, out)
            if target.suffix.lower() == ".zip":
                unpacked_dir = folder / target.stem
                all_paths.extend(unpack_lammps_bundle(target, unpacked_dir))
            else:
                all_paths.append(target)
        categorized = find_lammps_files(all_paths)
        parsed: dict[str, Any] = {}
        if categorized["logs"]:
            parsed = parse_lammps_log(categorized["logs"][0])
        ts = now_iso()
        with connect() as conn:
            cur = conn.execute("""INSERT INTO simulations(case_name,project_name,status,engine_version,ensemble,forcefield,atoms,steps,temperature,timestep,last_step,last_temp,last_etotal,warnings,errors,run_command,notes,tags,folder_path,summary_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                case_name, project_name.strip(), parsed.get("status", "NEW"), parsed.get("lammps_version", ""), ensemble.strip(), forcefield.strip(), parsed.get("atoms"), parsed.get("steps"), _number(temperature), _number(timestep), parsed.get("last_step"), parsed.get("last_temp"), parsed.get("last_etotal"), parsed.get("warnings", 0), parsed.get("errors", 0), run_command.strip(), notes.strip(), tags.strip(), folder_name, json.dumps(parsed, ensure_ascii=False), ts, ts,
            ))
            sim_id = int(cur.lastrowid)
            role_map = {id(path): role for role, paths in categorized.items() for path in paths}
            for path in all_paths:
                conn.execute("INSERT INTO simulation_files(simulation_id,role,file_path,original_name,file_size,created_at) VALUES (?,?,?,?,?,?)", (sim_id, role_map.get(id(path), "other"), str(path.relative_to(folder)), path.name, path.stat().st_size, ts))
            conn.execute("INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)", ("simulation_create", 34, f"归档LAMMPS案例：{case_name}", ts))
            conn.commit()
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        flash(request, f"模拟案例归档失败：{exc}", "error")
        return redirect("simulations_page", request)
    flash(request, "LAMMPS案例已归档并完成日志解析。")
    return redirect("simulations_page", request)


@app.post("/simulations/{simulation_id}/update", name="simulation_update")
def simulation_update(request: Request, simulation_id: int, status: str = Form("NEW"), notes: str = Form(""), tags: str = Form("")):
    with connect() as conn:
        conn.execute("UPDATE simulations SET status=?,notes=?,tags=?,updated_at=? WHERE id=?", (status, notes.strip(), tags.strip(), now_iso(), simulation_id))
        conn.commit()
    flash(request, "模拟案例已更新。")
    return redirect("simulations_page", request)


@app.post("/simulations/{simulation_id}/delete", name="simulation_delete")
def simulation_delete(request: Request, simulation_id: int):
    with connect() as conn:
        row = conn.execute("SELECT folder_path,case_name FROM simulations WHERE id=?", (simulation_id,)).fetchone()
        conn.execute("DELETE FROM simulations WHERE id=?", (simulation_id,))
        conn.commit()
    if row:
        shutil.rmtree(SIMULATION_DIR / row["folder_path"], ignore_errors=True)
    flash(request, "模拟案例已删除。")
    return redirect("simulations_page", request)


@app.get("/simulations/{simulation_id}/files/{file_id}", name="simulation_file")
def simulation_file(simulation_id: int, file_id: int):
    with connect() as conn:
        row = conn.execute("SELECT s.folder_path,f.file_path,f.original_name FROM simulation_files f JOIN simulations s ON s.id=f.simulation_id WHERE f.id=? AND f.simulation_id=?", (file_id, simulation_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404)
    base = (SIMULATION_DIR / row["folder_path"]).resolve()
    path = (base / row["file_path"]).resolve()
    if base not in path.parents or not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path, filename=row["original_name"])


@app.get("/cultivation", response_class=HTMLResponse, name="cultivation_page")
def cultivation_page(request: Request):
    with connect() as conn:
        xp = total_xp(conn)
        activity_rows = [dict(row) for row in conn.execute("SELECT action,SUM(xp) xp,COUNT(*) n FROM activities GROUP BY action ORDER BY xp DESC")]
        totals = dict(conn.execute("""SELECT COUNT(*) total, COALESCE(SUM(CASE WHEN trim(tags)!='' THEN 1 ELSE 0 END),0) tagged, COALESCE(SUM(CASE WHEN trim(summary)!='' THEN 1 ELSE 0 END),0) summarized, COALESCE(SUM(CASE WHEN analysis_json!='{}' THEN 1 ELSE 0 END),0) analyzed FROM entries""").fetchone())
        exp_total = conn.execute("SELECT COUNT(*) n FROM experiments").fetchone()["n"]
        sim_total = conn.execute("SELECT COUNT(*) n FROM simulations").fetchone()["n"]
        total_assets = totals["total"] + exp_total + sim_total
        quality_points = totals["tagged"] * 2 + totals["summarized"] * 2 + totals["analyzed"] * 4 + exp_total * 5 + sim_total * 5
        quality = min(100, round(quality_points / max(total_assets * 5, 1) * 100))
        quests = [dict(row) for row in conn.execute("SELECT * FROM quests ORDER BY completed,due_date,created_at DESC")]
        ach = achievements(conn)
        streak = activity_streak(conn)
    return templates.TemplateResponse(request=request, name="cultivation.html", context=context(request, "cultivation", xp=xp, realm=current_realm(xp), streak=streak, activity_rows=activity_rows, totals=totals, exp_total=exp_total, sim_total=sim_total, quality=quality, quests=quests, achievements=ach))



@app.get("/portable", name="portable_export")
def portable_export():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = BACKUP_DIR / f"ResearchCultivationOS_portable_{timestamp}.zip"
    excluded_dirs = {".venv", "__pycache__", ".git", "backups", "build", "dist"}
    excluded_suffixes = {".pyc", ".pyo"}
    with tempfile.TemporaryDirectory() as tmp:
        consistent_db = Path(tmp) / DB_PATH.name
        if DB_PATH.exists():
            source_conn = connect()
            destination_conn = sqlite3.connect(consistent_db)
            try:
                source_conn.backup(destination_conn)
            finally:
                destination_conn.close()
                source_conn.close()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path in BASE_DIR.rglob("*"):
                relative = path.relative_to(BASE_DIR)
                if any(part in excluded_dirs for part in relative.parts):
                    continue
                if relative.parts[:1] == ("instance",) and (path.name.startswith("research_os.db") or path.name.startswith("hub.db") or path.name in {"hub_secret.txt", "HUB_ADMIN_CREDENTIALS.txt"}):
                    continue
                if path == archive or path.suffix.lower() in excluded_suffixes:
                    continue
                if path.is_file():
                    zf.write(path, Path("ResearchCultivationOS") / relative)
            if consistent_db.exists():
                zf.write(consistent_db, "ResearchCultivationOS/instance/research_os.db")
            manifest = {
                "name": "Research Cultivation OS",
                "version": get_setting("portable_version", "1.2.0"),
                "created_at": now_iso(),
                "instructions": "Unzip, then double-click Start_Research_OS.cmd. The local environment is recreated automatically.",
            }
            zf.writestr("ResearchCultivationOS/PORTABLE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    log_activity("portable_export", 5, "生成整套便携迁移包")
    return FileResponse(archive, media_type="application/zip", filename=archive.name)


@app.get("/api/stats", name="api_stats")
def api_stats():
    with connect() as conn:
        xp = total_xp(conn)
        return JSONResponse(
            {
                "entries": conn.execute("SELECT COUNT(*) n FROM entries").fetchone()["n"],
                "xp": xp,
                "realm": current_realm(xp),
                "streak": activity_streak(conn),
            }
        )


def _safe_relative_path(value: str) -> Path:
    """Return a portable, traversal-safe relative path while preserving folders."""
    raw = (value or "").replace("\\", "/").strip("/")
    parts: list[str] = []
    for part in raw.split("/"):
        part = part.strip()
        if not part or part in {".", ".."}:
            continue
        parts.append(secure_filename(part))
    return Path(*parts) if parts else Path("file")


def _folder_stats(path: Path) -> tuple[int, int]:
    count = 0
    total = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                count += 1
                total += item.stat().st_size
    return count, total


def _foundation_tracks(conn) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    for row in conn.execute("SELECT * FROM research_tracks WHERE active=1 ORDER BY sort_order,id"):
        item = dict(row)
        item["tasks"] = [dict(x) for x in conn.execute(
            "SELECT * FROM research_plan_items WHERE track_id=? ORDER BY sort_order,id", (row["id"],)
        )]
        item["folders"] = [dict(x) for x in conn.execute(
            "SELECT * FROM research_folders WHERE track_id=? ORDER BY updated_at DESC", (row["id"],)
        )]
        total = len(item["tasks"])
        completed = sum(1 for x in item["tasks"] if x["status"] == "done")
        item["progress"] = round(completed / total * 100) if total else 0
        tracks.append(item)
    return tracks


def _parse_foundation_text(text: str) -> list[dict[str, Any]]:
    """Parse a forgiving Markdown-like master plan into research tracks."""
    tracks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    field_map = {
        "目标": "objective", "长期目标": "objective", "主目标": "objective",
        "当前阶段": "current_stage", "阶段": "current_stage",
        "下一步": "next_focus", "近期重点": "next_focus", "当前重点": "next_focus",
        "备注": "notes", "说明": "notes",
    }
    status_map = {"x": "done", "✓": "done", "完成": "done", "进行中": "active", "推进": "active", "暂停": "paused"}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        heading = re.match(r"^(?:#{1,4}\s*|【)([^】#]+?)(?:】)?$", line)
        if heading:
            name = heading.group(1).strip()
            if name and name not in {"科研底座", "研究计划", "总计划"}:
                current = {"name": name, "icon": "◇", "objective": "", "current_stage": "", "next_focus": "", "notes": "", "tasks": []}
                tracks.append(current)
            continue
        if current is None:
            section = re.match(r"^([^：:]{2,30})[：:]\s*$", line)
            if section:
                current = {"name": section.group(1).strip(), "icon": "◇", "objective": "", "current_stage": "", "next_focus": "", "notes": "", "tasks": []}
                tracks.append(current)
                continue
            else:
                continue
        field = re.match(r"^([^：:]{1,12})[：:]\s*(.+)$", line)
        if field and field.group(1).strip() in field_map:
            current[field_map[field.group(1).strip()]] = field.group(2).strip()
            continue
        icon_match = re.match(r"^(?:图标|ICON)[：:]\s*(.+)$", line, re.I)
        if icon_match:
            current["icon"] = icon_match.group(1).strip()[:4]
            continue
        task_match = re.match(r"^[-*+]\s*(?:\[([^\]]*)\])?\s*(.+)$", line)
        if task_match:
            marker = (task_match.group(1) or "").strip().lower()
            body = task_match.group(2).strip()
            parts = [x.strip() for x in re.split(r"\s*\|\s*", body) if x.strip()]
            title = parts[0]
            task = {"title": title, "description": "", "deliverable": "", "status": status_map.get(marker, "planned"), "priority": "normal", "due_date": ""}
            for part in parts[1:]:
                kv = re.match(r"^([^：:]+)[：:]\s*(.*)$", part)
                if not kv:
                    task["description"] = (task["description"] + " " + part).strip()
                    continue
                key, value = kv.group(1).strip(), kv.group(2).strip()
                if key in {"交付", "交付物", "证据"}: task["deliverable"] = value
                elif key in {"说明", "描述"}: task["description"] = value
                elif key in {"状态"}: task["status"] = {"完成":"done","进行中":"active","暂停":"paused","计划":"planned"}.get(value, value)
                elif key in {"优先", "优先级"}: task["priority"] = {"高":"high","中":"normal","低":"low"}.get(value, value)
                elif key in {"截止", "日期"}: task["due_date"] = value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else ""
            current["tasks"].append(task)
    return tracks


@app.get("/foundation", response_class=HTMLResponse, name="foundation_page")
def foundation_page(request: Request, edit_track: int | None = None):
    # v1.2 removes the long-term "main line" from the user experience. The
    # legacy tables and endpoints remain readable during migration so an
    # upgrade never destroys older data.
    return RedirectResponse(request.url_for("plans_page"), status_code=303)
    # Legacy renderer retained below for backward-compatible data recovery.
    with connect() as conn:
        tracks = _foundation_tracks(conn)
        unassigned_folders = [dict(x) for x in conn.execute(
            "SELECT * FROM research_folders WHERE track_id IS NULL ORDER BY updated_at DESC"
        )]
        totals = dict(conn.execute(
            "SELECT COUNT(*) total, COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END),0) done, COALESCE(SUM(CASE WHEN status='active' THEN 1 ELSE 0 END),0) active FROM research_plan_items"
        ).fetchone())
    return templates.TemplateResponse(
        request=request,
        name="foundation.html",
        context=context(
            request, "foundation", tracks=tracks, unassigned_folders=unassigned_folders,
            master_text=get_setting("foundation_master_text", ""), totals=totals, edit_track=edit_track,
        ),
    )


@app.post("/foundation/sync", name="foundation_sync")
def foundation_sync(request: Request, master_text: str = Form(...)):
    parsed = _parse_foundation_text(master_text)
    if not parsed:
        flash(request, "没有识别到学科标题。请使用“# 学科名”开始每条路线。", "error")
        return redirect("foundation_page", request)
    ts = now_iso()
    with connect() as conn:
        conn.execute("UPDATE research_tracks SET sort_order=sort_order+?", (len(parsed),))
        for order, track in enumerate(parsed):
            row = conn.execute("SELECT id,icon FROM research_tracks WHERE name=?", (track["name"],)).fetchone()
            if row:
                track_id = row["id"]
                icon = track["icon"] if track["icon"] != "◇" else row["icon"]
                conn.execute(
                    "UPDATE research_tracks SET icon=?,objective=?,current_stage=?,next_focus=?,notes=?,sort_order=?,active=1,updated_at=? WHERE id=?",
                    (icon, track["objective"], track["current_stage"], track["next_focus"], track["notes"], order, ts, track_id),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO research_tracks(name,icon,objective,current_stage,next_focus,notes,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (track["name"], track["icon"], track["objective"], track["current_stage"], track["next_focus"], track["notes"], order, ts, ts),
                )
                track_id = int(cur.lastrowid)
            if track["tasks"]:
                conn.execute("DELETE FROM research_plan_items WHERE track_id=?", (track_id,))
                for item_order, task in enumerate(track["tasks"]):
                    conn.execute(
                        "INSERT INTO research_plan_items(track_id,title,description,deliverable,status,priority,due_date,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (track_id, task["title"], task["description"], task["deliverable"], task["status"], task["priority"], task["due_date"] or None, item_order, ts, ts),
                    )
        conn.execute(
            "INSERT INTO settings(key,value) VALUES ('foundation_master_text',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (master_text.strip(),),
        )
        conn.execute("INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)", ("foundation_sync", 18, f"同步科研底座：{len(parsed)}条学科路线", ts))
        conn.commit()
    flash(request, f"已同步 {len(parsed)} 条学科路线。未写日期的任务会长期保留。")
    return redirect("foundation_page", request)


@app.post("/foundation/tracks/new", name="foundation_track_new")
def foundation_track_new(request: Request, name: str = Form(...), icon: str = Form("◇")):
    name = name.strip()
    if not name:
        flash(request, "学科名称不能为空。", "error")
        return redirect("foundation_page", request)
    ts = now_iso()
    try:
        with connect() as conn:
            order = conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 n FROM research_tracks").fetchone()["n"]
            conn.execute("INSERT INTO research_tracks(name,icon,sort_order,created_at,updated_at) VALUES (?,?,?,?,?)", (name, icon.strip()[:4] or "◇", order, ts, ts))
            conn.execute("INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)", ("foundation_track", 8, f"建立学科路线：{name}", ts))
            conn.commit()
    except sqlite3.IntegrityError:
        flash(request, "同名学科路线已经存在。", "error")
        return redirect("foundation_page", request)
    flash(request, "学科路线已建立。")
    return redirect("foundation_page", request)


@app.post("/foundation/tracks/{track_id}/save", name="foundation_track_save")
def foundation_track_save(
    request: Request, track_id: int, name: str = Form(...), icon: str = Form("◇"),
    objective: str = Form(""), current_stage: str = Form(""), next_focus: str = Form(""), notes: str = Form(""),
):
    try:
        with connect() as conn:
            conn.execute(
                "UPDATE research_tracks SET name=?,icon=?,objective=?,current_stage=?,next_focus=?,notes=?,updated_at=? WHERE id=?",
                (name.strip(), icon.strip()[:4] or "◇", objective.strip(), current_stage.strip(), next_focus.strip(), notes.strip(), now_iso(), track_id),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        flash(request, "同名学科路线已经存在，请换一个名称。", "error")
        return RedirectResponse(url=f"{request.url_for('foundation_page')}?edit_track={track_id}", status_code=303)
    flash(request, "这条学科路线已更新。")
    return redirect("foundation_track_page", request, track_id=track_id)


@app.post("/foundation/tracks/{track_id}/delete", name="foundation_track_delete")
def foundation_track_delete(request: Request, track_id: int):
    with connect() as conn:
        row = conn.execute("SELECT name FROM research_tracks WHERE id=?", (track_id,)).fetchone()
        conn.execute("DELETE FROM research_tracks WHERE id=?", (track_id,))
        conn.commit()
    flash(request, f"已删除学科路线：{row['name'] if row else track_id}。")
    return redirect("foundation_page", request)


@app.post("/foundation/tracks/{track_id}/tasks/new", name="foundation_task_new")
def foundation_task_new(
    request: Request, track_id: int, title: str = Form(...), description: str = Form(""),
    deliverable: str = Form(""), priority: str = Form("normal"), due_date: str = Form(""),
):
    ts = now_iso()
    with connect() as conn:
        order = conn.execute("SELECT COALESCE(MAX(sort_order),-1)+1 n FROM research_plan_items WHERE track_id=?", (track_id,)).fetchone()["n"]
        conn.execute(
            "INSERT INTO research_plan_items(track_id,title,description,deliverable,priority,due_date,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (track_id, title.strip(), description.strip(), deliverable.strip(), priority, due_date or None, order, ts, ts),
        )
        conn.commit()
    flash(request, "计划项已加入；截止日期可以留空，作为长期任务。")
    return redirect("foundation_track_page", request, track_id=track_id)


@app.post("/foundation/tasks/{task_id}/save", name="foundation_task_save")
def foundation_task_save(
    request: Request, task_id: int, title: str = Form(...), description: str = Form(""),
    deliverable: str = Form(""), status: str = Form("planned"), priority: str = Form("normal"), due_date: str = Form(""),
):
    with connect() as conn:
        row = conn.execute("SELECT track_id FROM research_plan_items WHERE id=?", (task_id,)).fetchone()
        conn.execute(
            "UPDATE research_plan_items SET title=?,description=?,deliverable=?,status=?,priority=?,due_date=?,updated_at=? WHERE id=?",
            (title.strip(), description.strip(), deliverable.strip(), status, priority, due_date or None, now_iso(), task_id),
        )
        conn.commit()
    flash(request, "计划项已修改。")
    return redirect("foundation_track_page", request, track_id=row["track_id"] if row else 1)


@app.post("/foundation/tasks/{task_id}/toggle", name="foundation_task_toggle")
def foundation_task_toggle(request: Request, task_id: int):
    with connect() as conn:
        row = conn.execute("SELECT status,title,track_id FROM research_plan_items WHERE id=?", (task_id,)).fetchone()
        if row:
            new_status = "done" if row["status"] != "done" else "active"
            conn.execute("UPDATE research_plan_items SET status=?,updated_at=? WHERE id=?", (new_status, now_iso(), task_id))
            if new_status == "done":
                conn.execute("INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)", ("foundation_task_done", 12, f"完成底座计划：{row['title']}", now_iso()))
            conn.commit()
    return redirect("foundation_track_page", request, track_id=row["track_id"] if row else 1)


@app.post("/foundation/tasks/{task_id}/delete", name="foundation_task_delete")
def foundation_task_delete(request: Request, task_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM research_plan_items WHERE id=?", (task_id,))
        conn.commit()
    flash(request, "计划项已删除。")
    return redirect("foundation_page", request)


@app.post("/foundation/folders/upload", name="foundation_folder_upload")
def foundation_folder_upload(
    request: Request, folder_name: str = Form(""), description: str = Form(""), track_id: str = Form(""),
    relative_paths: str = Form("[]"), files: list[UploadFile] = File(default=[]),
):
    uploads = [item for item in files if item.filename]
    if not uploads:
        flash(request, "请选择一个包含文件的文件夹。", "error")
        return redirect("foundation_page", request)
    try:
        rel_paths = json.loads(relative_paths or "[]")
    except json.JSONDecodeError:
        rel_paths = []
    raw_root = ""
    for candidate in rel_paths:
        if candidate:
            raw_root = str(candidate).replace("\\", "/").split("/")[0]
            break
    display_name = folder_name.strip() or raw_root or f"科研交付_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    storage_key = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:10]}"
    root = FOUNDATION_DIR / storage_key
    root.mkdir(parents=True, exist_ok=True)
    ts = now_iso()
    track_value = int(track_id) if track_id.strip().isdigit() else None
    saved: list[tuple[Path, str, str, int]] = []
    try:
        for index, upload in enumerate(uploads):
            rel_value = rel_paths[index] if index < len(rel_paths) else upload.filename or f"file_{index}"
            rel = _safe_relative_path(str(rel_value))
            # Drop the selected root folder name because the archive already has its own root.
            if len(rel.parts) > 1 and raw_root and rel.parts[0] == secure_filename(raw_root):
                rel = Path(*rel.parts[1:])
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as out:
                shutil.copyfileobj(upload.file, out)
            saved.append((target, str(rel).replace("\\", "/"), upload.content_type or mimetypes.guess_type(target.name)[0] or "", target.stat().st_size))
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO research_folders(track_id,name,description,storage_key,file_count,total_size,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (track_value, display_name, description.strip(), storage_key, len(saved), sum(x[3] for x in saved), ts, ts),
            )
            folder_id = int(cur.lastrowid)
            for target, rel, mime, size in saved:
                conn.execute(
                    "INSERT INTO research_folder_files(folder_id,relative_path,stored_path,original_name,mime_type,file_size,created_at) VALUES (?,?,?,?,?,?,?)",
                    (folder_id, rel, rel, target.name, mime, size, ts),
                )
            conn.execute("INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)", ("foundation_folder", min(35, 10 + len(saved)), f"归档科研交付文件夹：{display_name}", ts))
            conn.commit()
    except Exception as exc:
        shutil.rmtree(root, ignore_errors=True)
        flash(request, f"文件夹归档失败：{exc}", "error")
        return redirect("foundation_page", request)
    flash(request, f"文件夹“{display_name}”已独立归档，共 {len(saved)} 个文件。")
    return redirect("foundation_page", request)


@app.get("/foundation/folders/{folder_id}", response_class=HTMLResponse, name="foundation_folder_view")
def foundation_folder_view(request: Request, folder_id: int):
    with connect() as conn:
        folder = conn.execute("SELECT f.*,t.name track_name FROM research_folders f LEFT JOIN research_tracks t ON t.id=f.track_id WHERE f.id=?", (folder_id,)).fetchone()
        files = [dict(x) for x in conn.execute("SELECT * FROM research_folder_files WHERE folder_id=? ORDER BY relative_path", (folder_id,))]
    if not folder:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request=request, name="foundation_folder.html", context=context(request, "foundation", folder=dict(folder), files=files))


@app.get("/foundation/folders/{folder_id}/files/{file_id}", name="foundation_folder_file")
def foundation_folder_file(folder_id: int, file_id: int):
    with connect() as conn:
        row = conn.execute("SELECT f.storage_key,ff.stored_path,ff.original_name,ff.mime_type FROM research_folder_files ff JOIN research_folders f ON f.id=ff.folder_id WHERE ff.id=? AND ff.folder_id=?", (file_id, folder_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404)
    root = (FOUNDATION_DIR / row["storage_key"]).resolve()
    path = (root / row["stored_path"]).resolve()
    if root not in path.parents or not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path, filename=row["original_name"], media_type=row["mime_type"] or None)


@app.get("/foundation/folders/{folder_id}/download", name="foundation_folder_download")
def foundation_folder_download(folder_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM research_folders WHERE id=?", (folder_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404)
    root = FOUNDATION_DIR / row["storage_key"]
    archive = BACKUP_DIR / f"{secure_filename(row['name'])}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(root))
    return FileResponse(archive, filename=archive.name, media_type="application/zip")


@app.post("/foundation/folders/{folder_id}/delete", name="foundation_folder_delete")
def foundation_folder_delete(request: Request, folder_id: int):
    with connect() as conn:
        row = conn.execute("SELECT storage_key,name FROM research_folders WHERE id=?", (folder_id,)).fetchone()
        conn.execute("DELETE FROM research_folders WHERE id=?", (folder_id,))
        conn.commit()
    if row:
        shutil.rmtree(FOUNDATION_DIR / row["storage_key"], ignore_errors=True)
    flash(request, f"文件夹“{row['name'] if row else folder_id}”已删除。")
    return redirect("foundation_page", request)


init_db()

# Feature modules keep the high-frequency experience isolated from the legacy archive modules.
from features.daily import register_daily_routes
from features.assistant_hub import register_assistant_routes
from features.discover import register_discover_routes
from features.folders import register_folder_routes
from features.foundation_ui import register_foundation_ui_routes
from features.game_world import register_game_routes
from features.online_sync import register_online_routes
from features.review import register_review_routes
from features.alchemy import register_alchemy_routes

register_daily_routes(app, templates, context, flash)
register_assistant_routes(app, templates, context)
register_discover_routes(app, templates, context)
register_folder_routes(app, templates, context)
register_foundation_ui_routes(app, templates, context)
register_game_routes(app, templates, context, flash, current_realm)
register_online_routes(app, templates, context, flash)
register_review_routes(app, templates, context, flash)
register_alchemy_routes(app, templates, context, flash)
register_backup_jobs(app)
