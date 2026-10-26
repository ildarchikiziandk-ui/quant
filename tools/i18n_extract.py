"""Собрать все русские фразы интерфейса в i18n/keys.json (для перевода в i18n/en.json).

Запуск: python tools/i18n_extract.py [--missing]  — с --missing печатает фразы, которых ещё нет в en.json.
Разбор тот же, что и при переводе (services.i18n), поэтому ключи всегда совпадают.
"""
import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from services import i18n  # noqa: E402

# данные, а не надписи: списки слов модерации, словари Нуви
SKIP_PY = {"services/profanity.py", "services/moderation.py", "packs/v3/nuva_lang.py", "services/legal.py", "packs/v3/admin_plus.py", "services/i18n.py",
           "routers/admin.py"}
JS = ["static/js/app.js", "static/js/more.js", "static/js/chat.js", "static/js/secret.js", "static/js/gost.js",
      "static/packs/v3/v3.js", "static/packs/v3/calls.js", "static/packs/v3/media.js"]


def collect():
    keys = {}

    def fn(core):
        keys.setdefault(core, 0)
        keys[core] += 1
        return None

    for path in sorted(glob.glob(os.path.join(ROOT, "templates", "**", "*.html"), recursive=True)):
        name = os.path.relpath(path, os.path.join(ROOT, "templates"))
        if i18n.skip_template(name):
            continue
        with open(path, encoding="utf-8") as f:
            i18n.template(f.read(), fn)
    for rel in JS:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            i18n.js(f.read(), fn)
    for path in sorted(glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True)):
        rel = os.path.relpath(path, ROOT)
        if rel.startswith(("tests", "school", "tools", "android")) or rel in SKIP_PY or "/." in rel:
            continue
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docs.add(id(first.value))
        fstr = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                parts = []
                for v in node.values:
                    fstr.add(id(v))
                    parts.append(v.value if isinstance(v, ast.Constant) else "{}")
                s = "".join(parts)
                if i18n.CYR.search(s):
                    _py(s, fn)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and id(node) not in fstr:
                if i18n.CYR.search(node.value):
                    _py(node.value, fn)
    return keys


def _py(s, fn):
    if len(s) > 300 or s.count("\n") >= 2:
        return  # подсказки нейросети и словари — не надписи
    if len(s.split()) > 12 and not any(ch in s for ch in ".,!?:;«—"):
        return  # списки слов (игры, стоп-слова)
    if re.search(r"\\[bdwsS1]|\(\?|\[[^\]]*а-я|\|", s) or s.startswith(("[", "(", "^")) or "%" in s and "%H" in s:
        return  # регулярные выражения, служебные сообщения в журнал, форматы дат
    if "<" in s and ">" in s:
        i18n.html(s, fn)
    else:
        core = s.strip()
        if core:
            fn(core)


if __name__ == "__main__":
    keys = collect()
    os.makedirs(os.path.join(ROOT, "i18n"), exist_ok=True)
    with open(os.path.join(ROOT, "i18n", "keys.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(keys), f, ensure_ascii=False, indent=0)
    have = i18n.catalog("en")
    missing = [k for k in sorted(keys) if k not in have]
    print(f"фраз: {len(keys)}, без перевода: {len(missing)}, символов без перевода: {sum(len(k) for k in missing)}")
    if "--missing" in sys.argv:
        for k in missing:
            print(k)
