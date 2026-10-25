"""Nuvora 3.x: модули чатов, игр, помощника Нувы, красивых логинов и безопасности."""
from . import models  # noqa: F401  таблицы
from . import account, accounts, admin_more, admin_plus, admin_tools, ai, appupdate, calls, capsule, chat, chat_games, dayyot, feed, games, handles_shop, login_approve, media, payments, people, phone, stickers  # noqa: F401  маршруты регистрируются на общем router
from .common import router  # noqa: F401
from . import site

WHATSNEW = [
    ("Лента и интерфейс", "home", [
        ("users", "Лента «Подписки и подписчики» открывается по умолчанию: посты тех, на кого вы подписаны, и тех, кто подписан на вас"),
        ("sparkle", "Посты на телефоне — на всю ширину, без «0» под кнопками; «⋯» всегда в углу"),
        ("chat", "Сообщения: всё лишнее убрано в меню «⋯», папки появляются, когда вы их создадите"),
    ]),
    ("Игры в чате", "dice", [
        ("layers", "«Четыре в ряд»: фишки падают вниз, нужно собрать четыре подряд"),
        ("wave", "«Камень, ножницы, бумага» до двух побед — выбор друга виден, только когда оба выбрали"),
        ("dice", "«Кости»: кто выбросит больше на двух кубиках"),
        ("type", "«Виселица»: загадайте слово — друг угадывает по буквам"),
        ("reply", "Ответ на стикер или игру показывает понятную подпись, а не служебный код"),
    ]),
    ("Новый цвет", "palette", [
        ("smartphone", "Больше фирменного синего: кнопки, свои сообщения, активные вкладки"),
        ("check", "Мобильная версия: кнопки записи и отправки больше не уезжают за край экрана"),
    ]),
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
        ("at", "«Красивые логины»: короткие и звучные логины вроде @fox или @lucky — за искры"),
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
        ("gift", "Ежедневный сундук: искры за каждый день подряд, на 7-й — большой приз"),
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
JOBS = [feed.unmute_expired, capsule.capsules_due, account.new_device_alerts, handles_shop.seed_owner_aliases, calls.expire_job, media.expire_chat_media, accounts.seed_job, payments.pending_job]
GLOBALS = {
    "v3_card": chat.card, "v3_chest": people.chest_state, "v3_backup_left": account.backup_left,
    "v3_ai_on": ai.enabled, "v3_calls_on": calls.calls_on, "v3_posts_locked": accounts.posts_locked, "v3_login_approve": login_approve.enabled, "v3_mute_until": admin_tools.mute_until, "site_get": site.get, "v3_pay_keys": payments.keys_set, "v3_pay_on": payments.enabled, "v3_warnings": admin_tools.warnings_of, "v3_aliases": handles_shop.aliases_of,
}
