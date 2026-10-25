"""Нува — помощник Nuvora. С ключом GigaChat отвечает нейросетью (packs/v3/gigachat.py), без него — по справке (хватает 1 ГБ памяти).

Как отвечает:
  1. Готовит вопрос: растянутые буквы, английская раскладка, частые ошибки, синонимы, основы слов (стеммер),
     исправление опечаток по словарю справки.
  2. Простые фразы (привет, как дела, анекдот, время) и заготовки: подписи к фото, поздравления, идеи постов.
  3. Поиск по базе знаний — справка + ответы, добавленные модераторами на /ai/admin. Редкие слова весят больше
     частых (как в поисковиках, BM25), слова из вопроса статьи — вдвое больше слов из ответа.
  4. Понимает уточнения («а как это отключить?») — учитывает прошлый вопрос.
  5. Не нашла ответ — записывает вопрос в «Вопросы без ответа», чтобы модератор дописал ответ.
В редакторе поста: «Исправить текст» и «Подобрать хэштеги».
"""
import math
import random
import re
import time
from datetime import datetime

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import config
from database import SessionLocal, get_db
from deps import current_user, json_error, login_redirect, render
from routers.posts import read_payload
from services import social, timezones

from . import models as m
from . import nuva_lang as lang
from .common import router, s
from .help import ARTICLES


def enabled():
    return True


def smart():
    """Подключена ли нейросеть (для подписи на странице Нувы)."""
    from . import gigachat
    return gigachat.enabled()


# ---------------------------------------------------------------- словари
STOP = set("""и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из
ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо
ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти
мой тем чтобы нее сейчас были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая
много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между это мне меня мой
нужно хочу хотел хотела хочется подскажи подскажите скажи скажите пожалуйста привет здравствуйте делать сделать сделал сделала получается
каким каком какие какое каких который которые почему зачем вообще просто типа ли бы вот тут
начать начинать начну начала начал попробовать пробовать умею""".split())

SYNONYMS = {  # начало разговорного слова → слово из справки
    "2fa": "двухфакторная", "двухфактор": "двухфакторная", "двухэтап": "двухфакторная", "аутентиф": "двухфакторная",
    "пасс": "пароль", "пароль": "пароль", "ник": "логин", "никнейм": "логин", "юзернейм": "логин",
    "переписк": "чат", "сообщен": "чат", "личк": "чат", "лс": "чат", "диалог": "чат", "мессендж": "чат",
    "голосован": "опрос", "опросник": "опрос", "крестик": "крестики", "нолик": "крестики",
    "пуш": "уведомления", "уведомл": "уведомления", "оповещ": "уведомления", "оповещен": "уведомления",
    "забан": "заблокировать", "бан": "заблокировать", "блокир": "заблокировать", "черн": "заблокировать", "игнор": "заблокировать",
    "удали": "удалить", "стере": "удалить", "убра": "удалить", "снест": "удалить",
    "апк": "приложение", "apk": "приложение", "андроид": "приложение", "android": "приложение", "прилож": "приложение",
    "балл": "искры", "монет": "искры", "поинт": "искры", "бонус": "искры", "очк": "искры", "искр": "искры",
    "аватар": "профиль", "аватарк": "профиль", "аву": "профиль", "ава": "профиль", "фотк": "фото",
    "обои": "фон", "заставк": "фон", "тем": "оформление",
    "постав": "включить", "подключ": "включить", "активир": "включить",
    "поменя": "сменить", "измени": "сменить", "замени": "сменить", "исправ": "сменить",
    "взлом": "взломали", "украл": "взломали", "увели": "взломали",
    "письм": "капсула", "будущ": "капсула",
    "словечк": "словечко", "вордл": "словечко", "wordle": "словечко", "друз": "друзья", "подписк": "подписки",
    "техподдерж": "поддержку", "саппорт": "поддержку", "админ": "поддержку", "жалоб": "поддержку",
}

TYPOS = {}  # заполняется ниже из словаря «Исправить текст»

