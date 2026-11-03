"""Объединение баз после переезда: старая база (из копии Beget) + новая (что люди успели сделать на новом сервере).

Запуск (обычно через deploy/merge.sh):
  python tools/merge_db.py СТАРАЯ.db НОВАЯ.db ИТОГ.db СТАРЫЙ.env НОВЫЙ.env

Как объединяется:
- основа — старая база: все прежние аккаунты, посты и переписки остаются как были;
- из новой базы добавляется всё, чего в старой нет: новые люди, посты, комментарии, лайки, сообщения, подписки…
  У всех записей новые номера, ссылки между ними (кто автор, к какому посту комментарий) пересчитываются;
- один и тот же человек (совпали и логин, и email) — это один аккаунт: его новые посты попадают в старый аккаунт;
- логин занят старым аккаунтом, а email другой — это другой человек: ему выдаётся временный логин userNNNN,
  входить он может по-прежнему (свой прежний логин + свой пароль), на сайте он видит плашку «выдан временный логин»;
- сообщения в новой базе зашифрованы новым ключом — перешифровываются старым ключом (из старого .env),
  потому что после объединения сайт работает со старым ключом;
- справочники (достижения, задания, наборы стикеров, официальное сообщество) не дублируются.
"""
import base64
import os
import random
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ссылки на другие таблицы без ForeignKey в моделях: колонка → таблица
SOFT = {
    "user_id": "users", "peer_id": "users", "owner_id": "users", "target_id": "users", "author_id": "users",
    "viewer_id": "users", "a_id": "users", "b_id": "users", "sender_id": "users", "to_id": "users",
    "wall_owner_id": "users", "post_id": "posts", "repost_id": "posts", "pinned_post_id": "posts",
    "pinned_comment_id": "comments", "community_id": "v3_communities", "group_id": "group_chats",
    "call_id": "v3_calls", "notif_id": "notifications", "collection_id": "bookmark_collections",
    "correct_option_id": "poll_options", "chat_id": "secret_chats",
}
SKIP = {"user_sessions", "verification_codes", "typing_status", "v3_call_signals", "v3_seen_devices", "trends", "v3_login_approvals"}
NATURAL = {  # справочники: такая же запись в старой базе — значит, это она и есть
    "achievements": ["code"], "daily_tasks": ["code"], "sticker_packs": ["name"], "stickers": ["pack_id", "name"],
    "weekly_challenges": ["title", "week_start"], "v3_nuva_misses": ["key"],
    "promocodes": ["code"], "stop_words": ["word"], "announcements": ["text"],
}


