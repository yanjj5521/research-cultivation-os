from __future__ import annotations

from typing import Any

ARTIFACTS = {
    "qingxin_slip": {"name": "清心玉简", "icon": "▤", "price": 12, "desc": "开宗礼包即可换取，提醒自己只保留最重要的问题。"},
    "measuring_ruler": {"name": "量天尺", "icon": "⌇", "price": 45, "desc": "象征统一单位、尺度与比较口径。"},
    "returning_furnace": {"name": "归一炉", "icon": "◉", "price": 68, "desc": "把零散数据炼成可复用的方法。"},
    "star_compass": {"name": "观星罗盘", "icon": "✧", "price": 88, "desc": "帮助你在大量文献中不偏离主问题。"},
}

BUILDINGS = {
    "scripture_pavilion": {
        "name": "藏经阁", "icon": "阁", "desc": "文献、笔记与知识检索之所。", "asset": "spirit_wood",
        "base_cost": 8,
    },
    "alchemy_room": {
        "name": "炼丹房", "icon": "丹", "desc": "实验数据、机器学习与结构化资产之所。", "asset": "star_sand",
        "base_cost": 8,
    },
    "forge_hall": {
        "name": "炼器坊", "icon": "器", "desc": "LAMMPS、代码、SOP与可复现案例之所。", "asset": "mystic_iron",
        "base_cost": 8,
    },
    "herb_garden": {
        "name": "灵植园", "icon": "圃", "desc": "特殊任务获得的分级灵草在这里生长。", "asset": "spirit_wood",
        "base_cost": 10,
    },
}

HERB_STAGES = [
    (0, "种子", "·"),
    (8, "破土", "♩"),
    (20, "幼苗", "♧"),
    (38, "展叶", "☘"),
    (62, "含苞", "⚘"),
    (85, "灵花", "✿"),
    (100, "道果", "❋"),
]


def inventory_map(conn) -> dict[str, dict[str, Any]]:
    return {row["item_key"]: dict(row) for row in conn.execute("SELECT * FROM inventory_items")}


def building_level(conn, key: str) -> int:
    row = conn.execute("SELECT level FROM inventory_items WHERE item_key=? AND item_type='building'", (key,)).fetchone()
    return int(row["level"]) if row else 0


def building_cost(key: str, level: int) -> int:
    return int(BUILDINGS[key]["base_cost"] * max(1, level + 1))


def herb_stage(score: int) -> dict[str, Any]:
    selected = HERB_STAGES[0]
    for stage in HERB_STAGES:
        if score >= stage[0]:
            selected = stage
        else:
            break
    return {"threshold": selected[0], "name": selected[1], "icon": selected[2]}


def track_score(conn, track: Any) -> int:
    track_id = int(track["id"])
    tasks = conn.execute(
        "SELECT COUNT(*) total,COALESCE(SUM(status='done'),0) done FROM research_plan_items WHERE track_id=?",
        (track_id,),
    ).fetchone()
    entries = conn.execute("SELECT COUNT(*) n FROM entries WHERE domain=? AND status='active'", (track["name"],)).fetchone()["n"]
    direct_missions = conn.execute(
        "SELECT COUNT(*) n FROM daily_missions WHERE track_id=? AND completed=1", (track_id,)
    ).fetchone()["n"]
    keyword_missions = conn.execute(
        "SELECT COUNT(*) n FROM daily_missions WHERE completed=1 AND track_id IS NULL AND (title LIKE ? OR category LIKE ?)",
        (f"%{track['name']}%", f"%{track['name']}%"),
    ).fetchone()["n"]
    bonus = conn.execute("SELECT bonus_points FROM track_growth WHERE track_id=?", (track_id,)).fetchone()
    score = int(entries) * 5 + int(tasks["done"] or 0) * 12 + int(direct_missions) * 8 + int(keyword_missions) * 4 + int(bonus["bonus_points"] if bonus else 0)
    return min(100, score)


def garden(conn) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute("SELECT * FROM research_tracks WHERE active=1 ORDER BY sort_order,id"):
        track = dict(row)
        score = track_score(conn, row)
        track["growth"] = score
        track["herb"] = herb_stage(score)
        items.append(track)
    return items