LINKS = {  # статья справки → кнопка-переход
    "Как сменить логин или имя?": ("/settings?section=profile", "Открыть профиль в настройках"),
    "Забыл пароль — что делать?": ("/forgot-password", "Восстановить пароль"),
    "Как сменить пароль?": ("/settings?section=account", "Сменить пароль"),
    "Аккаунт взломали — что делать?": ("/settings?section=security", "Настройки безопасности"),
    "Как удалить аккаунт?": ("/settings?section=data", "Мои данные"),
    "Как включить двухфакторную защиту?": ("/settings?section=security", "Настройки безопасности"),
    "Что такое резервные коды?": ("/settings?section=security", "Настройки безопасности"),
    "Пришло уведомление о входе с нового устройства": ("/settings?section=security", "Проверить сеансы"),
    "Как поставить код-пароль на приложение?": ("/settings?section=security", "Настройки безопасности"),
    "Как разложить чаты по папкам?": ("/messages", "Открыть чаты"),
    "Как создать опрос или сыграть в крестики-нолики?": ("/messages", "Открыть чаты"),
    "Как получить искры?": ("/achievements", "Мои достижения"),
    "Можно ли иметь несколько логинов?": ("/settings?section=account", "Дополнительные логины"),
    "Как получить красивый логин?": ("/handles", "Красивые логины"),
    "Что такое капсула времени?": ("/capsule", "Написать письмо в будущее"),
    "Как играть в «Словечко»?": ("/games/word", "Играть"),
    "Не приходят уведомления на телефоне": ("/settings?section=notifications", "Настройки уведомлений"),
    "Как обновить приложение?": (config.ANDROID_APK_URL or "/", "Скачать приложение"),
    "Не нашли ответ?": ("/support", "Написать в поддержку"),
}


def _norm(text):
    return (text or "").lower().replace("ё", "е")


def _canon(word):
    for k, v in SYNONYMS.items():
        if word.startswith(k) and (len(k) >= 4 or word == k or len(word) <= len(k) + 3):
            return v
    return word


def stems_of(text):
    out = []
    for w in lang.words(text):
        w = TYPOS.get(w, w)
        if w in STOP or len(w) < 2:
            continue
        st = lang.stem(_canon(w))
        if st and st not in out:
            out.append(st)
    return out


# ---------------------------------------------------------------- база знаний
class _KB:
    def __init__(self):
        self.entries, self.df, self.vocab, self.known, self.stamp, self.checked = [], {}, {}, set(), None, 0

    def _db_stamp(self, db):
        row = db.query(func.count(m.NuvaAnswer.id), func.max(m.NuvaAnswer.updated_at)).one()
        return (row[0], row[1])

    def ensure(self, db):
        """Пересобирает индекс при изменении ответов модераторов (проверка не чаще раза в 20 секунд)."""
        if self.entries and time.time() - self.checked < 20:
            return self
        self.checked = time.time()
        stamp = self._db_stamp(db)
        if self.entries and stamp == self.stamp:
            return self
        entries = []
        for sec, _, q, a in ARTICLES:
            entries.append({"title": q, "text": a, "link": LINKS.get(q), "head": set(stems_of(q + " " + sec)), "body": set(stems_of(a)), "aid": None})
        for row in db.query(m.NuvaAnswer).all():
            link = (row.link_url, row.link_title or "Перейти") if row.link_url else None
            entries.append({"title": row.question, "text": row.answer, "link": link, "aid": row.id,
                            "head": set(stems_of(row.question + " " + (row.keywords or ""))), "body": set(stems_of(row.answer))})
        df = {}
        for e in entries:
            for st in e["head"] | e["body"]:
                df[st] = df.get(st, 0) + 1
        self.entries, self.df, self.stamp = entries, df, stamp
        self.vocab = dict(df)
        self.known = set(df) | STOP | {lang.stem(w) for w in STOP} | set(SMALLTALK_WORDS)
        return self

    def idf(self, st):
        n = len(self.entries)
        return math.log(1 + (n - self.df.get(st, 0) + 0.5) / (self.df.get(st, 0) + 0.5))

    def search(self, stems, limit=3):
        syn = _syn_stems()
        scored = []
        for e in self.entries:
            sc, hit = 0.0, 0
            for st in stems:
                boost = 1.3 if st in syn else 1.0  # слово узнано через синоним — человек явно спрашивает об этом
                if st in e["head"]:
                    sc += 2 * self.idf(st) * boost
                    hit += 1
                elif st in e["body"]:
                    sc += self.idf(st) * boost
                    hit += 1
            if hit:
                # слова, которых нет нигде в базе (тема, о которой справка ничего не знает), снижают уверенность
                unknown = sum(1 for st in stems if st not in self.df and len(st) >= 4)
                scored.append((sc * (0.6 + 0.4 * hit / len(stems)) * (0.55 ** unknown), e))
        scored.sort(key=lambda x: -x[0])
        return scored[:limit]


