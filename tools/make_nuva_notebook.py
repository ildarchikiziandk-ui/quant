"""Собирает блокнот Google Colab tools/nuva_finetune.ipynb для дообучения своей модели Нувы.

Внутрь блокнота вшиты учебные примеры (tools/nuva_train.jsonl, их делает tools/nuva_dataset.py) — ничего
загружать вручную не нужно. Блокнот: дообучает Qwen2.5-0.5B-Instruct (LoRA) → склеивает → переводит в GGUF →
отправляет на сервер Nuvora частями (/api/nuva-model/upload, код из deploy/nuva-upload-code.sh).
Запуск: python tools/nuva_dataset.py && python tools/make_nuva_notebook.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = open(os.path.join(ROOT, "tools", "nuva_train.jsonl"), encoding="utf-8").read()


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text.strip("\n").splitlines(True)}


cells = [
    md("""
# 🐋 Дообучение своей модели Нувы

1. Сверху: **Среда выполнения → Сменить среду выполнения → T4 GPU → Сохранить**.
2. В ячейке ниже вставьте **код загрузки** — его покажет на сервере команда `bash /opt/nuvora/deploy/nuva-upload-code.sh`.
3. **Среда выполнения → Выполнить все.** Обучение идёт ~20–40 минут, потом модель сама загрузится на сервер.
4. Когда внизу появится «✅ Модель загружена», запустите на сервере `bash /opt/nuvora/deploy/set-local-ai.sh`.
"""),
    code("""
SERVER = "https://nvurl.ru"  # адрес вашего сайта
SIZE = "0.5B"               # "0.5B" — быстрая и лёгкая (выдержит много людей сразу), "1.5B" — умнее, но отвечает в 2–3 раза медленнее
CODE = ""                   # ← вставьте сюда код загрузки в кавычках
assert CODE, "Вставьте код загрузки в CODE (команда на сервере: bash /opt/nuvora/deploy/nuva-upload-code.sh)"
"""),
    md("## 1. Устанавливаю программы"),
    code("""
!pip install -q "transformers==4.46.3" "peft==0.13.2" "accelerate==1.1.1" "datasets==3.1.0" sentencepiece
import torch
assert torch.cuda.is_available(), "Нет видеокарты: Среда выполнения → Сменить среду выполнения → T4 GPU"
print("Видеокарта:", torch.cuda.get_device_name(0))
"""),
    md("## 2. Учебные примеры Нувы (вшиты в блокнот)"),
    code("DATA = " + json.dumps(DATA, ensure_ascii=False) + """
open("nuva_train.jsonl", "w", encoding="utf-8").write(DATA)
print("примеров:", DATA.count("\\n"))
"""),
    md("## 3. Обучение (~20–40 минут)"),
    code("""
import json
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, DataCollatorForLanguageModeling, Trainer, TrainingArguments

BASE = f"Qwen/Qwen2.5-{SIZE}-Instruct"
tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float16).cuda()
model.gradient_checkpointing_enable()
model.enable_input_require_grads()
model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                                         target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
for p_ in model.parameters():  # обучаемые части — в float32, иначе fp16-обучение падает
    if p_.requires_grad:
        p_.data = p_.data.float()
rows = [json.loads(l) for l in open("nuva_train.jsonl", encoding="utf-8")]
enc = [tok(tok.apply_chat_template(r["messages"], tokenize=False), truncation=True, max_length=1024) for r in rows]
ds = Dataset.from_list([{"input_ids": e["input_ids"], "attention_mask": e["attention_mask"]} for e in enc])
args = TrainingArguments(output_dir="out", per_device_train_batch_size=2, gradient_accumulation_steps=4, num_train_epochs=3,
                         learning_rate=2e-4, warmup_ratio=0.05, lr_scheduler_type="cosine", fp16=True, logging_steps=10,
                         save_strategy="no", report_to=[])
Trainer(model=model, args=args, train_dataset=ds, data_collator=DataCollatorForLanguageModeling(tok, mlm=False)).train()
model = model.merge_and_unload().half()
model.save_pretrained("nuva-merged")
tok.save_pretrained("nuva-merged")
print("✅ Обучение закончено")
"""),
    md("## 4. Проверка: задаю Нуве вопросы"),
    code("""
system = json.loads(open("nuva_train.jsonl", encoding="utf-8").readline())["messages"][0]["content"].split("\\n\\nСправка Nuvora:")[0]
model.eval()
for q in ["Кто ты?", "Как получить искры?", "Придумай подпись к фото снега", "Сколько стоит Nuvora+?"]:
    msgs = [{"role": "system", "content": system + "\\n\\nСправка Nuvora:\\n(подходящих статей не нашлось)"}, {"role": "user", "content": q}]
    ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to("cuda")
    out = model.generate(ids, max_new_tokens=120, do_sample=False)
    print("❓", q, "\\n🐋", tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True), "\\n")
"""),
    md("## 5. Перевожу модель в формат для сервера (GGUF)"),
    code("""
!git clone -q --depth 1 https://github.com/ggml-org/llama.cpp
!pip install -q -r llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
!python llama.cpp/convert_hf_to_gguf.py nuva-merged --outfile nuva-f16.gguf --outtype f16
# сжимаем до q4_k_m: модель становится в 3 раза меньше и быстрее, а ум почти не теряет
!cmake -S llama.cpp -B llama.cpp/build -DLLAMA_CURL=OFF > /dev/null && cmake --build llama.cpp/build --target llama-quantize -j 4 > /dev/null
import os, subprocess
if os.path.exists("llama.cpp/build/bin/llama-quantize"):
    subprocess.run(["llama.cpp/build/bin/llama-quantize", "nuva-f16.gguf", "nuva-custom.gguf", "Q4_K_M"], check=True)
else:  # не собралось — запасной вариант q8_0 (больше по размеру)
    subprocess.run(["python", "llama.cpp/convert_hf_to_gguf.py", "nuva-merged", "--outfile", "nuva-custom.gguf", "--outtype", "q8_0"], check=True)
print("размер модели:", round(os.path.getsize("nuva-custom.gguf") / 1024 / 1024), "МБ")
"""),
    md("## 6. Отправляю модель на сервер Nuvora"),
    code("""
import math, os, requests
size = os.path.getsize("nuva-custom.gguf")
CH = 40 * 1024 * 1024
total = math.ceil(size / CH)
with open("nuva-custom.gguf", "rb") as f:
    for i in range(total):
        r = requests.post(f"{SERVER.rstrip('/')}/api/nuva-model/upload?part={i}&total={total}", data=f.read(CH),
                          headers={"X-Upload-Code": CODE.strip(), "Content-Type": "application/octet-stream"}, timeout=600)
        print(f"часть {i + 1} из {total}:", r.status_code, r.text[:120])
        r.raise_for_status()
print("✅ Модель загружена! Теперь на сервере: bash /opt/nuvora/deploy/set-local-ai.sh")
"""),
]

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"},
                                   "kernelspec": {"display_name": "Python 3", "name": "python3"}, "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 0}
out = os.path.join(ROOT, "tools", "nuva_finetune.ipynb")
json.dump(nb, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("блокнот →", out, round(os.path.getsize(out) / 1024), "КБ")
