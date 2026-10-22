# Рекламные ролики Nuvora 3.1 (11–20)

Готовые видео: `static/promo/nuvora-ad-11…20-*.mp4` (1080×1920, 14 с, со звуком).
Сцены каждого ролика описаны в `ads.html` (объект `ADS[n]`: крючок, заголовок, демонстрация).

Пересборка одного ролика (n = 1…10):
```
cp static/fonts/*.woff2 static/brand/logo-180.png static/icons.svg promo/ads-3.1/
cd promo/ads-3.1 && python3 -m http.server 8811 &
node render.mjs video n v.mp4 && python3 music.py n m.wav
ffmpeg -i v.mp4 -i m.wav -c:v copy -c:a aac -shortest out.mp4
```