KB = _KB()
_SYN = []


def _syn_stems():
    if not _SYN:
        _SYN.append({lang.stem(v) for v in SYNONYMS.values()})
    return _SYN[0]


def prepare(question):
    """Возвращает (текст после исправлений, основы слов с исправленными опечатками, была ли не та раскладка)."""
    q = lang.squeeze(question.strip())
    layout = lang.looks_like_wrong_layout(q, KB.known)
    if layout:
        q = lang.from_layout(q)
    stems = [lang.closest(st, KB.vocab) for st in stems_of(q)]
    return q, list(dict.fromkeys(stems)), layout


# ---------------------------------------------------------------- готовые ответы
CAPTIONS = {
    "мор": ["Море, солнце и никаких дедлайнов", "Соль на коже, ветер в волосах", "Здесь время течёт медленнее"],
    "закат": ["Небо сегодня постаралось", "Закат, который хочется поставить на паузу", "Тот самый вечерний свет"],
    "природ": ["Перезагрузка на природе", "Тишина, которую слышно", "Лучший фильтр — настоящая природа"],
    "гор": ["Чем выше, тем проще дышать", "Горы зовут — и я иду", "Вид, ради которого стоило подниматься"],
    "ед": ["Сначала фото, потом обед", "Еда — это тоже искусство", "Вкусно настолько, что пришлось поделиться"],
    "кот": ["Главный в доме — он", "Мурчание лечит лучше всего", "Тот, кто разрешает мне здесь жить"],
    "собак": ["Лучший друг на четырёх лапах", "Хвост виляет — день удался", "Мой самый верный фанат"],
    "друз": ["С ними даже обычный день — праздник", "Мои люди", "Собрались — и сразу стало теплее"],
    "город": ["Город, который не спит", "Гуляю и запоминаю", "Улицы, в которые влюбляешься"],
    "селфи": ["Просто я и хорошее настроение", "Сегодня без фильтров", "Улыбка — лучший аксессуар"],
    "зим": ["Зима пришла — и сразу стало уютно", "Снег скрипит, щёки горят", "Время пледа и какао"],
    "осен": ["Осень в лучшем её проявлении", "Шуршу листьями и не спешу", "Золотое время года"],
    "лет": ["Лето, не уходи", "Солнце в каждом кадре", "Тёплые воспоминания на потом"],
    "": ["Просто хороший день", "Момент, который хочется сохранить", "Ловлю мгновения", "Без слов — просто смотрите",
         "Маленькие радости — самые важные", "Вот так и живём"],
}
GREETINGS = {
    "рожд": ["С днём рождения! Пусть этот год принесёт много радости, здоровья и поводов улыбаться. Пусть всё задуманное сбывается!",
             "Поздравляю с днём рождения! Желаю ярких событий, верных друзей и сил на все мечты.",
             "С днём рождения! Пусть каждый день нового года жизни будет немного лучше предыдущего."],
    "нов": ["С Новым годом! Пусть он будет добрым, спокойным и полным приятных сюрпризов.",
            "С Новым годом! Желаю, чтобы все планы сбылись, а рядом были самые близкие."],
    "свадьб": ["Поздравляю со свадьбой! Любви, понимания и долгих счастливых лет вместе."],
    "мам": ["Мама, спасибо за заботу и тепло. Желаю здоровья, радости и спокойных дней!"],
    "пап": ["Папа, с праздником! Здоровья, сил и хорошего настроения."],
    "8 март": ["С 8 Марта! Весеннего настроения, тепла и улыбок."],
    "23 феврал": ["С 23 Февраля! Сил, уверенности и надёжных друзей рядом."],
    "выпуск": ["Поздравляю с выпуском! Пусть впереди будет интересный путь и много открытых дверей."],
    "": ["Поздравляю! Желаю здоровья, радости и исполнения желаний.", "С праздником! Пусть будет много светлых дней и хороших новостей."],
}
POST_IDEAS = [
    "Расскажите, чему вы научились за последний месяц", "Покажите вид из окна и опишите своё утро",
    "Посоветуйте книгу, фильм или сериал, который зацепил", "Сделайте опрос: «Чай или кофе?»",
    "Поделитесь маленькой победой этой недели", "Покажите любимое место в своём городе",
    "Напишите три факта о себе, один из которых — неправда, пусть друзья угадают",
    "Выложите фото без фильтров и расскажите историю за кадром", "Спросите подписчиков, о чём им интересно почитать",
    "Покажите, что у вас на рабочем столе", "Расскажите о самой смешной ситуации за неделю",
    "Поделитесь плейлистом на сегодня", "Опишите идеальный выходной в трёх словах и попросите друзей сделать так же",
]
JOKES = [
    "Программист ставит на тумбочку два стакана: с водой — если захочет пить, и пустой — если не захочет.",
    "— Доктор, мне кажется, что я кит. — Давно? — С тех пор как зарегистрировался в Nuvora.",
    "Кот смотрит на меня так, будто это я живу у него. Впрочем, так и есть.",
    "Я не опаздываю — я просто даю всем время соскучиться.",
    "Будильник — это устройство, которое каждое утро напоминает: сон закончился, а мечты остались.",
]
SKILLS = ("Я Нува — помощник Nuvora. Вот что я умею:\n"
          "— отвечать на вопросы о сайте: «как сменить пароль?», «как создать опрос?»\n"
          "— придумывать подписи к фото: «подпись к фото с моря»\n"
          "— писать короткие поздравления: «поздравление с днём рождения»\n"
          "— подкидывать идеи постов: «идея для поста»\n"
          "— рассказать анекдот, подсказать дату и время\n"
          "Понимаю опечатки и даже текст в английской раскладке.")
