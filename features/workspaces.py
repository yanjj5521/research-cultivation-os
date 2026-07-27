from __future__ import annotations
import uuid
from typing import Any, Callable

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from db import connect, now_iso


WORKSPACE_MODULES = {
    "knowledge": ("通用知识专题", "收录论文、笔记、代码和附件"),
    "experiments": ("实验台账", "使用结构化实验批次表"),
    "simulations": ("模拟案例", "归档输入、日志、轨迹和复现命令"),
    "datasets": ("数据集", "保存表格、字段、单位和数据说明"),
}
WORKSPACE_ACCENTS = {"clay", "sage", "ink", "amber"}


def _workspace_counts(conn, workspace_id: int, module: str) -> int:
    if module == "experiments":
        return int(conn.execute(
            "SELECT COUNT(*) n FROM experiments WHERE workspace_id=?", (workspace_id,)
        ).fetchone()["n"])
    if module == "simulations":
        return int(conn.execute(
            "SELECT COUNT(*) n FROM simulations WHERE workspace_id=?", (workspace_id,)
        ).fetchone()["n"])
    if module == "datasets":
        return int(conn.execute(
            "SELECT COUNT(*) n FROM entries WHERE workspace_id=? AND kind='dataset'", (workspace_id,)
        ).fetchone()["n"])
    return int(conn.execute(
        "SELECT COUNT(*) n FROM entries WHERE workspace_id=?", (workspace_id,)
    ).fetchone()["n"])


def register_workspace_routes(
    app,
    templates,
    context: Callable[..., dict[str, Any]],
    flash: Callable[[Request, str, str], None],
    entry_dict: Callable[[Any], dict[str, Any]],
):
    router = APIRouter()

    @router.get("/workspaces", response_class=HTMLResponse, name="workspaces_page")
    def workspaces_page(request: Request):
        with connect() as conn:
            items = []
            for row in conn.execute("SELECT * FROM workspaces ORDER BY active DESC,sort_order,id"):
                item = dict(row)
                item["record_count"] = _workspace_counts(conn, int(row["id"]), str(row["module"]))
                item["module_label"] = WORKSPACE_MODULES.get(
                    str(row["module"]), WORKSPACE_MODULES["knowledge"]
                )[0]
                items.append(item)
        return templates.TemplateResponse(
            request=request,
            name="workspaces.html",
            context=context(
                request,
                "workspaces",
                items=items,
                workspace_modules=WORKSPACE_MODULES,
                workspace_accents=sorted(WORKSPACE_ACCENTS),
            ),
        )

    @router.post("/workspaces/new", name="workspace_new")
    def workspace_new(
        request: Request,
        name: str = Form(...),
        icon: str = Form("研"),
        module: str = Form("knowledge"),
        description: str = Form(""),
    ):
        title = name.strip()[:40]
        if not title:
            flash(request, "工作区名称不能为空。", "error")
            return RedirectResponse(request.url_for("workspaces_page"), status_code=303)
        module_value = module if module in WORKSPACE_MODULES else "knowledge"
        ts = now_iso()
        with connect() as conn:
            order = int(conn.execute(
                "SELECT COALESCE(MAX(sort_order),0)+10 n FROM workspaces"
            ).fetchone()["n"])
            conn.execute(
                """
                INSERT INTO workspaces(
                    workspace_key,name,icon,module,description,accent,sort_order,active,created_at,updated_at
                ) VALUES (?,?,?,?,?,'clay',?,1,?,?)
                """,
                (uuid.uuid4().hex, title, icon.strip()[:2] or "研", module_value, description.strip()[:240], order, ts, ts),
            )
            conn.commit()
        flash(request, f"已建立工作区「{title}」。", "success")
        return RedirectResponse(request.url_for("workspaces_page"), status_code=303)

    @router.post("/workspaces/{workspace_id}/save", name="workspace_save")
    def workspace_save(
        request: Request,
        workspace_id: int,
        name: str = Form(...),
        icon: str = Form("研"),
        module: str = Form("knowledge"),
        description: str = Form(""),
        accent: str = Form("clay"),
        sort_order: int = Form(0),
        active: str = Form(""),
    ):
        title = name.strip()[:40]
        if not title:
            flash(request, "工作区名称不能为空。", "error")
            return RedirectResponse(request.url_for("workspaces_page"), status_code=303)
        with connect() as conn:
            row = conn.execute("SELECT id FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404)
            conn.execute(
                """
                UPDATE workspaces
                SET name=?,icon=?,module=?,description=?,accent=?,sort_order=?,active=?,updated_at=?
                WHERE id=?
                """,
                (
                    title,
                    icon.strip()[:2] or "研",
                    module if module in WORKSPACE_MODULES else "knowledge",
                    description.strip()[:240],
                    accent if accent in WORKSPACE_ACCENTS else "clay",
                    max(-999, min(int(sort_order or 0), 9999)),
                    1 if active == "1" else 0,
                    now_iso(),
                    workspace_id,
                ),
            )
            conn.commit()
        flash(request, "工作区设置已保存。", "success")
        return RedirectResponse(request.url_for("workspaces_page"), status_code=303)

    @router.get("/workspaces/{workspace_id}", response_class=HTMLResponse, name="workspace_open")
    def workspace_open(request: Request, workspace_id: int):
        with connect() as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404)
            workspace = dict(row)
            module = str(row["module"])
            if module == "knowledge":
                entries = [
                    entry_dict(item)
                    for item in conn.execute(
                        "SELECT * FROM entries WHERE workspace_id=? AND status='active' ORDER BY favorite DESC,updated_at DESC LIMIT 300",
                        (workspace_id,),
                    )
                ]
            else:
                entries = []
        if module == "experiments":
            return RedirectResponse(
                f"{request.url_for('experiments_page')}?workspace={workspace_id}", status_code=303
            )
        if module == "simulations":
            return RedirectResponse(
                f"{request.url_for('simulations_page')}?workspace={workspace_id}", status_code=303
            )
        if module == "datasets":
            return RedirectResponse(
                f"{request.url_for('datasets_page')}?workspace={workspace_id}", status_code=303
            )
        return templates.TemplateResponse(
            request=request,
            name="workspace.html",
            context=context(request, "workspace", workspace=workspace, entries=entries),
        )

    app.include_router(router)
