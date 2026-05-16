from fastapi import FastAPI, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import engine, get_db, Base
from datetime import datetime, timedelta
import models
import auth
import re
import os
import uuid
import hashlib
import random
from PIL import Image
import io

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "/root/quant/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime"}
ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"}
ALLOWED_FILE_TYPES = {"application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_VIDEO_SIZE = 100 * 1024 * 1024
MAX_AUDIO_SIZE = 10 * 1024 * 1024
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1920
ONLINE_THRESHOLD_MINUTES = 2

DAILY_TASKS_LIST = [
    {"code": "post_today", "title": "Опубликуй пост", "description": "Напиши хотя бы один пост сегодня", "emoji": "✍️", "points": 20, "task_type": "post", "target_count": 1},
    {"code": "like_5", "title": "Поставь 5 лайков", "description": "Лайкни 5 постов", "emoji": "❤️", "points": 15, "task_type": "like", "target_count": 5},
    {"code": "comment_3", "title": "Оставь 3 комментария", "description": "Прокомментируй 3 поста", "emoji": "💬", "points": 20, "task_type": "comment", "target_count": 3},
    {"code": "follow_1", "title": "Подпишись на кого-нибудь", "description": "Найди интересного человека", "emoji": "👤", "points": 10, "task_type": "follow", "target_count": 1},
    {"code": "message_1", "title": "Напиши сообщение", "description": "Отправь личное сообщение", "emoji": "✉️", "points": 10, "task_type": "message", "target_count": 1},
    {"code": "story_today", "title": "Добавь историю", "description": "Опубликуй историю сегодня", "emoji": "📸", "points": 25, "task_type": "story", "target_count": 1},
    {"code": "whale_3", "title": "Брось 3 кита", "description": "Нажми 🐋 на 3 постах", "emoji": "🐋", "points": 15, "task_type": "whale", "target_count": 3},
    {"code": "visit_today", "title": "Зайди в Quant", "description": "Просто зайди на сайт", "emoji": "⚡", "points": 5, "task_type": "visit", "target_count": 1},
]

ACHIEVEMENTS_LIST = [
    {"code": "first_post", "name": "Первый пост", "description": "Опубликовал первый пост", "emoji": "✍️", "points_reward": 10},
    {"code": "post_10", "name": "Блогер", "description": "10 постов", "emoji": "📝", "points_reward": 20},
    {"code": "post_50", "name": "Активный автор", "description": "50 постов", "emoji": "🔥", "points_reward": 50},
    {"code": "post_100", "name": "Легенда", "description": "100 постов", "emoji": "👑", "points_reward": 100},
    {"code": "likes_10", "name": "Популярный", "description": "10 лайков", "emoji": "❤️", "points_reward": 15},
    {"code": "likes_100", "name": "Звезда", "description": "100 лайков", "emoji": "⭐", "points_reward": 50},
    {"code": "likes_1000", "name": "Суперзвезда", "description": "1000 лайков", "emoji": "🌟", "points_reward": 200},
    {"code": "followers_10", "name": "На виду", "description": "10 подписчиков", "emoji": "👥", "points_reward": 20},
    {"code": "followers_100", "name": "Инфлюенсер", "description": "100 подписчиков", "emoji": "📣", "points_reward": 100},
    {"code": "followers_1000", "name": "Звезда сети", "description": "1000 подписчиков", "emoji": "🚀", "points_reward": 500},
    {"code": "comment_first", "name": "Комментатор", "description": "Первый комментарий", "emoji": "💬", "points_reward": 5},
    {"code": "repost_first", "name": "Репостер", "description": "Первый репост", "emoji": "🔁", "points_reward": 5},
    {"code": "whale_first", "name": "Китобой", "description": "Первый кит", "emoji": "🐋", "points_reward": 5},
    {"code": "plus_member", "name": "Quant Plus", "description": "Активировал Plus", "emoji": "💎", "points_reward": 50},
    {"code": "streak_7", "name": "Недельный марафон", "description": "7 дней подряд", "emoji": "🏆", "points_reward": 70},
    {"code": "streak_30", "name": "Месячный марафон", "description": "30 дней подряд", "emoji": "🔥", "points_reward": 300},
    {"code": "raffle_winner", "name": "Победитель", "description": "Выиграл розыгрыш", "emoji": "🎉", "points_reward": 100},
    {"code": "first_reel", "name": "Режиссёр", "description": "Первый рилс", "emoji": "🎬", "points_reward": 20},
    {"code": "first_story", "name": "Рассказчик", "description": "Первая история", "emoji": "📸", "points_reward": 10},
    {"code": "level_5", "name": "Опытный", "description": "Достиг 5 уровня", "emoji": "⚡", "points_reward": 50},
    {"code": "level_10", "name": "Ветеран", "description": "Достиг 10 уровня", "emoji": "🎖️", "points_reward": 100},
]

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_owner BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_starred BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified_badge BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_moderator BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked_until TIMESTAMP"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_plus BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS plus_until TIMESTAMP"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS plus_color VARCHAR DEFAULT '#a855f7'"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS pinned_post_id INTEGER"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cover VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS emoji_status VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS website VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_private BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_points INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_points INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS total_points INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS level INTEGER DEFAULT 1"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_days INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_streak_date VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_enabled BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_secret VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS theme VARCHAR DEFAULT 'light'"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_link VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS youtube_link VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS tiktok_link VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS image VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS media_type VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_repost BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS repost_id INTEGER"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS original_comment TEXT DEFAULT ''"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_draft BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS views INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_exclusive BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS exclusive_until TIMESTAMP"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_long BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS image VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS voice VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_url VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_name VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_size INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_video_circle BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to_id INTEGER REFERENCES messages(id)"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_edited BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS disappear_at TIMESTAMP"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_delivered BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS forwarded_from_id INTEGER REFERENCES users(id)"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS content_encrypted TEXT DEFAULT ''"))
        conn.execute(text("ALTER TABLE comments ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES comments(id)"))
        conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS text VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS reply_email VARCHAR DEFAULT ''"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS post_media (id SERIAL PRIMARY KEY, post_id INTEGER REFERENCES posts(id), media_url VARCHAR DEFAULT '', media_type VARCHAR DEFAULT 'image', position INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS reels (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), video_url VARCHAR, thumbnail_url VARCHAR DEFAULT '', caption TEXT DEFAULT '', views INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS reel_likes (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), reel_id INTEGER REFERENCES reels(id))"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS reel_comments (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), reel_id INTEGER REFERENCES reels(id), content TEXT, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS pinned_chats (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), pinned_user_id INTEGER REFERENCES users(id), created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS muted_chats (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), muted_user_id INTEGER REFERENCES users(id), created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), from_user_id INTEGER REFERENCES users(id), type VARCHAR, post_id INTEGER REFERENCES posts(id), text VARCHAR DEFAULT '', reply_email VARCHAR DEFAULT '', is_read BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS verification_codes (id SERIAL PRIMARY KEY, email VARCHAR, code VARCHAR, purpose VARCHAR DEFAULT 'register', created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS whales (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), post_id INTEGER REFERENCES posts(id))"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS reactions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), post_id INTEGER REFERENCES posts(id), emoji VARCHAR DEFAULT '')"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS promocodes (id SERIAL PRIMARY KEY, code VARCHAR UNIQUE, days INTEGER DEFAULT 30, max_uses INTEGER DEFAULT 1, uses INTEGER DEFAULT 0, is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS stories (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), media_url VARCHAR, media_type VARCHAR DEFAULT 'image', created_at TIMESTAMP DEFAULT NOW(), expires_at TIMESTAMP)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS story_views (id SERIAL PRIMARY KEY, story_id INTEGER REFERENCES stories(id), user_id INTEGER REFERENCES users(id), viewed_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS polls (id SERIAL PRIMARY KEY, post_id INTEGER REFERENCES posts(id) UNIQUE, question VARCHAR, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS poll_options (id SERIAL PRIMARY KEY, poll_id INTEGER REFERENCES polls(id), text VARCHAR)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS poll_votes (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), option_id INTEGER REFERENCES poll_options(id), poll_id INTEGER REFERENCES polls(id), created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS typing_status (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), target_id INTEGER REFERENCES users(id), updated_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS stop_words (id SERIAL PRIMARY KEY, word VARCHAR UNIQUE, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS push_subscriptions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), endpoint TEXT, p256dh TEXT, auth TEXT, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS achievements (id SERIAL PRIMARY KEY, code VARCHAR UNIQUE, name VARCHAR, description VARCHAR, emoji VARCHAR, points_reward INTEGER DEFAULT 0)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS user_achievements (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), achievement_id INTEGER REFERENCES achievements(id), earned_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS bookmarks (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), post_id INTEGER REFERENCES posts(id), created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS message_reactions (id SERIAL PRIMARY KEY, message_id INTEGER REFERENCES messages(id), user_id INTEGER REFERENCES users(id), emoji VARCHAR, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, reporter_id INTEGER REFERENCES users(id), target_id INTEGER REFERENCES users(id), reason VARCHAR DEFAULT '', text TEXT DEFAULT '', image_1 VARCHAR DEFAULT '', image_2 VARCHAR DEFAULT '', image_3 VARCHAR DEFAULT '', image_4 VARCHAR DEFAULT '', image_5 VARCHAR DEFAULT '', status VARCHAR DEFAULT 'new', admin_comment TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS user_sessions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), token_hash VARCHAR, device VARCHAR DEFAULT '', ip VARCHAR DEFAULT '', user_agent VARCHAR DEFAULT '', created_at TIMESTAMP DEFAULT NOW(), last_active TIMESTAMP DEFAULT NOW(), is_active BOOLEAN DEFAULT TRUE)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS special_requests (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), type VARCHAR, reason TEXT DEFAULT '', links VARCHAR DEFAULT '', status VARCHAR DEFAULT 'new', admin_comment TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS user_blocks (id SERIAL PRIMARY KEY, blocker_id INTEGER REFERENCES users(id), blocked_id INTEGER REFERENCES users(id), created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS daily_tasks (id SERIAL PRIMARY KEY, code VARCHAR UNIQUE, title VARCHAR, description VARCHAR, emoji VARCHAR DEFAULT '⚡', points INTEGER DEFAULT 10, task_type VARCHAR, target_count INTEGER DEFAULT 1, is_active BOOLEAN DEFAULT TRUE)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS user_daily_tasks (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), task_id INTEGER REFERENCES daily_tasks(id), progress INTEGER DEFAULT 0, is_completed BOOLEAN DEFAULT FALSE, completed_at TIMESTAMP, date VARCHAR DEFAULT '')"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS weekly_raffles (id SERIAL PRIMARY KEY, week_start TIMESTAMP, week_end TIMESTAMP, prize VARCHAR DEFAULT 'Quant Plus 30 дней', prize_days INTEGER DEFAULT 30, winner_id INTEGER REFERENCES users(id), is_finished BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS raffle_entries (id SERIAL PRIMARY KEY, raffle_id INTEGER REFERENCES weekly_raffles(id), user_id INTEGER REFERENCES users(id), tickets INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS trends (id SERIAL PRIMARY KEY, tag VARCHAR UNIQUE, count INTEGER DEFAULT 0, updated_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS drafts (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), content TEXT DEFAULT '', image VARCHAR DEFAULT '', created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("UPDATE users SET is_owner = TRUE WHERE username = 'rubl'"))
        conn.execute(text("UPDATE users SET email_verified = TRUE WHERE username = 'rubl'"))
        for a in ACHIEVEMENTS_LIST:
            conn.execute(text(f"INSERT INTO achievements (code, name, description, emoji, points_reward) VALUES ('{a['code']}', '{a['name']}', '{a['description']}', '{a['emoji']}', {a['points_reward']}) ON CONFLICT (code) DO NOTHING"))
        for t in DAILY_TASKS_LIST:
            conn.execute(text(f"INSERT INTO daily_tasks (code, title, description, emoji, points, task_type, target_count) VALUES ('{t['code']}', '{t['title']}', '{t['description']}', '{t['emoji']}', {t['points']}, '{t['task_type']}', {t['target_count']}) ON CONFLICT (code) DO NOTHING"))
        conn.commit()
except Exception as e:
    print(f"DB migration warning: {e}")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="/root/quant/uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

def validate_username(username):
    if len(username) < 3: return "Никнейм должен быть не короче 3 символов"
    if len(username) > 30: return "Никнейм должен быть не длиннее 30 символов"
    if not re.match(r'^[\w\.\-]+$', username, re.UNICODE): return "Никнейм может содержать только буквы, цифры, точку, дефис и подчёркивание"
    return None

def validate_password(password):
    if len(password) < 8: return "Пароль должен быть не короче 8 символов"
    if len(password) > 64: return "Пароль должен быть не длиннее 64 символов"
    if not re.search(r'[A-Za-zА-Яа-яЁё]', password): return "Пароль должен содержать хотя бы одну букву"
    if not re.search(r'\d', password): return "Пароль должен содержать хотя бы одну цифру"
    if password.lower() in ["12345678", "password", "qwerty123"]: return "Пароль слишком простой"
    return None

def get_unread(user, db):
    if not user: return 0
    return db.query(models.Notification).filter(models.Notification.user_id == user.id, models.Notification.is_read == False).count()

def get_unread_messages(user, db):
    if not user: return 0
    return db.query(models.Message).filter(models.Message.receiver_id == user.id, models.Message.is_read == False, models.Message.is_deleted == False).count()

def get_unread_from(user, db):
    if not user: return set()
    msgs = db.query(models.Message.sender_id).filter(models.Message.receiver_id == user.id, models.Message.is_read == False, models.Message.is_deleted == False).distinct().all()
    return set(m[0] for m in msgs)

def can_moderate(user):
    if not user: return False
    return bool(user.is_owner) or bool(user.is_moderator)

def is_user_blocked(user):
    if not user or not user.is_blocked: return False
    if user.blocked_until and datetime.utcnow() > user.blocked_until: return False
    return True

def is_user_plus(user):
    if not user or not user.is_plus: return False
    if user.plus_until and datetime.utcnow() > user.plus_until: return False
    return True

def is_user_online(user):
    if not user or not user.last_seen: return False
    return (datetime.utcnow() - user.last_seen).total_seconds() < ONLINE_THRESHOLD_MINUTES * 60

def check_stop_words(content, db):
    words = db.query(models.StopWord).all()
    content_lower = content.lower()
    for sw in words:
        if sw.word.lower() in content_lower: return True
    return False

def render_content(content):
    content = re.sub(r'@([\w\.\-]+)', r'<a href="/profile/\1" style="color:#1d9bf0;font-weight:600;">@\1</a>', content)
    content = re.sub(r'#([\w]+)', r'<a href="/hashtag/\1" style="color:#1d9bf0;font-weight:600;">#\1</a>', content)
    return content

def process_mentions(content, author, post_id, db):
    mentions = re.findall(r'@([\w\.\-]+)', content)
    notified = set()
    for username in mentions:
        if username in notified: continue
        mentioned_user = db.query(models.User).filter(models.User.username == username).first()
        if mentioned_user and mentioned_user.id != author.id:
            db.add(models.Notification(user_id=mentioned_user.id, from_user_id=author.id, type="mention", post_id=post_id))
            notified.add(username)

def update_trends(content, db):
    tags = re.findall(r'#([\w]+)', content)
    for tag in tags:
        tag = tag.lower()
        trend = db.query(models.Trend).filter(models.Trend.tag == tag).first()
        if trend:
            trend.count += 1
            trend.updated_at = datetime.utcnow()
        else:
            db.add(models.Trend(tag=tag, count=1))

def get_user_level(points):
    thresholds = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5500, 7000]
    for i, t in enumerate(thresholds):
        if points < t: return i
    return len(thresholds)

