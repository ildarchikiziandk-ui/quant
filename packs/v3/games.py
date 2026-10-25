"""Игры 3.0: «Словечко» (слово дня из 5 букв за 6 попыток) и 2048 с таблицей рекордов."""
import json
import zlib
from datetime import datetime

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, render
from routers.posts import read_payload
from services import gamification, social

from . import models as m
from .common import router, s, today

# Слова дня: обычные существительные из 5 букв (без «ё» — её приравниваем к «е»)
WORDS = """абзац аванс автор акула алмаз альбом ангел арбуз арена атлас афиша багаж бакен балет банан баран барин бархат башня
бегун белка берег бетон билет бизон блеск блюдо бочка бревно бровь брюки бублик буква булка бурав бутон быстро вагон
вафля ведро веник верба весна ветер вечер вилка винт вишня влага вожак вокал волна ворон вывод гамак гараж гвоздь гений
гитара глина globe голос город горох грант гроза груша гусар дверь девиз демон дождь доска дрова дубок дудка дятел
жабра жезл жилет жираф жетон завод загар закат замок запах заяц звезда зебра зелье земля зерно зефир знамя зонтик
игрок икона иголка индюк искра кабан какао камин канал капля карта каток кафель квест кефир кисть класс клоун ключ книга
кобра козёл койка кокос колос комар компас конус копьё кора корма короб космос кость котёл кофта кошка краб кран кровь
крона крыло кубик кукла купол кусок лагерь лампа лапша ласка лебедь лента лесок лиана лидер лимон линза лиса лодка ложка
локон лосось лотос лужа лунка лыжи магия майка манго марка маска масло мачта медаль метро мешок минус мираж модем молот
море мороз мотор мусор мысль мышка навык налог номер норка носок нота обида облако образ океан окрас опера орган оскал
отдых отзыв охота очерк пальма папка парус пасть пауза пачка пенал пепел перец песня петля пилот пирог пицца плащ пляж
повар поезд пояс приз проза птица пудра пульт пупок пушка пьеса радар радио разум ракета рамка рация ребус речка рикша
ринг рожок ролик роман роса рубин рукав рынок рысак рюкзак салат сапог сахар свеча север секта семья сено сетка сироп
скала сказ скрип слива слово сокол сосна спорт стакан стена стиль стол страх струя судно сумка сфера сцена табак талант
танец тапок тарел театр текст тепло тесто тигр толпа топор торт трава тренд труба туман тыква уголь узник улица успех
утюг факел фасад ферма фильм флаг форма фраза фрукт халат хвост хлеб холод хомяк хорда хребет цапля цветок цирк чайка
чашка шапка шарик шахта шифр шишка шкаф школа шорты шторм штрих шутка щенок экран эскиз юрист якорь ягода яхта""".split()
WORDS = sorted({w.replace("ё", "е") for w in WORDS if len(w) == 5 and all("а" <= ch <= "я" for ch in w.replace("ё", "е"))})


def word_of(day):
    return WORDS[zlib.crc32(("nuvora-word-" + day).encode()) % len(WORDS)]


def score(guess, answer):
    """Цвета букв как в Wordle: g — на месте, y — есть в слове, n — нет (повторы учитываются честно)."""
    res, left = ["n"] * 5, {}
    for i, (g, a) in enumerate(zip(guess, answer)):
        if g == a:
            res[i] = "g"
        else:
            left[a] = left.get(a, 0) + 1
    for i, g in enumerate(guess):
        if res[i] != "g" and left.get(g):
            res[i], left[g] = "y", left[g] - 1
    return "".join(res)


def _state(row, answer):
    guesses = json.loads(row.guesses or "[]") if row else []
    rows = [{"word": g, "score": score(g, answer)} for g in guesses]
    over = bool(row and (row.solved or len(guesses) >= 6))
    return {"rows": rows, "solved": bool(row and row.solved), "over": over, "answer": answer if over else None}


@router.get("/games")
def games(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    best = db.get(m.Score2048, user.id)
    played = db.query(m.WordGame).filter_by(user_id=user.id, day=today(user)).first()
    return render(request, db, "packs/v3/games.html", best2048=best.best if best else 0, word_done=bool(played and (played.solved or len(json.loads(played.guesses)) >= 6)))


@router.get("/games/word")
def word_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    t = today(user)
    row = db.query(m.WordGame).filter_by(user_id=user.id, day=t).first()
    wins = db.query(m.WordGame).filter_by(user_id=user.id, solved=True).count()
    played = db.query(m.WordGame).filter_by(user_id=user.id).count()
    return render(request, db, "packs/v3/word.html", state=_state(row, word_of(t)), day=t, wins=wins, played=played)


@router.post("/games/word/guess")
async def word_guess(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    g = s(data.get("word")).strip().lower().replace("ё", "е")
    if len(g) != 5 or not all("а" <= ch <= "я" for ch in g):
        return json_error("Нужно слово из 5 русских букв")
    t = today(user)
    answer = word_of(t)
    row = db.query(m.WordGame).filter_by(user_id=user.id, day=t).first()
    if not row:
        row = m.WordGame(user_id=user.id, day=t, guesses="[]")
        db.add(row)
    guesses = json.loads(row.guesses or "[]")
    if row.solved or len(guesses) >= 6:
        return json_error("Сегодняшнее слово уже сыграно — новое завтра")
    guesses.append(g)
    row.guesses = json.dumps(guesses, ensure_ascii=False)
    if g == answer:
        row.solved = True
        gamification.add_points(user, db, 5 + (6 - len(guesses)))  # раз в день: слово дня одно
    db.commit()
    return JSONResponse({"ok": True, **_state(row, answer)})


# ---------------------------------------------------------------- 2048
@router.get("/games/2048")
def g2048(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    best = db.get(m.Score2048, user.id)
    ids = social.following_ids(db, user) | {user.id}
    top = (db.query(m.Score2048, models.User).join(models.User, models.User.id == m.Score2048.user_id)
           .filter(m.Score2048.user_id.in_(ids)).order_by(m.Score2048.best.desc()).limit(10).all())
    return render(request, db, "packs/v3/g2048.html", best=best.best if best else 0, top=top)


@router.post("/games/2048/score")
async def g2048_score(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    sc = s(data.get("score"))
    if not sc.isdigit() or len(sc) > 7:
        return json_error("Неверный счёт")
    sc = int(sc)
    row = db.get(m.Score2048, user.id)
    if not row:
        row = m.Score2048(user_id=user.id, best=0)
        db.add(row)
    new = sc > (row.best or 0)
    if new:
        row.best, row.updated_at = sc, datetime.utcnow()
    db.commit()
    return JSONResponse({"ok": True, "best": row.best, "record": new})
