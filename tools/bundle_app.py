"""Готовит файлы сайта для APK: стили, скрипты, иконки, эмодзи, подарки и офлайн-экран.

Запуск (из корня репозитория, перед сборкой APK):  python3 tools/bundle_app.py
Кладёт всё в android/app/src/main/assets/www и пишет manifest.json:
  {"version": <версия статики>, "files": {"/static/css/app.css": "<версия>", "/static/emoji/1f600.svg": "*", ...}}
Приложение отдаёт файл из APK, если ?v= в адресе совпадает с версией из манифеста ("*" — всегда), иначе берёт из сети.
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services import assets  # noqa: E402

STATIC = os.path.join(ROOT, "static")
OUT = os.path.join(ROOT, "android", "app", "src", "main", "assets", "www")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    version = assets.static_version(STATIC)
    files = {}

    def put(rel, v):
        src = os.path.join(STATIC, rel)
        dst = os.path.join(OUT, "static", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        files["/static/" + rel] = v

    for rel in assets.versioned_files(STATIC):
        put(rel, version)
    for top in assets.STABLE:
        for root, _, names in os.walk(os.path.join(STATIC, top)):
            for n in names:
                if not n.startswith("."):
                    put(os.path.relpath(os.path.join(root, n), STATIC).replace(os.sep, "/"), "*")
    for n in assets.STABLE_FILES:
        if os.path.exists(os.path.join(STATIC, n)):
            put(n, "*")

    # спрайт иконок: та же версия, что посчитает сервер (хэш содержимого)
    try:
        from services import icons
        icons.write_sprite(os.path.join(OUT, "static", "icons.svg"))
        files["/static/icons.svg"] = icons.SPRITE_V
    except ImportError as e:  # без markupsafe спрайт не собрать — приложение возьмёт его из сети
        print("спрайт пропущен:", e)

    shutil.copyfile(os.path.join(ROOT, "templates", "offline.html"), os.path.join(OUT, "offline.html"))
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version, "files": files}, f, ensure_ascii=False, separators=(",", ":"))
    size = sum(os.path.getsize(os.path.join(dp, n)) for dp, _, ns in os.walk(OUT) for n in ns)
    print(f"Встроено файлов: {len(files)}, {size / 1e6:.1f} МБ, версия статики {version}")


if __name__ == "__main__":
    main()