def save_session(user, request, token, db):
    try:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        ua = request.headers.get("user-agent", "")
        ip = request.headers.get("x-real-ip", request.client.host if request.client else "")
        device = "Мобильный" if any(x in ua.lower() for x in ["mobile", "android", "iphone"]) else "Компьютер"
        browser = "Chrome" if "chrome" in ua.lower() else "Firefox" if "firefox" in ua.lower() else "Safari" if "safari" in ua.lower() else "Браузер"
        session = models.UserSession(user_id=user.id, token_hash=token_hash, device=f"{device} · {browser}", ip=ip, user_agent=ua[:200])
        db.add(session)
        db.commit()
    except Exception as e:
        print(f"Session save error: {e}")

def check_and_give_achievements(user, db):
    earned_codes = set(ua.achievement.code for ua in user.achievements)
    def give(code):
        if code in earned_codes: return
        ach = db.query(models.Achievement).filter(models.Achievement.code == code).first()
        if ach:
            db.add(models.UserAchievement(user_id=user.id, achievement_id=ach.id))
            user.total_points = (user.total_points or 0) + ach.points_reward
            earned_codes.add(code)
    from sqlalchemy import func
    post_count = db.query(models.Post).filter(models.Post.user_id == user.id, models.Post.is_repost == False, models.Post.is_published == True).count()
    if post_count >= 1: give("first_post")
    if post_count >= 10: give("post_10")
    if post_count >= 50: give("post_50")
    if post_count >= 100: give("post_100")
    total_likes = db.query(func.count(models.Like.id)).join(models.Post).filter(models.Post.user_id == user.id).scalar() or 0
    if total_likes >= 10: give("likes_10")
    if total_likes >= 100: give("likes_100")
    if total_likes >= 1000: give("likes_1000")
    followers_count = db.query(models.Follow).filter(models.Follow.following_id == user.id).count()
    if followers_count >= 10: give("followers_10")
    if followers_count >= 100: give("followers_100")
    if followers_count >= 1000: give("followers_1000")
    if db.query(models.Comment).filter(models.Comment.user_id == user.id).count() >= 1: give("comment_first")
    if db.query(models.Post).filter(models.Post.user_id == user.id, models.Post.is_repost == True).count() >= 1: give("repost_first")
    if db.query(models.Whale).filter(models.Whale.user_id == user.id).count() >= 1: give("whale_first")
    if db.query(models.Reel).filter(models.Reel.user_id == user.id).count() >= 1: give("first_reel")
    if db.query(models.Story).filter(models.Story.user_id == user.id).count() >= 1: give("first_story")
    if is_user_plus(user): give("plus_member")
    if (user.streak_days or 0) >= 7: give("streak_7")
    if (user.streak_days or 0) >= 30: give("streak_30")
    new_level = get_user_level(user.total_points or 0)
    if new_level >= 5: give("level_5")
    if new_level >= 10: give("level_10")
    user.level = new_level
    db.commit()

def get_today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def get_or_create_daily_tasks(user, db):
    today = get_today_str()
    existing = db.query(models.UserDailyTask).filter(models.UserDailyTask.user_id == user.id, models.UserDailyTask.date == today).all()
    if existing:
        return existing
    tasks = db.query(models.DailyTask).filter(models.DailyTask.is_active == True).all()
    for task in tasks:
        db.add(models.UserDailyTask(user_id=user.id, task_id=task.id, date=today, progress=0, is_completed=False))
    db.commit()
    return db.query(models.UserDailyTask).filter(models.UserDailyTask.user_id == user.id, models.UserDailyTask.date == today).all()

def update_task_progress(user, task_type, db, count=1):
    if not user: return
    today = get_today_str()
    tasks = db.query(models.UserDailyTask).join(models.DailyTask).filter(
        models.UserDailyTask.user_id == user.id,
        models.UserDailyTask.date == today,
        models.DailyTask.task_type == task_type,
        models.UserDailyTask.is_completed == False
    ).all()
    for ut in tasks:
        ut.progress = min(ut.progress + count, ut.task.target_count)
        if ut.progress >= ut.task.target_count:
            ut.is_completed = True
            ut.completed_at = datetime.utcnow()
            points = ut.task.points
            user.daily_points = (user.daily_points or 0) + points
            user.weekly_points = (user.weekly_points or 0) + points
            user.total_points = (user.total_points or 0) + points
            update_raffle_entry(user, db)
    db.commit()

def update_streak(user, db):
    today = get_today_str()
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    if user.last_streak_date == today:
        return
    if user.last_streak_date == yesterday:
        user.streak_days = (user.streak_days or 0) + 1
    else:
        user.streak_days = 1
    user.last_streak_date = today
    db.commit()

def update_raffle_entry(user, db):
    raffle = get_current_raffle(db)
    if not raffle: return
    entry = db.query(models.RaffleEntry).filter(models.RaffleEntry.raffle_id == raffle.id, models.RaffleEntry.user_id == user.id).first()
    if entry:
        entry.tickets += 1
    else:
        db.add(models.RaffleEntry(raffle_id=raffle.id, user_id=user.id, tickets=1))
    db.commit()

def get_current_raffle(db):
    now = datetime.utcnow()
    raffle = db.query(models.WeeklyRaffle).filter(models.WeeklyRaffle.week_start <= now, models.WeeklyRaffle.week_end >= now, models.WeeklyRaffle.is_finished == False).first()
    if not raffle:
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = week_start - timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=7)
        raffle = models.WeeklyRaffle(week_start=week_start, week_end=week_end)
        db.add(raffle)
        db.commit()
        db.refresh(raffle)
    return raffle

def finish_raffle_if_needed(db):
    now = datetime.utcnow()
    old_raffles = db.query(models.WeeklyRaffle).filter(models.WeeklyRaffle.week_end < now, models.WeeklyRaffle.is_finished == False).all()
    for raffle in old_raffles:
        entries = db.query(models.RaffleEntry).filter(models.RaffleEntry.raffle_id == raffle.id).all()
        if entries:
            pool = []
            for entry in entries:
                pool.extend([entry.user_id] * entry.tickets)
            winner_id = random.choice(pool)
            raffle.winner_id = winner_id
            winner = db.query(models.User).filter(models.User.id == winner_id).first()
            if winner:
                winner.is_plus = True
                winner.plus_until = datetime.utcnow() + timedelta(days=raffle.prize_days)
                db.add(models.Notification(user_id=winner_id, type="system", text=f"🎉 Поздравляем! Ты выиграл розыгрыш и получил Quant Plus на {raffle.prize_days} дней!"))
        raffle.is_finished = True
        db.commit()

