"""Nuvora 3.0: 20 новых функций."""
from . import models  # noqa: F401  таблицы
from . import account, ai, chat, dayyot, feed, games, people, spaces  # noqa: F401  маршруты регистрируются на общем router
from .common import router  # noqa: F401

WHATSNEW = [
    ("Чаты", "chat", [
        ("poll", "Опросы прямо в переписке — с процентами и несколькими ответами"),
        ("grid", "Крестики-нолики с другом в чате, с реваншем"),
        ("sparkle", "Сообщения с эффектами: конфетти, сердечки, снег и салют"),
        ("folder", "Свои папки чатов: «Семья», «Учёба», «Работа»"),
    ]),
    ("Лента", "home", [
        ("clock", "Обратный отсчёт в посте до важного события"),
        ("eye-off", "«Не показывать 30 дней» — временно скрыть автора из ленты"),
        ("users", "Лента «Только друзья» — посты взаимных подписок без рекомендаций"),
    ]),
    ("Люди и награды", "user", [
        ("link", "«Мои ссылки» — своя страница со всеми ссылками и счётчиком переходов"),
        ("gift", "Ежедневный сундук: очки за каждый день подряд, на 7-й — большой приз"),
        ("sparkle", "«Похожие на вас» — люди с общими интересами в разделе «Обзор»"),
    ]),
    ("Новые разделы", "grid", [
        ("bag", "Барахолка: продавайте и отдавайте вещи, фото, цена, город, избранное"),
        ("target", "Привычки: отмечайте каждый день, серия дней и календарь за месяц"),
        ("smile", "Дневник настроения с графиком за месяц"),
        ("mail", "Капсула времени — письмо себе в будущее"),
        ("dice", "Игра «Словечко»: угадай слово дня из 5 букв"),
        ("grid", "Игра 2048 с таблицей рекордов среди друзей"),
    ]),
    ("Помощник Нува", "bot", [
        ("bot", "Нува — помощник Nuvora: подскажет, как всё устроено, придумает подпись, поздравление или идею поста"),
        ("type", "Понимает опечатки, разные формы слов и даже текст в английской раскладке"),
        ("edit", "«Исправить текст» и «Подобрать хэштеги» прямо в редакторе поста"),
    ]),
    ("Безопасность и помощь", "shield", [
        ("bell", "Уведомление о входе в аккаунт с нового устройства"),
        ("key", "Резервные коды для входа, если потерян телефон с кодами 2FA"),
        ("layers", "Группировка уведомлений: «Лиза и ещё 3 оценили ваш пост»"),
        ("lifebuoy", "Центр помощи с ответами на частые вопросы и поиском"),
    ]),
]

MENU = [
    ("/ai", "bot", "Помощник Нува", "Разделы"),
    ("/market", "bag", "Барахолка", "Разделы"),
    ("/habits", "target", "Привычки", "Разделы"),
    ("/mood", "smile", "Дневник настроения", "Разделы"),
    ("/capsule", "mail", "Капсула времени", "Разделы"),
    ("/games", "dice", "Игры", "Разделы"),
    ("/friends", "users", "Только друзья", "Обзор"),
    ("/links", "link", "Мои ссылки", "Люди"),
    ("/help", "help", "Центр помощи", "Помощь"),
]

SLOTS = {
    "message_extra": "packs/v3/slot_message.html",
    "chat_tools": "packs/v3/slot_chat_tools.html",
    "chat_list_top": "packs/v3/slot_chat_list.html",
    "post_menu": "packs/v3/slot_post_menu.html",
    "composer_tools": "packs/v3/slot_composer_tools.html",
    "post_after_text": "packs/v3/slot_countdown.html",
    "home_top": "packs/v3/slot_home.html",
    "explore_top": "packs/v3/slot_explore.html",
    "profile_after_bio": "packs/v3/slot_profile.html",
    "profile_menu": "packs/v3/slot_profile_menu.html",
    "settings_bottom": "packs/v3/slot_settings.html",
    "notifications_top": "packs/v3/slot_notifications.html",
}

CSS = ["packs/v3/v3.css"]
JS = ["packs/v3/v3.js"]
JOBS = [feed.unmute_expired, spaces.capsules_due, account.new_device_alerts]
GLOBALS = {
    "v3_card": chat.card, "v3_countdown": feed.countdown, "v3_chest": people.chest_state, "v3_similar": people.similar_people,
    "v3_links_count": people.links_count, "v3_backup_left": account.backup_left, "v3_json": spaces.json_list,
    "v3_ai_on": ai.enabled,
}
