from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from db import get_setting, set_setting
from services.idle_space import (
    BUILTIN_WALLPAPERS,
    custom_wallpapers,
    current_wallpaper_filename,
    save_wallpaper_bytes,
    select_builtin_wallpaper,
    select_custom_wallpaper,
    wallpaper_url,
)


def register_idle_routes(app, templates, context, flash):
    router = APIRouter()

    @router.get("/idle", response_class=HTMLResponse, name="idle_page")
    def idle_page(request: Request):
        layout = get_setting("idle_layout", "vertical")
        if layout not in {"vertical", "horizontal"}:
            layout = "vertical"
        builtin_key = get_setting("idle_wallpaper_builtin", "dawn")
        return templates.TemplateResponse(
            request=request,
            name="idle.html",
            context=context(
                request,
                "idle",
                idle_layout=layout,
                idle_wallpaper_url=wallpaper_url(),
                idle_wallpaper_kind=get_setting("idle_wallpaper_kind", "builtin"),
                idle_wallpaper_file=current_wallpaper_filename(),
                builtin_wallpapers=BUILTIN_WALLPAPERS,
                custom_wallpapers=custom_wallpapers(),
                selected_builtin= builtin_key if builtin_key in BUILTIN_WALLPAPERS else "dawn",
                idle_focus=get_setting("idle_focus", "安静积累，下一步只做一件最重要的事。")[:160],
            ),
        )

    @router.post("/idle/config", name="idle_config_save")
    def idle_config_save(
        request: Request,
        layout: str = Form("vertical"),
        focus: str = Form(""),
        builtin_wallpaper: str = Form(""),
        custom_wallpaper: str = Form(""),
    ):
        set_setting("idle_layout", layout if layout in {"vertical", "horizontal"} else "vertical")
        set_setting("idle_focus", focus.strip()[:160] or "安静积累，下一步只做一件最重要的事。")
        if builtin_wallpaper:
            try:
                select_builtin_wallpaper(builtin_wallpaper)
            except ValueError as exc:
                flash(request, str(exc), "error")
                return RedirectResponse(request.url_for("idle_page"), status_code=303)
        if custom_wallpaper:
            try:
                select_custom_wallpaper(custom_wallpaper)
            except ValueError as exc:
                flash(request, str(exc), "error")
                return RedirectResponse(request.url_for("idle_page"), status_code=303)
        flash(request, "挂机界面已保存：只记录专注时间，不会自动增加修为或资产。")
        return RedirectResponse(request.url_for("idle_page"), status_code=303)

    @router.post("/idle/wallpaper", name="idle_wallpaper_upload")
    async def idle_wallpaper_upload(request: Request, file: UploadFile = File(...)):
        try:
            save_wallpaper_bytes(await file.read())
        except ValueError as exc:
            flash(request, str(exc), "error")
        else:
            flash(request, "自定义壁纸已保存到本机用户数据，不会上传同行会。")
        return RedirectResponse(request.url_for("idle_page"), status_code=303)

    app.include_router(router)
