"""Собирает блокнот Google Colab tools/voice_finetune.ipynb — обучение озвучки голосом владельца (7.11.2026).

Блокнот: скачивает записи из «Студии голоса» (/api/voice/dataset по коду загрузки) → переводит в wav 22 кГц →
доучивает готовый русский голос Piper (контрольная точка из rhasspy/piper-checkpoints) на этих записях →
переводит в ONNX → отправляет на сервер (/api/voice-model/upload). Голос сразу становится голосом «Прослушать».
Код загрузки — тот же, что для Нувы: `bash /opt/nuvora/deploy/nuva-upload-code.sh`.
Запуск: python tools/make_voice_notebook.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text.strip("\n").splitlines(True)}


cells = [
    md("""
# 🎙 Озвучка Nuvora вашим голосом

1. Сверху: **Среда выполнения → Сменить среду выполнения → T4 GPU → Сохранить**.
2. В ячейке ниже вставьте **код загрузки** — его покажет на сервере команда `bash /opt/nuvora/deploy/nuva-upload-code.sh`.
3. **Среда выполнения → Выполнить все.** Обучение идёт около часа. Не закрывайте вкладку.
4. Когда внизу появится «✅ Голос загружен», нажмите «Прослушать» у любого поста — это будет ваш голос.

Если обучение идёт слишком долго — нажмите ■ (остановить) у ячейки обучения и запустите ячейки ниже: возьмётся последнее сохранение.
"""),
    code("""
SERVER = "https://nvurl.ru"   # адрес вашего сайта
CODE = ""                     # ← вставьте сюда код загрузки в кавычках
EPOCHS = 1500                 # сколько кругов обучения: больше — похожее, но дольше (1500 ≈ час на T4)
BASE_VOICE = "denis"          # от какого готового голоса доучивать: denis или dmitri (мужские), irina (женский)
assert CODE, "Вставьте код загрузки в CODE (команда на сервере: bash /opt/nuvora/deploy/nuva-upload-code.sh)"
"""),
    md("## 1. Устанавливаю программы (~5 минут)"),
    code("""
!apt-get -qq install -y build-essential cmake ninja-build ffmpeg > /dev/null
!git clone -q --depth 1 --branch v1.8.0 https://github.com/OHF-Voice/piper1-gpl.git || git clone -q --depth 1 https://github.com/OHF-Voice/piper1-gpl.git
%cd piper1-gpl
!pip install -q -e '.[train]'
!./build_monotonic_align.sh
!python3 setup.py build_ext --inplace > /dev/null
%cd ..
import torch
assert torch.cuda.is_available(), "Нет видеокарты: Среда выполнения → Сменить среду выполнения → T4 GPU"
print("Видеокарта:", torch.cuda.get_device_name(0))
"""),
    md("## 2. Скачиваю ваши записи с сайта"),
    code("""
import io, os, subprocess, zipfile, requests
r = requests.get(SERVER + "/api/voice/dataset", headers={"x-upload-code": CODE}, timeout=300)
assert r.status_code == 200, f"Сервер ответил {r.status_code}: {r.text[:200]} — проверьте код загрузки"
os.makedirs("voice/wavs", exist_ok=True)
z = zipfile.ZipFile(io.BytesIO(r.content))
rows = []
for line in z.read("metadata.csv").decode("utf-8").splitlines():
    if "|" not in line:
        continue
    n, text = line.split("|", 1)
    src = next((x for x in z.namelist() if x.startswith(f"wavs/{n}.")), None)
    if not src:
        continue
    raw = "voice/" + os.path.basename(src)
    open(raw, "wb").write(z.read(src))
    out = f"voice/wavs/{n}.wav"
    ok = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-ac", "1", "-ar", "22050", "-af", "loudnorm", out]).returncode == 0
    if ok:
        rows.append(f"{n}.wav|{text}")
