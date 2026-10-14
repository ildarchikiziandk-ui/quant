"""Расширенные настройки пользователя.

Все настройки описаны в одном реестре PREFS и хранятся в JSON-колонке User.prefs. Страница
настроек строится по реестру автоматически. У каждой настройки есть реальное действие:
- where="server" — проверяется в коде сервера (лента, приватность, уведомления, чаты);
- where="client" — применяется в браузере: CSS-класс p-<key> на <html> или поведение в app.js.
"""
import json
import re
from datetime import datetime

from services import timezones

SECTIONS = {
    "feed": "📰 Лента",
    "privacy": "🔒 Приватность",
    "notifications": "🔔 Уведомления",
    "messages": "💬 Сообщения",
    "appearance": "🎨 Оформление",
    "accessibility": "♿ Доступность",
}

ONOFF = None
HOURS = [(str(h), f"{h:02d}:00") for h in range(24)]
AUDIENCE = [("all", "Все"), ("followers", "Мои подписчики"), ("nobody", "Никто")]


def _p(key, section, label, desc="", default=False, kind="bool", options=None, where="client", group=""):
    return {"key": key, "section": section, "label": label, "desc": desc, "default": default, "kind": kind,
            "options": options or [], "where": where, "group": group}


PREFS = [
    # --- Лента: рекомендации -------------------------------------------------------------------------------
    _p("feed_default_tab", "feed", "Вкладка по умолчанию", "Что открывать на главной", "foryou", "select",
       [("foryou", "Рекомендации"), ("following", "Подписки")], "server", "Рекомендации"),
    _p("rec_explore", "feed", "Новое в рекомендациях", "Насколько часто показывать авторов и темы, которых вы ещё не знаете", "normal", "select",
       [("low", "Реже — только то, что я люблю"), ("normal", "Сбалансированно"), ("high", "Чаще — хочу открывать новое")], "server", "Рекомендации"),
    _p("rec_freshness", "feed", "Свежесть постов", "Что важнее в рекомендациях", "normal", "select",
       [("fresh", "Самое новое"), ("normal", "Баланс"), ("popular", "Самое популярное")], "server", "Рекомендации"),
    _p("rec_reasons", "feed", "Объяснять рекомендации", "Подпись «Вам нравится #тег» над рекомендованным постом", True, where="server", group="Рекомендации"),
    _p("rec_hide_own", "feed", "Не показывать мои посты в рекомендациях", "", True, where="server", group="Рекомендации"),
    _p("rec_hide_seen", "feed", "Убирать уже просмотренное", "Посты, которые вы уже видели, опускаются вниз", True, where="server", group="Рекомендации"),
    # --- Лента: фильтры -------------------------------------------------------------------------------------
    _p("feed_hide_reposts", "feed", "Скрывать репосты", "Только оригинальные посты", where="server", group="Фильтры"),
    _p("feed_hide_polls", "feed", "Скрывать опросы", where="server", group="Фильтры"),
    _p("feed_hide_long", "feed", "Скрывать длинные посты", "Больше 500 символов", where="server", group="Фильтры"),
    _p("feed_hide_liked", "feed", "Скрывать посты, которые я уже лайкнул", where="server", group="Фильтры"),
    _p("feed_hide_media", "feed", "Только текст", "Скрывать посты с фото и видео", where="server", group="Фильтры"),
    _p("feed_muted_words", "feed", "Скрытые слова", "Посты с этими словами не попадут в ленту. Через запятую", "", "text", where="server", group="Фильтры"),
    # --- Лента: отображение ---------------------------------------------------------------------------------
    _p("autoplay_video", "feed", "Автовоспроизведение видео", "Видео запускается без звука, когда попадает на экран", True, group="Отображение"),
    _p("blur_media", "feed", "Размывать фото и видео", "Медиа открывается по нажатию", group="Отображение"),
    _p("hide_counters", "feed", "Скрыть счётчики", "Без цифр лайков, комментариев и репостов — меньше гонки за цифрами", group="Отображение"),
    _p("hide_reactions", "feed", "Скрыть эмодзи-реакции под постами", group="Отображение"),
    _p("expand_long", "feed", "Сразу раскрывать длинные посты", group="Отображение"),
    _p("double_tap_like", "feed", "Лайк двойным нажатием на фото", "", True, group="Отображение"),
    _p("infinite_scroll", "feed", "Бесконечная прокрутка", "Если выключить — посты подгружаются кнопкой", True, group="Отображение"),
    _p("hide_stories_bar", "feed", "Скрыть истории на главной", group="Отображение"),
    _p("links_new_tab", "feed", "Открывать внешние ссылки в новой вкладке", "", True, group="Отображение"),
    _p("hide_sidebar_tasks", "feed", "Скрыть блок «Задания дня»", group="Боковая панель"),
    _p("hide_sidebar_suggest", "feed", "Скрыть блок «Кого почитать»", group="Боковая панель"),
    _p("hide_sidebar_birthdays", "feed", "Скрыть дни рождения друзей", group="Боковая панель"),
    _p("focus_mode", "feed", "Режим фокуса", "Убрать правую колонку целиком", group="Боковая панель"),
    # --- Приватность ------------------------------------------------------------------------------------------
    _p("who_can_comment", "privacy", "Кто может комментировать мои посты", "", "all", "select", AUDIENCE, "server", "Взаимодействие"),
    _p("who_can_mention", "privacy", "Кто может упоминать меня через @", "", "all", "select", AUDIENCE, "server", "Взаимодействие"),
    _p("allow_reposts", "privacy", "Разрешить репосты моих постов", "", True, where="server", group="Взаимодействие"),
    _p("hide_followers_list", "privacy", "Скрыть список подписчиков", "Другие увидят только число", where="server", group="Профиль"),
    _p("hide_following_list", "privacy", "Скрыть список подписок", "", where="server", group="Профиль"),
    _p("hide_from_search", "privacy", "Не показывать меня в поиске и рекомендациях", "", where="server", group="Профиль"),
    _p("hide_birthday", "privacy", "Скрыть день рождения в профиле", "", where="server", group="Профиль"),
    _p("hide_gamification", "privacy", "Скрыть уровень, очки и стрик в профиле", "", where="server", group="Профиль"),
    _p("hide_achievements", "privacy", "Скрыть достижения в профиле", "", where="server", group="Профиль"),
    _p("guests_hidden", "privacy", "Скрыть посты от незарегистрированных", "Гости без аккаунта не увидят ваши посты", where="server", group="Профиль"),
    _p("who_can_ask", "privacy", "Кто может задавать мне вопросы", "Раздел «Вопросы» в профиле", "all", "select", AUDIENCE, "server", "Вопросы"),
    _p("allow_anonymous_questions", "privacy", "Разрешить анонимные вопросы", "", True, where="server", group="Вопросы"),
    _p("incognito_views", "privacy", "Не учитывать мои визиты в статистике чужих профилей", "", where="server", group="Следы"),
    _p("anonymous_stories", "privacy", "Смотреть истории анонимно", "Вы не попадёте в список просмотревших", where="server", group="Следы"),
    _p("read_receipts", "privacy", "Отчёты о прочтении ✓✓", "Если выключить, собеседники не увидят, что вы прочитали сообщение", True, where="server", group="Следы"),
    _p("typing_status", "privacy", "Показывать «печатает…»", "", True, where="server", group="Следы"),
    # --- Уведомления --------------------------------------------------------------------------------------------
    _p("notify_reposts", "notifications", "Репосты", "Когда репостят ваш пост", True, where="server", group="Дополнительно"),
    _p("notify_comment_likes", "notifications", "Лайки комментариев", "", True, where="server", group="Дополнительно"),
    _p("notify_story_reactions", "notifications", "Реакции на истории", "", True, where="server", group="Дополнительно"),
    _p("notify_achievements", "notifications", "Достижения и уровни", "", True, where="server", group="Дополнительно"),
    _p("notify_group_invites", "notifications", "Приглашения в группы", "", True, where="server", group="Дополнительно"),
    _p("notify_raffle", "notifications", "Розыгрыши", "", True, where="server", group="Дополнительно"),
    _p("notify_questions", "notifications", "Вопросы и ответы", "", True, where="server", group="Дополнительно"),
    _p("notify_gifts", "notifications", "Подарки", "", True, where="server", group="Дополнительно"),
    _p("notify_events", "notifications", "Мероприятия", "Кто идёт на ваши события", True, where="server", group="Дополнительно"),
    _p("quiet_hours", "notifications", "Тихие часы", "Не присылать push-уведомления ночью (по вашему часовому поясу)", where="server", group="Тихие часы"),
    _p("quiet_from", "notifications", "Тихие часы: с", "", "23", "select", HOURS, "server", "Тихие часы"),
    _p("quiet_to", "notifications", "Тихие часы: до", "", "8", "select", HOURS, "server", "Тихие часы"),
    _p("push_hide_text", "notifications", "Скрывать текст в push", "Вместо текста сообщения — «Новое сообщение»", where="server", group="Тихие часы"),
    _p("sound", "notifications", "Звуки на сайте", "Короткий звук при новом сообщении", True, group="На сайте"),
    _p("title_badge", "notifications", "Счётчик в названии вкладки", "(3) Nuvora — сколько непрочитанного", True, group="На сайте"),
    # --- Сообщения ------------------------------------------------------------------------------------------------
    _p("enter_to_send", "messages", "Отправлять по Enter", "Shift+Enter — новая строка. Если выключить — отправка по Ctrl+Enter", True),
    _p("chat_compact", "messages", "Компактные сообщения", "Меньше отступов между сообщениями"),
    _p("chat_big_emoji", "messages", "Крупные эмодзи", "Сообщение из одних эмодзи показывается крупно", True),
    _p("chat_timestamps", "messages", "Время у каждого сообщения", "", True),
    # --- Оформление -------------------------------------------------------------------------------------------------
    _p("compact", "appearance", "Компактный режим", "Меньше отступов, больше постов на экране"),
    _p("corners", "appearance", "Скругление углов", "", "round", "select", [("round", "Скруглённые"), ("soft", "Слегка"), ("sharp", "Прямые")]),
    _p("avatar_shape", "appearance", "Форма аватарок", "", "circle", "select", [("circle", "Круг"), ("squircle", "Скруглённый квадрат")]),
    _p("font_family", "appearance", "Шрифт", "", "system", "select", [("system", "Системный"), ("serif", "С засечками"), ("mono", "Моноширинный")]),
    _p("nav_labels", "appearance", "Подписи в нижнем меню на телефоне", "", True),
    _p("timezone", "appearance", "Часовой пояс", "Время сообщений, постов, отложенных публикаций и тихих часов", "moscow", "select",
       timezones.options(), "server", "Дата и время"),
    _p("absolute_time", "appearance", "Точное время вместо «5 мин назад»", "", group="Дата и время"),
    # --- Доступность -----------------------------------------------------------------------------------------------
    _p("reduce_motion", "accessibility", "Уменьшить анимации", "Отключить плавные переходы и движения"),
    _p("high_contrast", "accessibility", "Высокий контраст", "Более тёмный текст и чёткие границы"),
    _p("underline_links", "accessibility", "Подчёркивать ссылки", ""),
    _p("line_spacing", "accessibility", "Увеличенный межстрочный интервал", "Текст легче читать"),
    _p("big_buttons", "accessibility", "Крупные кнопки", "Проще попадать пальцем"),
    _p("hotkeys", "accessibility", "Горячие клавиши", "J/K, L, N и другие (нажмите ?)", True),
    _p("alt_hints", "accessibility", "Подсказки при наведении", "Показывать названия у кнопок-иконок", True),
]
BY_KEY = {p["key"]: p for p in PREFS}


