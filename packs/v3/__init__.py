"""Nuvora 3.x: модули чатов, игр, помощника Нувы, красивых логинов и безопасности."""
from . import models  # noqa: F401  таблицы
from . import account, accounts, admin_more, admin_plus, ai, appupdate, calls, capsule, chat, dayyot, feed, games, handles_shop, media, people, stickers  # noqa: F401  маршруты регистрируются на общем router
from .common import router  # noqa: F401

WHATSNEW = [
    ("Стикеры", "whale", [
        ("whale", "Три набора стикеров: «Кит Нуви», «Кот Мур» и «Капибара Капи» — 41 стикер, вкладки в панели"),
    ]),
    ("Звонки", "phone", [
        ("phone", "Звонки 1 на 1 прямо в переписке — кнопка с трубкой в шапке чата"),
        ("mic", "Выключение микрофона во время разговора, звонок не обрывается кнопкой «назад»"),
        ("history", "История звонков в переписке и уведомление о пропущенном звонке"),
    ]),
    ("Новое в 3.1", "sparkle", [
        ("smartphone", "Приложение стало настоящим приложением: стили, иконки и эмодзи встроены и открываются мгновенно"),
        ("download", "Без интернета: последние открытые страницы, офлайн-экран и 2048 работают без сети"),
        ("sparkle", "Больше анимаций: плавное появление карточек, «волна» от касаний, живые лайки и счётчики"),
        ("layers", "Интерфейс разгружен: одна карточка «Сегодня», компактный профиль, аккуратные настройки"),
        ("at", "«Красивые логины»: короткие и звучные логины вроде @fox или @lucky — за баллы"),
        ("users", "До трёх логинов у одного человека: основной и два дополнительных"),
        ("layers", "Меньше лишнего: убраны редко нужные разделы и повторяющиеся функции"),
    ]),
    ("Чаты", "chat", [
        ("poll", "Опросы прямо в переписке — с процентами и несколькими ответами"),
        ("grid", "Крестики-нолики с другом в чате, с реваншем"),
        ("sparkle", "Сообщения с эффектами: конфетти, сердечки, снег и салют"),
        ("folder", "Свои папки чатов: «Семья», «Учёба», «Работа»"),
    ]),
    ("Лента и награды", "home", [
        ("eye-off", "«Не показывать 30 дней» — временно скрыть автора из ленты"),
        ("gift", "Ежедневный сундук: очки за каждый день подряд, на 7-й — большой приз"),
        ("mail", "Капсула времени — письмо себе в будущее"),
    ]),
    ("Игры", "dice", [
        ("type", "Игра «Словечко»: угадай слово дня из 5 букв"),
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
    ("/capsule", "mail", "Капсула времени", "Разделы"),
    ("/games", "dice", "Игры", "Разделы"),
    ("/handles", "at", "Красивые логины", "Награды"),
    ("/help", "help", "Центр помощи", "Помощь"),
]

SLOTS = {
    "message_extra": "packs/v3/slot_message.html",
    "chat_tools": "packs/v3/slot_chat_tools.html",
    "chat_head": "packs/v3/slot_chat_head.html",
    "group_tools": "packs/v3/slot_group_tools.html",
    "chat_list_top": "packs/v3/slot_chat_list.html",
    "post_menu": "packs/v3/slot_post_menu.html",
    "composer_tools": "packs/v3/slot_composer_tools.html",
    "home_top": "packs/v3/slot_home.html",
    "settings_bottom": "packs/v3/slot_settings.html",
    "notifications_top": "packs/v3/slot_notifications.html",
}

CSS = ["packs/v3/v3.css"]
JS = ["packs/v3/v3.js", "packs/v3/calls.js", "packs/v3/media.js"]
JOBS = [feed.unmute_expired, capsule.capsules_due, account.new_device_alerts, handles_shop.seed_owner_aliases, calls.expire_job, media.expire_chat_media, accounts.seed_job]
GLOBALS = {
    "v3_card": chat.card, "v3_chest": people.chest_state, "v3_backup_left": account.backup_left,
    "v3_ai_on": ai.enabled, "v3_calls_on": calls.calls_on, "v3_posts_locked": accounts.posts_locked, "v3_aliases": handles_shop.aliases_of,
}
