from fastapi import FastAPI, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
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
from PIL import Image
import io

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "/root/quant/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime"}
ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_VIDEO_SIZE = 20 * 1024 * 1024
MAX_AUDIO_SIZE = 10 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1920

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
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS image VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS media_type VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS image VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS voice VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_delivered BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS text VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS reply_email VARCHAR DEFAULT ''"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), from_user_id INTEGER REFERENCES users(id), type VARCHAR, post_id INTEGER REFERENCES posts(id), text VARCHAR DEFAULT '', reply_email VARCHAR DEFAULT '', is_read BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS verification_codes (id SERIAL PRIMARY KEY, email VARCHAR, code VARCHAR, created_at TIMESTAMP DEFAULT NOW())"))
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
        conn.execute(text("UPDATE users SET is_owner = TRUE WHERE username = 'rubl'"))
        conn.commit()
except Exception as e:
    print(f"DB migration warning: {e}")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="/root/quant/uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

def validate_username(username):
    if len(username) < 3:
        return "Никнейм должен быть не короче 3 символов"
    if len(username) > 30:
        return "Никнейм должен быть не длиннее 30 символов"
    if not re.match(r'^[\w\.\-]+$', username, re.UNICODE):
        return "Никнейм может содержать только буквы, цифры, точку, дефис и подчёркивание"
    return None

def validate_password(password):
    if len(password) < 8:
        return "Пароль должен быть не короче 8 символов"
    if len(password) > 64:
        return "Пароль должен быть не длиннее 64 символов"
    if not re.search(r'[A-Za-zА-Яа-яЁё]', password):
        return "Пароль должен содержать хотя бы одну букву"
    if not re.search(r'\d', password):
        return "Пароль должен содержать хотя бы одну цифру"
    simple = ["12345678", "password", "qwerty123", "11111111", "00000000", "123456789"]
    if password.lower() in simple:
        return "Пароль слишком простой, придумай другой"
    return None

def get_unread(user, db):
    if not user:
        return 0
    return db.query(models.Notification).filter(models.Notification.user_id == user.id, models.Notification.is_read == False).count()

def get_unread_messages(user, db):
    if not user:
        return 0
    return db.query(models.Message).filter(models.Message.receiver_id == user.id, models.Message.is_read == False).count()

def get_unread_from(user, db):
    if not user:
        return set()
    msgs = db.query(models.Message.sender_id).filter(models.Message.receiver_id == user.id, models.Message.is_read == False).distinct().all()
    return set(m[0] for m in msgs)

def can_moderate(user):
    if not user:
        return False
    return bool(user.is_owner) or bool(user.is_moderator)

def is_user_blocked(user):
    if not user:
        return False
    if not user.is_blocked:
        return False
    if user.blocked_until and datetime.utcnow() > user.blocked_until:
        return False
    return True

def is_user_plus(user):
    if not user:
        return False
    if not user.is_plus:
        return False
    if user.plus_until and datetime.utcnow() > user.plus_until:
        return False
    return True

def check_stop_words(content, db):
    words = db.query(models.StopWord).all()
    content_lower = content.lower()
    for sw in words:
        if sw.word.lower() in content_lower:
            return True
    return False

def save_media_file(upload: UploadFile):
    if not upload or not upload.filename:
        return None, None
    content_type = (upload.content_type or "").lower()
    contents = upload.file.read()
    file_size = len(contents)
    if content_type in ALLOWED_IMAGE_TYPES:
        if file_size > MAX_IMAGE_SIZE:
            return None, f"Фото слишком большое (макс. {MAX_IMAGE_SIZE // 1024 // 1024} МБ)"
        media_type = "image"
    elif content_type in ALLOWED_VIDEO_TYPES:
        if file_size > MAX_VIDEO_SIZE:
            return None, f"Видео слишком большое (макс. {MAX_VIDEO_SIZE // 1024 // 1024} МБ)"
        media_type = "video"
    else:
        return None, "Неподдерживаемый формат. Разрешены: JPG, PNG, WEBP, MP4"
    ext = ".jpg"
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"
    elif "mp4" in content_type:
        ext = ".mp4"
    elif "quicktime" in content_type:
        ext = ".mov"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    if media_type == "image":
        try:
            img = Image.open(io.BytesIO(contents))
            img = _auto_rotate(img)
            if img.width > MAX_IMAGE_DIMENSION or img.height > MAX_IMAGE_DIMENSION:
                img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
            if ext == ".jpg" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            save_params = {"optimize": True}
            if ext in (".jpg", ".jpeg"):
                save_params["quality"] = 85
            elif ext == ".webp":
                save_params["quality"] = 85
            img.save(filepath, **save_params)
        except Exception as e:
            print(f"Image processing error: {e}")
            return None, "Не удалось обработать фото"
    else:
        with open(filepath, "wb") as f:
            f.write(contents)
    return f"/uploads/{filename}", media_type