def read_env(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def msg_cipher(env):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    raw = env.get("MESSAGE_KEY", "").strip()
    key = base64.b64decode(raw) if raw else HKDF(algorithm=hashes.SHA256(), length=32, salt=b"nuvora-messages-v1",
                                                 info=b"message-encryption").derive(env.get("SECRET_KEY", "").encode())
    return AESGCM(key)


def recrypt(value, old_c, new_c):
    if not value or not str(value).startswith("enc1:"):
        return value
    data = base64.b64decode(str(value)[5:])
    try:
        text = new_c.decrypt(data[:12], data[12:], b"nuvora-msg")
    except Exception:  # noqa: BLE001 — не расшифровалось новым ключом (уже старым?) — оставляем
        return value
    nonce = os.urandom(12)
    return "enc1:" + base64.b64encode(nonce + old_c.encrypt(nonce, text, b"nuvora-msg")).decode("ascii")


def upgrade_schema(path, old_env):
    """Старая база могла быть без новых колонок и таблиц — добавляем их тем же кодом, что и при запуске сайта.
    Ключи — из старого .env: после объединения сайт работает с ними."""
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    for k in ("SECRET_KEY", "MESSAGE_KEY"):
        os.environ[k] = old_env.get(k, "")  # пустое значение, а не отсутствие: иначе подхватится ключ из нового .env
    import models  # noqa: F401
    import packs.v3  # noqa: F401  таблицы пакета
    import migrations
    migrations.run()


def merge(old_db, new_db, out_db, old_env, new_env, log=print):
    shutil.copyfile(old_db, out_db)
    upgrade_schema(out_db, read_env(old_env))
    from database import Base
    import models  # noqa: F401
    from packs.v3 import models as _m  # noqa: F401
    import packs.v3  # noqa: F401  все модели пакета
    old_c, new_c = msg_cipher(read_env(old_env)), msg_cipher(read_env(new_env))
    src, dst = sqlite3.connect(new_db), sqlite3.connect(out_db)
    src.row_factory = sqlite3.Row
    idmap = {}          # таблица → {id в новой базе: id в итоговой}
    later = []          # (таблица, id в итоге, колонка, старое значение, целевая таблица) — ссылки на ещё не перенесённое
    stats = {}
    renamed = []
    has_owner = dst.execute("SELECT 1 FROM users WHERE is_owner=1").fetchone() is not None
    enc_cols = {(t.name, c.name) for t in Base.metadata.sorted_tables for c in t.columns if type(c.type).__name__ == "EncryptedText"}

    def cols(con, table):
        return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]

    for t in Base.metadata.sorted_tables:
        name = t.name
        if name in SKIP:
            continue
        try:
            scols = cols(src, name)
        except sqlite3.Error:
            continue
        dcols = cols(dst, name)
        if not scols or not dcols:
            continue
        common = [c for c in scols if c in dcols]
        pk = [c.name for c in t.primary_key.columns]
        fks = {}
        for c in t.columns:
            for fk in c.foreign_keys:
                fks[c.name] = fk.column.table.name
        if name == "v3_site_settings":  # настройки сайта: старые главнее, новые ключи (например, расписание транспорта) добавляем
            for r in src.execute("SELECT * FROM v3_site_settings"):
                dst.execute("INSERT OR IGNORE INTO v3_site_settings (key, value) VALUES (?, ?)", (r["key"], r["value"]))
            continue
        idmap.setdefault(name, {})
        # таблицы-связи (подписки, лайки, блокировки…): строка — это только ссылки, такая же связь не дублируется
        rest = [c for c in common if c != "id" and not c.endswith("_at") and c not in ("date",)]
        dedupe = rest if pk == ["id"] and len(rest) >= 2 and all(c in fks or c in SOFT for c in rest) else []
        n_in = 0
        for r in src.execute(f'SELECT * FROM "{name}" ORDER BY 1'):
            row = {c: r[c] for c in common}
            skip = False
            # ссылки с ForeignKey
            for c, target in fks.items():
                if c in row and row[c] is not None:
                    mapped = idmap.get(target, {}).get(row[c])
                    if mapped is None:
                        nullable = t.columns[c].nullable
                        if nullable:
                            row[c] = None
                        else:
                            skip = True
                    else:
                        row[c] = mapped
            if skip:
                continue
            # ссылки без ForeignKey
            soft_later = []
            for c in list(row):
                target = SOFT.get(c)
                if c in fks or not target or row[c] is None or not isinstance(row[c], int):
                    continue
                if name == "moderation_flags" and c == "object_id":
                    continue
                if target in idmap and (target != name):
                    row[c] = idmap[target].get(row[c])
                else:
                    soft_later.append((c, row[c], target))
                    row[c] = None
            if name == "moderation_flags" and row.get("object_id") is not None:
                target = "comments" if (r["kind"] if "kind" in r.keys() else "") == "comment" else "posts"
                row["object_id"] = idmap.get(target, {}).get(row["object_id"])
            for (tn, c) in enc_cols:
                if tn == name and row.get(c):
                    row[c] = recrypt(row[c], old_c, new_c)
            old_id = row.get("id") if pk == ["id"] else None
            # справочники и один и тот же человек — не дублируем
            if name in NATURAL:
                keys = NATURAL[name]
                q = " AND ".join(f'"{k}" IS ?' for k in keys)
                hit = dst.execute(f'SELECT id FROM "{name}" WHERE {q}', [row.get(k) for k in keys]).fetchone()
                if hit:
                    idmap[name][old_id] = hit[0]
                    continue
            if name == "weekly_raffles":  # розыгрыш недели — один на неделю: берём тот, что уже идёт в старой базе
                hit = dst.execute("SELECT id FROM weekly_raffles WHERE week_end > ? AND week_start < ?", (row.get("week_start"), row.get("week_end"))).fetchone()
                if hit:
                    idmap[name][old_id] = hit[0]
                    continue
            if name == "v3_communities":
                hit = dst.execute("SELECT id, is_official FROM v3_communities WHERE slug=?", (row.get("slug"),)).fetchone()
                if hit and (hit[1] or row.get("is_official")):
                    idmap[name][old_id] = hit[0]
                    continue
                if hit:
                    row["slug"] = f'{row["slug"]}-{random.randint(100, 999)}'
            if name == "users":
                un, em = (row.get("username") or ""), (row.get("email") or "")
                same = dst.execute("SELECT id FROM users WHERE lower(username)=lower(?) AND lower(email)=lower(?)", (un, em)).fetchone()
                if same:
                    idmap[name][old_id] = same[0]
                    continue
                if dst.execute("SELECT 1 FROM users WHERE lower(username)=lower(?)", (un,)).fetchone():
                    while True:
                        temp = f"user{random.randint(1000, 99999)}"
                        if not dst.execute("SELECT 1 FROM users WHERE lower(username)=?", (temp,)).fetchone():
                            break
                    row["username"], row["previous_username"], row["rename_notice"] = temp, un.lower(), 1
                    renamed.append((un, temp))
                if em and dst.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)", (em,)).fetchone():
                    local, _, dom = em.partition("@")
                    row["email"] = f"{local}+new{old_id}@{dom}"
                if row.get("yandex_id") and dst.execute("SELECT 1 FROM users WHERE yandex_id=?", (row["yandex_id"],)).fetchone():
                    row["yandex_id"] = None
                if has_owner:  # основатель — из старой базы
                    row["is_owner"], row["co_owner"] = 0, 0
            if name == "v3_user_aliases" and dst.execute("SELECT 1 FROM v3_user_aliases WHERE handle=?", (row.get("handle"),)).fetchone():
                continue
            if dedupe and dst.execute(f'SELECT 1 FROM "{name}" WHERE ' + " AND ".join(f'"{k}" IS ?' for k in dedupe),
                                      [row.get(k) for k in dedupe]).fetchone():
                continue  # такая связь уже есть (подписка, лайк, участие в группе…)
            if pk == ["id"]:
                row.pop("id", None)
            fields = list(row)
            sql = f'INSERT {"OR IGNORE " if pk != ["id"] else ""}INTO "{name}" ({",".join(chr(34) + f + chr(34) for f in fields)}) VALUES ({",".join("?" * len(fields))})'
            try:
                cur = dst.execute(sql, [row[f] for f in fields])
            except sqlite3.IntegrityError:
                continue
            if pk == ["id"]:
                idmap[name][old_id] = cur.lastrowid
                for c, val, target in soft_later:
                    later.append((name, cur.lastrowid, c, val, target))
            n_in += 1
        stats[name] = n_in
    for name, rid, c, val, target in later:  # ссылки на то, что перенесли позже (например, закреплённый пост)
        mapped = idmap.get(target, {}).get(val)
        if mapped is not None:
            dst.execute(f'UPDATE "{name}" SET "{c}"=? WHERE id=?', (mapped, rid))
    # «один и тот же человек»: его закреплённый пост в старом аккаунте не трогаем
    dst.commit()
    dst.close()
    src.close()
    added = {k: v for k, v in stats.items() if v}
    log("Перенесено из новой базы: " + ", ".join(f"{k} {v}" for k, v in sorted(added.items())) if added else "Из новой базы переносить нечего")
    for un, temp in renamed:
        log(f"  логин @{un} занят старым аккаунтом — новому человеку выдан @{temp}")
    return {"stats": stats, "renamed": renamed}


if __name__ == "__main__":
    if len(sys.argv) != 6:
        print(__doc__)
        sys.exit(1)
    merge(*sys.argv[1:6])
    print("Готово:", sys.argv[3])
