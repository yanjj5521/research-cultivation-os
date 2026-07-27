from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from db import connect
from services.prompt_builder import build_plan_prompt, build_today_prompt, current_state


def register_assistant_routes(app, templates, context: Callable[..., dict[str, Any]]):
    router = APIRouter()

    @router.get('/assistant', response_class=HTMLResponse, name='assistant_page')
    def assistant_page(request: Request, mode: str = 'today'):
        with connect() as conn:
            state = current_state(conn)
            plan = conn.execute("SELECT * FROM study_plans WHERE status='active' ORDER BY updated_at DESC LIMIT 1").fetchone()
            recent_questions = [dict(row) for row in conn.execute(
                "SELECT title,summary,content FROM entries WHERE kind IN ('question','idea','failure') ORDER BY updated_at DESC LIMIT 5"
            )]
        prompt = _build_prompt(mode, state, recent_questions)
        return templates.TemplateResponse(
            request=request,
            name='assistant.html',
            context=context(request, 'assistant', mode=mode, prompt=prompt, plan=dict(plan) if plan else None),
        )

    app.include_router(router)


def _build_prompt(mode: str, state: dict[str, Any], recent_questions: list[dict]) -> str:
    questions = '\n'.join(f"- {q['title']}" for q in recent_questions) or '- 暂无'
    profile = state.get("profile") or {}
    goals = profile.get("goals") or "根据当前问题灵活推进"

    if mode == 'plan':
        return build_plan_prompt(state)
    if mode == 'paper':
        return f"""你是材料科学与土木工程交叉领域的论文导师。请帮助我读一篇论文，但不要直接给长篇总结。

先让我提供论文或摘要，然后按顺序回答：
1. 作者真正的问题是什么？
2. 为什么这个问题在当时重要？
3. 每张关键图在证据链中承担什么角色？
4. 哪些结论是数据直接支持的，哪些属于解释？
5. 对我当前目标有什么可借鉴之处？
6. 最后只布置一个最小交付，并要求我写3–8条复盘关键文本。

我的当前目标：
{goals}

最近的问题：
{questions}"""
    if mode == 'debug':
        return """你是我的科研调试搭档。我会提供报错、实验异常或曲线。请严格按以下格式回答：\n1. 先复述我实际做了什么；\n2. 判断最可能的3个原因，按概率排序；\n3. 给出最小排查步骤，每次只改变一个变量；\n4. 指出需要我补充的日志、图片或参数；\n5. 不要一次布置大量任务，也不要凭空杜撰结果。"""
    return build_today_prompt(state)