def _raw(user):
    if user is None:
        return {}
    cache = getattr(user, "_prefs_cache", None)
    if cache is None:
        try:
            cache = json.loads(user.prefs or "{}")
        except (ValueError, TypeError):
            cache = {}
        try:
            user._prefs_cache = cache
        except AttributeError:
            pass
    return cache


def get(user, key):
    p = BY_KEY[key]
    v = _raw(user).get(key, p["default"])
    if p["kind"] == "select" and v not in [o[0] for o in p["options"]]:
        return p["default"]
    return v


def values(user):
    return {k: get(user, k) for k in BY_KEY}


def client_values(user):
    return {k: v for k, v in values(user).items() if BY_KEY[k]["where"] == "client"}


def html_classes(user):
    """CSS-классы для <html>: p-<key> для включённых флагов, p-<key>-<value> для списков."""
    out = []
    for k, v in client_values(user).items():
        p = BY_KEY[k]
        if p["kind"] == "bool" and v:
            out.append("p-" + k.replace("_", "-"))
        elif p["kind"] == "select":
            out.append(f"p-{k.replace('_', '-')}-{v}")
    return " ".join(out)


def section_prefs(section):
    groups = {}
    for p in PREFS:
        if p["section"] == section:
            groups.setdefault(p["group"], []).append(p)
    return list(groups.items())


