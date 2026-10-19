"""Версия статики: хэш содержимого стилей и скриптов.

Одна и та же версия на сервере и в приложении для Android: приложение везёт эти файлы внутри APK
и отдаёт их мгновенно (и без сети), но только пока версия совпадает с серверной — после обновления
сайта приложение само берёт свежие файлы из сети. Модуль без зависимостей: его подключает и сборщик APK.
"""
import hashlib
import os

VERSIONED = ("css", "js", "packs")          # файлы с ?v=версия — встраиваются, пока версия совпадает
STABLE = ("emoji", "gifts", "wallpapers", "brand")  # картинки без версии — меняются редко, встраиваются всегда
STABLE_FILES = ("favicon.png", "icon-192.png", "icon-512.png", "logo.svg")


def versioned_files(static_dir):
    out = []
    for top in VERSIONED:
        base = os.path.join(static_dir, top)
        for root, _, files in os.walk(base):
            for f in files:
                if not f.startswith("."):
                    out.append(os.path.relpath(os.path.join(root, f), static_dir).replace(os.sep, "/"))
    return sorted(out)


def static_version(static_dir):
    h = hashlib.sha1()
    for rel in versioned_files(static_dir):
        h.update(rel.encode())
        with open(os.path.join(static_dir, rel), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:10]
