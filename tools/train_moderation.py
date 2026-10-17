"""Обучение собственной модели токсичности Nuvora.

Данные: RUSSE Detox 2022 (s-nlp/russe_detox_2022) — токсичные русские комментарии и их вежливые
перефразы, написанные людьми. Перефразы — идеальные «трудные» негативы: тема та же, грубости нет,
поэтому модель учится находить именно оскорбления и мат, а не тему разговора.

Запуск (нужны numpy и scipy только для обучения, сайту они не нужны):
    python tools/train_moderation.py data/train.tsv data/dev.tsv
Результат: ml/toxicity_ru.bin
"""
import csv
import math
import os
import sys

import numpy as np
from scipy import sparse
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import moderation as M  # noqa: E402

# Обычные посты соцсети, в том числе с безобидными «блин», «капец», «офигенно» — чтобы модель не придиралась.
BENIGN = """Привет всем! Как прошли выходные?
Сегодня наконец-то выпал снег, красота
Блин, опять проспал будильник
Капец как жарко сегодня
Это просто офигенно, спасибо!
Чёрт, забыл зонтик дома
Кто идёт вечером на набережную?
Мой стрик уже 30 дней 🔥
Скачал приложение — летает
Сторис с утренней пробежки
Вкусный кофе в новой кофейне на углу
Поздравляю с днём рождения! Счастья и здоровья
Ну ты даёшь, вот это поворот
Офигеть, какой закат сегодня
Ребята, посоветуйте хороший фильм на вечер
Сдал экзамен на отлично, ура!
Купил новые кроссовки, очень удобные
Котик опять уронил цветок со стола 😂
Жесть, сколько снега навалило
Ну и погодка, конечно
Обожаю эту песню, слушаю на повторе
Хочу в отпуск, хоть на недельку
Мама испекла пирог, это лучший день
Спасибо всем за поздравления!
Какой ужас, пробки по всему городу
Это было эпично, давайте повторим
Не могу перестать смеяться с этого видео
Блин, ну почему понедельник так быстро наступает
Сделал себе тёмную тему, теперь глаза не устают
Кто-нибудь играл в новую игру? Стоит покупать?
Дурацкий будильник опять не сработал
Я в шоке, как быстро пролетело лето
Давай созвонимся вечером
Отличная идея, поддерживаю
Глупая ошибка, но я её исправил
Устал как собака, но доволен
Этот сериал просто бомба
Тренировка была адская, но я справился
Ура, пятница!
Наша команда выиграла матч!
Сегодня готовлю борщ по бабушкиному рецепту
Посмотрите, какой у меня получился рисунок
Подскажите, где в Казани вкусная шаурма?
Обновил аватарку, как вам?
Дождь весь день, сижу дома с книжкой
Всем доброе утро!
Спокойной ночи, друзья
Фух, наконец-то закончил проект
Кошмар, опять сломался ноутбук
Смешно до слёз
Вот это я понимаю сервис!
Ничего себе, сколько лайков
Я тупанул и сел не на тот автобус 😅
Он реально крутой музыкант
Убийственно смешной мем
Это бесит, когда интернет пропадает
Сегодня был сложный день, но я держусь
Кто со мной на концерт в субботу?
Классная фотка!
Согласен с тобой на все сто
Как дела у всех? Что нового?
Красивое платье, тебе очень идёт
Пробежал свои первые 10 километров
Это был худший фильм, что я видел, очень скучно
Не согласен, но уважаю твоё мнение
Политика меня утомила, давайте о котиках
Прочитал отличную книгу, рекомендую
Обалдеть, вот это новости
Тот самый момент, когда всё получилось
Ужасно хочу спать
Чёрный юмор не для всех
Я дико рад тебя видеть
Психанул и перекрасил стены в комнате
Этот уровень в игре просто убивает
Офигенный вид с крыши
Да ладно, не может быть!
Сосед опять сверлит с утра, ну сколько можно
Сегодня день рождения у моего пса!""".splitlines()


