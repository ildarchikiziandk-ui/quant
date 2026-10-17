"""Модули Nuvora 3.0.

Каждый модуль — пакет packs/<имя>/ со своими моделями, маршрутами, шаблонами, стилями и скриптами.
Ядро ничего о них не знает: всё подключается здесь. Модуль может объявить в своём __init__.py:

    router    — fastapi.APIRouter с маршрутами модуля
    WHATSNEW  — [(название группы, иконка, [(иконка, текст), ...]), ...] — пункты для страницы «Что нового»
    PREFS     — список настроек, созданных через services.prefs._p(...) (появятся в нужном разделе настроек)
    MENU      — [(ссылка, иконка, подпись, группа меню), ...] — пункты мобильного меню (группы: «Обзор», «Награды», «Люди», «Помощь» или новая)
    SLOTS     — {"имя слота": "путь/к/шаблону.html" или [список]} — вставки в страницы ядра (см. SLOT_NAMES)
    CSS, JS   — пути к файлам в /static, подключаются на всех страницах
    ICONS     — {"имя": "<path …/>"} — новые иконки (SVG-содержимое 24×24, как в services/icons.py)
    JOBS      — [функция(db), ...] — фоновые задачи (вызываются примерно раз в минуту)
    GLOBALS   — {"имя": объект} — функции и данные для шаблонов

Модели модуль объявляет в packs/<имя>/models.py (наследуя database.Base) и импортирует из своего __init__.py —
таблицы создаются автоматически при запуске.
"""
import importlib
import pkgutil

# Места в шаблонах ядра, куда модули могут добавить свои кнопки и блоки
SLOT_NAMES = {
    "home_top": "главная, над вкладками ленты",
    "sidebar": "правая колонка на компьютере",
    "post_menu": "меню «⋯» у поста (переменные: p — пост, main — оригинал для репоста)",
    "post_page": "страница поста, под панелью инструментов (post)",
    "post_after_text": "под текстом поста в ленте и на странице поста (p)",
    "composer_tools": "кнопки в редакторе поста",
    "composer_panels": "панели редактора поста",
    "profile_actions": "кнопки в шапке чужого профиля (profile_user)",
    "profile_menu": "меню «⋯» профиля (profile_user, me)",
    "profile_after_bio": "под описанием профиля (profile_user)",
    "profile_tabs": "дополнительные вкладки профиля — ссылки ?tab=… (profile_user, tab)",
    "profile_tab_body": "содержимое своей вкладки профиля: если tab ваш — выведите блок и сделайте {% set pack_tab.done = true %}",
    "chat_menu": "меню «⋯» в переписке (other)",
    "chat_tools": "кнопки слева от поля ввода сообщения (other)",
    "chat_after_box": "под лентой сообщений (other)",
    "message_extra": "внутри пузыря сообщения (m — сообщение, user)",
    "chat_list_top": "над списком чатов",
    "group_menu": "окно «О группе» (group, is_admin)",
    "group_tools": "кнопки у поля ввода в группе (group)",
    "notifications_top": "над списком уведомлений",
    "settings_bottom": "внизу любого раздела настроек (section)",
    "explore_top": "вверху раздела «Обзор»",
    "body_end": "в конце каждой страницы",
}

LOADED = []
ROUTERS, WHATSNEW, PREFS, MENU, CSS, JS, JOBS = [], [], [], [], [], [], []
SLOTS = {k: [] for k in SLOT_NAMES}
ICONS, GLOBALS = {}, {}


def load():
    """Импортирует все модули (вызывается до создания таблиц)."""
    if LOADED:
        return
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if not info.ispkg or info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        LOADED.append(mod)
        if getattr(mod, "router", None) is not None:
            ROUTERS.append(mod.router)
        WHATSNEW.extend(getattr(mod, "WHATSNEW", []))
        PREFS.extend(getattr(mod, "PREFS", []))
        MENU.extend(getattr(mod, "MENU", []))
        CSS.extend(getattr(mod, "CSS", []))
        JS.extend(getattr(mod, "JS", []))
        JOBS.extend(getattr(mod, "JOBS", []))
        ICONS.update(getattr(mod, "ICONS", {}))
        GLOBALS.update(getattr(mod, "GLOBALS", {}))
        for name, tpl in (getattr(mod, "SLOTS", {}) or {}).items():
            if name not in SLOTS:
                raise ValueError(f"packs.{info.name}: неизвестный слот {name!r}")
            SLOTS[name].extend(tpl if isinstance(tpl, (list, tuple)) else [tpl])


def slot(name):
    return SLOTS.get(name, [])


def menu_groups(base_groups):
    """Мобильное меню: пункты модулей добавляются в существующие группы или в новые."""
    groups = [(t, ic, list(items)) for t, ic, items in base_groups]
    for href, ic, label, group in MENU:
        for t, _gic, items in groups:
            if t == group:
                items.append((href, ic, label))
                break
        else:
            groups.append((group, ic, [(href, ic, label)]))
    return groups


def feature_count():
    return sum(len(items) for _, _, items in WHATSNEW)
