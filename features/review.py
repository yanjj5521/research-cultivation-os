from __future__ import annotations

import json
from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from db import connect, now_iso
from services.ai_provider import provider_status
from services.review_engine import (
    combine_sources,
    generate_questions,
    grade_answer,
    next_due_from_rating,
    pending_review_group,
)


def _questions(value: str) -> list[dict[str, Any]]:
    try:
        items = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _pill_quantity(conn, key: str) -> int:
    row = conn.execute(
        "SELECT quantity FROM inventory_items WHERE item_key=? AND item_type='pill'",
        (key,),
    ).fetchone()
    return int(row["quantity"]) if row else 0


def register_review_routes(
    app,
    templates,
    context: Callable[..., dict[str, Any]],
    flash: Callable[[Request, str, str], None],
):
    router = APIRouter()

    @router.get("/review", response_class=HTMLResponse, name="review_page")
    def review_page(request: Request):
        with connect() as conn:
            pending = pending_review_group(conn)
            history = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT s.*,COUNT(a.id) AS answer_count,
                           COALESCE(ROUND(AVG(a.score)),0) AS average_score
                    FROM review_sessions s
                    LEFT JOIN review_answers a ON a.session_id=s.id
                    GROUP BY s.id
                    ORDER BY s.id DESC
                    LIMIT 12
                    """
                )
            ]
            source_count = conn.execute("SELECT COUNT(*) n FROM review_sources").fetchone()["n"]
            due_count = conn.execute(
                "SELECT COUNT(*) n FROM review_answers WHERE next_due IS NOT NULL AND next_due<=?",
                (date.today().isoformat(),),
            ).fetchone()["n"]
            tribulation_pills = _pill_quantity(conn, "tribulation_pill")
        return templates.TemplateResponse(
            request=request,
            name="review.html",
            context=context(
                request,
                "review",
                pending=pending,
                history=history,
                source_count=source_count,
                due_count=due_count,
                tribulation_pills=tribulation_pills,
                ai_status=provider_status(),
                session=None,
                questions=[],
                answers={},
            ),
        )

    @router.post("/review/start", name="review_start")
    def review_start(request: Request, mode: str = Form("yesterday")):
        allowed = {"yesterday", "beast", "tribulation"}
        mode = mode if mode in allowed else "yesterday"
        with connect() as conn:
            pending = pending_review_group(conn) if mode == "yesterday" else None
            if mode == "yesterday":
                sources = pending["sources"] if pending else []
                source_date = pending["source_date"] if pending else ""
            else:
                sources = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT id,title,source_text,source_type,source_date
                        FROM review_sources
                        ORDER BY source_date DESC,id DESC
                        LIMIT 12
                        """
                    )
                ]
                source_date = sources[0]["source_date"] if sources else ""
            if not sources:
                flash(request, "还没有可用于出题的复盘关键文本。先完成一次交付并填写关键文本。", "error")
                return RedirectResponse(request.url_for("review_page"), status_code=303)
            if mode == "tribulation" and _pill_quantity(conn, "tribulation_pill") < 1:
                flash(request, "渡劫需要一枚渡劫丹，请先去炼丹炉炼制。", "error")
                return RedirectResponse(request.url_for("alchemy_page"), status_code=303)

        count = {"yesterday": 3, "beast": 4, "tribulation": 5}[mode]
        questions, provider, fallback_reason = generate_questions(
            combine_sources(sources),
            count=count,
            mode=mode,
        )
        titles = {
            "yesterday": f"{source_date} 交付复盘",
            "beast": "妖兽挑战 · 综合迁移",
            "tribulation": "雷劫 · 五问渡关",
        }
        with connect() as conn:
            if mode == "tribulation":
                conn.execute(
                    "UPDATE inventory_items SET quantity=quantity-1,updated_at=? WHERE item_key='tribulation_pill' AND quantity>0",
                    (now_iso(),),
                )
                conn.execute(
                    "DELETE FROM inventory_items WHERE item_key='tribulation_pill' AND quantity<=0"
                )
            cur = conn.execute(
                """
                INSERT INTO review_sessions(
                    mode,title,source_date,questions_json,status,provider,fallback_reason,created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    mode,
                    titles[mode],
                    source_date,
                    json.dumps(questions, ensure_ascii=False),
                    "active",
                    provider,
                    fallback_reason[:1000],
                    now_iso(),
                ),
            )
            session_id = int(cur.lastrowid)
            for source in sources:
                conn.execute(
                    "INSERT OR IGNORE INTO review_session_sources(session_id,review_source_id) VALUES (?,?)",
                    (session_id, source["id"]),
                )
            conn.commit()
        return RedirectResponse(
            request.url_for("review_session", session_id=session_id),
            status_code=303,
        )

    @router.get("/review/sessions/{session_id}", response_class=HTMLResponse, name="review_session")
    def review_session(request: Request, session_id: int):
        with connect() as conn:
            row = conn.execute("SELECT * FROM review_sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404)
            session = dict(row)
            questions = _questions(session["questions_json"])
            answers = {
                int(item["question_index"]): dict(item)
                for item in conn.execute(
                    "SELECT * FROM review_answers WHERE session_id=? ORDER BY question_index",
                    (session_id,),
                )
            }
            sources = [
                dict(item)
                for item in conn.execute(
                    """
                    SELECT s.title,s.source_date,s.source_type
                    FROM review_sources s
                    JOIN review_session_sources l ON l.review_source_id=s.id
                    WHERE l.session_id=?
                    ORDER BY s.id
                    """,
                    (session_id,),
                )
            ]
        return templates.TemplateResponse(
            request=request,
            name="review.html",
            context=context(
                request,
                "review",
                pending=None,
                history=[],
                source_count=0,
                due_count=0,
                tribulation_pills=0,
                ai_status=provider_status(),
                session=session,
                questions=questions,
                answers=answers,
                sources=sources,
            ),
        )

    @router.post("/review/sessions/{session_id}/answer", name="review_answer")
    def review_answer(
        request: Request,
        session_id: int,
        question_index: int = Form(...),
        answer: str = Form(...),
    ):
        answer = answer.strip()
        if not answer:
            flash(request, "请先写下你的回答。", "error")
            return RedirectResponse(request.url_for("review_session", session_id=session_id), status_code=303)
        with connect() as conn:
            session_row = conn.execute("SELECT * FROM review_sessions WHERE id=?", (session_id,)).fetchone()
            if not session_row:
                raise HTTPException(status_code=404)
            questions = _questions(session_row["questions_json"])
            if question_index < 0 or question_index >= len(questions):
                raise HTTPException(status_code=400)
            question = questions[question_index]

        result, provider, fallback_reason = grade_answer(question, answer)
        ts = now_iso()
        with connect() as conn:
            session_row = conn.execute("SELECT status,mode FROM review_sessions WHERE id=?", (session_id,)).fetchone()
            conn.execute(
                """
                INSERT INTO review_answers(
                    session_id,question_index,answer,score,level,feedback,evidence_quote,
                    confidence,provider,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id,question_index) DO UPDATE SET
                    answer=excluded.answer,score=excluded.score,level=excluded.level,
                    feedback=excluded.feedback,evidence_quote=excluded.evidence_quote,
                    confidence=excluded.confidence,provider=excluded.provider,updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    question_index,
                    answer,
                    result["score"],
                    result["level"],
                    result["feedback"],
                    result["evidence_quote"],
                    result["confidence"],
                    provider,
                    ts,
                    ts,
                ),
            )
            answer_count = conn.execute(
                "SELECT COUNT(*) n FROM review_answers WHERE session_id=?",
                (session_id,),
            ).fetchone()["n"]
            if answer_count >= len(questions) and session_row["status"] != "completed":
                conn.execute(
                    "UPDATE review_sessions SET status='completed',completed_at=? WHERE id=?",
                    (ts, session_id),
                )
                xp = {"yesterday": 8, "beast": 20, "tribulation": 40}.get(session_row["mode"], 8)
                conn.execute(
                    "INSERT INTO activities(action,xp,detail,created_at) VALUES (?,?,?,?)",
                    ("review_complete", xp, f"完成：{dict(session_row).get('mode', 'review')}", ts),
                )
            if fallback_reason:
                conn.execute(
                    "UPDATE review_sessions SET fallback_reason=CASE WHEN fallback_reason='' THEN ? ELSE fallback_reason END WHERE id=?",
                    (fallback_reason[:1000], session_id),
                )
            conn.commit()
        flash(request, "已保存评价。先看证据，再给自己一个掌握度判断。", "success")
        return RedirectResponse(
            f"{request.url_for('review_session', session_id=session_id)}#question-{question_index}",
            status_code=303,
        )

    @router.post("/review/sessions/{session_id}/rate", name="review_rate")
    def review_rate(
        request: Request,
        session_id: int,
        question_index: int = Form(...),
        self_rating: str = Form(...),
    ):
        if self_rating not in {"mastered", "partial", "forgot"}:
            raise HTTPException(status_code=400)
        with connect() as conn:
            conn.execute(
                """
                UPDATE review_answers
                SET self_rating=?,next_due=?,updated_at=?
                WHERE session_id=? AND question_index=?
                """,
                (
                    self_rating,
                    next_due_from_rating(self_rating),
                    now_iso(),
                    session_id,
                    question_index,
                ),
            )
            conn.commit()
        return RedirectResponse(
            f"{request.url_for('review_session', session_id=session_id)}#question-{question_index}",
            status_code=303,
        )

    @router.post("/review/snooze", name="review_snooze")
    def review_snooze(request: Request):
        with connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO review_snoozes(review_day,created_at) VALUES (?,?)",
                (date.today().isoformat(), now_iso()),
            )
            conn.commit()
        flash(request, "今天先不弹出；复盘材料仍会保留。", "success")
        return RedirectResponse(request.url_for("dashboard"), status_code=303)

    app.include_router(router)
