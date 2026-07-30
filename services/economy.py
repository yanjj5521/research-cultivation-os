from __future__ import annotations

from typing import Any

from db import now_iso

ASSETS = {
    "spirit_stone": {"name": "灵石", "icon": "◆"},
    "spirit_wood": {"name": "灵木", "icon": "⌁"},
    "mystic_iron": {"name": "玄铁", "icon": "⬢"},
    "star_sand": {"name": "星砂", "icon": "✦"},
}


def balance(conn, asset_key: str = "spirit_stone") -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM asset_transactions WHERE asset_key=?",
        (asset_key,),
    ).fetchone()
    return int(row["total"] or 0)


def balances(conn) -> dict[str, int]:
    values = {key: 0 for key in ASSETS}
    for row in conn.execute("SELECT asset_key,COALESCE(SUM(amount),0) total FROM asset_transactions GROUP BY asset_key"):
        values[row["asset_key"]] = int(row["total"] or 0)
    return values


def transact(conn, asset_key: str, amount: int, reason: str, mission_id: int | None = None) -> None:
    if asset_key not in ASSETS:
        raise ValueError("未知资材")
    if amount < 0 and balance(conn, asset_key) + amount < 0:
        raise ValueError(f"{ASSETS[asset_key]['name']}不足")
    conn.execute(
        "INSERT INTO asset_transactions(asset_key,amount,reason,mission_id,created_at) VALUES (?,?,?,?,?)",
        (asset_key, int(amount), reason, mission_id, now_iso()),
    )


def mission_rewards(mission: Any) -> dict[str, int]:
    xp = max(1, int(mission["xp"] or 1))
    optional = bool(mission["optional"])
    stones = max(5, round(xp * (0.55 if optional else 0.8)))
    reward = {"spirit_stone": stones}
    category = str(mission["category"] or "")
    title = str(mission["title"] or "")
    text = f"{category} {title}".lower()
    if any(token in text for token in ["实验", "水泥", "膨胀石墨", "eg"]):
        reward["mystic_iron"] = 2 if not optional else 1
    elif any(token in text for token in ["md", "lammps", "机器学习", "ml", "代码", "数据"]):
        reward["star_sand"] = 2 if not optional else 1
    else:
        reward["spirit_wood"] = 2 if not optional else 1
    return reward


def award_mission(conn, mission: Any) -> dict[str, int]:
    rewards = mission_rewards(mission)
    equipped = conn.execute(
        """
        SELECT item_key,level FROM inventory_items
        WHERE item_type='artifact' AND equipped=1
        ORDER BY updated_at DESC,id DESC LIMIT 1
        """
    ).fetchone()
    if equipped and equipped["item_key"] == "returning_furnace":
        material_key = next(
            (key for key in rewards if key != "spirit_stone"),
            "spirit_wood",
        )
        rewards[material_key] = rewards.get(material_key, 0) + max(
            1, int(equipped["level"] or 1)
        )
    for asset_key, amount in rewards.items():
        transact(conn, asset_key, amount, f"完成任务：{mission['title']}", int(mission["id"]))
    return rewards