SMALLTALK_WORDS = ["привет", "здравствуй", "спасибо", "пока", "анекдот", "шутка", "подпись", "поздравление", "идея", "время",
                   "дела", "скучно", "бот", "нового", "умеешь"]
DEFAULT_TIPS = ["Что ты умеешь?", "Как создать опрос в чате?", "Подпись к фото с моря", "Идея для поста"]


def _pick(table, q):
    for k, items in table.items():
        if k and k in q:
            return random.choice(items)
    return random.choice(table[""])


def _smalltalk(q, user):
    """Простые фразы. q — вопрос в нижнем регистре после исправлений. Возвращает (текст, подсказки, ссылки) или None."""
    if re.search(r"^(прив|здравств|здраст|добр(ый|ое|ого)|хай|хелло|hello|hi\b|салют|ку\b|хей)", q):
        return "Привет! Я Нува, помощник Nuvora. Спросите, как что-то сделать на сайте, или попросите подпись к фото.", ["Что ты умеешь?", "Идея для поста"], []
    if re.search(r"(как (у тебя )?дела|как ты\b|как жизнь|как поживаешь)", q):
        return random.choice(["Отлично, спасибо! Помогаю людям разобраться с Nuvora. А у вас как?",
                              "Всё хорошо! Готова помочь. Что подсказать?"]), ["Что нового в Nuvora?"], []
    if re.search(r"(спасиб|благодар|thanks|thank you|пасиб|спс\b|мерси)", q):
        return "Пожалуйста! Обращайтесь, если что-то ещё понадобится.", [], []
    if re.search(r"(молодец|умница|умная|люблю тебя|ты лучш|круто|супер)", q):
        return "Спасибо, очень приятно! Стараюсь.", [], []
    if re.search(r"(дура|тупая|тупой|глупая|бесполезн|не помогл)", q):
        return ("Жаль, что не получилось помочь. Я простой помощник и отвечаю по справке. Попробуйте спросить по-другому "
                "или напишите в поддержку — там ответят люди."), [], [("/support", "Написать в поддержку")]
    if re.search(r"^(пока|до свидан|бывай|спокойной ночи)", q):
        return "До встречи! Хорошего дня.", [], []
    if re.search(r"^(ок|окей|ok|хорошо|понятно|ясно|ага|угу|да|ладно)\b[.!]?$", q):
        return "Отлично! Если появятся вопросы — пишите.", [], []
    if re.search(r"(что ты (умеешь|можешь)|кто ты|ты кто|^помощь$|^помоги$|^help$|что умеешь)", q):
        return SKILLS, ["Как создать опрос в чате?", "Подпись к фото с моря"], []
    if re.search(r"(ты (бот|робот|человек|живая|настоящ)|ты ии|ты нейросеть)", q):
        return "Я программа-помощник, а не человек и не нейросеть: отвечаю по справке Nuvora и готовым шаблонам.", [], []
    if re.search(r"(кто тебя (создал|сделал|придумал)|кто твой (создатель|автор)|кто (создал|сделал) (nuvora|нувору|сайт))", q):
        return "Меня сделала команда Nuvora — вместе с самой соцсетью.", [], []
    if re.search(r"(что нового|какие новинки|обновлени[ея]|новые функции)", q):
        import packs
        items = [t for _, _, its in packs.WHATSNEW for _, t in its]
        pick = random.sample(items, min(3, len(items)))
        return "Из нового в Nuvora:\n" + "\n".join("— " + t for t in pick), [], [("/whats-new", "Все новинки")]
    if re.search(r"(скучно|нечем заняться|чем заняться)", q):
        return "Сыграйте в «Словечко» или 2048, загляните в «Обзор» или напишите пост — вдруг кто-то тоже скучает.", ["Идея для поста"], [("/games", "Игры"), ("/explore", "Обзор")]
    if re.search(r"(анекдот|шутк|пошути|рассмеши|смешное)", q):
        return random.choice(JOKES), ["Ещё шутку"], []
    if re.search(r"(погод)", q):
        return "Погоду я пока не знаю — загляните в приложение погоды. А вот подпись к фото с прогулки придумаю!", ["Подпись к фото"], []
    if re.search(r"(который час|сколько времени|какое (сегодня )?число|какой (сегодня )?день|какая (сегодня )?дата|какой год)", q):
        now = timezones.to_local(datetime.utcnow(), user) if user else datetime.utcnow()
        months = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()
        days = "понедельник вторник среда четверг пятница суббота воскресенье".split()
        return f"Сейчас {now:%H:%M}, {days[now.weekday()]}, {now.day} {months[now.month - 1]} {now.year} года.", [], []
    if re.search(r"(подпис|caption)", q) and not re.search(r"(электрон|документ|подписк|подписат|подписал)", q):
        return "Вот вариант подписи: «" + _pick(CAPTIONS, q) + "». Попросите ещё раз — придумаю другую.", ["Ещё подпись"], [("/create", "Создать пост")]
    if re.search(r"(поздрав|пожелан)", q):
        return _pick(GREETINGS, q), ["Ещё поздравление"], []
    if re.search(r"(иде[яиюй]|о ч[её]м (написать|пост)|что (написать|выложить|запостить|опубликовать))", q):
        return "Идея для поста: " + random.choice(POST_IDEAS).lower() + ".", ["Ещё идея"], [("/create", "Написать пост")]
    return None


