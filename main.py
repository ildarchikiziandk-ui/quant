from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import config
import migrations
from database import SessionLocal
from deps import templates
from routers import (admin, api, auth_routes, explore, extras, feed, more, groups, messages, misc, notifications, posts,
                     profile, secret, settings, stories, tasks)

migrations.run()

app = FastAPI(title=config.BRAND_NAME, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _norm_host(h: str) -> str:
    h = (h or "").lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Защита от CSRF: небезопасные запросы с чужого Origin/Referer отклоняются.
    if request.method not in SAFE_METHODS:
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin and origin != "null":
            allowed = {_norm_host(h) for h in (request.headers.get("host", ""), request.headers.get("x-forwarded-host", ""),
                                               urlparse(config.SITE_URL).netloc) if h}
            if _norm_host(urlparse(origin).netloc) not in allowed:
                print(f"[csrf] blocked {request.method} {request.url.path} origin={origin!r} host={request.headers.get('host')!r}")
                if "application/json" in request.headers.get("accept", "") or request.headers.get("x-requested-with"):
                    return JSONResponse({"ok": False, "error": "Запрос отклонён. Обновите страницу и попробуйте снова."}, status_code=403)
                return HTMLResponse("<meta charset='utf-8'><p style='font-family:sans-serif;padding:24px'>Запрос отклонён из соображений безопасности. "
                                    "<a href='/'>Вернитесь на сайт</a>, обновите страницу и попробуйте снова.</p>", status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
    return response


for r in (auth_routes, feed, posts, profile, settings, messages, groups, stories, explore, notifications,
          tasks, extras, more, secret, admin, api, misc):
    app.include_router(r.router)


def _error_page(request: Request, code: int, title: str, text: str):
    if request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"ok": False, "error": title}, status_code=code)
    db = SessionLocal()
    try:
        from deps import base_context
        ctx = base_context(request, db, sidebar=False)
        ctx.update(code=code, title=title, text=text)
        return templates.TemplateResponse(request, "error.html", ctx, status_code=code)
    finally:
        db.close()


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return _error_page(request, 404, "Страница не найдена", "Возможно, её удалили или ссылка неверна.")
    if exc.status_code == 405:
        return _error_page(request, 405, "Метод не поддерживается", "Попробуйте вернуться назад.")
    return _error_page(request, exc.status_code, "Ошибка", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return _error_page(request, 422, "Некорректный запрос", "Проверьте заполненные поля и попробуйте снова.")


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"
