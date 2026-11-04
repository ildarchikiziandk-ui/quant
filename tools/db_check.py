"""Проверить и подготовить базу SQLite из файловой копии (например, бэкапа Beget).
Копия снималась с работающего сервера, поэтому:
  1) рядом с quant.db может лежать quant.db-wal — свежие записи, ещё не перенесённые в основной файл;
     их надо «влить» в базу, иначе пропадут последние часы/дни;
  2) файл мог скопироваться «на ходу» и повредиться — проверяем и, если нужно, спасаем всё, что читается.
Запуск: python tools/db_check.py /root/old/quant.db      (база правится на месте, оригинал — в .orig)
Выход: 0 — база в порядке (или спасена), 1 — открыть не удалось."""
import os
import shutil
import sqlite3
import subprocess
import sys


def check(path):
    con = sqlite3.connect(path)
    try:
        res = con.execute("PRAGMA integrity_check").fetchall()
        return [r[0] for r in res]
    finally:
        con.close()


def main(path):
    if not os.path.exists(path):
        print(f"нет файла {path}")
        return 1
    orig = path + ".orig"
    if not os.path.exists(orig):
        shutil.copy2(path, orig)
        for ext in ("-wal", "-shm"):
            if os.path.exists(path + ext):
                shutil.copy2(path + ext, orig + ext)
    if os.path.exists(path + "-wal"):
        print(f"   нашёл {os.path.basename(path)}-wal — вливаю свежие записи в базу")
    try:
        con = sqlite3.connect(path)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("PRAGMA journal_mode=DELETE")
        con.close()
    except sqlite3.DatabaseError as e:
        print(f"   не удалось влить журнал: {e}")
    try:
        res = check(path)
    except sqlite3.DatabaseError as e:
        res = [str(e)]
    if res == ["ok"]:
        print(f"   {os.path.basename(path)}: база в порядке")
        return 0
    print(f"   {os.path.basename(path)}: есть повреждения ({'; '.join(res[:3])}) — спасаю всё, что читается")
    fixed = path + ".recovered"
    if os.path.exists(fixed):
        os.remove(fixed)
    ok = False
    if shutil.which("sqlite3"):
        dump = subprocess.run(["sqlite3", path, ".recover"], capture_output=True, text=True)
        if dump.stdout:
            subprocess.run(["sqlite3", fixed], input=dump.stdout, text=True, capture_output=True)
            ok = os.path.exists(fixed)
    if not ok:  # без sqlite3 — построчная выгрузка тем, что читается
        try:
            src, dst = sqlite3.connect(path), sqlite3.connect(fixed)
            for line in src.iterdump():
                try:
                    dst.execute(line)
                except sqlite3.DatabaseError:
                    pass
            dst.commit()
            dst.close()
            src.close()
            ok = True
        except sqlite3.DatabaseError as e:
            print(f"   спасти не получилось: {e}")
            return 1
    try:
        res = check(fixed)
    except sqlite3.DatabaseError as e:
        print(f"   спасённая база тоже не открывается: {e}")
        return 1
    os.replace(fixed, path)
    print(f"   спасено ({res[0]}); оригинал лежит в {orig}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) > 1 else print(__doc__) or 1)
