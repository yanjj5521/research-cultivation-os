from __future__ import annotations

from typing import Any


DEFAULT_NAV_LABELS = {
    "dashboard": "主页",
    "daily": "每日任务",
    "cultivation": "修炼记录",
    "review": "温故知新",
    "plans": "近期计划",
    "projects": "课题推进",
    "career": "生涯罗盘",
    "retreat": "闭关计时",
    "idle": "挂机静修",
    "literature_report": "文献汇报",
    "workbench": "实用工作台",
    "trials": "秘境试炼",
    "achievements": "成就图鉴",
    "alchemy": "炼丹炉",
    "world": "我的洞府",
    "profile": "个人主页",
    "assistant": "AI 协作",
    "online": "同行会",
    "library": "知识库",
    "folders": "交付文件夹",
    "note_new": "写笔记",
    "upload": "上传资料",
    "search": "全库检索",
    "discover": "联网找论文",
    "workspaces": "工作区管理",
    "settings": "设置与备份",
    "group_cultivation": "科研主线",
    "group_knowledge": "轻量推进",
    "group_workspaces": "我的工作区",
    "group_growth": "成长与趣味",
    "group_system": "协作与系统",
    "start": "记录进展",
    "knowledge_export": "一键导出知识库",
    "backup": "完整备份",
}

NAV_GROUP_DEFAULT_ITEMS = {
    "cultivation": (
        "dashboard", "literature_report", "workbench", "projects", "library", "search", "note_new", "upload",
    ),
    "knowledge": (
        "daily", "plans", "review", "cultivation", "retreat", "folders", "discover",
    ),
    "workspaces": ("workspace_shortcuts", "workspaces"),
    "growth": (
        "career", "trials", "achievements", "alchemy", "world", "profile", "idle",
    ),
    "system": ("assistant", "online", "settings"),
}

# The default sidebar should answer “what helps me learn or write now?” in one
# glance.  Everything else remains available through navigation settings, but
# does not compete with reading, reporting, writing, figures and knowledge.
NAV_ITEM_DEFAULT_VISIBLE = {
    "dashboard": True,
    "literature_report": True,
    "workbench": True,
    "projects": True,
    "library": True,
    "search": True,
    "note_new": True,
    "discover": True,
    "online": True,
    "settings": True,
}

DEFAULT_NAV_LAYOUT = [
    {
        "key": group_key,
        "items": [{"key": item_key, "visible": NAV_ITEM_DEFAULT_VISIBLE.get(item_key, False)} for item_key in item_keys],
    }
    for group_key, item_keys in NAV_GROUP_DEFAULT_ITEMS.items()
]


def normalize_nav_labels(value: Any) -> dict[str, str]:
    labels = dict(DEFAULT_NAV_LABELS)
    if isinstance(value, dict):
        for key in DEFAULT_NAV_LABELS:
            candidate = str(value.get(key, "")).strip()[:24]
            if candidate:
                labels[key] = candidate
    return labels


def _nav_visible(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "hidden"}
    if value is None:
        return False
    return bool(value)


def normalize_nav_layout(value: Any) -> list[dict[str, Any]]:
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
                items.append({"key": item_key, "visible": NAV_ITEM_DEFAULT_VISIBLE.get(item_key, False)})
        normalized.append({"key": group_key, "items": items})

    for group_key, item_keys in NAV_GROUP_DEFAULT_ITEMS.items():
        if group_key not in seen_groups:
            normalized.append(
                {
                    "key": group_key,
                    "items": [
                        {"key": item_key, "visible": NAV_ITEM_DEFAULT_VISIBLE.get(item_key, False)} for item_key in item_keys
                    ],
                }
            )
    return normalized