FOLLOWUP = re.compile(r"^(а|и|ну|а если|а как|а где|а можно|а что)\b|\b(это|этого|этим|его|ее|их|там|туда|тоже|так же|также|опять|снова)\b")


def answer(question, user=None, db=None, prev=""):
    """Ответ Нувы: {"text", "tips", "links": [{"url","title"}], "found"}."""
    own = db is None
    db = db or SessionLocal()
    try:
        KB.ensure(db)
        q, stems, layout = prepare(question)
        low = _norm(q).strip()
        note = f"(Похоже, текст набран в английской раскладке — я прочитала его как «{q}».)\n" if layout else ""
        if not low:
            return {"text": "Напишите вопрос — я постараюсь помочь.", "tips": DEFAULT_TIPS, "links": [], "found": True}
        st = _smalltalk(" ".join(lang.words(low)) if not re.search(r"[!?.]$", low) else low.rstrip("!?."), user)
        if st:
            return {"text": note + st[0], "tips": st[1], "links": [{"url": u, "title": t} for u, t in st[2]], "found": True}
        hits = KB.search(stems) if stems else []
        best = hits[0][0] if hits else 0
        if prev and (FOLLOWUP.search(low) or best < 3.0 or len(stems) <= 2):   # уточнение — добавляем прошлый вопрос
            _, pst, _ = prepare(prev)
            ctx = KB.search(list(dict.fromkeys(stems + pst))) if stems or pst else []
            related = FOLLOWUP.search(low) or set(stems) & (ctx[0][1]["head"] | ctx[0][1]["body"]) if ctx else False
            if ctx and ctx[0][0] > best * 1.2 and related:
                hits, best = ctx, ctx[0][0]
        if hits and best >= 2.6:
            e = hits[0][1]
            if e["aid"]:
                db.query(m.NuvaAnswer).filter_by(id=e["aid"]).update({"hits": m.NuvaAnswer.hits + 1})
                db.commit()
            more = [h[1]["title"] for h in hits[1:] if h[0] >= 2.6 and h[0] >= best * 0.5]
            links = [{"url": e["link"][0], "title": e["link"][1]}] if e["link"] else []
            title = "" if e["aid"] else e["title"] + "\n"
            return {"text": note + title + e["text"], "tips": more, "links": links, "found": True}
        record_miss(db, question)
        tips = [h[1]["title"] for h in hits if h[0] >= 1.2] or DEFAULT_TIPS[:3]
        return {"text": note + "Я пока не знаю ответа на этот вопрос — я простой помощник и отвечаю по справке. Я записала вопрос, "
                       "чтобы команда добавила ответ. А пока попробуйте спросить по-другому или напишите в поддержку.",
                "tips": tips[:3], "links": [{"url": "/support", "title": "Написать в поддержку"}], "found": False}
    finally:
        if own:
            db.close()