def update(user, section, form):
    data = dict(_raw(user))
    for p in PREFS:
        if p["section"] != section:
            continue
        k = p["key"]
        if p["kind"] == "bool":
            data[k] = form.get(k) in ("on", "1", "true", "yes")
        elif p["kind"] == "select":
            v = str(form.get(k, p["default"]))
            data[k] = v if v in [o[0] for o in p["options"]] else p["default"]
        else:
            data[k] = re.sub(r"\s+", " ", str(form.get(k, "")))[:500].strip()
    user.prefs = json.dumps(data, ensure_ascii=False)
    user._prefs_cache = data


# --- Хелперы для серверных настроек ---------------------------------------------------------------------------------
def muted_words(user):
    return [w.strip().lower() for w in (get(user, "feed_muted_words") or "").split(",") if len(w.strip()) >= 2][:50]


def audience_allows(db, owner, actor, key):
    """Проверка настроек вида «кто может …» (all / followers / nobody)."""
    from services import social
    if not owner or not actor or owner.id == actor.id:
        return True
    v = get(owner, key)
    if v == "nobody":
        return False
    if v == "followers":
        return social.is_following(db, actor, owner)
    return True


def in_quiet_hours(user, now=None):
    if not get(user, "quiet_hours"):
        return False
    h = timezones.to_local(now or datetime.utcnow(), user).hour  # в поясе пользователя
    a, b = int(get(user, "quiet_from")), int(get(user, "quiet_to"))
    return (a <= h < b) if a < b else (h >= a or h < b)


NOTIFY_PREFS = {"repost": "notify_reposts", "comment_like": "notify_comment_likes", "story_reaction": "notify_story_reactions",
                "achievement": "notify_achievements", "level": "notify_achievements", "group_invite": "notify_group_invites",
                "raffle": "notify_raffle", "question": "notify_questions", "answer": "notify_questions", "gift": "notify_gifts",
                "event": "notify_events"}


def sql_flag_off(column, key):
    """SQL-условие «у пользователя НЕ включена булева настройка key» (для фильтров в запросах)."""
    from sqlalchemy import or_
    return or_(column == None, column == "", ~column.like(f'%"{key}": true%'))
