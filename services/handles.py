"""Красивые логины Nuvora.

ELITE — самые лучшие: пока не выдаются никому (их может занять только владелец или администратор).
PREMIUM — очень красивые: продаются за баллы в «Магазине логинов» (/handles).
Логины, которые уже кто-то занял до появления списков, остаются у своих владельцев.
"""

ELITE = set("""
love star king queen angel legend alpha omega dream life sun moon sky boss art music money gold diamond world cosmos space
fire ice wolf lion tiger dragon phoenix zeus apollo aurora nova luna sol vip top best god russia moscow piter kazan
nuvora whale rubl ildar mint hello yes one zero infinity universe galaxy heaven paradise genius prince princess
""".split())

_TIERS = {
    # три буквы — самые короткие и звучные
    3000: "fox cat owl bee ray joy sea zen max leo mia eva ivy kai neo ace jet rio ash elf orb gem oak elk".split(),
    # короткие слова и имена
    2000: """lucky smile soul vibe mood ruby jade rose lily mint kiwi lava wave hero ninja pixel neon echo
    nika lisa kate alex anna olga dima ivan misha sasha vika sonya mark nick lena yana roma oleg ilya liza masha
    tima artem egor gleb kira mila nina vera""".split(),
    # красивые слова
    1200: """happy sunny magic heart cherry honey sugar coffee cookie panda kitty bunny sweet storm thunder shadow ghost
    night light crystal pearl silver amber violet lemon mango peach berry melon ocean river comet rocket planet
    orbit lunar solar stellar velvet sakura lotus maple cedar arctic polar frost blaze ember spark flash
    pilot ranger knight wizard samurai viking hunter""".split(),
    # имена и прочее красивое
    800: """maria daria polina alina sofia anastasia ekaterina victoria natalia tatiana svetlana irina valeria
    nikita andrey sergey dmitry alexey maxim pavel denis kirill anton vlad stas danil arsen timur ruslan
    bestie friend family dreamer artist singer dancer gamer coder writer traveler""".split(),
}
PREMIUM = {}
for _price, _names in _TIERS.items():
    for _n in _names:
        _n = _n.lower()
        if _n not in ELITE and _n not in PREMIUM:
            PREMIUM[_n] = _price


MAX_ALIASES = 2  # дополнительные логины: всего у человека до трёх


def owner_of(db, name):
    """Кто владеет логином: основным или дополнительным. None — логин свободен."""
    import models
    from sqlalchemy import func
    from packs.v3 import models as pm
    low = (name or "").lower().lstrip("@")
    u = db.query(models.User).filter(func.lower(models.User.username) == low).first()
    if u:
        return u
    a = db.query(pm.UserAlias).filter_by(handle=low).first()
    return db.get(models.User, a.user_id) if a else None


def is_staff(user):
    return bool(user and (getattr(user, "is_owner", False) or getattr(user, "is_admin", False)))


def check(name, user=None):
    """Можно ли занять логин обычным способом (регистрация, смена в настройках)."""
    low = (name or "").lower()
    if is_staff(user):
        return None
    if low in ELITE:
        return "Этот логин зарезервирован Nuvora"
    if low in PREMIUM:
        return f"@{low} — красивый логин, его можно купить за {PREMIUM[low]} баллов в «Магазине логинов» (Меню → Красивые логины)"
    return None