def _miss_key(question):
    return " ".join(lang.words(lang.squeeze(question)))[:200]


def record_miss(db, question):
    key = _miss_key(question)
    if len(key) < 3:
        return
    row = db.query(m.NuvaMiss).filter_by(key=key).first()
    if row:
        row.count, row.last_at = (row.count or 0) + 1, datetime.utcnow()
    else:
        db.add(m.NuvaMiss(key=key, question=question.strip()[:300]))
    db.commit()


# ---------------------------------------------------------------- исправить текст и хэштеги
FIX_TYPOS = {
    "севодня": "сегодня", "извени": "извини", "извените": "извините", "здраствуйте": "здравствуйте",
    "здраствуй": "здравствуй", "пожалуста": "пожалуйста", "пожалуйсто": "пожалуйста", "вообщем": "в общем",
    "впринципе": "в принципе", "незнаю": "не знаю", "немогу": "не могу", "нехочу": "не хочу", "тоесть": "то есть",
    "чтоли": "что ли", "кароче": "короче", "координально": "кардинально", "агенство": "агентство", "симпотичный": "симпатичный",
    "симпотичная": "симпатичная", "ихний": "их", "ихние": "их", "будующий": "будущий", "будующее": "будущее", "длинна": "длина", "ехай": "поезжай", "ложи": "клади", "щас": "сейчас", "щя": "сейчас", "чо": "что", "чё": "что", "оч": "очень", "спс": "спасибо", "пжл": "пожалуйста",
    "плиз": "пожалуйста", "седня": "сегодня", "ваще": "вообще", "щастье": "счастье", "интерестно": "интересно",
    "чуствую": "чувствую", "чуство": "чувство", "пачему": "почему", "патаму": "потому",
    "атличный": "отличный", "класно": "классно", "калоссально": "колоссально", "прийдти": "прийти", "придти": "прийти", "атлично": "отлично", "пагулять": "погулять", "превет": "привет", "привед": "привет",
}
HYPHEN = ["кто", "что", "где", "когда", "куда", "как", "какой", "какая", "какое", "какие", "почему", "зачем", "чей", "сколько"]
COMMA_BEFORE = ["а", "но", "чтобы", "потому что", "который", "которая", "которое", "которые", "поэтому", "однако", "зато"]


def _keep_case(src, repl):
    return repl[:1].upper() + repl[1:] if src[:1].isupper() else repl


def fix_text(text):
    t = text.replace("\r\n", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" +([,.!?;:)])", r"\1", t)                              # пробел перед знаком
    t = re.sub(r"([,;:])(?=[^\s\d)])", r"\1 ", t)                        # пробел после запятой
    t = re.sub(r"([.!?])(?=[А-ЯЁA-Z])", r"\1 ", t)                       # пробел после точки перед новой фразой
    t = re.sub(r"([!?])(?=[а-яё])", r"\1 ", t)
    t = re.sub(r"(?<=[а-яё]{3})\.(?=[а-яё]{2})", ". ", t)                 # «дела.пока» (но не «т.е.» и не ссылки)
    t = re.sub(r"\b([Нн])езнаю\b", r"\1е знаю", t)

    def word(mo):
        w = mo.group(0)
        low = w.lower().replace("ё", "е")
        return _keep_case(w, FIX_TYPOS[low]) if low in FIX_TYPOS else w
    t = re.sub(r"[А-Яа-яЁё]+", word, t)
    for w in HYPHEN:                                                     # кто то → кто-то, где нибудь → где-нибудь
        t = re.sub(rf"\b({w}) (то|либо|нибудь)\b", r"\1-\2", t, flags=re.I)
    t = re.sub(r"\b(из) (за|под)\b", r"\1-\2", t, flags=re.I)
    t = re.sub(r"\b(по) (моему|твоему|нашему|вашему|русски|английски|другому|прежнему|настоящему)\b", r"\1-\2", t, flags=re.I)
    t = re.sub(r"\b(вс[её]) (таки)\b", "всё-таки", t, flags=re.I)
    for w in COMMA_BEFORE:                                               # «…день но» → «…день, но»
        t = re.sub(rf"(?<=[а-яёa-z0-9]) ({w})\b", r", \1", t)
    t = re.sub(r",\s*,", ",", t)

    def cap(mo):
        return mo.group(1) + mo.group(2).upper()
    t = re.sub(r"(^|[.!?…]\s+|\n\s*)([а-яёa-z])", cap, t)               # заглавная в начале фразы
    lines = t.split("\n")
    if lines and lines[-1].strip() and re.search(r"[А-Яа-яЁёA-Za-z0-9]$", lines[-1].strip()) and len(lines[-1].split()) >= 3:
        lines[-1] = lines[-1].rstrip() + "."
    return "\n".join(lines).strip()