open("voice/metadata.csv", "w", encoding="utf-8").write("\\n".join(rows) + "\\n")
print("Записей:", len(rows))
assert len(rows) >= 30, "Слишком мало записей — запишите хотя бы 30 фраз в «Студии голоса»"
"""),
    md("## 3. Беру готовый русский голос, от которого будем доучивать"),
    code("""
from huggingface_hub import hf_hub_download, list_repo_files
files = [f for f in list_repo_files("rhasspy/piper-checkpoints", repo_type="dataset") if f.startswith("ru/ru_RU/") and "/medium/" in f and f.endswith(".ckpt")]
print("Есть русские контрольные точки:", files)
pick = next((f for f in files if f"/{BASE_VOICE}/" in f), None) or next((f for f in files if "/denis/" in f or "/dmitri/" in f), files[0] if files else None)
assert pick, "Не нашлось русской контрольной точки"
CKPT = hf_hub_download("rhasspy/piper-checkpoints", pick, repo_type="dataset")
print("Доучиваю от:", pick)
"""),
    md("## 4. Обучение (~1 час). Можно остановить раньше — возьмётся последнее сохранение"),
    code("""
!python3 -m piper.train fit \\
  --data.voice_name "nuvora-custom" \\
  --data.csv_path voice/metadata.csv \\
  --data.audio_dir voice/wavs \\
  --model.sample_rate 22050 \\
  --data.espeak_voice "ru" \\
  --data.cache_dir voice/cache \\
  --data.config_path voice/nuvora-custom.onnx.json \\
  --data.batch_size 16 \\
  --model.warmstart_ckpt "$CKPT" \\
  --trainer.max_epochs $EPOCHS \\
  --trainer.check_val_every_n_epoch 50
"""),
    md("## 5. Перевожу в формат для сайта и слушаю пример"),
    code("""
import glob
ckpts = sorted(glob.glob("lightning_logs/*/checkpoints/last.ckpt"), key=os.path.getmtime) or sorted(glob.glob("lightning_logs/*/checkpoints/*.ckpt"), key=os.path.getmtime)
assert ckpts, "Нет сохранений обучения — запустите ячейку обучения хотя бы на несколько минут"
!python3 -m piper.train.export_onnx --checkpoint "{ckpts[-1]}" --output-file voice/nuvora-custom.onnx
import wave
from piper import PiperVoice
with wave.open("voice/test.wav", "wb") as w:
    PiperVoice.load("voice/nuvora-custom.onnx", "voice/nuvora-custom.onnx.json").synthesize_wav("Привет! Это Nuvora, и теперь посты читает мой голос.", w)
from IPython.display import Audio, display
display(Audio("voice/test.wav"))
"""),
    md("## 6. Отправляю голос на сайт"),
    code("""
cfg = open("voice/nuvora-custom.onnx.json", "rb").read()
r = requests.post(SERVER + "/api/voice-model/upload?kind=json", data=cfg, headers={"x-upload-code": CODE}, timeout=120)
assert r.ok, r.text
data = open("voice/nuvora-custom.onnx", "rb").read()
PART = 40 * 1024 * 1024
parts = [data[i:i + PART] for i in range(0, len(data), PART)]
for i, chunk in enumerate(parts):
    for attempt in range(4):
        try:
            r = requests.post(f"{SERVER}/api/voice-model/upload?kind=onnx&part={i}&total={len(parts)}", data=chunk, headers={"x-upload-code": CODE}, timeout=600)
            break
        except Exception as e:
            print("повтор…", e)
    assert r.ok and r.json().get("ok"), r.text
    print(f"часть {i + 1} из {len(parts)} — ок")
print("✅ Голос загружен! Нажмите «Прослушать» у любого поста на сайте.")
"""),
]

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"provenance": []}, "kernelspec": {"display_name": "Python 3", "name": "python3"},
                                   "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 0}
out = os.path.join(ROOT, "tools", "voice_finetune.ipynb")
json.dump(nb, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("готово:", out)