def save_media_file(upload: UploadFile):
    if not upload or not upload.filename: return None, None
    content_type = (upload.content_type or "").lower()
    contents = upload.file.read()
    file_size = len(contents)
    if content_type in ALLOWED_IMAGE_TYPES:
        if file_size > MAX_IMAGE_SIZE: return None, "Фото слишком большое (макс. 10 МБ)"
        media_type = "image"
    elif content_type in ALLOWED_VIDEO_TYPES:
        if file_size > MAX_VIDEO_SIZE: return None, "Видео слишком большое (макс. 100 МБ)"
        media_type = "video"
    else:
        return None, "Неподдерживаемый формат"
    ext = ".jpg"
    if "png" in content_type: ext = ".png"
    elif "webp" in content_type: ext = ".webp"
    elif "mp4" in content_type: ext = ".mp4"
    elif "quicktime" in content_type: ext = ".mov"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    if media_type == "image":
        try:
            img = Image.open(io.BytesIO(contents))
            img = _auto_rotate(img)
            if img.width > MAX_IMAGE_DIMENSION or img.height > MAX_IMAGE_DIMENSION:
                img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
            if ext == ".jpg" and img.mode in ("RGBA", "P"): img = img.convert("RGB")
            save_params = {"optimize": True}
            if ext in (".jpg", ".jpeg"): save_params["quality"] = 85
            elif ext == ".webp": save_params["quality"] = 85
            img.save(filepath, **save_params)
        except Exception as e:
            print(f"Image processing error: {e}")
            return None, "Не удалось обработать фото"
    else:
        with open(filepath, "wb") as f:
            f.write(contents)
    return f"/uploads/{filename}", media_type

def save_file_attachment(upload: UploadFile):
    if not upload or not upload.filename: return None, None, 0
    contents = upload.file.read()
    file_size = len(contents)
    if file_size > MAX_FILE_SIZE: return None, None, 0
    ext = os.path.splitext(upload.filename)[1].lower() or ".bin"
    filename = f"file_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(contents)
    return f"/uploads/{filename}", upload.filename, file_size

def save_audio_file(upload: UploadFile):
    if not upload or not upload.filename: return None
    contents = upload.file.read()
    if len(contents) > MAX_AUDIO_SIZE: return None
    ext = ".webm"
    content_type = (upload.content_type or "").lower()
    if "ogg" in content_type: ext = ".ogg"
    elif "mp4" in content_type: ext = ".mp4"
    elif "mpeg" in content_type: ext = ".mp3"
    elif "wav" in content_type: ext = ".wav"
    filename = f"voice_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(contents)
    return f"/uploads/{filename}"

def _auto_rotate(img):
    try:
        exif = img._getexif()
        if exif:
            orientation = exif.get(274)
            if orientation == 3: img = img.rotate(180, expand=True)
            elif orientation == 6: img = img.rotate(270, expand=True)
            elif orientation == 8: img = img.rotate(90, expand=True)
    except Exception:
        pass
    return img

def delete_media_file(url):
    if not url or not url.startswith("/uploads/"): return
    filepath = os.path.join(UPLOAD_DIR, url.replace("/uploads/", ""))
    try:
        if os.path.exists(filepath): os.remove(filepath)
    except Exception as e:
        print(f"Could not delete file: {e}")

BLOCKED_RESPONSE = """<html><body style='font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#f5f5f5;margin:0'><div style='background:#fff;border-radius:16px;padding:40px;text-align:center;max-width:400px'><div style='font-size:48px;margin-bottom:16px'>🚫</div><h2>Аккаунт заблокирован</h2><p style='color:#888;margin:16px 0 24px'>Ваш аккаунт заблокирован администратором.</p><a href='/' style='background:#0f0f0f;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600'>На главную</a></div></body></html>"""

# ===== РОУТЫ =====

@app.get("/", response_class=HTMLResponse)
def home(request: Request, tab: str = "foryou", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if user:
        user.last_seen = datetime.utcnow()
        update_streak(user, db)
        finish_raffle_if_needed(db)
        get_or_create_daily_tasks(user, db)
        update_task_progress(user, "visit", db)
        db.commit()
    scheduled = db.query(models.Post).filter(models.Post.is_published == False, models.Post.scheduled_at <= datetime.utcnow()).all()
    for p in scheduled:
        p.is_published = True
    if scheduled: db.commit()
    expired = db.query(models.Story).filter(models.Story.expires_at < datetime.utcnow()).all()
    for s in expired:
        delete_media_file(s.media_url)
        db.query(models.StoryView).filter(models.StoryView.story_id == s.id).delete()
        db.delete(s)
    if expired: db.commit()
    active_stories = db.query(models.Story).filter(models.Story.expires_at > datetime.utcnow()).order_by(models.Story.created_at.asc()).all()
    seen_users = set()
    stories_data = []
    my_stories = []
    if user:
        my_stories = [s for s in active_stories if s.user_id == user.id]
    for s in active_stories:
        if user and s.user_id == user.id: continue
        if s.user_id not in seen_users:
            seen_users.add(s.user_id)
            user_stories = [x for x in active_stories if x.user_id == s.user_id]
            seen = False
            if user:
                view = db.query(models.StoryView).filter(models.StoryView.story_id == user_stories[0].id, models.StoryView.user_id == user.id).first()
                seen = view is not None
            stories_data.append({"user": s.author, "first_story_id": user_stories[0].id, "seen": seen, "count": len(user_stories)})
    if tab == "following" and user:
        following_ids = [f.following_id for f in user.following]
        posts = db.query(models.Post).filter(models.Post.user_id.in_(following_ids), models.Post.is_published == True).order_by(models.Post.created_at.desc()).all()
    else:
        posts = db.query(models.Post).filter(models.Post.is_published == True).order_by(models.Post.created_at.desc()).limit(200).all()
        following_ids = set(f.following_id for f in user.following) if user else set()
        now = datetime.utcnow()
        def score(post):
            age_hours = max((now - post.created_at).total_seconds() / 3600, 0.1)
            return 1000 / (age_hours + 2) + len(post.likes) * 3 + len(post.comments) * 2 + len(post.whales) + (50 if post.user_id in following_ids else 0)
        posts = sorted(posts, key=score, reverse=True)
    bookmarked_ids = set(b.post_id for b in user.bookmarks) if user else set()
    liked_ids = set()
    whaled_ids = set()
    if user:
        liked_ids = set(l.post_id for l in db.query(models.Like).filter(models.Like.user_id == user.id).all())
        whaled_ids = set(w.post_id for w in db.query(models.Whale).filter(models.Whale.user_id == user.id).all())
    daily_tasks = get_or_create_daily_tasks(user, db) if user else []
    raffle = get_current_raffle(db) if user else None
    user_tickets = 0
    if user and raffle:
        entry = db.query(models.RaffleEntry).filter(models.RaffleEntry.raffle_id == raffle.id, models.RaffleEntry.user_id == user.id).first()
        user_tickets = entry.tickets if entry else 0
    trends = db.query(models.Trend).order_by(models.Trend.count.desc()).limit(5).all()
    suggested_users = []
    if user:
        following_ids_list = [f.following_id for f in user.following]
        following_ids_list.append(user.id)
        suggested_users = db.query(models.User).filter(~models.User.id.in_(following_ids_list)).order_by(models.User.created_at.desc()).limit(3).all()
    return templates.TemplateResponse(request, "home.html", {
        "user": user, "posts": posts,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "tab": tab, "is_plus": is_user_plus(user),
        "stories_data": stories_data, "my_stories": my_stories,
        "render_content": render_content, "is_online": is_user_online,
        "bookmarked_ids": bookmarked_ids, "liked_ids": liked_ids, "whaled_ids": whaled_ids,
        "top_post_id": posts[0].id if posts else 0,
        "daily_tasks": daily_tasks, "raffle": raffle, "user_tickets": user_tickets,
        "trends": trends, "suggested_users": suggested_users
    })

@app.get("/reels", response_class=HTMLResponse)
def reels_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if user:
        user.last_seen = datetime.utcnow()
        db.commit()
    reels = db.query(models.Reel).order_by(models.Reel.created_at.desc()).limit(50).all()
    liked_reel_ids = set()
    if user:
        liked_reel_ids = set(l.reel_id for l in db.query(models.ReelLike).filter(models.ReelLike.user_id == user.id).all())
    return templates.TemplateResponse(request, "reels.html", {
        "user": user, "reels": reels,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "is_plus": is_user_plus(user), "liked_reel_ids": liked_reel_ids
    })

@app.post("/reels/upload")
async def upload_reel(request: Request, video: UploadFile = File(...), caption: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user): return HTMLResponse(BLOCKED_RESPONSE)
    url, type_or_error = save_media_file(video)
    if not url: return RedirectResponse("/reels", status_code=302)
    reel = models.Reel(user_id=user.id, video_url=url, caption=caption)
    db.add(reel)
    db.commit()
    check_and_give_achievements(user, db)
    update_task_progress(user, "post", db)
    return RedirectResponse("/reels", status_code=302)

@app.post("/reels/like/{reel_id}")
def like_reel(reel_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"ok": False})
    existing = db.query(models.ReelLike).filter(models.ReelLike.user_id == user.id, models.ReelLike.reel_id == reel_id).first()
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(models.ReelLike(user_id=user.id, reel_id=reel_id))
        liked = True
    db.commit()
    count = db.query(models.ReelLike).filter(models.ReelLike.reel_id == reel_id).count()
    return JSONResponse({"ok": True, "liked": liked, "count": count})

@app.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    user.last_seen = datetime.utcnow()
    db.commit()
    daily_tasks = get_or_create_daily_tasks(user, db)
    raffle = get_current_raffle(db)
    user_tickets = 0
    total_entries = 0
    if raffle:
        entry = db.query(models.RaffleEntry).filter(models.RaffleEntry.raffle_id == raffle.id, models.RaffleEntry.user_id == user.id).first()
        user_tickets = entry.tickets if entry else 0
        total_entries = db.query(models.RaffleEntry).filter(models.RaffleEntry.raffle_id == raffle.id).count()
    past_raffles = db.query(models.WeeklyRaffle).filter(models.WeeklyRaffle.is_finished == True).order_by(models.WeeklyRaffle.week_end.desc()).limit(5).all()
    completed_today = sum(1 for t in daily_tasks if t.is_completed)
    leaderboard = db.query(models.User).order_by(models.User.total_points.desc()).limit(10).all()
    return templates.TemplateResponse(request, "tasks.html", {
        "user": user, "daily_tasks": daily_tasks,
        "raffle": raffle, "user_tickets": user_tickets,
        "total_entries": total_entries, "past_raffles": past_raffles,
        "completed_today": completed_today, "total_tasks": len(daily_tasks),
        "leaderboard": leaderboard,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "is_plus": is_user_plus(user)
    })

@app.get("/trends", response_class=HTMLResponse)
def trends_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    trends = db.query(models.Trend).order_by(models.Trend.count.desc()).limit(20).all()
    return templates.TemplateResponse(request, "trends.html", {
        "user": user, "trends": trends,
        "unread": get_unread(user, db) if user else 0,
        "unread_msg": get_unread_messages(user, db) if user else 0,
        "is_plus": is_user_plus(user)
    })

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {})