TOPICS = {
    "мор": ["море", "отпуск"], "пляж": ["пляж", "лето"], "закат": ["закат", "небо"], "рассвет": ["рассвет", "утро"],
    "кот": ["котики"], "кош": ["котики"], "собак": ["собака", "питомец"], "пес": ["собака"], "ед": ["еда"], "обед": ["еда"],
    "ужин": ["еда"], "кофе": ["кофе", "утро"], "спорт": ["спорт"], "трениров": ["спорт", "зож"], "бег": ["бег", "спорт"],
    "музык": ["музыка"], "песн": ["музыка"], "кино": ["кино"], "фильм": ["кино"], "сериал": ["сериалы"], "книг": ["книги"],
    "путешеств": ["путешествия"], "поездк": ["путешествия"], "учеб": ["учёба"], "школ": ["школа"], "универ": ["студенты"],
    "работ": ["работа"], "друз": ["друзья"], "природ": ["природа"], "лес": ["природа", "лес"], "гор": ["горы"],
    "фото": ["фото"], "город": ["город"], "прогулк": ["прогулка"], "погул": ["прогулка"], "парк": ["парк", "прогулка"],
    "снег": ["зима"], "зим": ["зима"], "лет": ["лето"], "осен": ["осень"], "весн": ["весна"], "праздник": ["праздник"],
    "рожден": ["деньрождения"], "игр": ["игры"], "код": ["программирование"], "рисун": ["творчество"], "рису": ["творчество"],
}


def hashtags(text):
    """До 5 хэштегов: сначала темы из словаря, потом самые частые длинные слова текста."""
    low = _norm(text)
    have = set(re.findall(r"#([\wа-я]+)", low))
    tags = []
    words = re.findall(r"[а-я]+", re.sub(r"#[\wа-я]+", " ", low))
    for w in words:
        for k, vals in TOPICS.items():
            if w.startswith(k):
                tags += [v for v in vals if v not in tags]
    freq = {}
    for w in words:
        if len(w) >= 6 and w not in STOP:
            freq[w] = freq.get(w, 0) + 1
    tags += [w for w, _ in sorted(freq.items(), key=lambda x: (-x[1], -len(x[0]))) if w not in tags]
    return [t for t in tags if t.replace("ё", "е") not in have][:5]


TYPOS.update(FIX_TYPOS)


# ---------------------------------------------------------------- маршруты
@router.get("/ai")
def ai_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    misses = db.query(m.NuvaMiss).count() if user and social.can_mod(user) else None
    return render(request, db, "packs/v3/ai.html", q=q[:300], misses=misses)


