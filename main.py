from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import config
from html import escape as html_escape
import migrations
from database import SessionLocal
from deps import templates
from routers import (admin, api, auth_routes, chatx, explore, extras, features, feed, more, groups, messages, misc, notifications,
                     posts, profile, secret, settings, stories, tasks)

import packs  # noqa: E402  модули Nuvora 3.0: таблицы, маршруты, иконки, настройки
packs.load()
migrations.run()

from services import icons as _icons  # noqa: E402
from services import prefs as _prefs  # noqa: E402
_icons.ICONS.update(packs.ICONS)
import deps as _deps  # noqa: E402
_deps.load_pack_globals()
_icons.write_sprite("static/icons.svg")
for _p in packs.PREFS:
    if _p["key"] not in _prefs.BY_KEY:
        _prefs.PREFS.append(_p)
        _prefs.BY_KEY[_p["key"]] = _p

app = FastAPI(title=config.BRAND_NAME, docs_url=None, redoc_url=None, openapi_url=None)
class CachedStatic(StaticFiles):
    """Статика с кэшем в браузере: файлы с ?v=… — на год (версия меняется при обновлении), остальное — на день.
    Загрузки пользователей имеют уникальные имена и тоже кэшируются надолго."""
    def __init__(self, *a, long=False, **kw):
        super().__init__(*a, **kw)
        self.long = long

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            versioned = b"v=" in (scope.get("query_string") or b"")
            if self.long or versioned:
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif path.endswith(("sw.js", "manifest.webmanifest")):
                resp.headers["Cache-Control"] = "no-cache"
            else:
                resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp


app.mount("/static", CachedStatic(directory="static"), name="static")
app.mount("/uploads", CachedStatic(directory=config.UPLOAD_DIR, long=True), name="uploads")
from starlette.middleware.gzip import GZipMiddleware  # noqa: E402


class TextGZip(GZipMiddleware):
    """Сжимаем HTML, JSON, CSS и JS (в 4–6 раз меньше), но не фото и видео: они уже сжаты, а видео ещё и
    перематывается по частям (Range) — сжатие это ломает."""
    async def __call__(self, scope, receive, send):
        p = scope.get("path", "") if scope.get("type") == "http" else ""
        if p.startswith(("/uploads/", "/download/", "/static/promo/")) or p.endswith((".mp4", ".webm", ".png", ".jpg", ".webp", ".apk")):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


app.add_middleware(TextGZip, minimum_size=1200, compresslevel=5)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _norm_host(h: str) -> str:
    h = (h or "").lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if not config.SECRET_CHATS_ENABLED and request.url.path in ("/static/js/gost.js", "/static/js/secret.js"):
        return PlainTextResponse("Not found", status_code=404)
    path = request.url.path
    from packs.v3 import site
    if site.get("maintenance") and not path.startswith(("/static/", "/login", "/logout", "/sw.js", "/healthz", "/admin", "/offline")):
        from deps import current_user
        from database import SessionLocal
        db = SessionLocal()
        try:
            u = current_user(request, db)
            from services import social as _social
            staff = bool(u and (u.is_owner or _social.can_mod(u)))
        finally:
            db.close()
        if not staff:  # технические работы: сайт видят только владелец и модераторы
            return HTMLResponse("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                                "<body style='font-family:sans-serif;background:#f6f1e8;color:#1f1d1a;display:grid;place-items:center;min-height:90vh;"
                                "text-align:center;padding:20px'><div><img src='/static/brand/logo-180.png' width=64 height=64 style='border-radius:18px'>"
                                f"<h2>Nuvora</h2><p>{html_escape(site.get('maintenance_text'))}</p></div>", status_code=503)
    if not path.startswith("/static/") and request.client:  # блокировка по IP из админ-панели
        from packs.v3.admin_plus import ip_banned
        if ip_banned(request.client.host):
            return HTMLResponse("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                                "<body style='font-family:sans-serif;background:#f6f1e8;color:#1f1d1a;display:grid;place-items:center;min-height:90vh;"
                                "text-align:center;padding:20px'><div><h2>Доступ ограничен</h2><p>С вашего адреса вход на сайт закрыт администрацией.</p></div>",
                                status_code=403)
    if site.is_disabled(path):  # выключенные разделы
        if request.method == "GET" and not request.headers.get("x-requested-with"):
            return RedirectResponse("/", status_code=303)
        return JSONResponse({"ok": False, "error": "Этот раздел убран"}, status_code=404)
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


@app.on_event("startup")
async def _background_jobs():
    """Фоновые задачи (раз в 10 секунд): отложенные сообщения, напоминания; раз в час — дни рождения друзей."""
    import asyncio
    state = {"bday": "", "n": 0}

    def tick():
        from datetime import datetime as _dt
        db = SessionLocal()
        try:
            chatx.deliver_scheduled(db)
            features.deliver_reminders(db)
            state["n"] += 1
            if state["n"] % 60 == 1:  # примерно раз в 10 минут — уборка старого
                features.cleanup(db)
            if state["n"] % 6 == 0:  # фоновые задачи модулей — раз в минуту
                for job in packs.JOBS:
                    try:
                        job(db)
                    except Exception as e:  # noqa: BLE001
                        db.rollback()
                        print(f"[jobs] {getattr(job, '__name__', job)}: {e}")
            now = _dt.utcnow()
            key = now.strftime("%Y-%m-%d")
            if now.hour >= 6 and state["bday"] != key:  # около 9 утра по Москве
                state["bday"] = key
                features.notify_birthdays(db)
        except Exception as e:  # фоновая задача не должна падать
            print(f"[jobs] {e}")
        finally:
            db.close()

    async def loop():
        while True:
            await asyncio.get_running_loop().run_in_executor(None, tick)
            await asyncio.sleep(10)
    asyncio.get_running_loop().create_task(loop())


for _r in packs.ROUTERS:  # модули — первыми, чтобы их адреса не перехватывались общими маршрутами
    app.include_router(_r)
for r in (auth_routes, feed, posts, profile, settings, chatx, features, messages, groups, stories, explore, notifications,
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