def save_audio_file(upload: UploadFile):
    if not upload or not upload.filename:
        return None
    contents = upload.file.read()
    if len(contents) > MAX_AUDIO_SIZE:
        return None
    ext = ".webm"
    content_type = (upload.content_type or "").lower()
    if "ogg" in content_type:
        ext = ".ogg"
    elif "mp4" in content_type or "m4a" in content_type:
        ext = ".mp4"
    elif "mpeg" in content_type or "mp3" in content_type:
        ext = ".mp3"
    elif "wav" in content_type:
        ext = ".wav"
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
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)
    except Exception:
        pass
    return img

def delete_media_file(url):
    if not url or not url.startswith("/uploads/"):
        return
    filename = url.replace("/uploads/", "")
    filepath = os.path.join(UPLOAD_DIR, filename)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"Could not delete file {filepath}: {e}")

def process_mentions(content, author, post_id, db):
    mentions = re.findall(r'@([\w\.\-]+)', content)
    notified = set()
    for username in mentions:
        if username in notified:
            continue
        mentioned_user = db.query(models.User).filter(models.User.username == username).first()
        if mentioned_user and mentioned_user.id != author.id:
            db.add(models.Notification(
                user_id=mentioned_user.id,
                from_user_id=author.id,
                type="mention",
                post_id=post_id
            ))
            notified.add(username)

def render_mentions(content):
    return re.sub(
        r'@([\w\.\-]+)',
        r'<a href="/profile/\1" style="color:#1d9bf0;font-weight:600;">@\1</a>',
        content
    )

BLOCKED_RESPONSE = """<html><body style='font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#f5f5f5;margin:0'><div style='background:#fff;border-radius:16px;padding:40px;text-align:center;border:1px solid #e8e8e8;max-width:400px'><div style='font-size:48px;margin-bottom:16px'>🚫</div><h2 style='margin-bottom:8px'>Аккаунт заблокирован</h2><p style='color:#888;margin-bottom:24px'>Ваш аккаунт временно заблокирован администратором. Вы можете только просматривать ленту.</p><a href='/' style='background:#0f0f0f;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600'>На главную</a></div></body></html>"""

@app.get("/", response_class=HTMLResponse)
def home(request: Request, tab: str = "foryou", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    expired = db.query(models.Story).filter(models.Story.expires_at < datetime.utcnow()).all()
    for s in expired:
        delete_media_file(s.media_url)
        db.query(models.StoryView).filter(models.StoryView.story_id == s.id).delete()
        db.delete(s)
    if expired:
        db.commit()
    active_stories = db.query(models.Story).filter(models.Story.expires_at > datetime.utcnow()).order_by(models.Story.created_at.asc()).all()
    seen_users = set()
    stories_data = []
    my_story = None
    for s in active_stories:
        if user and s.user_id == user.id:
            if my_story is None:
                my_story = s
            continue
        if s.user_id not in seen_users:
            seen_users.add(s.user_id)
            user_stories = [x for x in active_stories if x.user_id == s.user_id]
            first_story = user_stories[0]
            seen = False
            if user:
                view = db.query(models.StoryView).filter(models.StoryView.story_id == first_story.id, models.StoryView.user_id == user.id).first()
                seen = view is not None
            stories_data.append({"user": s.author, "first_story_id": first_story.id, "seen": seen})
    if tab == "following" and user:
        following_ids = [f.following_id for f in user.following]
        posts = db.query(models.Post).filter(models.Post.user_id.in_(following_ids)).order_by(models.Post.created_at.desc()).all()
    else:
        posts = db.query(models.Post).order_by(models.Post.created_at.desc()).limit(200).all()
        following_ids = set()
        if user:
            following_ids = set(f.following_id for f in user.following)
        now = datetime.utcnow()
        def score(post):
            age_hours = max((now - post.created_at).total_seconds() / 3600, 0.1)
            freshness = 1000 / (age_hours + 2)
            likes = len(post.likes) * 3
            comments = len(post.comments) * 2
            whales = len(post.whales) * 1
            follow_bonus = 50 if post.user_id in following_ids else 0
            return freshness + likes + comments + whales + follow_bonus
        posts = sorted(posts, key=score, reverse=True)
    return templates.TemplateResponse(request, "home.html", {"user": user, "posts": posts, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "tab": tab, "is_plus": is_user_plus(user), "stories_data": stories_data, "my_story": my_story, "render_mentions": render_mentions})

@app.get("/post/{post_id}", response_class=HTMLResponse)
def post_page(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "post.html", {"user": user, "post": post, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "is_plus": is_user_plus(user), "render_mentions": render_mentions})

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {})

