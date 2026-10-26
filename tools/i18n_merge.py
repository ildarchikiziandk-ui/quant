"""Добавить переводы из i18n/src/*.tsv (строки «номер<TAB>перевод», номер — позиция в i18n/keys.json) в i18n/en.json.

После слияния файлы .tsv удаляются: номера действительны только для текущего keys.json.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
keys = json.load(open(os.path.join(ROOT, "i18n", "keys.json"), encoding="utf-8"))
path = os.path.join(ROOT, "i18n", "en.json")
en = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
added = 0
for f in sorted(glob.glob(os.path.join(ROOT, "i18n", "src", "*.tsv"))):
    for line in open(f, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        idx, _, tr = line.partition("\t")
        k = keys[int(idx)]
        tr = tr.replace("\\n", "\n")
        if k.count("{}") != tr.count("{}"):
            sys.exit(f"{f}: {idx}: число {{}} не совпадает: {k!r} → {tr!r}")
        en[k] = tr
        added += 1
    os.remove(f)
json.dump(en, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
print(f"добавлено {added}, всего {len(en)}")