def read_tsv(path):
    pos, neg = [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("toxic_comment"):
                pos.append(row["toxic_comment"])
            for k in ("neutral_comment1", "neutral_comment2", "neutral_comment3"):
                if row.get(k):
                    neg.append(row[k])
    return pos, neg


def build(texts, vocab, grow):
    rows, cols = [], []
    for i, t in enumerate(texts):
        hs = {M.fhash(f) for f in M.features(t)}
        for h in hs:
            j = vocab.get(h)
            if j is None and grow:
                j = vocab[h] = len(vocab)
            if j is not None:
                rows.append(i)
                cols.append(j)
    X = sparse.csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(len(texts), len(vocab)))
    # нормировка как в M.toxicity: сумма весов делится на sqrt(числа признаков текста)
    n = np.array([max(1, len({M.fhash(f) for f in M.features(t)})) for t in texts], dtype=np.float32)
    return sparse.diags(1 / np.sqrt(n)) @ X


def train(X, y, sw, l2):
    d = X.shape[1]

    def loss(wb):
        w, b = wb[:d], wb[d]
        z = X @ w + b
        p = 1 / (1 + np.exp(-z))
        ll = sw * (np.logaddexp(0, z) - y * z)
        g = sw * (p - y)
        return ll.sum() + 0.5 * l2 * w @ w, np.concatenate([X.T @ g + l2 * w, [g.sum()]])

    res = minimize(loss, np.zeros(d + 1), jac=True, method="L-BFGS-B", options={"maxiter": 400})
    return res.x[:d], res.x[d]


def auc(y, s):
    o = np.argsort(s)
    r = np.empty(len(s))
    r[o] = np.arange(1, len(s) + 1)
    npos = y.sum()
    return (r[y == 1].sum() - npos * (npos + 1) / 2) / (npos * (len(y) - npos))


def report(y, s, name):
    print(f"{name}: AUC={auc(y, s):.4f}")
    for th in (0.5, 0.7, 0.85, 0.93):
        pred = s >= th
        tp, fp, fn = (pred & (y == 1)).sum(), (pred & (y == 0)).sum(), (~pred & (y == 1)).sum()
        print(f"  порог {th:.2f}: точность {tp / max(1, tp + fp):.3f}  полнота {tp / max(1, tp + fn):.3f}  "
              f"ложных срабатываний {fp / max(1, (y == 0).sum()):.3%}")


def main(train_path, dev_path, out=M.MODEL_PATH, keep=60000, l2=0.1):
    tp, tn = read_tsv(train_path)
    dp, dn = read_tsv(dev_path)
    tn += BENIGN * 3
    texts, y = tp + tn, np.array([1] * len(tp) + [0] * len(tn), dtype=np.float64)
    sw = np.where(y == 1, len(tn) / len(tp), 1.0)
    print(f"обучение: {len(tp)} токсичных, {len(tn)} нормальных")
    vocab = {}
    X = build(texts, vocab, True)
    print(f"признаков: {len(vocab)}")
    w, b = train(X, y, sw, l2)

    # оставляем самые важные признаки — модель становится крошечной почти без потери качества
    order = np.argsort(-np.abs(w))[:keep]
    inv = {j: h for h, j in vocab.items()}
    weights = {inv[j]: float(w[j]) for j in order if abs(w[j]) > 1e-4}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    M.save_model(out, float(b), weights)
    print(f"сохранено {len(weights)} признаков → {out} ({os.path.getsize(out) / 1024:.0f} КБ)")

    M._model = M.load_model(out)
    ys = np.array([1] * len(dp) + [0] * len(dn))
    s = np.array([M.toxicity(t) for t in dp + dn])
    report(ys, s, "проверка на отложенных данных (dev)")
    b2 = np.array([M.toxicity(t) for t in BENIGN])
    print(f"обычные посты: средняя оценка {b2.mean():.3f}, максимум {b2.max():.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