@app.post("/register")
def register(request: Request, name: str = Form(...), username: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    error = validate_username(username)
    if error: return templates.TemplateResponse(request, "register.html", {"error": error})
    error = validate_password(password)
    if error: return templates.TemplateResponse(request, "register.html", {"error": error})
    if db.query(models.User).filter(models.User.username == username).first():
        return templates.TemplateResponse(request, "register.html", {"error": f"Никнейм @{username} уже занят"})
    if db.query(models.User).filter(models.User.email == email).first():
        return templates.TemplateResponse(request, "register.html", {"error": "Этот email уже зарегистрирован"})
    user = models.User(name=name, username=username, email=email, password=auth.hash_password(password), is_verified=True, email_verified=True)
    db.add(user)
    db.commit()
    token = auth.create_token({"sub": username})
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("token", token)
    save_session(user, request, token, db)
    return response

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not auth.verify_password(password, user.password):
        return templates.TemplateResponse(request, "login.html", {"error": "Неверный никнейм или пароль"})
    token = auth.create_token({"sub": username})
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("token", token)
    save_session(user, request, token, db)
    return response

@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if user:
        token = request.cookies.get("token")
        if token:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            session = db.query(models.UserSession).filter(models.UserSession.token_hash == token_hash).first()
            if session:
                session.is_active = False
                db.commit()
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("token")
    return response

@app.post("/post")
async def create_post(request: Request, content: str = Form(...),
    media: UploadFile = File(None), media_2: UploadFile = File(None),
    media_3: UploadFile = File(None), media_4: UploadFile = File(None),
    media_5: UploadFile = File(None),
    poll_question: str = Form(""), poll_option_1: str = Form(""),
    poll_option_2: str = Form(""), poll_option_3: str = Form(""), poll_option_4: str = Form(""),
    scheduled_at: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user): return HTMLResponse(BLOCKED_RESPONSE)
    if not content or not content.strip(): return RedirectResponse("/", status_code=302)
    if check_stop_words(content, db): return RedirectResponse("/?error=stopword", status_code=302)
    media_url = ""
    media_type = ""
    extra_media = []
    all_uploads = [u for u in [media, media_2, media_3, media_4, media_5] if u and u.filename]
    if all_uploads:
        url, type_or_error = save_media_file(all_uploads[0])
        if url:
            media_url = url
            media_type = type_or_error
            for extra in all_uploads[1:]:
                eurl, etype = save_media_file(extra)
                if eurl: extra_media.append({"url": eurl, "type": etype})
    sched = None
    is_published = True
    if scheduled_at.strip():
        try:
            sched = datetime.strptime(scheduled_at.strip(), "%Y-%m-%dT%H:%M")
            if sched > datetime.utcnow(): is_published = False
        except Exception: pass
    is_long = len(content) > 500
    post = models.Post(content=content, user_id=user.id, image=media_url, media_type=media_type, scheduled_at=sched, is_published=is_published, is_long=is_long)
    db.add(post)
    db.flush()
    for i, em in enumerate(extra_media):
        db.add(models.PostMedia(post_id=post.id, media_url=em["url"], media_type=em["type"], position=i+1))
    if poll_question.strip():
        options = [o.strip() for o in [poll_option_1, poll_option_2, poll_option_3, poll_option_4] if o.strip()]
        if len(options) >= 2:
            poll = models.Poll(post_id=post.id, question=poll_question.strip())
            db.add(poll)
            db.flush()
            for opt_text in options:
                db.add(models.PollOption(poll_id=poll.id, text=opt_text))
    if is_published:
        process_mentions(content, user, post.id, db)
        update_trends(content, db)
    db.commit()
    check_and_give_achievements(user, db)
    if is_published: update_task_progress(user, "post", db)
    return RedirectResponse("/", status_code=302)

@app.post("/like/{post_id}")
def like_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user): return HTMLResponse(BLOCKED_RESPONSE)
    existing = db.query(models.Like).filter(models.Like.user_id == user.id, models.Like.post_id == post_id).first()
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(models.Like(user_id=user.id, post_id=post_id))
        liked = True
        post = db.query(models.Post).filter(models.Post.id == post_id).first()
        if post and post.user_id != user.id:
            db.add(models.Notification(user_id=post.user_id, from_user_id=user.id, type="like", post_id=post_id))
        update_task_progress(user, "like", db)
    db.commit()
    check_and_give_achievements(user, db)
    count = db.query(models.Like).filter(models.Like.post_id == post_id).count()
    return JSONResponse({"ok": True, "liked": liked, "count": count})

@app.post("/whale/{post_id}")
def whale_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user): return HTMLResponse(BLOCKED_RESPONSE)
    existing = db.query(models.Whale).filter(models.Whale.user_id == user.id, models.Whale.post_id == post_id).first()
    if existing:
        db.delete(existing)
        whaled = False
    else:
        db.add(models.Whale(user_id=user.id, post_id=post_id))
        whaled = True
        update_task_progress(user, "whale", db)
        check_and_give_achievements(user, db)
    db.commit()
    count = db.query(models.Whale).filter(models.Whale.post_id == post_id).count()
    return JSONResponse({"ok": True, "whaled": whaled, "count": count})

@app.post("/comment/{post_id}")
def add_comment(post_id: int, request: Request, content: str = Form(...), parent_id: int = Form(None), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user): return HTMLResponse(BLOCKED_RESPONSE)
    if check_stop_words(content, db): return RedirectResponse(f"/post/{post_id}?error=stopword", status_code=302)
    comment = models.Comment(content=content, user_id=user.id, post_id=post_id, parent_id=parent_id)
    db.add(comment)
    db.flush()
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if post and post.user_id != user.id:
        db.add(models.Notification(user_id=post.user_id, from_user_id=user.id, type="comment", post_id=post_id))
    process_mentions(content, user, post_id, db)
    db.commit()
    check_and_give_achievements(user, db)
    update_task_progress(user, "comment", db)
    return RedirectResponse(f"/post/{post_id}", status_code=302)