@app.post("/register")
def register(request: Request, name: str = Form(...), username: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    error = validate_username(username)
    if error:
        return templates.TemplateResponse(request, "register.html", {"error": error})
    error = validate_password(password)
    if error:
        return templates.TemplateResponse(request, "register.html", {"error": error})
    if db.query(models.User).filter(models.User.username == username).first():
        return templates.TemplateResponse(request, "register.html", {"error": f"Никнейм @{username} уже занят"})
    if db.query(models.User).filter(models.User.email == email).first():
        return templates.TemplateResponse(request, "register.html", {"error": "Этот email уже зарегистрирован"})
    user = models.User(name=name, username=username, email=email, password=auth.hash_password(password), is_verified=True)
    db.add(user)
    db.commit()
    token = auth.create_token({"sub": username})
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("token", token)
    return response

@app.post("/verify")
def verify(request: Request, email: str = Form(...), username: str = Form(...), name: str = Form(...), password: str = Form(...), code: str = Form(...), db: Session = Depends(get_db)):
    vc = db.query(models.VerificationCode).filter(models.VerificationCode.email == email, models.VerificationCode.code == code).first()
    if not vc:
        return templates.TemplateResponse(request, "verify.html", {"request": request, "email": email, "username": username, "name": name, "password": password, "error": "Неверный код"})
    if (datetime.utcnow() - vc.created_at).seconds > 600:
        return templates.TemplateResponse(request, "verify.html", {"request": request, "email": email, "username": username, "name": name, "password": password, "error": "Код истёк"})
    user = models.User(name=name, username=username, email=email, password=auth.hash_password(password), is_verified=True)
    db.add(user)
    db.query(models.VerificationCode).filter(models.VerificationCode.email == email).delete()
    db.commit()
    token = auth.create_token({"sub": username})
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("token", token)
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
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("token")
    return response

@app.post("/post")
async def create_post(request: Request, content: str = Form(...), media: UploadFile = File(None), poll_question: str = Form(""), poll_option_1: str = Form(""), poll_option_2: str = Form(""), poll_option_3: str = Form(""), poll_option_4: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    if not content or not content.strip():
        return RedirectResponse("/", status_code=302)
    if check_stop_words(content, db):
        posts = db.query(models.Post).order_by(models.Post.created_at.desc()).all()
        return templates.TemplateResponse(request, "home.html", {"user": user, "posts": posts, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "tab": "foryou", "upload_error": "⛔ Пост содержит запрещённые слова", "is_plus": is_user_plus(user), "stories_data": [], "my_story": None, "render_mentions": render_mentions})
    media_url = ""
    media_type = ""
    if media and media.filename:
        url, type_or_error = save_media_file(media)
        if url is None and type_or_error:
            posts = db.query(models.Post).order_by(models.Post.created_at.desc()).all()
            return templates.TemplateResponse(request, "home.html", {"user": user, "posts": posts, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "tab": "foryou", "upload_error": type_or_error, "is_plus": is_user_plus(user), "stories_data": [], "my_story": None, "render_mentions": render_mentions})
        if url:
            media_url = url
            media_type = type_or_error
    post = models.Post(content=content, user_id=user.id, image=media_url, media_type=media_type)
    db.add(post)
    db.flush()
    # Создаём опрос если заполнен вопрос и хотя бы 2 варианта
    if poll_question.strip():
        options = [o.strip() for o in [poll_option_1, poll_option_2, poll_option_3, poll_option_4] if o.strip()]
        if len(options) >= 2:
            poll = models.Poll(post_id=post.id, question=poll_question.strip())
            db.add(poll)
            db.flush()
            for opt_text in options:
                db.add(models.PollOption(poll_id=poll.id, text=opt_text))
    process_mentions(content, user, post.id, db)
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/poll/vote/{option_id}")
def poll_vote(option_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    option = db.query(models.PollOption).filter(models.PollOption.id == option_id).first()
    if not option:
        return RedirectResponse("/", status_code=302)
    poll = option.poll
    existing = db.query(models.PollVote).filter(models.PollVote.user_id == user.id, models.PollVote.poll_id == poll.id).first()
    if existing:
        return RedirectResponse(f"/post/{poll.post_id}", status_code=302)
    db.add(models.PollVote(user_id=user.id, option_id=option_id, poll_id=poll.id))
    db.commit()
    return RedirectResponse(f"/post/{poll.post_id}", status_code=302)

@app.post("/delete/{post_id}")
def delete_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    if can_moderate(user):
        post = db.query(models.Post).filter(models.Post.id == post_id).first()
    else:
        post = db.query(models.Post).filter(models.Post.id == post_id, models.Post.user_id == user.id).first()
    if post:
        if post.image:
            delete_media_file(post.image)
        db.query(models.Like).filter(models.Like.post_id == post_id).delete()
        db.query(models.Comment).filter(models.Comment.post_id == post_id).delete()
        db.query(models.Notification).filter(models.Notification.post_id == post_id).delete()
        db.query(models.Whale).filter(models.Whale.post_id == post_id).delete()
        db.query(models.Reaction).filter(models.Reaction.post_id == post_id).delete()
        if post.poll:
            for opt in post.poll.options:
                db.query(models.PollVote).filter(models.PollVote.option_id == opt.id).delete()
            db.query(models.PollOption).filter(models.PollOption.poll_id == post.poll.id).delete()
            db.query(models.PollVote).filter(models.PollVote.poll_id == post.poll.id).delete()
            db.delete(post.poll)
        db.delete(post)
        db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/delete_comment/{comment_id}")
def delete_comment(comment_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    if can_moderate(user):
        comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    else:
        comment = db.query(models.Comment).filter(models.Comment.id == comment_id, models.Comment.user_id == user.id).first()
    if comment:
        db.delete(comment)
        db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/like/{post_id}")
def like_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    existing = db.query(models.Like).filter(models.Like.user_id == user.id, models.Like.post_id == post_id).first()
    if existing:
        db.delete(existing)
    else:
        db.add(models.Like(user_id=user.id, post_id=post_id))
        post = db.query(models.Post).filter(models.Post.id == post_id).first()
        if post and post.user_id != user.id:
            db.add(models.Notification(user_id=post.user_id, from_user_id=user.id, type="like", post_id=post_id))
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/whale/{post_id}")
def whale_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    existing = db.query(models.Whale).filter(models.Whale.user_id == user.id, models.Whale.post_id == post_id).first()
    if existing:
        db.delete(existing)
    else:
        db.add(models.Whale(user_id=user.id, post_id=post_id))
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/react/{post_id}")
def react_post(post_id: int, request: Request, emoji: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    if not is_user_plus(user):
        return RedirectResponse("/", status_code=302)
    allowed = ["🔥", "😂", "😮", "😢", "👏", "🎉"]
    if emoji not in allowed:
        return RedirectResponse("/", status_code=302)
    existing = db.query(models.Reaction).filter(models.Reaction.user_id == user.id, models.Reaction.post_id == post_id, models.Reaction.emoji == emoji).first()
    if existing:
        db.delete(existing)
    else:
        db.add(models.Reaction(user_id=user.id, post_id=post_id, emoji=emoji))
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/comment/{post_id}")
def add_comment(post_id: int, request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    if check_stop_words(content, db):
        return RedirectResponse(f"/post/{post_id}?error=stopword", status_code=302)
    comment = models.Comment(content=content, user_id=user.id, post_id=post_id)
    db.add(comment)
    db.flush()
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if post and post.user_id != user.id:
        db.add(models.Notification(user_id=post.user_id, from_user_id=user.id, type="comment", post_id=post_id))
    process_mentions(content, user, post_id, db)
    db.commit()
    return RedirectResponse(f"/post/{post_id}", status_code=302)

@app.get("/profile/{username}", response_class=HTMLResponse)
def profile(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = auth.get_current_user(request, db)
    profile_user = db.query(models.User).filter(models.User.username == username).first()
    if not profile_user:
        return RedirectResponse("/", status_code=302)
    posts = db.query(models.Post).filter(models.Post.user_id == profile_user.id).order_by(models.Post.created_at.desc()).all()
    is_following = False
    if current_user:
        is_following = db.query(models.Follow).filter(models.Follow.follower_id == current_user.id, models.Follow.following_id == profile_user.id).first() is not None
    following_ids = set(f.following_id for f in profile_user.following)
    follower_ids = set(f.follower_id for f in profile_user.followers)
    friend_ids = following_ids & follower_ids
    friends = db.query(models.User).filter(models.User.id.in_(friend_ids)).all() if friend_ids else []
    is_friend = False
    if current_user and current_user.id != profile_user.id and is_following:
        is_friend = db.query(models.Follow).filter(models.Follow.follower_id == profile_user.id, models.Follow.following_id == current_user.id).first() is not None
    promocodes = []
    if current_user and current_user.is_owner and current_user.username == username:
        promocodes = db.query(models.Promocode).order_by(models.Promocode.created_at.desc()).all()
    stop_words = []
    if current_user and current_user.is_owner and current_user.username == username:
        stop_words = db.query(models.StopWord).order_by(models.StopWord.created_at.desc()).all()
    return templates.TemplateResponse(request, "profile.html", {"user": current_user, "profile_user": profile_user, "posts": posts, "is_following": is_following, "friends": friends, "is_friend": is_friend, "unread": get_unread(current_user, db), "unread_msg": get_unread_messages(current_user, db), "is_plus": is_user_plus(current_user), "profile_is_plus": is_user_plus(profile_user), "promocodes": promocodes, "render_mentions": render_mentions, "stop_words": stop_words})

@app.post("/follow/{username}")
def follow(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = auth.get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(current_user):
        return HTMLResponse(BLOCKED_RESPONSE)
    target = db.query(models.User).filter(models.User.username == username).first()
    if not target or target.id == current_user.id:
        return RedirectResponse("/", status_code=302)
    existing = db.query(models.Follow).filter(models.Follow.follower_id == current_user.id, models.Follow.following_id == target.id).first()
    if existing:
        db.delete(existing)
    else:
        db.add(models.Follow(follower_id=current_user.id, following_id=target.id))
        db.add(models.Notification(user_id=target.id, from_user_id=current_user.id, type="follow"))
    db.commit()
    return RedirectResponse(f"/profile/{username}", status_code=302)

@app.get("/messages", response_class=HTMLResponse)
def messages_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    conversations = db.query(models.User).join(models.Message, (models.Message.sender_id == user.id) | (models.Message.receiver_id == user.id)).filter(models.User.id != user.id).distinct().all()
    unread_from = get_unread_from(user, db)
    return templates.TemplateResponse(request, "messages.html", {"user": user, "conversations": conversations, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "unread_from": unread_from})

@app.get("/messages/{username}", response_class=HTMLResponse)
def conversation(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other:
        return RedirectResponse("/messages", status_code=302)
    msgs = db.query(models.Message).filter(((models.Message.sender_id == user.id) & (models.Message.receiver_id == other.id)) | ((models.Message.sender_id == other.id) & (models.Message.receiver_id == user.id))).order_by(models.Message.created_at).all()
    for msg in msgs:
        if msg.receiver_id == user.id and not msg.is_read:
            msg.is_read = True
            msg.is_delivered = True
    db.commit()
    return templates.TemplateResponse(request, "conversation.html", {"user": user, "other": other, "messages": msgs, "unread": get_unread(user, db), "unread_msg": 0})

@app.post("/messages/{username}")
async def send_message(username: str, request: Request, content: str = Form(""), image: UploadFile = File(None), voice: UploadFile = File(None), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other:
        return RedirectResponse("/messages", status_code=302)
    image_url = ""
    voice_url = ""
    if image and image.filename:
        url, _ = save_media_file(image)
        if url:
            image_url = url
    if voice and voice.filename:
        url = save_audio_file(voice)
        if url:
            voice_url = url
    if not content.strip() and not image_url and not voice_url:
        return RedirectResponse(f"/messages/{username}", status_code=302)
    db.add(models.Message(sender_id=user.id, receiver_id=other.id, content=content, image=image_url, voice=voice_url, is_delivered=True))
    db.commit()
    return RedirectResponse(f"/messages/{username}", status_code=302)

@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    results = []
    if q:
        results = db.query(models.User).filter(models.User.username.ilike(f"%{q}%") | models.User.name.ilike(f"%{q}%")).limit(20).all()
    return templates.TemplateResponse(request, "search.html", {"user": user, "results": results, "q": q, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db)})

@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    notifs = db.query(models.Notification).filter(models.Notification.user_id == user.id).order_by(models.Notification.created_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "notifications.html", {"user": user, "notifications": notifs, "unread": 0, "unread_msg": get_unread_messages(user, db)})

@app.post("/notifications/read")
def notifications_read(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    db.query(models.Notification).filter(models.Notification.user_id == user.id).update({"is_read": True})
    db.commit()
    return RedirectResponse("/notifications", status_code=302)

@app.post("/support/reply/{notif_id}")
def support_reply(notif_id: int, request: Request, reply: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner:
        return RedirectResponse("/", status_code=302)
    notif = db.query(models.Notification).filter(models.Notification.id == notif_id).first()
    if not notif:
        return RedirectResponse("/notifications", status_code=302)
    from email_service import send_support_reply
    if notif.from_user_id:
        sender = db.query(models.User).filter(models.User.id == notif.from_user_id).first()
        if sender:
            db.add(models.Notification(user_id=sender.id, from_user_id=user.id, type="support_reply", text=reply))
            db.commit()
    elif notif.reply_email:
        send_support_reply(notif.reply_email, reply)
    return RedirectResponse("/notifications", status_code=302)

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(request, "settings.html", {"user": user, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "is_plus": is_user_plus(user)})

@app.post("/settings")
async def settings_save(request: Request, name: str = Form(...), bio: str = Form(""), username: str = Form(...), avatar: UploadFile = File(None), plus_color: str = Form("#a855f7"), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    error = validate_username(username)
    if error:
        return templates.TemplateResponse(request, "settings.html", {"user": user, "error": error})
    existing = db.query(models.User).filter(models.User.username == username, models.User.id != user.id).first()
    if existing:
        return templates.TemplateResponse(request, "settings.html", {"user": user, "error": f"Никнейм @{username} уже занят"})
    if avatar and avatar.filename:
        content_type = (avatar.content_type or "").lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            return templates.TemplateResponse(request, "settings.html", {"user": user, "error": "Для аватарки разрешены только JPG, PNG, WEBP"})
        contents = await avatar.read()
        if len(contents) > MAX_IMAGE_SIZE:
            return templates.TemplateResponse(request, "settings.html", {"user": user, "error": "Фото слишком большое (макс. 10 МБ)"})
        try:
            img = Image.open(io.BytesIO(contents))
            img = _auto_rotate(img)
            img.thumbnail((400, 400), Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            filename = f"avatar_{uuid.uuid4().hex}.jpg"
            filepath = os.path.join(UPLOAD_DIR, filename)
            img.save(filepath, quality=85, optimize=True)
            if user.avatar:
                delete_media_file(user.avatar)
            user.avatar = f"/uploads/{filename}"
        except Exception as e:
            print(f"Avatar error: {e}")
            return templates.TemplateResponse(request, "settings.html", {"user": user, "error": "Не удалось обработать фото"})
    if is_user_plus(user) and re.match(r'^#[0-9a-fA-F]{6}$', plus_color):
        user.plus_color = plus_color
    user.name = name
    user.bio = bio
    user.username = username
    db.commit()
    token = auth.create_token({"sub": username})
    response = RedirectResponse(f"/profile/{username}", status_code=302)
    response.set_cookie("token", token)
    return response

@app.post("/settings/password")
def change_password(request: Request, old_password: str = Form(...), new_password: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not auth.verify_password(old_password, user.password):
        return templates.TemplateResponse(request, "settings.html", {"user": user, "error": "Старый пароль неверный"})
    error = validate_password(new_password)
    if error:
        return templates.TemplateResponse(request, "settings.html", {"user": user, "error": error})
    user.password = auth.hash_password(new_password)
    db.commit()
    return templates.TemplateResponse(request, "settings.html", {"user": user, "success": "Пароль успешно изменён"})

@app.post("/activate_plus")
def activate_plus(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    promo = db.query(models.Promocode).filter(models.Promocode.code == code.upper().strip(), models.Promocode.is_active == True).first()
    if not promo or promo.uses >= promo.max_uses:
        return templates.TemplateResponse(request, "settings.html", {"user": user, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "is_plus": is_user_plus(user), "error": "Промокод не найден, уже использован или истёк"})
    promo.uses += 1
    if promo.uses >= promo.max_uses:
        promo.is_active = False
    user.is_plus = True
    user.plus_until = datetime.utcnow() + timedelta(days=promo.days)
    db.commit()
    return templates.TemplateResponse(request, "settings.html", {"user": user, "unread": get_unread(user, db), "unread_msg": get_unread_messages(user, db), "is_plus": True, "success": f"Quant Plus активирован на {promo.days} дней!"})

@app.post("/admin/block/{username}")
def block_user(username: str, request: Request, days: int = Form(1), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner:
        return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target and not target.is_owner:
        target.is_blocked = True
        target.blocked_until = datetime.utcnow() + timedelta(days=days)
        db.commit()
    return RedirectResponse(f"/profile/{username}", status_code=302)

@app.post("/admin/unblock/{username}")
def unblock_user(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner:
        return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target:
        target.is_blocked = False
        target.blocked_until = None
        db.commit()
    return RedirectResponse(f"/profile/{username}", status_code=302)

@app.post("/admin/create_promo")
def create_promo(request: Request, code: str = Form(...), days: int = Form(30), max_uses: int = Form(1), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner:
        return RedirectResponse("/", status_code=302)
    code = code.upper().strip()
    existing = db.query(models.Promocode).filter(models.Promocode.code == code).first()
    if existing:
        return RedirectResponse(f"/profile/{user.username}?error=promo_exists", status_code=302)
    db.add(models.Promocode(code=code, days=days, max_uses=max_uses))
    db.commit()
    return RedirectResponse(f"/profile/{user.username}", status_code=302)

@app.post("/admin/star/{username}")
def give_star(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner:
        return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target:
        target.is_starred = not target.is_starred
        db.commit()
    return RedirectResponse(f"/profile/{username}", status_code=302)

@app.post("/admin/verify/{username}")
def give_verify(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner:
        return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target:
        target.is_verified_badge = not target.is_verified_badge
        db.commit()
    return RedirectResponse(f"/profile/{username}", status_code=302)

@app.post("/admin/mod/{username}")
def give_mod(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner:
        return RedirectResponse("/", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if target:
        target.is_moderator = not target.is_moderator
        db.commit()
    return RedirectResponse(f"/profile/{username}", status_code=302)

@app.post("/admin/stopword/add")
def add_stop_word(request: Request, word: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner:
        return RedirectResponse("/", status_code=302)
    word = word.strip().lower()
    if word and not db.query(models.StopWord).filter(models.StopWord.word == word).first():
        db.add(models.StopWord(word=word))
        db.commit()
    return RedirectResponse(f"/profile/{user.username}", status_code=302)

@app.post("/admin/stopword/delete/{word_id}")
def delete_stop_word(word_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user or not user.is_owner:
        return RedirectResponse("/", status_code=302)
    sw = db.query(models.StopWord).filter(models.StopWord.id == word_id).first()
    if sw:
        db.delete(sw)
        db.commit()
    return RedirectResponse(f"/profile/{user.username}", status_code=302)

@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    return templates.TemplateResponse(request, "support.html", {"user": user, "unread": get_unread(user, db) if user else 0, "unread_msg": get_unread_messages(user, db) if user else 0})

@app.post("/support")
def support_submit(request: Request, subject: str = Form(...), message: str = Form(...), email: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    user_email = user.email if user else email.strip()
    if not user_email:
        return templates.TemplateResponse(request, "support.html", {"user": user, "unread": get_unread(user, db) if user else 0, "unread_msg": get_unread_messages(user, db) if user else 0, "error": "Укажи email для ответа"})
    owner = db.query(models.User).filter(models.User.username == "rubl").first()
    sender_name = user.username if user else user_email
    notif_text = f"📧 {sender_name}\n📌 {subject}\n💬 {message[:300]}"
    if owner:
        db.add(models.Notification(user_id=owner.id, from_user_id=user.id if user else None, type="support", text=notif_text, reply_email=user_email if not user else ""))
        db.commit()
    try:
        from email_service import send_support_confirmation
        send_support_confirmation(user_email, subject)
    except Exception as e:
        print(f"Support email error: {e}")
    return templates.TemplateResponse(request, "support.html", {"user": user, "unread": get_unread(user, db) if user else 0, "unread_msg": get_unread_messages(user, db) if user else 0, "success": True})

@app.get("/terms", response_class=HTMLResponse)
def terms(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    return templates.TemplateResponse(request, "terms.html", {"user": user, "unread": get_unread(user, db) if user else 0, "unread_msg": get_unread_messages(user, db) if user else 0})

@app.get("/auth/yandex")
def yandex_login():
    from yandex_auth import YANDEX_CLIENT_ID, YANDEX_REDIRECT_URI, YANDEX_AUTH_URL
    url = f"{YANDEX_AUTH_URL}?response_type=code&client_id={YANDEX_CLIENT_ID}&redirect_uri={YANDEX_REDIRECT_URI}"
    return RedirectResponse(url)

@app.get("/api/messages/{username}")
def api_messages(username: str, request: Request, after: int = 0, db: Session = Depends(get_db)):
    from fastapi.responses import JSONResponse
    user = auth.get_current_user(request, db)
    if not user:
        return JSONResponse({"messages": []})
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other:
        return JSONResponse({"messages": []})
    msgs = db.query(models.Message).filter(
        ((models.Message.sender_id == user.id) & (models.Message.receiver_id == other.id)) |
        ((models.Message.sender_id == other.id) & (models.Message.receiver_id == user.id))
    ).filter(models.Message.id > after).order_by(models.Message.created_at).all()
    for msg in msgs:
        if msg.receiver_id == user.id and not msg.is_read:
            msg.is_read = True
            msg.is_delivered = True
    db.commit()
    return JSONResponse({"messages": [{"id": m.id, "sender_id": m.sender_id, "content": m.content, "image": m.image or "", "voice": m.voice or "", "time": m.created_at.strftime("%H:%M"), "is_read": m.is_read, "is_delivered": m.is_delivered} for m in msgs]})

@app.post("/api/typing/{username}")
def api_typing(username: str, request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import JSONResponse
    user = auth.get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False})
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other:
        return JSONResponse({"ok": False})
    ts = db.query(models.TypingStatus).filter(models.TypingStatus.user_id == user.id, models.TypingStatus.target_id == other.id).first()
    if ts:
        ts.updated_at = datetime.utcnow()
    else:
        db.add(models.TypingStatus(user_id=user.id, target_id=other.id))
    db.commit()
    return JSONResponse({"ok": True})

@app.get("/api/typing/{username}")
def api_typing_check(username: str, request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import JSONResponse
    user = auth.get_current_user(request, db)
    if not user:
        return JSONResponse({"typing": False})
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other:
        return JSONResponse({"typing": False})
    threshold = datetime.utcnow() - timedelta(seconds=4)
    ts = db.query(models.TypingStatus).filter(models.TypingStatus.user_id == other.id, models.TypingStatus.target_id == user.id, models.TypingStatus.updated_at > threshold).first()
    return JSONResponse({"typing": ts is not None})

@app.get("/api/users/search")
def api_users_search(q: str = "", db: Session = Depends(get_db)):
    from fastapi.responses import JSONResponse
    if not q or len(q) < 1:
        return JSONResponse({"users": []})
    results = db.query(models.User).filter(models.User.username.ilike(f"{q}%")).limit(5).all()
    return JSONResponse({"users": [{"username": u.username, "name": u.name or u.username} for u in results]})

@app.get("/auth/yandex/callback")
async def yandex_callback(code: str, request: Request, db: Session = Depends(get_db)):
    import httpx
    from yandex_auth import YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET, YANDEX_REDIRECT_URI, YANDEX_TOKEN_URL, YANDEX_USER_URL
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(YANDEX_TOKEN_URL, data={"grant_type": "authorization_code", "code": code, "client_id": YANDEX_CLIENT_ID, "client_secret": YANDEX_CLIENT_SECRET, "redirect_uri": YANDEX_REDIRECT_URI})
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return RedirectResponse("/login?error=yandex", status_code=302)
        user_resp = await client.get(YANDEX_USER_URL, headers={"Authorization": f"OAuth {access_token}"})
        yandex_user = user_resp.json()
    yandex_id = str(yandex_user.get("id", ""))
    email = yandex_user.get("default_email", f"yandex_{yandex_id}@yandex.ru")
    name = yandex_user.get("real_name") or yandex_user.get("display_name") or "Пользователь"
    username_base = yandex_user.get("login", f"yandex_{yandex_id}")
    username_base = re.sub(r'[^\w\.\-]', '_', username_base)[:28]
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        username = username_base
        counter = 1
        while db.query(models.User).filter(models.User.username == username).first():
            username = f"{username_base}_{counter}"
            counter += 1
        user = models.User(name=name, username=username, email=email, password=auth.hash_password(yandex_id + "yandex"), is_verified=True)
        db.add(user)
        db.commit()
    token = auth.create_token({"sub": user.username})
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("token", token)
    return response

@app.post("/story/upload")
async def story_upload(request: Request, media: UploadFile = File(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if is_user_blocked(user):
        return HTMLResponse(BLOCKED_RESPONSE)
    url, type_or_error = save_media_file(media)
    if url is None:
        return RedirectResponse("/", status_code=302)
    expires = datetime.utcnow() + timedelta(hours=24)
    story = models.Story(user_id=user.id, media_url=url, media_type=type_or_error, expires_at=expires)
    db.add(story)
    db.commit()
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
    return templates.TemplateResponse(request, "story_view.html", {"user": user, "story": story, "all_stories": all_stories, "current_index": current_index, "views_count": views_count, "unread": get_unread(user, db) if user else 0, "unread_msg": get_unread_messages(user, db) if user else 0})

@app.post("/story/delete/{story_id}")
def story_delete(story_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if story and (story.user_id == user.id or user.is_owner):
        delete_media_file(story.media_url)
        db.query(models.StoryView).filter(models.StoryView.story_id == story_id).delete()
        db.delete(story)
        db.commit()
    return RedirectResponse("/", status_code=302)