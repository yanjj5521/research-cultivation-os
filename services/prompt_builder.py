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
    cultivation_tasks = [
        dict(row)
        for row in conn.execute(
            """
            SELECT title,deliverable,difficulty,status
            FROM quests
            WHERE completed=0
            ORDER BY difficulty DESC,updated_at DESC,id DESC
            LIMIT 8
            """
        )
    ]
    workspaces = [
        dict(row)
        for row in conn.execute(
            "SELECT name,module,description FROM workspaces WHERE active=1 ORDER BY sort_order,id"
        )
    ]
    return {
        "profile": dict(profile) if profile else {},
        "active_plan": dict(active_plan) if active_plan else None,
        "unfinished": unfinished,
        "recent": recent,
        "logs": logs,
        "cultivation_tasks": cultivation_tasks,
        "workspaces": workspaces,
    }


def build_plan_prompt(state: dict[str, Any]) -> str:
    profile = state.get("profile") or {}
    unfinished = state.get("unfinished") or []
    recent = state.get("recent") or []
    logs = state.get("logs") or []
    cultivation_tasks = state.get("cultivation_tasks") or []
    workspaces = state.get("workspaces") or []
    unfinished_text = "\n".join(
        f"- {item['title']}（交付：{item.get('deliverable') or '最小可验证成果'}）"
        for item in unfinished
    ) or "- 暂无"
    recent_text = "\n".join(
        f"- {item['title']}：{(item.get('review_text') or item.get('note') or '已交付')[:180]}"
        for item in recent
    ) or "- 暂无"
    log_text = "\n".join(f"- {item['mood']}：{item['note'][:160]}" for item in logs) or "- 暂无"
    cultivation_text = "\n".join(
        f"- {item['title']}（验收：{item.get('deliverable') or '尚未填写'}）"
        for item in cultivation_tasks
    ) or "- 暂无"
    workspace_text = "、".join(item["name"] for item in workspaces) or "暂无"
    goals = (profile.get("goals") or "根据当前学习状态灵活推进").strip()
    return f"""你是我的短周期科研计划设计师。请根据网站当前状态，生成一段可直接导入“问道科研”的近期计划。

设计原则：
1. 不建立长期固定主线，不替我承诺30天或更久；只安排未来3–7天。
2. 严格区分两类任务：
   - “修炼任务”是跨天的能力或成果里程碑，以验收证据为完成条件，不绑定某一天。
   - “每日任务”是今天能执行并交付的下一行动，可以关联修炼任务，但不能直接冒充里程碑。
3. 每天1–3项必做，最多1项可选，总时长控制在60–150分钟。
4. 每项每日任务必须留下真实交付；“看视频、读一读、了解一下”不能单独算完成。
5. 优先解决最近卡点和未完成事项；已经掌握的内容改为复盘或应用，不重复抄写。
6. 不得输出 XP、经验或修为。奖励由网站按统一时长规则计算，任何导入值都会被忽略。
7. 计划可以随时被下一份计划替换，不制造补课债务。
8. 输出只能使用下面格式，不要附加解释；若现有修炼任务已经足够，可省略“修炼任务”段：

# 计划名称
> 一句话说明这几天解决什么
## 修炼任务
- [小成/进阶/突破] 跨天成果目标 | 验收：可核验的达成证据 | 工作区：已有工作区名称
## Day 1 | 当日主题
- [重点] 可执行行动 | 45min | 交付：... | 关联修炼：修炼任务标题
- [工具] 可执行行动 | 30min | 交付：...
- [可选] 可执行行动 | 20min | 交付：...

我的当前目标：
{goals}

尚未完成：
{unfinished_text}

现有修炼任务：
{cultivation_text}

现有工作区：
{workspace_text}

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