@app.post("/follow/{username}")
def follow(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = auth.get_current_user(request, db)
    if not current_user: return RedirectResponse("/login", status_code=302)
    if is_user_blocked(current_user): return HTMLResponse(BLOCKED_RESPONSE)
    target = db.query(models.User).filter(models.User.username == username).first()
    if not target or target.id == current_user.id: return RedirectResponse("/", status_code=302)
    existing = db.query(models.Follow).filter(models.Follow.follower_id == current_user.id, models.Follow.following_id == target.id).first()
    if existing:
        db.delete(existing)
    else:
        db.add(models.Follow(follower_id=current_user.id, following_id=target.id))
        db.add(models.Notification(user_id=target.id, from_user_id=current_user.id, type="follow"))
        check_and_give_achievements(target, db)
        update_task_progress(current_user, "follow", db)
    db.commit()
    return RedirectResponse(f"/profile/{username}", status_code=302)

@app.get("/profile/{username}", response_class=HTMLResponse)
def profile(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = auth.get_current_user(request, db)
    if current_user:
        current_user.last_seen = datetime.utcnow()
        db.commit()
    profile_user = db.query(models.User).filter(models.User.username == username).first()
    if not profile_user: return RedirectResponse("/", status_code=302)
    is_following = False
    if current_user:
        is_following = db.query(models.Follow).filter(models.Follow.follower_id == current_user.id, models.Follow.following_id == profile_user.id).first() is not None
    is_private_and_hidden = profile_user.is_private and not is_following and (not current_user or current_user.id != profile_user.id)
    posts = []
    if not is_private_and_hidden:
        posts = db.query(models.Post).filter(models.Post.user_id == profile_user.id, models.Post.is_published == True).order_by(models.Post.created_at.desc()).all()
    pinned_post = None
    if profile_user.pinned_post_id and not is_private_and_hidden:
        pinned_post = db.query(models.Post).filter(models.Post.id == profile_user.pinned_post_id).first()
    following_ids = set(f.following_id for f in profile_user.following)
    follower_ids = set(f.follower_id for f in profile_user.followers)
    friend_ids = following_ids & follower_ids
    friends = db.query(models.User).filter(models.User.id.in_(friend_ids)).all() if friend_ids else []
    is_friend = False
    if current_user and current_user.id != profile_user.id and is_following:
        is_friend = db.query(models.Follow).filter(models.Follow.follower_id == profile_user.id, models.Follow.following_id == current_user.id).first() is not None
    user_achievements = db.query(models.UserAchievement).filter(models.UserAchievement.user_id == profile_user.id).all()
    total_views = sum(p.views or 0 for p in posts)
    reels = db.query(models.Reel).filter(models.Reel.user_id == profile_user.id).order_by(models.Reel.created_at.desc()).all()
    is_user_blocked_by_me = False
    if current_user and current_user.id != profile_user.id:
        is_user_blocked_by_me = db.query(models.UserBlock).filter(models.UserBlock.blocker_id == current_user.id, models.UserBlock.blocked_id == profile_user.id).first() is not None
    already_reported = False
    if current_user and current_user.id != profile_user.id:
        week_ago = datetime.utcnow() - timedelta(days=7)
        already_reported = db.query(models.Report).filter(models.Report.reporter_id == current_user.id, models.Report.target_id == profile_user.id, models.Report.created_at >= week_ago).count() >= 3
    liked_ids = set()
    if current_user:
        liked_ids = set(l.post_id for l in db.query(models.Like).filter(models.Like.user_id == current_user.id).all())
    return templates.TemplateResponse(request, "profile.html", {
        "user": current_user, "profile_user": profile_user, "posts": posts,
        "pinned_post": pinned_post, "is_following": is_following,
        "friends": friends, "is_friend": is_friend,
        "unread": get_unread(current_user, db), "unread_msg": get_unread_messages(current_user, db),
        "is_plus": is_user_plus(current_user), "profile_is_plus": is_user_plus(profile_user),
        "render_content": render_content, "is_online": is_user_online,
        "user_achievements": user_achievements, "total_views": total_views,
        "reels": reels, "already_reported": already_reported,
        "is_private_and_hidden": is_private_and_hidden,
        "is_user_blocked_by_me": is_user_blocked_by_me, "liked_ids": liked_ids
    })

@app.get("/messages", response_class=HTMLResponse)
def messages_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user): return HTMLResponse(BLOCKED_RESPONSE)
    user.last_seen = datetime.utcnow()
    db.commit()
    conversations = db.query(models.User).join(models.Message, (models.Message.sender_id == user.id) | (models.Message.receiver_id == user.id)).filter(models.User.id != user.id).distinct().all()
    unread_from = get_unread_from(user, db)
    pinned_ids = set(p.pinned_user_id for p in db.query(models.PinnedChat).filter(models.PinnedChat.user_id == user.id).all())
    muted_ids = set(m.muted_user_id for m in db.query(models.MutedChat).filter(models.MutedChat.user_id == user.id).all())
    pinned_convs = [c for c in conversations if c.id in pinned_ids]
    other_convs = [c for c in conversations if c.id not in pinned_ids]
    return templates.TemplateResponse(request, "messages.html", {
        "user": user, "conversations": other_convs, "pinned_convs": pinned_convs,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "unread_from": unread_from, "is_online": is_user_online,
        "pinned_ids": pinned_ids, "muted_ids": muted_ids
    })

@app.post("/messages/pin/{username}")
def pin_chat(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if not target: return RedirectResponse("/messages", status_code=302)
    existing = db.query(models.PinnedChat).filter(models.PinnedChat.user_id == user.id, models.PinnedChat.pinned_user_id == target.id).first()
    if existing: db.delete(existing)
    else: db.add(models.PinnedChat(user_id=user.id, pinned_user_id=target.id))
    db.commit()
    return RedirectResponse("/messages", status_code=302)

@app.post("/messages/mute/{username}")
def mute_chat(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if not target: return RedirectResponse("/messages", status_code=302)
    existing = db.query(models.MutedChat).filter(models.MutedChat.user_id == user.id, models.MutedChat.muted_user_id == target.id).first()
    if existing: db.delete(existing)
    else: db.add(models.MutedChat(user_id=user.id, muted_user_id=target.id))
    db.commit()
    return RedirectResponse(f"/messages/{username}", status_code=302)

@app.get("/messages/{username}", response_class=HTMLResponse)
def conversation(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user): return HTMLResponse(BLOCKED_RESPONSE)
    user.last_seen = datetime.utcnow()
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other: return RedirectResponse("/messages", status_code=302)
    msgs = db.query(models.Message).filter(
        ((models.Message.sender_id == user.id) & (models.Message.receiver_id == other.id)) |
        ((models.Message.sender_id == other.id) & (models.Message.receiver_id == user.id))
    ).order_by(models.Message.created_at).all()
    for msg in msgs:
        if msg.disappear_at and datetime.utcnow() > msg.disappear_at:
            msg.is_deleted = True
            msg.content = ""
        if msg.receiver_id == user.id and not msg.is_read and not msg.is_deleted:
            msg.is_read = True
            msg.is_delivered = True
    db.commit()
    for msg in msgs:
        if msg.content_encrypted and not msg.content:
            msg.content = auth.decrypt_message(msg.content_encrypted)
    is_pinned = db.query(models.PinnedChat).filter(models.PinnedChat.user_id == user.id, models.PinnedChat.pinned_user_id == other.id).first() is not None
    is_muted = db.query(models.MutedChat).filter(models.MutedChat.user_id == user.id, models.MutedChat.muted_user_id == other.id).first() is not None
    pinned_message = db.query(models.Message).filter(
        ((models.Message.sender_id == user.id) & (models.Message.receiver_id == other.id)) |
        ((models.Message.sender_id == other.id) & (models.Message.receiver_id == user.id)),
        models.Message.is_pinned == True
    ).first()
    return templates.TemplateResponse(request, "conversation.html", {
        "user": user, "other": other, "messages": msgs,
        "unread": get_unread(user, db), "unread_msg": 0,
        "is_online": is_user_online, "is_pinned": is_pinned,
        "is_muted": is_muted, "pinned_message": pinned_message
    })

@app.post("/messages/{username}")
async def send_message(username: str, request: Request,
    content: str = Form(""), image: UploadFile = File(None),
    voice: UploadFile = File(None), file: UploadFile = File(None),
    reply_to_id: int = Form(None), disappear: str = Form(""),
    db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user): return HTMLResponse(BLOCKED_RESPONSE)
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other: return RedirectResponse("/messages", status_code=302)
    image_url = ""
    voice_url = ""
    file_url = ""
    file_name = ""
    file_size = 0
    is_video_circle = False
    if image and image.filename:
        url, _ = save_media_file(image)
        if url: image_url = url
    if voice and voice.filename:
        content_type = (voice.content_type or "").lower()
        if "video" in content_type:
            url, _ = save_media_file(voice)
            if url:
                image_url = url
                is_video_circle = True
        else:
            url = save_audio_file(voice)
            if url: voice_url = url
    if file and file.filename:
        furl, fname, fsize = save_file_attachment(file)
        if furl:
            file_url = furl
            file_name = fname
            file_size = fsize
    if not content.strip() and not image_url and not voice_url and not file_url:
        return RedirectResponse(f"/messages/{username}", status_code=302)
    encrypted = auth.encrypt_message(content) if content.strip() else ""
    disappear_at = None
    if disappear == "24h": disappear_at = datetime.utcnow() + timedelta(hours=24)
    elif disappear == "1h": disappear_at = datetime.utcnow() + timedelta(hours=1)
    msg = models.Message(
        sender_id=user.id, receiver_id=other.id,
        content=content, content_encrypted=encrypted,
        image=image_url, voice=voice_url,
        file_url=file_url, file_name=file_name, file_size=file_size,
        is_video_circle=is_video_circle, is_delivered=True,
        reply_to_id=reply_to_id, disappear_at=disappear_at
    )
    db.add(msg)
    db.commit()
    update_task_progress(user, "message", db)
    return RedirectResponse(f"/messages/{username}", status_code=302)

@app.post("/messages/{username}/clear")
def clear_chat(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other: return RedirectResponse("/messages", status_code=302)
    msgs = db.query(models.Message).filter(
        ((models.Message.sender_id == user.id) & (models.Message.receiver_id == other.id)) |
        ((models.Message.sender_id == other.id) & (models.Message.receiver_id == user.id))
    ).all()
    for msg in msgs:
        msg.is_deleted = True
        msg.content = ""
    db.commit()
    return RedirectResponse(f"/messages/{username}", status_code=302)

@app.post("/api/message/pin/{message_id}")
def pin_message(message_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"ok": False})
    msg = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not msg: return JSONResponse({"ok": False})
    if msg.sender_id != user.id and msg.receiver_id != user.id: return JSONResponse({"ok": False})
    msg.is_pinned = not msg.is_pinned
    db.commit()
    return JSONResponse({"ok": True, "pinned": msg.is_pinned})

@app.post("/api/message/edit/{message_id}")
async def edit_message(message_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"ok": False})
    data = await request.json()
    new_content = data.get("content", "").strip()
    if not new_content: return JSONResponse({"ok": False})
    msg = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not msg or msg.sender_id != user.id or msg.is_deleted: return JSONResponse({"ok": False})
    msg.content = new_content
    msg.content_encrypted = auth.encrypt_message(new_content)
    msg.is_edited = True
    msg.edited_at = datetime.utcnow()
    db.commit()
    return JSONResponse({"ok": True})

@app.get("/messages/{username}/search", response_class=HTMLResponse)
def search_messages(username: str, request: Request, q: str = "", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other: return RedirectResponse("/messages", status_code=302)
    results = []
    if q:
        results = db.query(models.Message).filter(
            ((models.Message.sender_id == user.id) & (models.Message.receiver_id == other.id)) |
            ((models.Message.sender_id == other.id) & (models.Message.receiver_id == user.id)),
            models.Message.content.ilike(f"%{q}%"),
            models.Message.is_deleted == False
        ).order_by(models.Message.created_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "message_search.html", {
        "user": user, "other": other, "results": results, "q": q,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db)
    })

@app.post("/story/upload")
async def story_upload(request: Request, media: UploadFile = File(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    url, type_or_error = save_media_file(media)
    if url is None: return RedirectResponse("/", status_code=302)
    expires = datetime.utcnow() + timedelta(hours=24)
    story = models.Story(user_id=user.id, media_url=url, media_type=type_or_error, expires_at=expires)
    db.add(story)
    db.commit()
    update_task_progress(user, "story", db)
    check_and_give_achievements(user, db)
    return RedirectResponse("/", status_code=302)

@app.get("/story/{story_id}", response_class=HTMLResponse)
def story_view(story_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story or story.expires_at < datetime.utcnow():
        return RedirectResponse("/", status_code=302)
    if user and user.id != story.user_id:
        existing_view = db.query(models.StoryView).filter(models.StoryView.story_id == story_id, models.StoryView.user_id == user.id).first()
        if not existing_view:
            db.add(models.StoryView(story_id=story_id, user_id=user.id))
            db.commit()
    all_stories = db.query(models.Story).filter(models.Story.user_id == story.user_id, models.Story.expires_at > datetime.utcnow()).order_by(models.Story.created_at).all()
    current_index = next((i for i, s in enumerate(all_stories) if s.id == story_id), 0)
    views_count = db.query(models.StoryView).filter(models.StoryView.story_id == story_id).count()
    return templates.TemplateResponse(request, "story_view.html", {
        "user": user, "story": story, "all_stories": all_stories,
        "current_index": current_index, "views_count": views_count,
        "unread": get_unread(user, db) if user else 0,
        "unread_msg": get_unread_messages(user, db) if user else 0
    })

@app.post("/story/delete/{story_id}")
def story_delete(story_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if story and (story.user_id == user.id or user.is_owner):
        delete_media_file(story.media_url)
        db.query(models.StoryView).filter(models.StoryView.story_id == story_id).delete()
        db.delete(story)
        db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/delete/{post_id}")
def delete_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if can_moderate(user):
        post = db.query(models.Post).filter(models.Post.id == post_id).first()
    else:
        post = db.query(models.Post).filter(models.Post.id == post_id, models.Post.user_id == user.id).first()
    if post:
        if post.image: delete_media_file(post.image)
        for pm in post.media_items:
            delete_media_file(pm.media_url)
            db.delete(pm)
        db.query(models.Like).filter(models.Like.post_id == post_id).delete()
        db.query(models.Comment).filter(models.Comment.post_id == post_id).delete()
        db.query(models.Notification).filter(models.Notification.post_id == post_id).delete()
        db.query(models.Whale).filter(models.Whale.post_id == post_id).delete()
        db.query(models.Reaction).filter(models.Reaction.post_id == post_id).delete()
        db.query(models.Post).filter(models.Post.repost_id == post_id).delete()
        db.query(models.Bookmark).filter(models.Bookmark.post_id == post_id).delete()
        if user.pinned_post_id == post_id: user.pinned_post_id = None
        db.delete(post)
        db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/repost/{post_id}")
def repost(post_id: int, request: Request, comment: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    original = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not original: return RedirectResponse("/", status_code=302)
    existing = db.query(models.Post).filter(models.Post.user_id == user.id, models.Post.repost_id == post_id).first()
    if existing: return RedirectResponse(f"/post/{post_id}", status_code=302)
    repost_post = models.Post(content=original.content, user_id=user.id, image=original.image, media_type=original.media_type, is_repost=True, repost_id=post_id, original_comment=comment, is_published=True)
    db.add(repost_post)
    db.commit()
    check_and_give_achievements(user, db)
    return RedirectResponse("/", status_code=302)

@app.post("/pin/{post_id}")
def pin_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    user.pinned_post_id = None if user.pinned_post_id == post_id else post_id
    db.commit()
    return RedirectResponse(f"/profile/{user.username}", status_code=302)

@app.post("/bookmark/{post_id}")
def bookmark_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    existing = db.query(models.Bookmark).filter(models.Bookmark.user_id == user.id, models.Bookmark.post_id == post_id).first()
    if existing: db.delete(existing)
    else: db.add(models.Bookmark(user_id=user.id, post_id=post_id))
    db.commit()
    return JSONResponse({"ok": True})

@app.get("/bookmarks", response_class=HTMLResponse)
def bookmarks_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    bookmarks = db.query(models.Bookmark).filter(models.Bookmark.user_id == user.id).order_by(models.Bookmark.created_at.desc()).all()
    posts = [b.post for b in bookmarks if b.post]
    bookmarked_ids = set(b.post_id for b in user.bookmarks)
    liked_ids = set(l.post_id for l in db.query(models.Like).filter(models.Like.user_id == user.id).all())
    return templates.TemplateResponse(request, "bookmarks.html", {
        "user": user, "posts": posts,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "render_content": render_content, "is_online": is_user_online,
        "bookmarked_ids": bookmarked_ids, "is_plus": is_user_plus(user),
        "liked_ids": liked_ids, "whaled_ids": set()
    })

@app.get("/post/{post_id}", response_class=HTMLResponse)
def post_page(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if user:
        user.last_seen = datetime.utcnow()
        db.commit()
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post: return RedirectResponse("/", status_code=302)
    post.views = (post.views or 0) + 1
    db.commit()
    liked = False
    whaled = False
    if user:
        liked = db.query(models.Like).filter(models.Like.user_id == user.id, models.Like.post_id == post_id).first() is not None
        whaled = db.query(models.Whale).filter(models.Whale.user_id == user.id, models.Whale.post_id == post_id).first() is not None
    return templates.TemplateResponse(request, "post.html", {
        "user": user, "post": post,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "is_plus": is_user_plus(user), "render_content": render_content,
        "is_online": is_user_online, "user_liked": liked, "user_whaled": whaled
    })

@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    user_results = []
    post_results = []
    if q:
        user_results = db.query(models.User).filter(models.User.username.ilike(f"%{q}%") | models.User.name.ilike(f"%{q}%")).limit(10).all()
        post_results = db.query(models.Post).filter(models.Post.is_published == True, models.Post.content.ilike(f"%{q}%")).order_by(models.Post.created_at.desc()).limit(20).all()
    return templates.TemplateResponse(request, "search.html", {
        "user": user, "results": user_results, "post_results": post_results, "q": q,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "render_content": render_content
    })

@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    user.last_seen = datetime.utcnow()
    db.commit()
    notifs = db.query(models.Notification).filter(models.Notification.user_id == user.id).order_by(models.Notification.created_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "notifications.html", {
        "user": user, "notifications": notifs,
        "unread": 0, "unread_msg": get_unread_messages(user, db)
    })

@app.post("/notifications/read")
def notifications_read(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    db.query(models.Notification).filter(models.Notification.user_id == user.id).update({"is_read": True})
    db.commit()
    return RedirectResponse("/notifications", status_code=302)

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    current_token = request.cookies.get("token")
    current_hash = hashlib.sha256(current_token.encode()).hexdigest() if current_token else ""
    sessions = db.query(models.UserSession).filter(models.UserSession.user_id == user.id, models.UserSession.is_active == True).order_by(models.UserSession.last_active.desc()).all()
    return templates.TemplateResponse(request, "settings.html", {
        "user": user, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "is_plus": is_user_plus(user), "sessions": sessions, "current_hash": current_hash
    })

@app.post("/settings")
async def settings_save(request: Request, name: str = Form(...), bio: str = Form(""),
    username: str = Form(...), emoji_status: str = Form(""),
    website: str = Form(""), birthday: str = Form(""), city: str = Form(""),
    telegram_link: str = Form(""), youtube_link: str = Form(""), tiktok_link: str = Form(""),
    is_private: str = Form(""), theme: str = Form("light"),
    avatar: UploadFile = File(None), cover: UploadFile = File(None),
    plus_color: str = Form("#a855f7"), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    error = validate_username(username)
    if error: return templates.TemplateResponse(request, "settings.html", {"user": user, "error": error, "is_plus": is_user_plus(user), "unread": 0, "unread_msg": 0})
    existing = db.query(models.User).filter(models.User.username == username, models.User.id != user.id).first()
    if existing: return templates.TemplateResponse(request, "settings.html", {"user": user, "error": f"Никнейм @{username} уже занят", "is_plus": is_user_plus(user), "unread": 0, "unread_msg": 0})
    if avatar and avatar.filename:
        content_type = (avatar.content_type or "").lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            return templates.TemplateResponse(request, "settings.html", {"user": user, "error": "Для аватарки разрешены только JPG, PNG, WEBP", "is_plus": is_user_plus(user), "unread": 0, "unread_msg": 0})
        contents = await avatar.read()
        if len(contents) > MAX_IMAGE_SIZE:
            return templates.TemplateResponse(request, "settings.html", {"user": user, "error": "Фото слишком большое", "is_plus": is_user_plus(user), "unread": 0, "unread_msg": 0})
        try:
            img = Image.open(io.BytesIO(contents))
            img = _auto_rotate(img)
            img.thumbnail((400, 400), Image.LANCZOS)
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            filename = f"avatar_{uuid.uuid4().hex}.jpg"
            filepath = os.path.join(UPLOAD_DIR, filename)
            img.save(filepath, quality=85, optimize=True)
            if user.avatar: delete_media_file(user.avatar)
            user.avatar = f"/uploads/{filename}"
        except Exception as e:
            print(f"Avatar error: {e}")
    if cover and cover.filename:
        content_type = (cover.content_type or "").lower()
        if content_type in ALLOWED_IMAGE_TYPES:
            contents = await cover.read()
            if len(contents) <= MAX_IMAGE_SIZE:
                try:
                    img = Image.open(io.BytesIO(contents))
                    img = _auto_rotate(img)
                    img.thumbnail((1200, 400), Image.LANCZOS)
                    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                    filename = f"cover_{uuid.uuid4().hex}.jpg"
                    filepath = os.path.join(UPLOAD_DIR, filename)
                    img.save(filepath, quality=85, optimize=True)
                    if user.cover: delete_media_file(user.cover)
                    user.cover = f"/uploads/{filename}"
                except Exception: pass
    if is_user_plus(user) and re.match(r'^#[0-9a-fA-F]{6}$', plus_color):
        user.plus_color = plus_color
    allowed_emojis = ["", "🔥", "❤️", "😎", "🚀", "💎", "⭐", "🎮", "🎵", "📚", "💻", "🌍"]
    if emoji_status in allowed_emojis: user.emoji_status = emoji_status
    user.name = name
    user.bio = bio
    user.username = username
    user.website = website[:100] if website else ""
    user.birthday = birthday[:20] if birthday else ""
    user.city = city[:50] if city else ""
    user.telegram_link = telegram_link[:100] if telegram_link else ""
    user.youtube_link = youtube_link[:100] if youtube_link else ""
    user.tiktok_link = tiktok_link[:100] if tiktok_link else ""
    user.is_private = is_private == "on"
    user.theme = theme if theme in ["light", "dark"] else "light"
    db.commit()
    token = auth.create_token({"sub": username})
    response = RedirectResponse(f"/profile/{username}", status_code=302)
    response.set_cookie("token", token)
    return response

@app.post("/settings/password")
def change_password(request: Request, old_password: str = Form(...), new_password: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    if not auth.verify_password(old_password, user.password):
        return templates.TemplateResponse(request, "settings.html", {"user": user, "error": "Старый пароль неверный", "is_plus": is_user_plus(user), "unread": 0, "unread_msg": 0})
    error = validate_password(new_password)
    if error:
        return templates.TemplateResponse(request, "settings.html", {"user": user, "error": error, "is_plus": is_user_plus(user), "unread": 0, "unread_msg": 0})
    user.password = auth.hash_password(new_password)
    db.commit()
    return templates.TemplateResponse(request, "settings.html", {"user": user, "success": "Пароль успешно изменён", "is_plus": is_user_plus(user), "unread": 0, "unread_msg": 0})

@app.post("/activate_plus")
def activate_plus(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    promo = db.query(models.Promocode).filter(models.Promocode.code == code.upper().strip(), models.Promocode.is_active == True).first()
    if not promo or promo.uses >= promo.max_uses:
        return templates.TemplateResponse(request, "plus.html", {"user": user, "unread": 0, "unread_msg": 0, "is_plus": is_user_plus(user), "error": "Промокод не найден или уже использован"})
    promo.uses += 1
    if promo.uses >= promo.max_uses: promo.is_active = False
    user.is_plus = True
    user.plus_until = datetime.utcnow() + timedelta(days=promo.days)
    db.commit()
    check_and_give_achievements(user, db)
    return templates.TemplateResponse(request, "plus.html", {"user": user, "unread": 0, "unread_msg": 0, "is_plus": True, "success": f"🎉 Quant Plus активирован на {promo.days} дней!"})

@app.get("/plus", response_class=HTMLResponse)
def plus_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    return templates.TemplateResponse(request, "plus.html", {
        "user": user, "unread": get_unread(user, db) if user else 0,
        "unread_msg": get_unread_messages(user, db) if user else 0,
        "is_plus": is_user_plus(user)
    })

@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    return templates.TemplateResponse(request, "support.html", {"user": user, "unread": get_unread(user, db) if user else 0, "unread_msg": get_unread_messages(user, db) if user else 0})

@app.post("/support")
def support_submit(request: Request, subject: str = Form(...), message: str = Form(...), email: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    user_email = user.email if user else email.strip()
    if not user_email:
        return templates.TemplateResponse(request, "support.html", {"user": user, "unread": 0, "unread_msg": 0, "error": "Укажи email"})
    owner = db.query(models.User).filter(models.User.username == "rubl").first()
    if owner:
        db.add(models.Notification(user_id=owner.id, from_user_id=user.id if user else None, type="support", text=f"📧 {user.username if user else user_email}\n📌 {subject}\n💬 {message[:300]}", reply_email=user_email if not user else ""))
        db.commit()
    try:
        from email_service import send_support_confirmation
        send_support_confirmation(user_email, subject)
    except: pass
    return templates.TemplateResponse(request, "support.html", {"user": user, "unread": 0, "unread_msg": 0, "success": True})

@app.post("/support/reply/{notif_id}")
def support_reply(notif_id: int, request: Request, reply: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    notif = db.query(models.Notification).filter(models.Notification.id == notif_id).first()
    if not notif: return RedirectResponse("/notifications", status_code=302)
    if notif.from_user_id:
        db.add(models.Notification(user_id=notif.from_user_id, from_user_id=user.id, type="support_reply", text=reply))
        db.commit()
    elif notif.reply_email:
        try:
            from email_service import send_support_reply
            send_support_reply(notif.reply_email, reply)
        except: pass
    return RedirectResponse("/notifications", status_code=302)

@app.get("/hashtag/{tag}", response_class=HTMLResponse)
def hashtag_page(tag: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    posts = db.query(models.Post).filter(models.Post.is_published == True, models.Post.content.ilike(f"%#{tag}%")).order_by(models.Post.created_at.desc()).limit(100).all()
    trend = db.query(models.Trend).filter(models.Trend.tag == tag.lower()).first()
    return templates.TemplateResponse(request, "hashtag.html", {
        "user": user, "posts": posts, "tag": tag, "trend": trend,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "render_content": render_content, "is_online": is_user_online
    })

@app.get("/terms", response_class=HTMLResponse)
def terms(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    return templates.TemplateResponse(request, "terms.html", {"user": user, "unread": get_unread(user, db) if user else 0, "unread_msg": get_unread_messages(user, db) if user else 0})

@app.get("/qr/{username}", response_class=HTMLResponse)
def qr_page(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    profile_user = db.query(models.User).filter(models.User.username == username).first()
    if not profile_user: return RedirectResponse("/", status_code=302)
    try:
        import qrcode
        import qrcode.image.svg
        factory = qrcode.image.svg.SvgPathImage
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=2)
        qr.add_data(f"https://quantru.duckdns.org/profile/{username}")
        qr.make(fit=True)
        img = qr.make_image(image_factory=factory)
        buf = io.BytesIO()
        img.save(buf)
        qr_svg = buf.getvalue().decode("utf-8")
    except:
        qr_svg = ""
    return templates.TemplateResponse(request, "qr.html", {
        "user": user, "profile_user": profile_user, "qr_svg": qr_svg,
        "profile_url": f"https://quantru.duckdns.org/profile/{username}",
        "unread": get_unread(user, db) if user else 0, "unread_msg": get_unread_messages(user, db) if user else 0
    })

@app.post("/block_user/{username}")
def block_user_action(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if not target or target.id == user.id: return RedirectResponse("/", status_code=302)
    existing = db.query(models.UserBlock).filter(models.UserBlock.blocker_id == user.id, models.UserBlock.blocked_id == target.id).first()
    if existing: db.delete(existing)
    else: db.add(models.UserBlock(blocker_id=user.id, blocked_id=target.id))
    db.commit()
    return RedirectResponse(f"/profile/{username}", status_code=302)

@app.post("/react/{post_id}")
def react_post(post_id: int, request: Request, emoji: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not is_user_plus(user): return RedirectResponse("/", status_code=302)
    allowed = ["🔥", "😂", "😮", "😢", "👏", "🎉"]
    if emoji not in allowed: return RedirectResponse("/", status_code=302)
    existing = db.query(models.Reaction).filter(models.Reaction.user_id == user.id, models.Reaction.post_id == post_id, models.Reaction.emoji == emoji).first()
    if existing: db.delete(existing)
    else: db.add(models.Reaction(user_id=user.id, post_id=post_id, emoji=emoji))
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/poll/vote/{option_id}")
def poll_vote(option_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    option = db.query(models.PollOption).filter(models.PollOption.id == option_id).first()
    if not option: return RedirectResponse("/", status_code=302)
    poll = option.poll
    existing = db.query(models.PollVote).filter(models.PollVote.user_id == user.id, models.PollVote.poll_id == poll.id).first()
    if existing: return RedirectResponse(f"/post/{poll.post_id}", status_code=302)
    db.add(models.PollVote(user_id=user.id, option_id=option_id, poll_id=poll.id))
    db.commit()
    return RedirectResponse(f"/post/{poll.post_id}", status_code=302)

# ADMIN

@app.post("/admin/block/{username}")
def admin_block_user(username: str, request: Request, days: int = Form(1), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target and not target.is_owner:
        target.is_blocked = True
        target.blocked_until = datetime.utcnow() + timedelta(days=days)
        db.commit()
    return RedirectResponse(f"/admin?tab=users&q={username}", status_code=302)

@app.post("/admin/unblock/{username}")
def admin_unblock_user(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target:
        target.is_blocked = False
        target.blocked_until = None
        db.commit()
    return RedirectResponse(f"/admin?tab=users&q={username}", status_code=302)

@app.post("/admin/create_promo")
def create_promo(request: Request, code: str = Form(...), days: int = Form(30), max_uses: int = Form(1), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    code = code.upper().strip()
    if not db.query(models.Promocode).filter(models.Promocode.code == code).first():
        db.add(models.Promocode(code=code, days=days, max_uses=max_uses))
        db.commit()
    return RedirectResponse("/admin?tab=promocodes", status_code=302)

@app.post("/admin/star/{username}")
def give_star(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target:
        target.is_starred = not target.is_starred
        db.commit()
    return RedirectResponse(f"/admin?tab=users&q={username}", status_code=302)

@app.post("/admin/verify/{username}")
def give_verify(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target:
        target.is_verified_badge = not target.is_verified_badge
        db.commit()
    return RedirectResponse(f"/admin?tab=users&q={username}", status_code=302)

@app.post("/admin/mod/{username}")
def give_mod(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target:
        target.is_moderator = not target.is_moderator
        db.commit()
    return RedirectResponse(f"/admin?tab=users&q={username}", status_code=302)

@app.post("/admin/give_plus/{username}")
def give_plus(username: str, request: Request, days: int = Form(30), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target:
        target.is_plus = True
        target.plus_until = datetime.utcnow() + timedelta(days=days)
        db.commit()
    return RedirectResponse(f"/admin?tab=users&q={username}", status_code=302)

@app.post("/admin/stopword/add")
def add_stop_word(request: Request, word: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    word = word.strip().lower()
    if word and not db.query(models.StopWord).filter(models.StopWord.word == word).first():
        db.add(models.StopWord(word=word))
        db.commit()
    return RedirectResponse("/admin?tab=settings", status_code=302)

@app.post("/admin/stopword/delete/{word_id}")
def delete_stop_word(word_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    sw = db.query(models.StopWord).filter(models.StopWord.id == word_id).first()
    if sw:
        db.delete(sw)
        db.commit()
    return RedirectResponse("/admin?tab=settings", status_code=302)

@app.post("/admin/delete_post/{post_id}")
def admin_delete_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not can_moderate(user): return RedirectResponse("/", status_code=302)
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if post:
        if post.image: delete_media_file(post.image)
        db.query(models.Like).filter(models.Like.post_id == post_id).delete()
        db.query(models.Comment).filter(models.Comment.post_id == post_id).delete()
        db.query(models.Notification).filter(models.Notification.post_id == post_id).delete()
        db.query(models.Whale).filter(models.Whale.post_id == post_id).delete()
        db.query(models.Reaction).filter(models.Reaction.post_id == post_id).delete()
        db.delete(post)
        db.commit()
    return RedirectResponse("/admin?tab=posts", status_code=302)

@app.post("/admin/notify_all")
def admin_notify_all(request: Request, text: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    all_users = db.query(models.User).all()
    for u in all_users:
        if u.id != user.id:
            db.add(models.Notification(user_id=u.id, from_user_id=user.id, type="system", text=text))
    db.commit()
    return RedirectResponse("/admin?tab=notify&sent=1", status_code=302)

@app.post("/admin/special_request/action/{req_id}")
def special_request_action(req_id: int, request: Request, action: str = Form(...), comment: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    req = db.query(models.SpecialRequest).filter(models.SpecialRequest.id == req_id).first()
    if not req: return RedirectResponse("/admin?tab=requests", status_code=302)
    req.status = action
    req.admin_comment = comment
    if action == "approve" and req.user:
        if req.type == "verify": req.user.is_verified_badge = True
        elif req.type == "star": req.user.is_starred = True
        elif req.type == "mod": req.user.is_moderator = True
        db.add(models.Notification(user_id=req.user_id, from_user_id=user.id, type="system", text=f"✅ Твоя заявка одобрена! {comment}"))
    elif action == "reject":
        db.add(models.Notification(user_id=req.user_id, from_user_id=user.id, type="system", text=f"❌ Твоя заявка отклонена. {comment}"))
    db.commit()
    return RedirectResponse("/admin?tab=requests", status_code=302)

@app.post("/admin/report/action/{report_id}")
def report_action(report_id: int, request: Request, action: str = Form(...), comment: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report: return RedirectResponse("/admin?tab=reports", status_code=302)
    report.status = action
    report.admin_comment = comment
    if action == "block" and report.target:
        report.target.is_blocked = True
        report.target.blocked_until = datetime.utcnow() + timedelta(days=7)
        db.add(models.Notification(user_id=report.target_id, from_user_id=user.id, type="system", text="Ваш аккаунт заблокирован по жалобе на 7 дней."))
    elif action == "warn" and report.target:
        db.add(models.Notification(user_id=report.target_id, from_user_id=user.id, type="system", text=f"⚠️ Предупреждение: {comment}"))
    if report.reporter_id:
        db.add(models.Notification(user_id=report.reporter_id, from_user_id=user.id, type="system", text=f"Ваша жалоба рассмотрена. Решение: {action}."))
    db.commit()
    return RedirectResponse("/admin?tab=reports", status_code=302)

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, tab: str = "stats", q: str = "", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", status_code=302)
    from sqlalchemy import func
    stats = {
        "total_users": db.query(models.User).count(),
        "new_today": db.query(models.User).filter(models.User.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)).count(),
        "new_week": db.query(models.User).filter(models.User.created_at >= datetime.utcnow() - timedelta(days=7)).count(),
        "total_posts": db.query(models.Post).filter(models.Post.is_published == True).count(),
        "posts_today": db.query(models.Post).filter(models.Post.is_published == True, models.Post.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)).count(),
        "active_24h": db.query(models.User).filter(models.User.last_seen >= datetime.utcnow() - timedelta(hours=24)).count(),
        "total_messages": db.query(models.Message).filter(models.Message.is_deleted == False).count(),
        "plus_users": db.query(models.User).filter(models.User.is_plus == True).count(),
        "total_reels": db.query(models.Reel).count(),
        "total_stories": db.query(models.Story).count(),
    }
    users = []
    if tab == "users":
        if q: users = db.query(models.User).filter(models.User.username.ilike(f"%{q}%") | models.User.name.ilike(f"%{q}%") | models.User.email.ilike(f"%{q}%")).limit(50).all()
        else: users = db.query(models.User).order_by(models.User.created_at.desc()).limit(50).all()
    posts = db.query(models.Post).filter(models.Post.is_published == True).order_by(models.Post.created_at.desc()).limit(50).all() if tab == "posts" else []
    promocodes = db.query(models.Promocode).order_by(models.Promocode.created_at.desc()).all() if tab == "promocodes" else []
    stop_words = db.query(models.StopWord).order_by(models.StopWord.created_at.desc()).all() if tab == "settings" else []
    reports = db.query(models.Report).order_by(models.Report.created_at.desc()).limit(50).all() if tab == "reports" else []
    special_requests = db.query(models.SpecialRequest).order_by(models.SpecialRequest.created_at.desc()).limit(50).all() if tab == "requests" else []
    raffle = get_current_raffle(db) if tab == "raffle" else None
    raffle_entries = db.query(models.RaffleEntry).filter(models.RaffleEntry.raffle_id == raffle.id).order_by(models.RaffleEntry.tickets.desc()).all() if raffle else []
    new_reports_count = db.query(models.Report).filter(models.Report.status == "new").count()
    new_requests_count = db.query(models.SpecialRequest).filter(models.SpecialRequest.status == "new").count()
    return templates.TemplateResponse(request, "admin.html", {
        "user": user, "tab": tab, "q": q, "stats": stats,
        "users": users, "posts": posts, "promocodes": promocodes,
        "stop_words": stop_words, "reports": reports,
        "special_requests": special_requests, "raffle": raffle, "raffle_entries": raffle_entries,
        "new_reports_count": new_reports_count, "new_requests_count": new_requests_count,
        "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db),
        "is_plus": is_user_plus(user), "render_content": render_content
    })

@app.post("/sessions/revoke/{session_id}")
def revoke_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    session = db.query(models.UserSession).filter(models.UserSession.id == session_id, models.UserSession.user_id == user.id).first()
    if session:
        session.is_active = False
        db.commit()
    return RedirectResponse("/settings", status_code=302)

@app.post("/sessions/revoke_all")
def revoke_all_sessions(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    current_token = request.cookies.get("token")
    current_hash = hashlib.sha256(current_token.encode()).hexdigest() if current_token else ""
    db.query(models.UserSession).filter(models.UserSession.user_id == user.id, models.UserSession.token_hash != current_hash).update({"is_active": False})
    db.commit()
    return RedirectResponse("/settings", status_code=302)

@app.get("/blocked", response_class=HTMLResponse)
def blocked_users_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    blocked = db.query(models.UserBlock).filter(models.UserBlock.blocker_id == user.id).all()
    return templates.TemplateResponse(request, "blocked.html", {"user": user, "blocked": blocked, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "is_plus": is_user_plus(user)})

@app.get("/mentions", response_class=HTMLResponse)
def mentions_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    mentions = db.query(models.Notification).filter(models.Notification.user_id == user.id, models.Notification.type == "mention").order_by(models.Notification.created_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "mentions.html", {"user": user, "mentions": mentions, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "is_plus": is_user_plus(user)})

@app.get("/special_request", response_class=HTMLResponse)
def special_request_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    existing = db.query(models.SpecialRequest).filter(models.SpecialRequest.user_id == user.id, models.SpecialRequest.status == "new").first()
    return templates.TemplateResponse(request, "special_request.html", {"user": user, "existing": existing, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "is_plus": is_user_plus(user)})

@app.post("/special_request")
def special_request_submit(request: Request, type: str = Form(...), reason: str = Form(...), links: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    existing = db.query(models.SpecialRequest).filter(models.SpecialRequest.user_id == user.id, models.SpecialRequest.status == "new").first()
    if existing: return RedirectResponse("/special_request", status_code=302)
    req = models.SpecialRequest(user_id=user.id, type=type, reason=reason, links=links)
    db.add(req)
    owner = db.query(models.User).filter(models.User.username == "rubl").first()
    if owner:
        type_labels = {"verify": "Верификация ✔", "star": "Особый статус ⭐", "mod": "Модератор 🛡️"}
        db.add(models.Notification(user_id=owner.id, from_user_id=user.id, type="system", text=f"💎 Заявка на {type_labels.get(type, type)} от @{user.username}\n{reason[:200]}"))
    db.commit()
    return templates.TemplateResponse(request, "special_request.html", {"user": user, "existing": req, "success": True, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "is_plus": is_user_plus(user)})

@app.post("/report/{username}")
async def report_submit(username: str, request: Request, reason: str = Form(...), text: str = Form(""), image_1: UploadFile = File(None), image_2: UploadFile = File(None), image_3: UploadFile = File(None), image_4: UploadFile = File(None), image_5: UploadFile = File(None), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if not target or target.id == user.id: return RedirectResponse("/", status_code=302)
    images = []
    for img_upload in [image_1, image_2, image_3, image_4, image_5]:
        if img_upload and img_upload.filename:
            url, _ = save_media_file(img_upload)
            images.append(url or "")
        else:
            images.append("")
    report = models.Report(reporter_id=user.id, target_id=target.id, reason=reason, text=text, image_1=images[0], image_2=images[1], image_3=images[2], image_4=images[3], image_5=images[4])
    db.add(report)
    owner = db.query(models.User).filter(models.User.username == "rubl").first()
    if owner:
        db.add(models.Notification(user_id=owner.id, from_user_id=user.id, type="report", text=f"🚩 @{user.username} пожаловался на @{target.username}\nПричина: {reason}\n{text[:200]}"))
    db.commit()
    return RedirectResponse(f"/profile/{username}?reported=1", status_code=302)

@app.get("/auth/yandex")
def yandex_login():
    from yandex_auth import YANDEX_CLIENT_ID, YANDEX_REDIRECT_URI, YANDEX_AUTH_URL
    return RedirectResponse(f"{YANDEX_AUTH_URL}?response_type=code&client_id={YANDEX_CLIENT_ID}&redirect_uri={YANDEX_REDIRECT_URI}")

@app.get("/auth/yandex/callback")
async def yandex_callback(code: str, request: Request, db: Session = Depends(get_db)):
    import httpx
    from yandex_auth import YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET, YANDEX_REDIRECT_URI, YANDEX_TOKEN_URL, YANDEX_USER_URL
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(YANDEX_TOKEN_URL, data={"grant_type": "authorization_code", "code": code, "client_id": YANDEX_CLIENT_ID, "client_secret": YANDEX_CLIENT_SECRET, "redirect_uri": YANDEX_REDIRECT_URI})
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token: return RedirectResponse("/login?error=yandex", status_code=302)
        user_resp = await client.get(YANDEX_USER_URL, headers={"Authorization": f"OAuth {access_token}"})
        yandex_user = user_resp.json()
    yandex_id = str(yandex_user.get("id", ""))
    email = yandex_user.get("default_email", f"yandex_{yandex_id}@yandex.ru")
    name = yandex_user.get("real_name") or yandex_user.get("display_name") or "Пользователь"
    username_base = re.sub(r'[^\w\.\-]', '_', yandex_user.get("login", f"yandex_{yandex_id}"))[:28]
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        username = username_base
        counter = 1
        while db.query(models.User).filter(models.User.username == username).first():
            username = f"{username_base}_{counter}"
            counter += 1
        user = models.User(name=name, username=username, email=email, password=auth.hash_password(yandex_id + "yandex"), is_verified=True, email_verified=True)
        db.add(user)
        db.commit()
    token = auth.create_token({"sub": user.username})
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("token", token)
    save_session(user, request, token, db)
    return response

# API

@app.get("/api/messages/{username}")
def api_messages(username: str, request: Request, after: int = 0, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"messages": []})
    user.last_seen = datetime.utcnow()
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other: return JSONResponse({"messages": []})
    msgs = db.query(models.Message).filter(
        ((models.Message.sender_id == user.id) & (models.Message.receiver_id == other.id)) |
        ((models.Message.sender_id == other.id) & (models.Message.receiver_id == user.id))
    ).filter(models.Message.id > after).order_by(models.Message.created_at).all()
    for msg in msgs:
        if msg.disappear_at and datetime.utcnow() > msg.disappear_at:
            msg.is_deleted = True
            msg.content = ""
        if msg.receiver_id == user.id and not msg.is_read and not msg.is_deleted:
            msg.is_read = True
            msg.is_delivered = True
        if msg.content_encrypted and not msg.is_deleted:
            msg.content = auth.decrypt_message(msg.content_encrypted)
    db.commit()
    result = []
    for m in msgs:
        reactions = {}
        for r in m.msg_reactions:
            reactions[r.emoji] = reactions.get(r.emoji, 0) + 1
        reply_content = ""
        if m.reply_to and not m.reply_to.is_deleted:
            reply_content = m.reply_to.content[:50]
        result.append({
            "id": m.id, "sender_id": m.sender_id,
            "content": "" if m.is_deleted else m.content,
            "image": "" if m.is_deleted else (m.image or ""),
            "voice": "" if m.is_deleted else (m.voice or ""),
            "file_url": "" if m.is_deleted else (m.file_url or ""),
            "file_name": "" if m.is_deleted else (m.file_name or ""),
            "file_size": 0 if m.is_deleted else (m.file_size or 0),
            "is_video_circle": m.is_video_circle,
            "time": m.created_at.strftime("%H:%M"),
            "is_read": m.is_read, "is_delivered": m.is_delivered,
            "is_deleted": m.is_deleted, "is_edited": m.is_edited,
            "is_pinned": m.is_pinned,
            "reply_to_id": m.reply_to_id, "reply_content": reply_content,
            "forwarded_from_id": m.forwarded_from_id,
            "forwarded_from_name": (m.forwarded_from.name or m.forwarded_from.username) if m.forwarded_from else None,
            "reactions": reactions
        })
    return JSONResponse({"messages": result})

@app.post("/api/typing/{username}")
def api_typing(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"ok": False})
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other: return JSONResponse({"ok": False})
    user.last_seen = datetime.utcnow()
    ts = db.query(models.TypingStatus).filter(models.TypingStatus.user_id == user.id, models.TypingStatus.target_id == other.id).first()
    if ts: ts.updated_at = datetime.utcnow()
    else: db.add(models.TypingStatus(user_id=user.id, target_id=other.id))
    db.commit()
    return JSONResponse({"ok": True})

@app.get("/api/typing/{username}")
def api_typing_check(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"typing": False})
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other: return JSONResponse({"typing": False})
    threshold = datetime.utcnow() - timedelta(seconds=4)
    ts = db.query(models.TypingStatus).filter(models.TypingStatus.user_id == other.id, models.TypingStatus.target_id == user.id, models.TypingStatus.updated_at > threshold).first()
    return JSONResponse({"typing": ts is not None})

@app.get("/api/users/search")
def api_users_search(q: str = "", db: Session = Depends(get_db)):
    if not q: return JSONResponse({"users": []})
    results = db.query(models.User).filter(models.User.username.ilike(f"{q}%")).limit(5).all()
    return JSONResponse({"users": [{"username": u.username, "name": u.name or u.username} for u in results]})

@app.get("/api/feed/new")
def api_feed_new(request: Request, after: int = 0, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if user: user.last_seen = datetime.utcnow()
    posts = db.query(models.Post).filter(models.Post.is_published == True, models.Post.id > after).order_by(models.Post.created_at.desc()).limit(20).all()
    result = [{"id": p.id, "content": p.content, "author_username": p.author.username, "author_name": p.author.name or p.author.username, "author_avatar": p.author.avatar or "", "created_at": p.created_at.strftime("%d.%m.%Y %H:%M"), "likes": len(p.likes), "comments": len(p.comments), "image": p.image or "", "media_type": p.media_type or "", "is_repost": p.is_repost} for p in posts]
    if user: db.commit()
    return JSONResponse({"posts": result})

@app.post("/api/message/react/{message_id}")
async def react_to_message(message_id: int, request: Request, db: Session = Depends(get_db)):
    from collections import Counter
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"ok": False})
    data = await request.json()
    emoji = data.get("emoji", "")
    if emoji not in ["❤️", "😂", "😮", "👍", "🔥", "😢"]: return JSONResponse({"ok": False})
    msg = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not msg or msg.is_deleted: return JSONResponse({"ok": False})
    existing = db.query(models.MessageReaction).filter(models.MessageReaction.message_id == message_id, models.MessageReaction.user_id == user.id, models.MessageReaction.emoji == emoji).first()
    if existing: db.delete(existing)
    else: db.add(models.MessageReaction(message_id=message_id, user_id=user.id, emoji=emoji))
    db.commit()
    reactions = db.query(models.MessageReaction).filter(models.MessageReaction.message_id == message_id).all()
    counts = Counter(r.emoji for r in reactions)
    return JSONResponse({"ok": True, "reactions": dict(counts)})

@app.post("/api/message/delete/{message_id}")
def delete_message_api(message_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"ok": False})
    msg = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not msg or (msg.sender_id != user.id and not user.is_owner): return JSONResponse({"ok": False})
    msg.is_deleted = True
    msg.content = ""
    msg.image = ""
    msg.voice = ""
    msg.file_url = ""
    db.commit()
    return JSONResponse({"ok": True})

@app.post("/api/message/forward/{message_id}")
async def forward_message(message_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"ok": False})
    data = await request.json()
    other = db.query(models.User).filter(models.User.username == data.get("to_username", "")).first()
    if not other: return JSONResponse({"ok": False, "error": "Пользователь не найден"})
    msg = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not msg or msg.is_deleted: return JSONResponse({"ok": False})
    new_msg = models.Message(sender_id=user.id, receiver_id=other.id, content=msg.content, content_encrypted=auth.encrypt_message(msg.content), image=msg.image, voice=msg.voice, forwarded_from_id=msg.sender_id, is_delivered=True)
    db.add(new_msg)
    db.commit()
    return JSONResponse({"ok": True, "to": other.username})

@app.get("/api/ping")
def api_ping(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if user:
        user.last_seen = datetime.utcnow()
        current_token = request.cookies.get("token")
        if current_token:
            token_hash = hashlib.sha256(current_token.encode()).hexdigest()
            session = db.query(models.UserSession).filter(models.UserSession.token_hash == token_hash).first()
            if session: session.last_active = datetime.utcnow()
        db.commit()
    return JSONResponse({"ok": True})