@router.post("/ai/chat")
async def ai_chat(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    question = s(data.get("question")).strip()[:2000]
    if not question:
        return json_error("Напишите вопрос")
    from . import gigachat
    from services import ratelimit
    if gigachat.enabled() and (user.is_owner or ratelimit.hit(f"giga:{user.id}", config.GIGACHAT_PER_HOUR, 3600)):
        hist = data.get("history")
        if isinstance(hist, str):
            try:
                hist = __import__("json").loads(hist)
            except ValueError:
                hist = []
        q, stems, _ = prepare(question)
        KB.ensure(db)
        hits = KB.search(stems, limit=4) if stems else []
        text = gigachat.chat(question, hist if isinstance(hist, list) else [], user, hits)
        if text:
            top = hits[0] if hits and hits[0][0] >= 3.5 else None
            links = [{"url": top[1]["link"][0], "title": top[1]["link"][1]}] if top and top[1]["link"] else []
            return JSONResponse({"ok": True, "text": text, "tips": [], "links": links, "found": True, "ai": True})
    res = answer(question[:500], user, db, prev=s(data.get("prev"))[:500])
    return JSONResponse({"ok": True, **res})


@router.post("/ai/rewrite")
async def ai_rewrite(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    text, mode = s(data.get("text"))[:5000], s(data.get("mode"))
    if len(text.strip()) < 3:
        return json_error("Сначала напишите текст")
    if mode == "fix":
        from . import gigachat
        out = gigachat.rewrite(text, "fix") or fix_text(text)
        return JSONResponse({"ok": True, "text": out, "same": out == text.strip()})
    if mode == "tags":
        tags = hashtags(text)
        if not tags:
            return json_error("Не получилось подобрать хэштеги — допишите текст подробнее")
        return JSONResponse({"ok": True, "text": text.rstrip() + "\n\n" + " ".join("#" + t for t in tags), "same": False})
    return json_error("Неизвестное действие")


# ---------------------------------------------------------------- админка: вопросы без ответа и свои ответы
def _mod(request, db):
    user = current_user(request, db)
    return user if user and social.can_mod(user) else None


@router.get("/ai/admin")
def ai_admin(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    if not social.can_mod(user):
        return render(request, db, "error.html", status_code=403, code=403, title="Нет доступа", text="Раздел для модераторов.")
    misses = db.query(m.NuvaMiss).order_by(m.NuvaMiss.count.desc(), m.NuvaMiss.last_at.desc()).limit(100).all()
    answers = db.query(m.NuvaAnswer).order_by(m.NuvaAnswer.updated_at.desc()).all()
    return render(request, db, "packs/v3/nuva_admin.html", misses=misses, answers=answers)


def _safe_link(url):
    url = s(url).strip()[:300]
    if not url:
        return ""
    if url.startswith("/") and not url.startswith("//"):
        return url
    return url if re.match(r"^https?://[^\s/]+\.[^\s]+$", url) else None


@router.post("/ai/admin/answer")
async def ai_admin_save(request: Request, db: Session = Depends(get_db)):
    user = _mod(request, db)
    if not user:
        return json_error("Нет доступа", 403)
    data = await read_payload(request)
    question, text = s(data.get("question")).strip()[:200], s(data.get("answer")).strip()[:3000]
    if len(question) < 3 or len(text) < 3:
        return json_error("Нужны вопрос и ответ")
    link = _safe_link(data.get("link_url"))
    if link is None:
        return json_error("Ссылка должна начинаться с / или https://")
    aid = s(data.get("id"))
    row = db.query(m.NuvaAnswer).filter_by(id=int(aid)).first() if aid.isdigit() and len(aid) < 10 else None
    if not row:
        row = m.NuvaAnswer(created_by=user.id)
        db.add(row)
    row.question, row.answer, row.keywords = question, text, s(data.get("keywords")).strip()[:300]
    row.link_url, row.link_title, row.updated_at = link, s(data.get("link_title")).strip()[:60], datetime.utcnow()
    db.commit()
    KB.checked = 0
    KB.ensure(db)
    solved = 0
    for miss in db.query(m.NuvaMiss).all():  # вопросы, на которые теперь есть ответ, убираем из списка
        _, stems, _ = prepare(miss.question)
        hits = KB.search(stems) if stems else []
        if hits and hits[0][0] >= 2.6:
            db.delete(miss)
            solved += 1
    miss_id = s(data.get("miss_id"))
    if miss_id.isdigit():
        db.query(m.NuvaMiss).filter_by(id=int(miss_id)).delete()
    db.commit()
    return JSONResponse({"ok": True, "id": row.id, "solved": solved})


@router.post("/ai/admin/answer/{aid}/delete")
def ai_admin_delete(aid: int, request: Request, db: Session = Depends(get_db)):
    if not _mod(request, db):
        return json_error("Нет доступа", 403)
    db.query(m.NuvaAnswer).filter_by(id=aid).delete()
    db.commit()
    KB.checked = 0
    return JSONResponse({"ok": True})


@router.post("/ai/admin/miss/{mid}/delete")
def ai_admin_miss_delete(mid: int, request: Request, db: Session = Depends(get_db)):
    if not _mod(request, db):
        return json_error("Нет доступа", 403)
    db.query(m.NuvaMiss).filter_by(id=mid).delete()
    db.commit()
    return JSONResponse({"ok": True})
