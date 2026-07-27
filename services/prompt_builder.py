from __future__ import annotations

from typing import Any


def current_state(conn) -> dict[str, Any]:
    profile = conn.execute(
        "SELECT display_name,title,goals,skills,capabilities FROM player_profile WHERE id=1"
    ).fetchone()
    active_plan = conn.execute(
        "SELECT id,name,current_day,total_days FROM study_plans WHERE status='active' ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    unfinished = []
    if active_plan:
        unfinished = [
            dict(row)
            for row in conn.execute(
                """
                SELECT category,title,deliverable,duration_minutes
                FROM daily_missions
                WHERE plan_id=? AND completed=0
                ORDER BY day_index,optional,sort_order,id
                LIMIT 8
                """,
                (active_plan["id"],),
            )
        ]
    recent = [
        dict(row)
        for row in conn.execute(
            """
            SELECT m.title,d.review_text,d.note,d.created_at
            FROM mission_deliveries d
            JOIN daily_missions m ON m.id=d.mission_id
            ORDER BY d.created_at DESC
            LIMIT 6
            """
        )
    ]
    logs = [
        dict(row)
        for row in conn.execute(
            "SELECT mood,note,updated_at FROM daily_logs WHERE trim(note)!='' ORDER BY updated_at DESC LIMIT 4"
        )
    ]
    return {
        "profile": dict(profile) if profile else {},
        "active_plan": dict(active_plan) if active_plan else None,
        "unfinished": unfinished,
        "recent": recent,
        "logs": logs,
    }


def build_plan_prompt(state: dict[str, Any]) -> str:
    profile = state.get("profile") or {}
    unfinished = state.get("unfinished") or []
    recent = state.get("recent") or []
    logs = state.get("logs") or []
    unfinished_text = "\n".join(
        f"- {item['title']}（交付：{item.get('deliverable') or '最小可验证成果'}）"
        for item in unfinished
    ) or "- 暂无"
    recent_text = "\n".join(
        f"- {item['title']}：{(item.get('review_text') or item.get('note') or '已交付')[:180]}"
        for item in recent
    ) or "- 暂无"
    log_text = "\n".join(f"- {item['mood']}：{item['note'][:160]}" for item in logs) or "- 暂无"
    goals = (profile.get("goals") or "根据当前学习状态灵活推进").strip()
    return f"""你是我的短周期科研计划设计师。请根据网站当前状态，生成一段可直接导入“问道科研”的近期计划。

设计原则：
1. 不建立长期固定主线，不替我承诺30天或更久；只安排未来3–7天。
2. 每天1–3项必做，最多1项可选，总时长控制在60–150分钟。
3. 每项任务必须留下真实交付；“看视频、读一读、了解一下”不能单独算完成。
4. 优先解决最近卡点和未完成事项；已经掌握的内容改为复盘或应用，不重复抄写。
5. 计划可以随时被下一份计划替换，不制造补课债务。
6. 输出只能使用下面格式，不要附加解释：

# 计划名称
> 一句话说明这几天解决什么
## Day 1 | 当日主题
- [重点] 任务 | 45min | 20XP | 交付：...
- [工具] 任务 | 30min | 15XP | 交付：...
- [可选] 任务 | 20min | 8XP | 交付：...

我的当前目标：
{goals}

尚未完成：
{unfinished_text}

最近真实交付：
{recent_text}

最近状态：
{log_text}

请生成下一段近期计划。"""


def build_today_prompt(state: dict[str, Any]) -> str:
    profile = state.get("profile") or {}
    unfinished = state.get("unfinished") or []
    task_text = "\n".join(
        f"- [{item['category']}] {item['title']}；交付={item.get('deliverable') or '最小可验证成果'}"
        for item in unfinished[:4]
    ) or "- 今天尚未设置任务"
    return f"""你是我的科研学习搭档。网站只负责保存近期计划与真实交付，你负责解释和追问。

当前目标：
{profile.get('goals') or '根据当前问题灵活推进'}

今天最靠前的未完成任务：
{task_text}

请先让我选择其中一项，然后：
- 每次只推进一个关键问题；
- 用小白能懂但不失真的方式解释；
- 主动追问我的因果链、证据和边界条件；
- 结尾给出一个可以上传到网站的最小交付；
- 额外要求我写3–8条“复盘关键文本”，供明天出题。"""
