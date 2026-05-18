from fastapi import FastAPI, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text, func, or_, and_
from database import engine, get_db, Base
from datetime import datetime, timedelta, date
import models, auth, re, os, uuid, io, json
from PIL import Image

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "/root/quant/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg","image/jpg","image/png","image/webp","image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4","video/quicktime","video/webm"}
ALLOWED_AUDIO_TYPES = {"audio/webm","audio/ogg","audio/mp4","audio/mpeg"}
ALLOWED_FILE_TYPES = {"application/pdf","application/msword","text/plain","application/zip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_VIDEO_SIZE = 100 * 1024 * 1024
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1920

# --- DB Migrations ---
try:
    with engine.connect() as conn:
        new_cols = [
            ("users","cover","VARCHAR DEFAULT ''"),
            ("users","website","VARCHAR DEFAULT ''"),
            ("users","birthday","VARCHAR DEFAULT ''"),
            ("users","emoji_status","VARCHAR DEFAULT ''"),
            ("users","city","VARCHAR DEFAULT ''"),
            ("users","telegram_link","VARCHAR DEFAULT ''"),
            ("users","youtube_link","VARCHAR DEFAULT ''"),
            ("users","tiktok_link","VARCHAR DEFAULT ''"),
            ("users","last_seen","TIMESTAMP"),
            ("users","pinned_post_id","INTEGER"),
            ("users","is_private","BOOLEAN DEFAULT FALSE"),
            ("users","daily_points","INTEGER DEFAULT 0"),
            ("users","weekly_points","INTEGER DEFAULT 0"),
            ("users","total_points","INTEGER DEFAULT 0"),
            ("users","level","INTEGER DEFAULT 1"),
            ("users","streak_days","INTEGER DEFAULT 0"),
            ("users","last_streak_date","VARCHAR DEFAULT ''"),
            ("users","two_factor_enabled","BOOLEAN DEFAULT FALSE"),
            ("users","two_factor_secret","VARCHAR DEFAULT ''"),
            ("users","email_verified","BOOLEAN DEFAULT FALSE"),
            ("users","theme","VARCHAR DEFAULT 'light'"),
            ("users","font_size","VARCHAR DEFAULT 'medium'"),
            ("users","who_can_message","VARCHAR DEFAULT 'all'"),
            ("users","who_can_see_stories","VARCHAR DEFAULT 'all'"),
            ("users","hide_likes","BOOLEAN DEFAULT FALSE"),
            ("users","language","VARCHAR DEFAULT 'ru'"),
            ("posts","original_comment","TEXT DEFAULT ''"),
            ("posts","is_repost","BOOLEAN DEFAULT FALSE"),
            ("posts","repost_id","INTEGER"),
            ("posts","views","INTEGER DEFAULT 0"),
            ("posts","is_exclusive","BOOLEAN DEFAULT FALSE"),
            ("posts","is_long","BOOLEAN DEFAULT FALSE"),
            ("posts","pinned_comment_id","INTEGER"),
            ("messages","image","VARCHAR DEFAULT ''"),
            ("messages","content_encrypted","TEXT DEFAULT ''"),
            ("messages","voice","VARCHAR DEFAULT ''"),
            ("messages","file_url","VARCHAR DEFAULT ''"),
            ("messages","file_name","VARCHAR DEFAULT ''"),
            ("messages","file_size","INTEGER DEFAULT 0"),
            ("messages","gif_url","VARCHAR DEFAULT ''"),
            ("messages","is_video_circle","BOOLEAN DEFAULT FALSE"),
            ("messages","reply_to_id","INTEGER"),
            ("messages","is_edited","BOOLEAN DEFAULT FALSE"),
            ("messages","edited_at","TIMESTAMP"),
            ("messages","disappear_at","TIMESTAMP"),
            ("messages","is_pinned","BOOLEAN DEFAULT FALSE"),
            ("messages","is_delivered","BOOLEAN DEFAULT FALSE"),
            ("messages","forwarded_from_id","INTEGER"),
            ("messages","is_deleted","BOOLEAN DEFAULT FALSE"),
            ("messages","is_muted","BOOLEAN DEFAULT FALSE"),
            ("messages","sticker_id","INTEGER"),
            ("messages","group_id","INTEGER"),
            ("comments","parent_id","INTEGER"),
            ("comments","is_pinned","BOOLEAN DEFAULT FALSE"),
            ("notifications","text","VARCHAR DEFAULT ''"),
            ("notifications","reply_email","VARCHAR DEFAULT ''"),
        ]
        for table, col, col_type in new_cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"))
            except: pass

        new_tables = [
            """CREATE TABLE IF NOT EXISTS post_media (id SERIAL PRIMARY KEY, post_id INTEGER REFERENCES posts(id), media_url VARCHAR DEFAULT '', media_type VARCHAR DEFAULT 'image', position INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS reels (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), video_url VARCHAR, thumbnail_url VARCHAR DEFAULT '', caption TEXT DEFAULT '', views INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS reel_likes (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), reel_id INTEGER REFERENCES reels(id))""",
            """CREATE TABLE IF NOT EXISTS reel_comments (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), reel_id INTEGER REFERENCES reels(id), content TEXT, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS group_chats (id SERIAL PRIMARY KEY, name VARCHAR, avatar VARCHAR DEFAULT '', description VARCHAR DEFAULT '', owner_id INTEGER REFERENCES users(id), created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS group_members (id SERIAL PRIMARY KEY, group_id INTEGER REFERENCES group_chats(id), user_id INTEGER REFERENCES users(id), is_admin BOOLEAN DEFAULT FALSE, joined_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS group_messages (id SERIAL PRIMARY KEY, group_id INTEGER REFERENCES group_chats(id), sender_id INTEGER REFERENCES users(id), content TEXT DEFAULT '', image VARCHAR DEFAULT '', voice VARCHAR DEFAULT '', file_url VARCHAR DEFAULT '', file_name VARCHAR DEFAULT '', sticker_id INTEGER, gif_url VARCHAR DEFAULT '', reply_to_id INTEGER, is_deleted BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS message_reactions (id SERIAL PRIMARY KEY, message_id INTEGER REFERENCES messages(id), user_id INTEGER REFERENCES users(id), emoji VARCHAR, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS pinned_chats (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), pinned_user_id INTEGER REFERENCES users(id), pinned_group_id INTEGER REFERENCES group_chats(id), created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS muted_chats (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), muted_user_id INTEGER REFERENCES users(id), muted_group_id INTEGER REFERENCES group_chats(id), created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS sticker_packs (id SERIAL PRIMARY KEY, name VARCHAR, description VARCHAR DEFAULT '', cover_url VARCHAR DEFAULT '', is_free BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS stickers (id SERIAL PRIMARY KEY, name VARCHAR, emoji VARCHAR DEFAULT '', image_url VARCHAR DEFAULT '', pack_id INTEGER REFERENCES sticker_packs(id), is_animated BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS user_stickers (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), pack_id INTEGER REFERENCES sticker_packs(id), added_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS stories (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), media_url VARCHAR, media_type VARCHAR DEFAULT 'image', text_overlay VARCHAR DEFAULT '', music_url VARCHAR DEFAULT '', created_at TIMESTAMP DEFAULT NOW(), expires_at TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS story_views (id SERIAL PRIMARY KEY, story_id INTEGER REFERENCES stories(id), user_id INTEGER REFERENCES users(id), viewed_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS story_reactions (id SERIAL PRIMARY KEY, story_id INTEGER REFERENCES stories(id), user_id INTEGER REFERENCES users(id), emoji VARCHAR, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS polls (id SERIAL PRIMARY KEY, post_id INTEGER REFERENCES posts(id) UNIQUE, question VARCHAR, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS poll_options (id SERIAL PRIMARY KEY, poll_id INTEGER REFERENCES polls(id), text VARCHAR)""",
            """CREATE TABLE IF NOT EXISTS poll_votes (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), option_id INTEGER REFERENCES poll_options(id), poll_id INTEGER REFERENCES polls(id), created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS bookmarks (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), post_id INTEGER REFERENCES posts(id), created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, reporter_id INTEGER REFERENCES users(id), target_id INTEGER REFERENCES users(id), reason VARCHAR DEFAULT '', text TEXT DEFAULT '', status VARCHAR DEFAULT 'new', admin_comment TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS post_reports (id SERIAL PRIMARY KEY, reporter_id INTEGER REFERENCES users(id), post_id INTEGER REFERENCES posts(id), reason VARCHAR DEFAULT '', status VARCHAR DEFAULT 'new', created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS user_blocks (id SERIAL PRIMARY KEY, blocker_id INTEGER REFERENCES users(id), blocked_id INTEGER REFERENCES users(id), created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS achievements (id SERIAL PRIMARY KEY, code VARCHAR UNIQUE, name VARCHAR, description VARCHAR, emoji VARCHAR, points_reward INTEGER DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS user_achievements (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), achievement_id INTEGER REFERENCES achievements(id), earned_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS daily_tasks (id SERIAL PRIMARY KEY, code VARCHAR UNIQUE, title VARCHAR, description VARCHAR, emoji VARCHAR DEFAULT '⚡', points INTEGER DEFAULT 10, task_type VARCHAR, target_count INTEGER DEFAULT 1, is_active BOOLEAN DEFAULT TRUE)""",
            """CREATE TABLE IF NOT EXISTS user_daily_tasks (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), task_id INTEGER REFERENCES daily_tasks(id), progress INTEGER DEFAULT 0, is_completed BOOLEAN DEFAULT FALSE, completed_at TIMESTAMP, date VARCHAR DEFAULT '')""",
            """CREATE TABLE IF NOT EXISTS weekly_raffles (id SERIAL PRIMARY KEY, week_start TIMESTAMP, week_end TIMESTAMP, prize VARCHAR DEFAULT 'Quant Plus 30 дней', prize_days INTEGER DEFAULT 30, winner_id INTEGER REFERENCES users(id), is_finished BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS raffle_entries (id SERIAL PRIMARY KEY, raffle_id INTEGER REFERENCES weekly_raffles(id), user_id INTEGER REFERENCES users(id), tickets INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS trends (id SERIAL PRIMARY KEY, tag VARCHAR UNIQUE, count INTEGER DEFAULT 0, updated_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS drafts (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), content TEXT DEFAULT '', image VARCHAR DEFAULT '', created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS call_logs (id SERIAL PRIMARY KEY, caller_id INTEGER REFERENCES users(id), receiver_id INTEGER REFERENCES users(id), call_type VARCHAR DEFAULT 'voice', status VARCHAR DEFAULT 'missed', duration INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS push_subscriptions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), endpoint TEXT, p256dh TEXT, auth TEXT, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS user_sessions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), token_hash VARCHAR, device VARCHAR DEFAULT '', ip VARCHAR DEFAULT '', user_agent VARCHAR DEFAULT '', created_at TIMESTAMP DEFAULT NOW(), last_active TIMESTAMP DEFAULT NOW(), is_active BOOLEAN DEFAULT TRUE)""",
            """CREATE TABLE IF NOT EXISTS verification_codes (id SERIAL PRIMARY KEY, email VARCHAR, code VARCHAR, purpose VARCHAR DEFAULT 'register', created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS weekly_challenges (id SERIAL PRIMARY KEY, title VARCHAR, description VARCHAR, emoji VARCHAR DEFAULT '🏆', points INTEGER DEFAULT 100, task_type VARCHAR, target_count INTEGER DEFAULT 1, week_start TIMESTAMP, week_end TIMESTAMP, is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS user_weekly_challenges (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), challenge_id INTEGER REFERENCES weekly_challenges(id), progress INTEGER DEFAULT 0, is_completed BOOLEAN DEFAULT FALSE, completed_at TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS typing_status (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), target_id INTEGER REFERENCES users(id), group_id INTEGER REFERENCES group_chats(id), updated_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS special_requests (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), type VARCHAR, reason TEXT DEFAULT '', links VARCHAR DEFAULT '', status VARCHAR DEFAULT 'new', admin_comment TEXT DEFAULT '', created_at TIMESTAMP DEFAULT NOW())""",
        ]
        for t_sql in new_tables:
            try:
                conn.execute(text(t_sql))
            except: pass

        # Seed achievements
        achievements_data = [
            ("first_post","Первый пост","Опубликуй первый пост","📝",10),
            ("first_like","Лайкни!","Поставь первый лайк","❤️",5),
            ("first_follow","Подписчик","Подпишись на кого-нибудь","👤",5),
            ("popular","Популярный","Набери 10 подписчиков","🌟",50),
            ("very_popular","Знаменитость","Набери 100 подписчиков","⭐",200),
            ("active","Активный","Опубликуй 10 постов","🔥",30),
            ("prolific","Плодовитый","Опубликуй 50 постов","💪",100),
            ("social","Общительный","Напиши 20 комментариев","💬",30),
            ("liker","Любитель лайков","Поставь 50 лайков","❤️",20),
            ("streak_3","Стрик 3 дня","Заходи 3 дня подряд","🔥",30),
            ("streak_7","Стрик 7 дней","Заходи 7 дней подряд","🏆",100),
            ("streak_30","Стрик 30 дней","Заходи 30 дней подряд","👑",500),
            ("whale","Кит","Поставь 10 китов","🐋",30),
            ("photographer","Фотограф","Опубликуй 5 фото","📷",20),
            ("videographer","Видеограф","Загрузи первый рилс","🎬",50),
            ("rich","Богач","Набери 1000 очков","💰",100),
        ]
        for code, name, desc, emoji, pts in achievements_data:
            try:
                conn.execute(text("INSERT INTO achievements(code,name,description,emoji,points_reward) VALUES(:c,:n,:d,:e,:p) ON CONFLICT(code) DO NOTHING"), {"c":code,"n":name,"d":desc,"e":emoji,"p":pts})
            except: pass

        # Seed daily tasks
        tasks_data = [
            ("daily_post","Опубликуй пост","Опубликуй хотя бы один пост сегодня","📝",20,"post",1),
            ("daily_like","Поставь лайки","Поставь 3 лайка","❤️",10,"like",3),
            ("daily_comment","Прокомментируй","Оставь комментарий","💬",15,"comment",1),
            ("daily_follow","Подпишись","Подпишись на нового пользователя","👤",10,"follow",1),
            ("daily_story","История","Опубликуй историю","📸",25,"story",1),
            ("daily_login","Ежедневный вход","Просто зайди на Quant","⚡",5,"login",1),
            ("daily_message","Напиши сообщение","Напиши кому-нибудь","✉️",10,"message",1),
        ]
        for code, title, desc, emoji, pts, ttype, target in tasks_data:
            try:
                conn.execute(text("INSERT INTO daily_tasks(code,title,description,emoji,points,task_type,target_count) VALUES(:c,:t,:d,:e,:p,:tt,:tc) ON CONFLICT(code) DO NOTHING"), {"c":code,"t":title,"d":desc,"e":emoji,"p":pts,"tt":ttype,"tc":target})
            except: pass

        conn.execute(text("UPDATE users SET is_owner=TRUE WHERE username='rubl'"))
        conn.commit()
except Exception as e:
    print(f"Migration warning: {e}")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="/root/quant/uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

# --- Helpers ---
def validate_username(u):
    if len(u)<3: return "Минимум 3 символа"
    if len(u)>30: return "Максимум 30 символов"
    if not re.match(r'^[a-zA-Z0-9_]+$', u): return "Только латиница, цифры и _"
    return None

def validate_password(p):
    if len(p)<6: return "Минимум 6 символов"
    if len(p)>64: return "Максимум 64 символа"
    return None

def get_unread(user, db):
    if not user: return 0
    return db.query(models.Notification).filter(models.Notification.user_id==user.id, models.Notification.is_read==False).count()

def get_unread_msg(user, db):
    if not user: return 0
    return db.query(models.Message).filter(models.Message.receiver_id==user.id, models.Message.is_read==False, models.Message.is_deleted==False).count()

def is_blocked(user):
    if not user or not user.is_blocked: return False
    if user.blocked_until and datetime.utcnow()>user.blocked_until: return False
    return True

def is_plus(user):
    if not user or not user.is_plus: return False
    if user.plus_until and datetime.utcnow()>user.plus_until: return False
    return True

def can_mod(user):
    return user and (user.is_owner or user.is_moderator)

def save_file(upload: UploadFile):
    if not upload or not upload.filename: return None, None
    ct = (upload.content_type or "").lower()
    contents = upload.file.read()
    size = len(contents)
    if ct in ALLOWED_IMAGE_TYPES:
        if size > MAX_IMAGE_SIZE: return None, "Фото слишком большое (макс 10 МБ)"
        mtype = "image"
    elif ct in ALLOWED_VIDEO_TYPES:
        if size > MAX_VIDEO_SIZE: return None, "Видео слишком большое (макс 100 МБ)"
        mtype = "video"
    elif ct in ALLOWED_AUDIO_TYPES:
        mtype = "audio"
    elif ct in ALLOWED_FILE_TYPES:
        if size > MAX_FILE_SIZE: return None, "Файл слишком большой (макс 50 МБ)"
        mtype = "file"
    else:
        return None, "Неподдерживаемый формат"
    ext_map = {"image/jpeg":".jpg","image/jpg":".jpg","image/png":".png","image/webp":".webp","image/gif":".gif","video/mp4":".mp4","video/quicktime":".mov","video/webm":".webm","audio/webm":".webm","audio/ogg":".ogg","audio/mp4":".m4a","audio/mpeg":".mp3","application/pdf":".pdf","text/plain":".txt","application/zip":".zip"}
    ext = ext_map.get(ct, ".bin")
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    if mtype == "image":
        try:
            img = Image.open(io.BytesIO(contents))
            try:
                exif = img._getexif()
                if exif:
                    orient = exif.get(274)
                    if orient==3: img=img.rotate(180,expand=True)
                    elif orient==6: img=img.rotate(270,expand=True)
                    elif orient==8: img=img.rotate(90,expand=True)
            except: pass
            if img.width>MAX_IMAGE_DIMENSION or img.height>MAX_IMAGE_DIMENSION:
                img.thumbnail((MAX_IMAGE_DIMENSION,MAX_IMAGE_DIMENSION),Image.LANCZOS)
            if ext in (".jpg",) and img.mode in ("RGBA","P"):
                img=img.convert("RGB")
            params={"optimize":True}
            if ext in (".jpg",".jpeg"): params["quality"]=85
            elif ext==".webp": params["quality"]=85
            img.save(fpath,**params)
        except Exception as ex:
            print(f"Image error: {ex}")
            return None, "Не удалось обработать фото"
    else:
        with open(fpath,"wb") as f: f.write(contents)
    return f"/uploads/{fname}", mtype

def delete_file(url):
    if not url or not url.startswith("/uploads/"): return
    try:
        fpath = os.path.join(UPLOAD_DIR, url.replace("/uploads/",""))
        if os.path.exists(fpath): os.remove(fpath)
    except: pass

def add_points(user, db, points, task_code=None):
    user.daily_points = (user.daily_points or 0) + points
    user.weekly_points = (user.weekly_points or 0) + points
    user.total_points = (user.total_points or 0) + points
    user.level = max(1, (user.total_points or 0) // 500 + 1)
    db.commit()
    if task_code:
        complete_task(user, db, task_code)

def complete_task(user, db, task_type):
    today = date.today().isoformat()
    task = db.query(models.DailyTask).filter(models.DailyTask.task_type==task_type, models.DailyTask.is_active==True).first()
    if not task: return
    ut = db.query(models.UserDailyTask).filter(models.UserDailyTask.user_id==user.id, models.UserDailyTask.task_id==task.id, models.UserDailyTask.date==today).first()
    if not ut:
        ut = models.UserDailyTask(user_id=user.id, task_id=task.id, progress=0, date=today)
        db.add(ut)
        db.flush()
    if ut.is_completed: return
    ut.progress = (ut.progress or 0) + 1
    if ut.progress >= task.target_count:
        ut.is_completed = True
        ut.completed_at = datetime.utcnow()
        add_points(user, db, task.points)
    db.commit()

def update_streak(user, db):
    today = date.today().isoformat()
    if user.last_streak_date == today: return
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if user.last_streak_date == yesterday:
        user.streak_days = (user.streak_days or 0) + 1
    elif user.last_streak_date != today:
        user.streak_days = 1
    user.last_streak_date = today
    db.commit()

def get_daily_tasks(user, db):
    if not user: return []
    today = date.today().isoformat()
    tasks = db.query(models.DailyTask).filter(models.DailyTask.is_active==True).all()
    result = []
    for task in tasks:
        ut = db.query(models.UserDailyTask).filter(models.UserDailyTask.user_id==user.id, models.UserDailyTask.task_id==task.id, models.UserDailyTask.date==today).first()
        if not ut:
            ut = models.UserDailyTask(user_id=user.id, task_id=task.id, progress=0, date=today)
            db.add(ut)
        result.append(ut)
    db.commit()
    return result

def get_trends(db, limit=5):
    return db.query(models.Trend).order_by(models.Trend.count.desc()).limit(limit).all()

def update_trends(content, db):
    tags = re.findall(r'#(\w+)', content)
    for tag in set(tags):
        t = db.query(models.Trend).filter(models.Trend.tag==tag.lower()).first()
        if t:
            t.count += 1
            t.updated_at = datetime.utcnow()
        else:
            db.add(models.Trend(tag=tag.lower(), count=1))
    if tags: db.commit()

def check_achievement(user, db, code):
    ach = db.query(models.Achievement).filter(models.Achievement.code==code).first()
    if not ach: return
    exists = db.query(models.UserAchievement).filter(models.UserAchievement.user_id==user.id, models.UserAchievement.achievement_id==ach.id).first()
    if not exists:
        db.add(models.UserAchievement(user_id=user.id, achievement_id=ach.id))
        db.add(models.Notification(user_id=user.id, type="achievement", text=f"Получено достижение: {ach.emoji} {ach.name}"))
        add_points(user, db, ach.points_reward)
        db.commit()

def tpl(request, name, ctx):
    user = ctx.get("user")
    if user:
        ctx.setdefault("unread", get_unread(user, None) if "db" not in ctx else 0)
        ctx.setdefault("unread_msg", 0)
        ctx.setdefault("is_plus", is_plus(user))
    return templates.TemplateResponse(request, name, ctx)

def base_ctx(request, db, extra=None):
    user = auth.get_current_user(request, db)
    if user:
        user.last_seen = datetime.utcnow()
        update_streak(user, db)
        db.commit()
    ctx = {
        "user": user,
        "unread": get_unread(user, db),
        "unread_msg": get_unread_msg(user, db),
        "is_plus": is_plus(user),
        "trends": get_trends(db),
        "daily_tasks": get_daily_tasks(user, db),
    }
    if extra: ctx.update(extra)
    return ctx, user

BLOCKED_HTML = """<html><body style='font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#0a0a0a;margin:0'><div style='background:#141414;border-radius:20px;padding:40px;text-align:center;border:1px solid #2a2a2a;max-width:400px;color:white'><div style='font-size:48px;margin-bottom:16px'>🚫</div><h2 style='margin-bottom:8px'>Аккаунт заблокирован</h2><p style='color:#777;margin-bottom:24px'>Обратись в поддержку для разблокировки</p><a href='/' style='background:#f0f0f0;color:#0f0f0f;padding:10px 24px;border-radius:10px;text-decoration:none;font-weight:700'>На главную</a></div></body></html>"""

# ===================== ROUTES =====================

@app.get("/", response_class=HTMLResponse)
def home(request: Request, tab: str="foryou", db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    now = datetime.utcnow()
    if tab=="following" and user:
        fids = [f.following_id for f in user.following]
        posts = db.query(models.Post).filter(models.Post.user_id.in_(fids), models.Post.is_published==True, models.Post.is_draft==False).order_by(models.Post.created_at.desc()).all()
    else:
        posts = db.query(models.Post).filter(models.Post.is_published==True, models.Post.is_draft==False).order_by(models.Post.created_at.desc()).limit(300).all()
        fids = set()
        if user:
            fids = set(f.following_id for f in user.following)
        def score(p):
            age = max((now-p.created_at).total_seconds()/3600, 0.1)
            return 800/(age+2)+len(p.likes)*3+len(p.comments)*2+len(p.whales)+(50 if p.user_id in fids else 0)
        posts = sorted(posts, key=score, reverse=True)

    liked = set()
    whaled = set()
    bookmarked = set()
    if user:
        liked = set(l.post_id for l in db.query(models.Like).filter(models.Like.user_id==user.id).all())
        whaled = set(w.post_id for w in db.query(models.Whale).filter(models.Whale.user_id==user.id).all())
        bookmarked = set(b.post_id for b in db.query(models.Bookmark).filter(models.Bookmark.user_id==user.id).all())

    now_dt = datetime.utcnow()
    stories_raw = db.query(models.Story).filter(models.Story.expires_at>now_dt).order_by(models.Story.created_at.desc()).all()
    story_by_user = {}
    for s in stories_raw:
        if s.user_id not in story_by_user:
            story_by_user[s.user_id] = type('SG',(),{'user':s.author,'stories':[s]})()
        else:
            story_by_user[s.user_id].stories.append(s)

    drafts = db.query(models.Draft).filter(models.Draft.user_id==user.id).order_by(models.Draft.updated_at.desc()).all() if user else []
    suggested = []
    if user:
        fids_list = [f.following_id for f in user.following] + [user.id]
        suggested = db.query(models.User).filter(~models.User.id.in_(fids_list)).order_by(models.User.total_points.desc()).limit(5).all()

    ctx.update({"posts":posts, "tab":tab, "liked_posts":liked, "whaled_posts":whaled, "bookmarked_posts":bookmarked, "stories":list(story_by_user.values()), "drafts":drafts, "suggested_users":suggested})
    return templates.TemplateResponse(request, "home.html", ctx)

@app.get("/post/{post_id}", response_class=HTMLResponse)
def post_page(post_id: int, request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    post = db.query(models.Post).filter(models.Post.id==post_id).first()
    if not post: return RedirectResponse("/", 302)
    post.views = (post.views or 0) + 1
    db.commit()
    comments = db.query(models.Comment).filter(models.Comment.post_id==post_id, models.Comment.parent_id==None).order_by(models.Comment.is_pinned.desc(), models.Comment.created_at.asc()).all()
    liked = False
    whaled = False
    if user:
        liked = db.query(models.Like).filter(models.Like.user_id==user.id, models.Like.post_id==post_id).first() is not None
        whaled = db.query(models.Whale).filter(models.Whale.user_id==user.id, models.Whale.post_id==post_id).first() is not None
    ctx.update({"post":post, "comments":comments, "liked":liked, "whaled":whaled})
    return templates.TemplateResponse(request, "post.html", ctx)

@app.post("/post/create")
async def create_post(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    if is_blocked(user): return HTMLResponse(BLOCKED_HTML)
    form = await request.form()
    content = (form.get("content") or "").strip()
    poll_q = form.get("poll_question","").strip()
    poll_opts = form.getlist("poll_options")
    image_file = form.get("image")
    video_file = form.get("video")
    if not content and not image_file and not video_file:
        return JSONResponse({"error":"empty"}, 400)
    media_url = ""
    media_type = ""
    mfile = video_file if (video_file and hasattr(video_file,"filename") and video_file.filename) else (image_file if (image_file and hasattr(image_file,"filename") and image_file.filename) else None)
    if mfile:
        url, mt = save_file(mfile)
        if url: media_url, media_type = url, mt or ""
    post = models.Post(content=content, user_id=user.id, image=media_url, media_type=media_type, is_long=len(content)>400)
    db.add(post)
    db.flush()
    if poll_q and len(poll_opts)>=2:
        poll = models.Poll(post_id=post.id, question=poll_q)
        db.add(poll)
        db.flush()
        for opt in poll_opts[:6]:
            if opt.strip():
                db.add(models.PollOption(poll_id=poll.id, text=opt.strip()))
    update_trends(content, db)
    db.commit()
    add_points(user, db, 5)
    complete_task(user, db, "post")
    posts_count = db.query(models.Post).filter(models.Post.user_id==user.id).count()
    if posts_count==1: check_achievement(user, db, "first_post")
    if posts_count==10: check_achievement(user, db, "active")
    if posts_count==50: check_achievement(user, db, "prolific")
    return JSONResponse({"ok":True, "post_id":post.id})

@app.post("/post/{post_id}/delete")
async def delete_post(post_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    post = db.query(models.Post).filter(models.Post.id==post_id).first()
    if not post: return JSONResponse({"error":"not found"}, 404)
    if post.user_id!=user.id and not can_mod(user): return JSONResponse({"error":"forbidden"}, 403)
    delete_file(post.image)
    for pm in post.media_items: delete_file(pm.media_url)
    db.query(models.Like).filter(models.Like.post_id==post_id).delete()
    db.query(models.Whale).filter(models.Whale.post_id==post_id).delete()
    db.query(models.Comment).filter(models.Comment.post_id==post_id).delete()
    db.query(models.Notification).filter(models.Notification.post_id==post_id).delete()
    db.query(models.Reaction).filter(models.Reaction.post_id==post_id).delete()
    db.query(models.Bookmark).filter(models.Bookmark.post_id==post_id).delete()
    db.query(models.PostReport).filter(models.PostReport.post_id==post_id).delete()
    db.query(models.PostMedia).filter(models.PostMedia.post_id==post_id).delete()
    if post.poll:
        for opt in post.poll.options:
            db.query(models.PollVote).filter(models.PollVote.option_id==opt.id).delete()
            db.delete(opt)
        db.delete(post.poll)
    db.delete(post)
    db.commit()
    return JSONResponse({"ok":True})

@app.post("/like/{post_id}")
async def like_post(post_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    ex = db.query(models.Like).filter(models.Like.user_id==user.id, models.Like.post_id==post_id).first()
    liked = False
    if ex:
        db.delete(ex)
    else:
        db.add(models.Like(user_id=user.id, post_id=post_id))
        liked = True
        post = db.query(models.Post).filter(models.Post.id==post_id).first()
        if post and post.user_id!=user.id:
            db.add(models.Notification(user_id=post.user_id, from_user_id=user.id, type="like", post_id=post_id))
        complete_task(user, db, "like")
        like_count = db.query(models.Like).filter(models.Like.user_id==user.id).count()
        if like_count==1: check_achievement(user, db, "first_like")
        if like_count==50: check_achievement(user, db, "liker")
    db.commit()
    count = db.query(models.Like).filter(models.Like.post_id==post_id).count()
    return JSONResponse({"liked":liked, "count":count})

@app.post("/whale/{post_id}")
async def whale_post(post_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    ex = db.query(models.Whale).filter(models.Whale.user_id==user.id, models.Whale.post_id==post_id).first()
    whaled = False
    if ex:
        db.delete(ex)
    else:
        db.add(models.Whale(user_id=user.id, post_id=post_id))
        whaled = True
        whale_count = db.query(models.Whale).filter(models.Whale.user_id==user.id).count()
        if whale_count==10: check_achievement(user, db, "whale")
    db.commit()
    count = db.query(models.Whale).filter(models.Whale.post_id==post_id).count()
    return JSONResponse({"whaled":whaled, "count":count})

@app.post("/bookmark/{post_id}")
async def bookmark_post(post_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    ex = db.query(models.Bookmark).filter(models.Bookmark.user_id==user.id, models.Bookmark.post_id==post_id).first()
    bm = False
    if ex:
        db.delete(ex)
    else:
        db.add(models.Bookmark(user_id=user.id, post_id=post_id))
        bm = True
    db.commit()
    return JSONResponse({"bookmarked":bm})

@app.get("/bookmarks", response_class=HTMLResponse)
def bookmarks_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    bms = db.query(models.Bookmark).filter(models.Bookmark.user_id==user.id).order_by(models.Bookmark.created_at.desc()).all()
    posts = [b.post for b in bms if b.post]
    ctx["posts"] = posts
    return templates.TemplateResponse(request, "bookmarks.html", ctx)

@app.post("/post/{post_id}/comment")
async def add_comment(post_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    data = await request.json()
    content = (data.get("content") or "").strip()
    parent_id = data.get("parent_id")
    if not content: return JSONResponse({"error":"empty"}, 400)
    c = models.Comment(content=content, user_id=user.id, post_id=post_id, parent_id=parent_id)
    db.add(c)
    post = db.query(models.Post).filter(models.Post.id==post_id).first()
    if post and post.user_id!=user.id:
        db.add(models.Notification(user_id=post.user_id, from_user_id=user.id, type="comment", post_id=post_id))
    db.commit()
    add_points(user, db, 2)
    complete_task(user, db, "comment")
    return JSONResponse({"ok":True})

@app.post("/comment/{comment_id}/delete")
async def delete_comment(comment_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    c = db.query(models.Comment).filter(models.Comment.id==comment_id).first()
    if not c: return JSONResponse({"error":"not found"}, 404)
    if c.user_id!=user.id and not can_mod(user): return JSONResponse({"error":"forbidden"}, 403)
    db.delete(c)
    db.commit()
    return JSONResponse({"ok":True})

@app.post("/post/{post_id}/pin-comment/{comment_id}")
def pin_comment(post_id: int, comment_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    post = db.query(models.Post).filter(models.Post.id==post_id).first()
    if not post or (post.user_id!=user.id and not can_mod(user)): return RedirectResponse(f"/post/{post_id}", 302)
    post.pinned_comment_id = comment_id
    c = db.query(models.Comment).filter(models.Comment.id==comment_id).first()
    if c: c.is_pinned = True
    db.commit()
    return RedirectResponse(f"/post/{post_id}", 302)

@app.post("/poll/vote/{option_id}")
def poll_vote(option_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    opt = db.query(models.PollOption).filter(models.PollOption.id==option_id).first()
    if not opt: return RedirectResponse("/", 302)
    ex = db.query(models.PollVote).filter(models.PollVote.user_id==user.id, models.PollVote.poll_id==opt.poll_id).first()
    if not ex:
        db.add(models.PollVote(user_id=user.id, option_id=option_id, poll_id=opt.poll_id))
        db.commit()
    post = db.query(models.Post).join(models.Poll).filter(models.Poll.id==opt.poll_id).first()
    return RedirectResponse(f"/post/{post.id}" if post else "/", 302)

@app.post("/repost/{post_id}")
async def repost(post_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    data = await request.json()
    comment = data.get("comment","")
    orig = db.query(models.Post).filter(models.Post.id==post_id).first()
    if not orig: return JSONResponse({"error":"not found"}, 404)
    p = models.Post(content=orig.content, user_id=user.id, image=orig.image, media_type=orig.media_type, is_repost=True, repost_id=post_id, original_comment=comment)
    db.add(p)
    db.commit()
    return JSONResponse({"ok":True})

@app.post("/post/{post_id}/pin")
def pin_post(post_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    post = db.query(models.Post).filter(models.Post.id==post_id, models.Post.user_id==user.id).first()
    if post:
        user.pinned_post_id = post_id if user.pinned_post_id!=post_id else None
        db.commit()
    return RedirectResponse(f"/profile/{user.username}", 302)

@app.post("/post/{post_id}/report")
async def report_post(post_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    data = await request.json()
    db.add(models.PostReport(reporter_id=user.id, post_id=post_id, reason=data.get("reason","")))
    db.commit()
    return JSONResponse({"ok":True})

# --- Auth ---
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})

@app.post("/login")
def login(request: Request, username: str=Form(...), password: str=Form(...), db: Session=Depends(get_db)):
    user = db.query(models.User).filter(or_(models.User.username==username, models.User.email==username)).first()
    if not user or not auth.verify_password(password, user.password):
        return templates.TemplateResponse(request, "login.html", {"error":"Неверный логин или пароль", "username":username})
    token = auth.create_token({"sub":user.username})
    resp = RedirectResponse("/", 302)
    resp.set_cookie("token", token, max_age=60*60*24*30, httponly=True)
    return resp

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {})

@app.post("/register")
def register(request: Request, username: str=Form(...), email: str=Form(...), password: str=Form(...), confirm_password: str=Form(...), db: Session=Depends(get_db)):
    err = validate_username(username)
    if err: return templates.TemplateResponse(request, "register.html", {"error":err, "username":username, "email":email})
    err = validate_password(password)
    if err: return templates.TemplateResponse(request, "register.html", {"error":err, "username":username, "email":email})
    if password!=confirm_password: return templates.TemplateResponse(request, "register.html", {"error":"Пароли не совпадают", "username":username, "email":email})
    if db.query(models.User).filter(models.User.username==username).first():
        return templates.TemplateResponse(request, "register.html", {"error":f"Логин @{username} уже занят", "username":username, "email":email})
    if db.query(models.User).filter(models.User.email==email).first():
        return templates.TemplateResponse(request, "register.html", {"error":"Email уже зарегистрирован", "username":username})
    user = models.User(username=username, email=email, password=auth.hash_password(password), is_verified=True, name=username)
    db.add(user)
    db.commit()
    token = auth.create_token({"sub":username})
    resp = RedirectResponse("/", 302)
    resp.set_cookie("token", token, max_age=60*60*24*30, httponly=True)
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse("/", 302)
    resp.delete_cookie("token")
    return resp

# --- Yandex OAuth ---
@app.get("/auth/yandex")
def yandex_login():
    from yandex_auth import YANDEX_CLIENT_ID, YANDEX_REDIRECT_URI, YANDEX_AUTH_URL
    url = f"{YANDEX_AUTH_URL}?response_type=code&client_id={YANDEX_CLIENT_ID}&redirect_uri={YANDEX_REDIRECT_URI}"
    return RedirectResponse(url)

@app.get("/auth/yandex/callback")
async def yandex_callback(code: str, request: Request, db: Session=Depends(get_db)):
    import httpx
    from yandex_auth import YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET, YANDEX_REDIRECT_URI, YANDEX_TOKEN_URL, YANDEX_USER_URL
    async with httpx.AsyncClient() as client:
        tr = await client.post(YANDEX_TOKEN_URL, data={"grant_type":"authorization_code","code":code,"client_id":YANDEX_CLIENT_ID,"client_secret":YANDEX_CLIENT_SECRET,"redirect_uri":YANDEX_REDIRECT_URI})
        td = tr.json()
        at = td.get("access_token")
        if not at: return RedirectResponse("/login", 302)
        ur = await client.get(YANDEX_USER_URL, headers={"Authorization":f"OAuth {at}"})
        yu = ur.json()
    yid = str(yu.get("id",""))
    email = yu.get("default_email", f"yandex_{yid}@yandex.ru")
    name = yu.get("real_name") or yu.get("display_name") or "Пользователь"
    ubase = re.sub(r'[^\w]','_',yu.get("login",f"y_{yid}"))[:28]
    user = db.query(models.User).filter(models.User.email==email).first()
    if not user:
        un = ubase
        i = 1
        while db.query(models.User).filter(models.User.username==un).first():
            un = f"{ubase}_{i}"; i+=1
        user = models.User(name=name, username=un, email=email, password=auth.hash_password(yid+"yandex"), is_verified=True)
        db.add(user); db.commit()
    token = auth.create_token({"sub":user.username})
    resp = RedirectResponse("/", 302)
    resp.set_cookie("token", token, max_age=60*60*24*30, httponly=True)
    return resp

# --- Profile ---
@app.get("/profile/{username}", response_class=HTMLResponse)
def profile(username: str, request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    pu = db.query(models.User).filter(models.User.username==username).first()
    if not pu: return RedirectResponse("/", 302)
    posts = db.query(models.Post).filter(models.Post.user_id==pu.id, models.Post.is_published==True, models.Post.is_draft==False).order_by(models.Post.created_at.desc()).all()
    is_following = False
    if user:
        is_following = db.query(models.Follow).filter(models.Follow.follower_id==user.id, models.Follow.following_id==pu.id).first() is not None
    pinned = db.query(models.Post).filter(models.Post.id==pu.pinned_post_id).first() if pu.pinned_post_id else None
    achievements = db.query(models.UserAchievement).filter(models.UserAchievement.user_id==pu.id).all()
    profile_reels = db.query(models.Reel).filter(models.Reel.user_id==pu.id).order_by(models.Reel.created_at.desc()).all()
    stats = {}
    if user and user.id==pu.id:
        stats["total_views"] = sum(p.views or 0 for p in posts)
        stats["total_likes"] = sum(len(p.likes) for p in posts)
        stats["total_comments"] = sum(len(p.comments) for p in posts)
    promocodes = []
    if user and user.is_owner and user.id==pu.id:
        promocodes = db.query(models.Promocode).order_by(models.Promocode.created_at.desc()).all()
    ctx.update({"profile_user":pu, "posts":posts, "is_following":is_following, "pinned_post":pinned, "achievements":achievements, "profile_reels":profile_reels, "stats":stats, "promocodes":promocodes, "profile_is_plus":is_plus(pu), "now":datetime.utcnow()})
    return templates.TemplateResponse(request, "profile.html", ctx)

@app.get("/profile/{username}/followers", response_class=HTMLResponse)
def followers_page(username: str, request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    pu = db.query(models.User).filter(models.User.username==username).first()
    if not pu: return RedirectResponse("/", 302)
    followers = [f.follower for f in pu.followers]
    ctx.update({"profile_user":pu, "followers":followers})
    return templates.TemplateResponse(request, "followers.html", ctx)

@app.get("/profile/{username}/following", response_class=HTMLResponse)
def following_page(username: str, request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    pu = db.query(models.User).filter(models.User.username==username).first()
    if not pu: return RedirectResponse("/", 302)
    following = [f.following for f in pu.following]
    ctx.update({"profile_user":pu, "following":following})
    return templates.TemplateResponse(request, "following.html", ctx)

@app.post("/follow/{username}")
def follow(username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    target = db.query(models.User).filter(models.User.username==username).first()
    if not target or target.id==user.id: return RedirectResponse("/", 302)
    ex = db.query(models.Follow).filter(models.Follow.follower_id==user.id, models.Follow.following_id==target.id).first()
    if ex:
        db.delete(ex)
    else:
        db.add(models.Follow(follower_id=user.id, following_id=target.id))
        db.add(models.Notification(user_id=target.id, from_user_id=user.id, type="follow"))
        complete_task(user, db, "follow")
        fc = db.query(models.Follow).filter(models.Follow.follower_id==user.id).count()
        if fc==1: check_achievement(user, db, "first_follow")
        tc = db.query(models.Follow).filter(models.Follow.following_id==target.id).count()
        if tc==10: check_achievement(target, db, "popular")
        if tc==100: check_achievement(target, db, "very_popular")
    db.commit()
    return RedirectResponse(f"/profile/{username}", 302)

# --- Settings ---
@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    sessions = db.query(models.UserSession).filter(models.UserSession.user_id==user.id, models.UserSession.is_active==True).order_by(models.UserSession.last_active.desc()).all()
    blocked_users = [b.blocked for b in db.query(models.UserBlock).filter(models.UserBlock.blocker_id==user.id).all()]
    ctx.update({"sessions":sessions, "blocked_users":blocked_users, "success":None, "error":None})
    return templates.TemplateResponse(request, "settings.html", ctx)

@app.post("/settings/profile")
async def settings_profile(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    form = await request.form()
    user.name = (form.get("name") or "").strip()[:60]
    user.bio = (form.get("bio") or "").strip()[:300]
    user.website = (form.get("website") or "").strip()[:100]
    user.city = (form.get("city") or "").strip()[:60]
    user.birthday = (form.get("birthday") or "").strip()[:20]
    user.emoji_status = (form.get("emoji_status") or "").strip()[:8]
    user.telegram_link = (form.get("telegram_link") or "").strip()[:100]
    user.youtube_link = (form.get("youtube_link") or "").strip()[:100]
    user.tiktok_link = (form.get("tiktok_link") or "").strip()[:100]
    db.commit()
    return RedirectResponse(f"/profile/{user.username}", 302)

@app.post("/settings/password")
async def settings_password(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    form = await request.form()
    old = form.get("old_password","")
    new = form.get("new_password","")
    confirm = form.get("confirm_password","")
    sessions = db.query(models.UserSession).filter(models.UserSession.user_id==user.id, models.UserSession.is_active==True).all()
    blocked_users = [b.blocked for b in db.query(models.UserBlock).filter(models.UserBlock.blocker_id==user.id).all()]
    if not auth.verify_password(old, user.password):
        ctx.update({"sessions":sessions, "blocked_users":blocked_users, "error":"Старый пароль неверный"})
        return templates.TemplateResponse(request, "settings.html", ctx)
    err = validate_password(new)
    if err:
        ctx.update({"sessions":sessions, "blocked_users":blocked_users, "error":err})
        return templates.TemplateResponse(request, "settings.html", ctx)
    if new!=confirm:
        ctx.update({"sessions":sessions, "blocked_users":blocked_users, "error":"Пароли не совпадают"})
        return templates.TemplateResponse(request, "settings.html", ctx)
    user.password = auth.hash_password(new)
    db.commit()
    ctx.update({"sessions":sessions, "blocked_users":blocked_users, "success":"Пароль изменён"})
    return templates.TemplateResponse(request, "settings.html", ctx)

@app.post("/settings/privacy")
async def settings_privacy(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    form = await request.form()
    user.who_can_message = form.get("who_can_message","all")
    user.who_can_see_stories = form.get("who_can_see_stories","all")
    user.is_private = "is_private" in form
    user.hide_likes = "hide_likes" in form
    db.commit()
    return RedirectResponse("/settings", 302)

@app.post("/settings/theme")
async def settings_theme(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"ok":False})
    data = await request.json()
    user.theme = data.get("theme","light")
    db.commit()
    return JSONResponse({"ok":True})

@app.post("/settings/avatar")
async def settings_avatar(request: Request, avatar: UploadFile=File(...), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    url, err = save_file(avatar)
    if url:
        delete_file(user.avatar)
        user.avatar = url
        db.commit()
    return RedirectResponse(f"/profile/{user.username}", 302)

@app.post("/settings/cover")
async def settings_cover(request: Request, cover: UploadFile=File(...), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    url, err = save_file(cover)
    if url:
        delete_file(user.cover)
        user.cover = url
        db.commit()
    return RedirectResponse(f"/profile/{user.username}", 302)

@app.post("/settings/plus-color")
async def plus_color(request: Request, color: str=Form(...), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not is_plus(user): return RedirectResponse("/settings", 302)
    if re.match(r'^#[0-9a-fA-F]{6}$', color):
        user.plus_color = color
        db.commit()
    return RedirectResponse("/settings", 302)

@app.post("/settings/promocode")
async def activate_promo(request: Request, code: str=Form(...), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    promo = db.query(models.Promocode).filter(models.Promocode.code==code.upper().strip(), models.Promocode.is_active==True).first()
    ctx, _ = base_ctx(request, db)
    sessions = db.query(models.UserSession).filter(models.UserSession.user_id==user.id).all()
    blocked_users = []
    if not promo or promo.uses>=promo.max_uses:
        ctx.update({"sessions":sessions,"blocked_users":blocked_users,"error":"Промокод не найден или исчерпан"})
        return templates.TemplateResponse(request, "settings.html", ctx)
    promo.uses+=1
    if promo.uses>=promo.max_uses: promo.is_active=False
    user.is_plus=True
    user.plus_until = datetime.utcnow()+timedelta(days=promo.days)
    db.commit()
    ctx.update({"sessions":sessions,"blocked_users":blocked_users,"success":f"Quant Plus активирован на {promo.days} дней!"})
    return templates.TemplateResponse(request, "settings.html", ctx)

@app.post("/settings/sessions/{session_id}/revoke")
def revoke_session(session_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    s = db.query(models.UserSession).filter(models.UserSession.id==session_id, models.UserSession.user_id==user.id).first()
    if s: s.is_active=False; db.commit()
    return RedirectResponse("/settings", 302)

@app.post("/unblock/{username}")
def unblock_user_route(username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    target = db.query(models.User).filter(models.User.username==username).first()
    if target:
        b = db.query(models.UserBlock).filter(models.UserBlock.blocker_id==user.id, models.UserBlock.blocked_id==target.id).first()
        if b: db.delete(b); db.commit()
    return RedirectResponse("/settings", 302)

# --- Messages ---
@app.get("/messages", response_class=HTMLResponse)
def messages_list(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    now = datetime.utcnow()
    all_msgs = db.query(models.Message).filter(or_(models.Message.sender_id==user.id, models.Message.receiver_id==user.id), models.Message.group_id==None).order_by(models.Message.created_at.desc()).all()
    seen_ids = set()
    chats = []
    for m in all_msgs:
        other_id = m.receiver_id if m.sender_id==user.id else m.sender_id
        if other_id in seen_ids: continue
        seen_ids.add(other_id)
        other = db.query(models.User).filter(models.User.id==other_id).first()
        if not other: continue
        unread = db.query(models.Message).filter(models.Message.sender_id==other_id, models.Message.receiver_id==user.id, models.Message.is_read==False).count()
        muted = db.query(models.MutedChat).filter(models.MutedChat.user_id==user.id, models.MutedChat.muted_user_id==other_id).first() is not None
        preview = ""
        if m.content: preview = m.content[:40]
        elif m.image: preview = "📷 Фото"
        elif m.voice: preview = "🎙 Голосовое"
        elif m.file_url: preview = f"📎 {m.file_name}"
        chats.append(type('C',(),{'other_user':other,'last_message':preview,'last_time':m.created_at.strftime("%H:%M"),'unread':unread,'is_muted':muted})())
    ctx.update({"chats":chats, "now":now})
    return templates.TemplateResponse(request, "messages.html", ctx)

@app.get("/messages/{username}", response_class=HTMLResponse)
def conversation_page(username: str, request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    other = db.query(models.User).filter(models.User.username==username).first()
    if not other: return RedirectResponse("/messages", 302)
    msgs = db.query(models.Message).filter(
        or_(and_(models.Message.sender_id==user.id, models.Message.receiver_id==other.id), and_(models.Message.sender_id==other.id, models.Message.receiver_id==user.id))
    ).filter(models.Message.group_id==None).order_by(models.Message.created_at.asc()).all()
    for m in msgs:
        if m.receiver_id==user.id and not m.is_read:
            m.is_read=True; m.is_delivered=True
    db.commit()
    is_online = other.last_seen and (datetime.utcnow()-other.last_seen).total_seconds()<300
    ctx.update({"other":other, "messages":msgs, "is_online":is_online})
    return templates.TemplateResponse(request, "conversation.html", ctx)

@app.post("/messages/send")
async def send_message(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    data = await request.json()
    receiver_username = data.get("receiver")
    content = data.get("content","").strip()
    sticker_emoji = data.get("sticker_emoji","")
    reply_to_id = data.get("reply_to_id")
    other = db.query(models.User).filter(models.User.username==receiver_username).first()
    if not other: return JSONResponse({"error":"not found"}, 404)
    m = models.Message(sender_id=user.id, receiver_id=other.id, content=content, reply_to_id=reply_to_id)
    if sticker_emoji:
        m.content = sticker_emoji
    db.add(m)
    db.commit()
    complete_task(user, db, "message")
    return JSONResponse({"ok":True, "id":m.id})

@app.post("/messages/send-image")
async def send_image_msg(request: Request, receiver: str=Form(...), image: UploadFile=File(...), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    other = db.query(models.User).filter(models.User.username==receiver).first()
    if not other: return JSONResponse({"error":"not found"}, 404)
    url, _ = save_file(image)
    if url:
        db.add(models.Message(sender_id=user.id, receiver_id=other.id, image=url))
        db.commit()
    return JSONResponse({"ok":True})

@app.post("/messages/send-voice")
async def send_voice_msg(request: Request, receiver: str=Form(...), voice: UploadFile=File(None), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    other = db.query(models.User).filter(models.User.username==receiver).first()
    if not other: return JSONResponse({"error":"not found"}, 404)
    if voice and voice.filename:
        url, _ = save_file(voice)
        if url:
            db.add(models.Message(sender_id=user.id, receiver_id=other.id, voice=url))
            db.commit()
    return JSONResponse({"ok":True})

@app.post("/messages/send-file")
async def send_file_msg(request: Request, receiver: str=Form(...), file: UploadFile=File(...), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    other = db.query(models.User).filter(models.User.username==receiver).first()
    if not other: return JSONResponse({"error":"not found"}, 404)
    url, _ = save_file(file)
    if url:
        db.add(models.Message(sender_id=user.id, receiver_id=other.id, file_url=url, file_name=file.filename or "file"))
        db.commit()
    return JSONResponse({"ok":True})

@app.get("/messages/poll/{username}")
def poll_messages(username: str, request: Request, after: int=0, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"messages":[]})
    other = db.query(models.User).filter(models.User.username==username).first()
    if not other: return JSONResponse({"messages":[]})
    msgs = db.query(models.Message).filter(
        or_(and_(models.Message.sender_id==user.id, models.Message.receiver_id==other.id), and_(models.Message.sender_id==other.id, models.Message.receiver_id==user.id))
    ).filter(models.Message.id>after, models.Message.is_deleted==False).order_by(models.Message.created_at.asc()).all()
    for m in msgs:
        if m.receiver_id==user.id and not m.is_read:
            m.is_read=True; m.is_delivered=True
    db.commit()
    return JSONResponse({"messages":[{"id":m.id,"sender_id":m.sender_id,"content":m.content or "","image":m.image or "","voice":m.voice or "","time":m.created_at.strftime("%H:%M"),"is_mine":m.sender_id==user.id} for m in msgs]})

@app.post("/messages/{msg_id}/delete")
async def delete_msg(msg_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    m = db.query(models.Message).filter(models.Message.id==msg_id, models.Message.sender_id==user.id).first()
    if m: m.is_deleted=True; m.content=""; db.commit()
    return JSONResponse({"ok":True})

@app.post("/chats/pin/{username}")
async def pin_chat(username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    other = db.query(models.User).filter(models.User.username==username).first()
    if not other: return JSONResponse({"error":"not found"}, 404)
    ex = db.query(models.PinnedChat).filter(models.PinnedChat.user_id==user.id, models.PinnedChat.pinned_user_id==other.id).first()
    if ex: db.delete(ex)
    else: db.add(models.PinnedChat(user_id=user.id, pinned_user_id=other.id))
    db.commit()
    return JSONResponse({"ok":True})

@app.post("/chats/mute/{username}")
async def mute_chat(username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    other = db.query(models.User).filter(models.User.username==username).first()
    if not other: return JSONResponse({"error":"not found"}, 404)
    ex = db.query(models.MutedChat).filter(models.MutedChat.user_id==user.id, models.MutedChat.muted_user_id==other.id).first()
    if ex: db.delete(ex)
    else: db.add(models.MutedChat(user_id=user.id, muted_user_id=other.id))
    db.commit()
    return JSONResponse({"ok":True})

@app.post("/chats/clear/{username}")
async def clear_chat(username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    other = db.query(models.User).filter(models.User.username==username).first()
    if not other: return JSONResponse({"ok":False})
    msgs = db.query(models.Message).filter(or_(and_(models.Message.sender_id==user.id, models.Message.receiver_id==other.id), and_(models.Message.sender_id==other.id, models.Message.receiver_id==user.id))).all()
    for m in msgs: m.is_deleted=True
    db.commit()
    return JSONResponse({"ok":True})

# --- Groups ---
@app.get("/groups", response_class=HTMLResponse)
def groups_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    my_group_ids = [gm.group_id for gm in db.query(models.GroupMember).filter(models.GroupMember.user_id==user.id).all()]
    groups = db.query(models.GroupChat).filter(models.GroupChat.id.in_(my_group_ids)).all()
    ctx["groups"] = groups
    return templates.TemplateResponse(request, "groups.html", ctx)

@app.post("/groups/create")
async def create_group(request: Request, name: str=Form(...), description: str=Form(""), avatar: UploadFile=File(None), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    av_url = ""
    if avatar and avatar.filename:
        url, _ = save_file(avatar)
        if url: av_url = url
    g = models.GroupChat(name=name, description=description, owner_id=user.id, avatar=av_url)
    db.add(g); db.flush()
    db.add(models.GroupMember(group_id=g.id, user_id=user.id, is_admin=True))
    db.commit()
    return RedirectResponse(f"/groups/{g.id}", 302)

@app.get("/groups/{group_id}", response_class=HTMLResponse)
def group_chat_page(group_id: int, request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    g = db.query(models.GroupChat).filter(models.GroupChat.id==group_id).first()
    if not g: return RedirectResponse("/groups", 302)
    member = db.query(models.GroupMember).filter(models.GroupMember.group_id==group_id, models.GroupMember.user_id==user.id).first()
    if not member: return RedirectResponse("/groups", 302)
    msgs = db.query(models.GroupMessage).filter(models.GroupMessage.group_id==group_id).order_by(models.GroupMessage.created_at.asc()).limit(100).all()
    ctx.update({"group":g, "messages":msgs})
    return templates.TemplateResponse(request, "group_chat.html", ctx)

@app.post("/groups/{group_id}/send")
async def send_group_msg(group_id: int, request: Request, content: str=Form(""), image: UploadFile=File(None), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    img_url = ""
    if image and image.filename:
        url, _ = save_file(image)
        if url: img_url = url
    if not content.strip() and not img_url: return RedirectResponse(f"/groups/{group_id}", 302)
    db.add(models.GroupMessage(group_id=group_id, sender_id=user.id, content=content, image=img_url))
    db.commit()
    return RedirectResponse(f"/groups/{group_id}", 302)

@app.get("/api/groups/{group_id}/messages")
def api_group_messages(group_id: int, request: Request, after: int=0, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"messages":[]})
    msgs = db.query(models.GroupMessage).filter(models.GroupMessage.group_id==group_id, models.GroupMessage.id>after).order_by(models.GroupMessage.created_at.asc()).all()
    return JSONResponse({"messages":[{"id":m.id,"sender_id":m.sender_id,"sender_name":m.sender.name or m.sender.username,"sender_initial":m.sender.username[0].upper(),"content":m.content or "","time":m.created_at.strftime("%H:%M"),"is_mine":m.sender_id==user.id} for m in msgs]})

@app.post("/groups/{group_id}/invite/{username}")
def invite_to_group(group_id: int, username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    target = db.query(models.User).filter(models.User.username==username).first()
    if not target: return RedirectResponse(f"/groups/{group_id}", 302)
    ex = db.query(models.GroupMember).filter(models.GroupMember.group_id==group_id, models.GroupMember.user_id==target.id).first()
    if not ex:
        db.add(models.GroupMember(group_id=group_id, user_id=target.id))
        db.commit()
    return RedirectResponse(f"/groups/{group_id}", 302)

# --- Stories ---
@app.get("/stories/create", response_class=HTMLResponse)
def stories_create_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    return templates.TemplateResponse(request, "story_create.html", ctx)

@app.post("/stories/create")
async def create_story(request: Request, media: UploadFile=File(...), text_overlay: str=Form(""), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    url, mtype = save_file(media)
    if not url: return RedirectResponse("/", 302)
    story = models.Story(user_id=user.id, media_url=url, media_type=mtype or "image", text_overlay=text_overlay, expires_at=datetime.utcnow()+timedelta(hours=24))
    db.add(story); db.commit()
    add_points(user, db, 5)
    complete_task(user, db, "story")
    return RedirectResponse("/", 302)

@app.get("/stories/{username}", response_class=HTMLResponse)
def view_stories(username: str, request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    su = db.query(models.User).filter(models.User.username==username).first()
    if not su: return RedirectResponse("/", 302)
    stories = db.query(models.Story).filter(models.Story.user_id==su.id, models.Story.expires_at>datetime.utcnow()).order_by(models.Story.created_at.asc()).all()
    if user:
        for s in stories:
            if not db.query(models.StoryView).filter(models.StoryView.story_id==s.id, models.StoryView.user_id==user.id).first():
                db.add(models.StoryView(story_id=s.id, user_id=user.id))
        db.commit()
    ctx.update({"story_user":su, "stories":stories})
    return templates.TemplateResponse(request, "stories_view.html", ctx)

# --- Reels ---
@app.get("/reels", response_class=HTMLResponse)
def reels_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    reels = db.query(models.Reel).order_by(models.Reel.created_at.desc()).limit(50).all()
    liked_reels = set()
    if user:
        liked_reels = set(r.reel_id for r in db.query(models.ReelLike).filter(models.ReelLike.user_id==user.id).all())
    ctx.update({"reels":reels, "liked_reels":liked_reels})
    return templates.TemplateResponse(request, "reels.html", ctx)

@app.post("/reels/upload")
async def upload_reel(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    form = await request.form()
    video = form.get("video")
    caption = (form.get("caption") or "").strip()
    if not video or not hasattr(video,"filename"): return JSONResponse({"error":"no file"}, 400)
    url, mtype = save_file(video)
    if not url: return JSONResponse({"error":"save failed"}, 400)
    reel = models.Reel(user_id=user.id, video_url=url, caption=caption)
    db.add(reel); db.commit()
    add_points(user, db, 10)
    check_achievement(user, db, "videographer")
    return JSONResponse({"ok":True, "id":reel.id})

@app.post("/reels/{reel_id}/like")
async def like_reel(reel_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    ex = db.query(models.ReelLike).filter(models.ReelLike.user_id==user.id, models.ReelLike.reel_id==reel_id).first()
    liked = False
    if ex: db.delete(ex)
    else: db.add(models.ReelLike(user_id=user.id, reel_id=reel_id)); liked=True
    db.commit()
    count = db.query(models.ReelLike).filter(models.ReelLike.reel_id==reel_id).count()
    return JSONResponse({"liked":liked, "count":count})

@app.post("/reels/{reel_id}/comment")
async def comment_reel(reel_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    data = await request.json()
    content = (data.get("content") or "").strip()
    if not content: return JSONResponse({"error":"empty"}, 400)
    db.add(models.ReelComment(user_id=user.id, reel_id=reel_id, content=content))
    db.commit()
    return JSONResponse({"ok":True})

# --- Search ---
@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str="", db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    users, posts, tags = [], [], []
    if q:
        users = db.query(models.User).filter(or_(models.User.username.ilike(f"%{q}%"), models.User.name.ilike(f"%{q}%"))).limit(20).all()
        posts = db.query(models.Post).filter(models.Post.content.ilike(f"%{q}%"), models.Post.is_published==True).order_by(models.Post.created_at.desc()).limit(20).all()
        tags = db.query(models.Trend).filter(models.Trend.tag.ilike(f"%{q.lstrip('#')}%")).order_by(models.Trend.count.desc()).limit(10).all()
    ctx.update({"query":q, "users":users, "posts":posts, "tags":tags})
    return templates.TemplateResponse(request, "search.html", ctx)

@app.get("/hashtag/{tag}", response_class=HTMLResponse)
def hashtag_page(tag: str, request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    posts = db.query(models.Post).filter(models.Post.content.ilike(f"%#{tag}%"), models.Post.is_published==True).order_by(models.Post.created_at.desc()).limit(50).all()
    ctx.update({"tag":tag, "posts":posts})
    return templates.TemplateResponse(request, "hashtag.html", ctx)

# --- Notifications ---
@app.get("/notifications", response_class=HTMLResponse)
def notifs_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    notifs = db.query(models.Notification).filter(models.Notification.user_id==user.id).order_by(models.Notification.created_at.desc()).limit(80).all()
    ctx.update({"notifications":notifs})
    return templates.TemplateResponse(request, "notifications.html", ctx)

@app.post("/notifications/read-all")
def notifs_read_all(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    db.query(models.Notification).filter(models.Notification.user_id==user.id).update({"is_read":True})
    db.commit()
    return RedirectResponse("/notifications", 302)

@app.post("/notifications/{notif_id}/read")
async def notif_read(notif_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    n = db.query(models.Notification).filter(models.Notification.id==notif_id, models.Notification.user_id==user.id).first()
    if n: n.is_read=True; db.commit()
    return JSONResponse({"ok":True})

# --- Tasks ---
@app.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    raffle = db.query(models.WeeklyRaffle).filter(models.WeeklyRaffle.is_finished==False).order_by(models.WeeklyRaffle.created_at.desc()).first()
    if not raffle:
        now = datetime.utcnow()
        raffle = models.WeeklyRaffle(week_start=now, week_end=now+timedelta(days=7))
        db.add(raffle); db.commit()
    my_tickets = 0
    if raffle:
        entry = db.query(models.RaffleEntry).filter(models.RaffleEntry.raffle_id==raffle.id, models.RaffleEntry.user_id==user.id).first()
        my_tickets = entry.tickets if entry else 0
    challenge = db.query(models.WeeklyChallenge).filter(models.WeeklyChallenge.is_active==True, models.WeeklyChallenge.week_end>datetime.utcnow()).first()
    my_challenge = None
    if challenge:
        my_challenge = db.query(models.UserWeeklyChallenge).filter(models.UserWeeklyChallenge.challenge_id==challenge.id, models.UserWeeklyChallenge.user_id==user.id).first()
        if not my_challenge:
            my_challenge = models.UserWeeklyChallenge(user_id=user.id, challenge_id=challenge.id)
            db.add(my_challenge); db.commit()
    leaderboard = db.query(models.User).order_by(models.User.total_points.desc()).limit(10).all()
    ctx.update({"raffle":raffle, "my_tickets":my_tickets, "weekly_challenge":my_challenge, "leaderboard":leaderboard})
    return templates.TemplateResponse(request, "tasks.html", ctx)

# --- Trends ---
@app.get("/trends", response_class=HTMLResponse)
def trends_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    trends = db.query(models.Trend).order_by(models.Trend.count.desc()).limit(30).all()
    ctx["trends"] = trends
    from builtins import enumerate as _enumerate
    return templates.TemplateResponse(request, "trends.html", {**ctx, "enumerate":_enumerate})

# --- Drafts ---
@app.post("/drafts/save")
async def save_draft(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    data = await request.json()
    content = data.get("content","").strip()
    if not content: return JSONResponse({"error":"empty"}, 400)
    db.add(models.Draft(user_id=user.id, content=content))
    db.commit()
    return JSONResponse({"ok":True})

@app.post("/drafts/{draft_id}/delete")
def delete_draft(draft_id: int, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    d = db.query(models.Draft).filter(models.Draft.id==draft_id, models.Draft.user_id==user.id).first()
    if d: db.delete(d); db.commit()
    return RedirectResponse("/", 302)

# --- Support ---
@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    return templates.TemplateResponse(request, "support.html", ctx)

@app.post("/support")
async def support_submit(request: Request, subject: str=Form(...), message: str=Form(...), email: str=Form(""), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    ctx, _ = base_ctx(request, db)
    user_email = user.email if user else email.strip()
    if not user_email:
        ctx["error"] = "Укажи email"
        return templates.TemplateResponse(request, "support.html", ctx)
    owner = db.query(models.User).filter(models.User.username=="rubl").first()
    text = f"📧 {user.username if user else user_email}\n📌 {subject}\n💬 {message[:300]}"
    if owner:
        db.add(models.Notification(user_id=owner.id, from_user_id=user.id if user else None, type="support", text=text, reply_email=user_email if not user else ""))
        db.commit()
    try:
        from email_service import send_support_confirmation
        send_support_confirmation(user_email, subject)
    except: pass
    ctx["success"] = True
    return templates.TemplateResponse(request, "support.html", ctx)

@app.post("/support/reply/{notif_id}")
def support_reply(notif_id: int, request: Request, reply: str=Form(...), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", 302)
    n = db.query(models.Notification).filter(models.Notification.id==notif_id).first()
    if not n: return RedirectResponse("/notifications", 302)
    if n.from_user_id:
        db.add(models.Notification(user_id=n.from_user_id, from_user_id=user.id, type="support_reply", text=reply))
        db.commit()
    elif n.reply_email:
        try:
            from email_service import send_support_reply
            send_support_reply(n.reply_email, reply)
        except: pass
    return RedirectResponse("/notifications", 302)

# --- Admin ---
@app.post("/admin/block/{username}")
def admin_block(username: str, request: Request, days: int=Form(1), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not can_mod(user): return RedirectResponse("/", 302)
    target = db.query(models.User).filter(models.User.username==username).first()
    if target and not target.is_owner:
        target.is_blocked=True; target.blocked_until=datetime.utcnow()+timedelta(days=days); db.commit()
    return RedirectResponse(f"/profile/{username}", 302)

@app.post("/admin/unblock/{username}")
def admin_unblock(username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not can_mod(user): return RedirectResponse("/", 302)
    target = db.query(models.User).filter(models.User.username==username).first()
    if target: target.is_blocked=False; target.blocked_until=None; db.commit()
    return RedirectResponse(f"/profile/{username}", 302)

@app.post("/admin/star/{username}")
def admin_star(username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", 302)
    target = db.query(models.User).filter(models.User.username==username).first()
    if target: target.is_starred=not target.is_starred; db.commit()
    return RedirectResponse(f"/profile/{username}", 302)

@app.post("/admin/verify/{username}")
def admin_verify(username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", 302)
    target = db.query(models.User).filter(models.User.username==username).first()
    if target: target.is_verified_badge=not target.is_verified_badge; db.commit()
    return RedirectResponse(f"/profile/{username}", 302)

@app.post("/admin/mod/{username}")
def admin_mod(username: str, request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", 302)
    target = db.query(models.User).filter(models.User.username==username).first()
    if target: target.is_moderator=not target.is_moderator; db.commit()
    return RedirectResponse(f"/profile/{username}", 302)

@app.post("/admin/create_promo")
def admin_create_promo(request: Request, code: str=Form(...), days: int=Form(30), max_uses: int=Form(1), db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner: return RedirectResponse("/", 302)
    code = code.upper().strip()
    if not db.query(models.Promocode).filter(models.Promocode.code==code).first():
        db.add(models.Promocode(code=code, days=days, max_uses=max_uses)); db.commit()
    return RedirectResponse(f"/profile/{user.username}", 302)

# --- Terms ---
@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    return templates.TemplateResponse(request, "terms.html", ctx)

# --- Calls (WebRTC signaling) ---
call_sessions = {}

@app.get("/call/{call_type}/{username}", response_class=HTMLResponse)
def call_page(call_type: str, username: str, request: Request, db: Session=Depends(get_db)):
    ctx, user = base_ctx(request, db)
    if not user: return RedirectResponse("/login", 302)
    other = db.query(models.User).filter(models.User.username==username).first()
    if not other: return RedirectResponse("/messages", 302)
    call_id = f"{user.id}_{other.id}_{int(datetime.utcnow().timestamp())}"
    call_sessions[call_id] = {"status":"ringing","caller_id":user.id,"receiver_id":other.id,"offer":None,"answer":None,"ice_candidates":[]}
    ctx.update({"other":other, "call_type":call_type, "call_id":call_id})
    return templates.TemplateResponse(request, "call.html", ctx)

@app.post("/api/call/{call_id}/offer")
async def call_offer(call_id: str, request: Request):
    data = await request.json()
    if call_id in call_sessions:
        call_sessions[call_id]["offer"] = data.get("offer")
        call_sessions[call_id]["status"] = "ringing"
    return JSONResponse({"ok":True})

@app.get("/api/call/{call_id}/status")
def call_status(call_id: str):
    s = call_sessions.get(call_id, {})
    return JSONResponse({"status":s.get("status","ended"),"answer":s.get("answer"),"ice_candidates":s.get("ice_candidates",[])})

@app.post("/api/call/{call_id}/end")
async def call_end(call_id: str):
    if call_id in call_sessions:
        call_sessions[call_id]["status"]="ended"
    return JSONResponse({"ok":True})

# --- Export ---
@app.get("/export-data")
def export_data(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return RedirectResponse("/login", 302)
    posts = db.query(models.Post).filter(models.Post.user_id==user.id).all()
    data = {"username":user.username,"email":user.email,"bio":user.bio or "","created_at":str(user.created_at),"posts":[{"id":p.id,"content":p.content,"created_at":str(p.created_at)} for p in posts]}
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return StreamingResponse(io.BytesIO(content.encode()), media_type="application/json", headers={"Content-Disposition":f"attachment; filename=quant_{user.username}.json"})

@app.post("/delete-account")
async def delete_account(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user: return JSONResponse({"error":"auth"}, 401)
    db.query(models.Like).filter(models.Like.user_id==user.id).delete()
    db.query(models.Whale).filter(models.Whale.user_id==user.id).delete()
    db.query(models.Follow).filter(or_(models.Follow.follower_id==user.id, models.Follow.following_id==user.id)).delete()
    db.query(models.Notification).filter(models.Notification.user_id==user.id).delete()
    db.query(models.Bookmark).filter(models.Bookmark.user_id==user.id).delete()
    for p in db.query(models.Post).filter(models.Post.user_id==user.id).all():
        delete_file(p.image)
        db.query(models.Like).filter(models.Like.post_id==p.id).delete()
        db.query(models.Comment).filter(models.Comment.post_id==p.id).delete()
        db.delete(p)
    delete_file(user.avatar)
    delete_file(user.cover)
    db.delete(user)
    db.commit()
    resp = JSONResponse({"ok":True})
    resp.delete_cookie("token")
    return resp

# --- Utility ---
@app.get("/api/ping")
def ping(request: Request, db: Session=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if user: user.last_seen=datetime.utcnow(); db.commit()
    return JSONResponse({"ok":True})

@app.get("/offline", response_class=HTMLResponse)
def offline_page(request: Request):
    return templates.TemplateResponse(request, "offline.html", {})