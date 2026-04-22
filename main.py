from fastapi import FastAPI, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import engine, get_db, Base
from datetime import datetime
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
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_VIDEO_SIZE = 20 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1920

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_owner BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_starred BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified_badge BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_moderator BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS image VARCHAR DEFAULT ''"))
        conn.execute(text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS media_type VARCHAR DEFAULT ''"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), from_user_id INTEGER REFERENCES users(id), type VARCHAR, post_id INTEGER REFERENCES posts(id), is_read BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS verification_codes (id SERIAL PRIMARY KEY, email VARCHAR, code VARCHAR, created_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS whales (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), post_id INTEGER REFERENCES posts(id))"))
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

def can_moderate(user):
    if not user:
        return False
    return bool(user.is_owner) or bool(user.is_moderator)

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

@app.get("/", response_class=HTMLResponse)
def home(request: Request, tab: str = "foryou", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if tab == "following" and user:
        following_ids = [f.following_id for f in user.following]
        posts = db.query(models.Post).filter(models.Post.user_id.in_(following_ids)).order_by(models.Post.created_at.desc()).all()
    else:
        posts = db.query(models.Post).order_by(models.Post.created_at.desc()).all()
    return templates.TemplateResponse(request, "home.html", {"user": user, "posts": posts, "unread": get_unread(user, db), "tab": tab})

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
async def create_post(request: Request, content: str = Form(...), media: UploadFile = File(None), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not content or not content.strip():
        return RedirectResponse("/", status_code=302)
    media_url = ""
    media_type = ""
    if media and media.filename:
        url, type_or_error = save_media_file(media)
        if url is None and type_or_error:
            posts = db.query(models.Post).order_by(models.Post.created_at.desc()).all()
            return templates.TemplateResponse(request, "home.html", {"user": user, "posts": posts, "unread": get_unread(user, db), "tab": "foryou", "upload_error": type_or_error})
        if url:
            media_url = url
            media_type = type_or_error
    post = models.Post(content=content, user_id=user.id, image=media_url, media_type=media_type)
    db.add(post)
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/delete/{post_id}")
def delete_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
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
        db.delete(post)
        db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/delete_comment/{comment_id}")
def delete_comment(comment_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
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
    existing = db.query(models.Whale).filter(models.Whale.user_id == user.id, models.Whale.post_id == post_id).first()
    if existing:
        db.delete(existing)
    else:
        db.add(models.Whale(user_id=user.id, post_id=post_id))
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/comment/{post_id}")
def add_comment(post_id: int, request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    db.add(models.Comment(content=content, user_id=user.id, post_id=post_id))
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if post and post.user_id != user.id:
        db.add(models.Notification(user_id=post.user_id, from_user_id=user.id, type="comment", post_id=post_id))
    db.commit()
    return RedirectResponse("/", status_code=302)

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
    return templates.TemplateResponse(request, "profile.html", {"user": current_user, "profile_user": profile_user, "posts": posts, "is_following": is_following, "friends": friends, "is_friend": is_friend, "unread": get_unread(current_user, db)})

@app.post("/follow/{username}")
def follow(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = auth.get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
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
    conversations = db.query(models.User).join(models.Message, (models.Message.sender_id == user.id) | (models.Message.receiver_id == user.id)).filter(models.User.id != user.id).distinct().all()
    return templates.TemplateResponse(request, "messages.html", {"user": user, "conversations": conversations, "unread": get_unread(user, db)})

@app.get("/messages/{username}", response_class=HTMLResponse)
def conversation(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other:
        return RedirectResponse("/messages", status_code=302)
    msgs = db.query(models.Message).filter(((models.Message.sender_id == user.id) & (models.Message.receiver_id == other.id)) | ((models.Message.sender_id == other.id) & (models.Message.receiver_id == user.id))).order_by(models.Message.created_at).all()
    for msg in msgs:
        if msg.receiver_id == user.id and not msg.is_read:
            msg.is_read = True
    db.commit()
    return templates.TemplateResponse(request, "conversation.html", {"user": user, "other": other, "messages": msgs, "unread": get_unread(user, db)})

@app.post("/messages/{username}")
def send_message(username: str, request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other:
        return RedirectResponse("/messages", status_code=302)
    db.add(models.Message(sender_id=user.id, receiver_id=other.id, content=content))
    db.commit()
    return RedirectResponse(f"/messages/{username}", status_code=302)

@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    results = []
    if q:
        results = db.query(models.User).filter(models.User.username.ilike(f"%{q}%") | models.User.name.ilike(f"%{q}%")).limit(20).all()
    return templates.TemplateResponse(request, "search.html", {"user": user, "results": results, "q": q, "unread": get_unread(user, db)})

@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    notifs = db.query(models.Notification).filter(models.Notification.user_id == user.id).order_by(models.Notification.created_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "notifications.html", {"user": user, "notifications": notifs, "unread": 0})

@app.post("/notifications/read")
def notifications_read(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    db.query(models.Notification).filter(models.Notification.user_id == user.id).update({"is_read": True})
    db.commit()
    return RedirectResponse("/notifications", status_code=302)

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(request, "settings.html", {"user": user, "unread": get_unread(user, db)})

@app.post("/settings")
async def settings_save(request: Request, name: str = Form(...), bio: str = Form(""), username: str = Form(...), avatar: UploadFile = File(None), db: Session = Depends(get_db)):
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

@app.get("/terms", response_class=HTMLResponse)
def terms(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    return templates.TemplateResponse(request, "terms.html", {"user": user, "unread": get_unread(user, db)})

@app.get("/auth/yandex")
def yandex_login():
    from yandex_auth import YANDEX_CLIENT_ID, YANDEX_REDIRECT_URI, YANDEX_AUTH_URL
    url = f"{YANDEX_AUTH_URL}?response_type=code&client_id={YANDEX_CLIENT_ID}&redirect_uri={YANDEX_REDIRECT_URI}"
    return RedirectResponse(url)
@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    return templates.TemplateResponse(request, "support.html", {"user": user, "unread": get_unread(user, db)})

@app.post("/support")
def support_submit(request: Request, subject: str = Form(...), message: str = Form(...), email: str = Form(""), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    from email_service import send_support_confirmation
    user_email = user.email if user else email
    if not user_email:
        return templates.TemplateResponse(request, "support.html", {"user": user, "unread": get_unread(user, db), "error": "Укажи email для ответа"})
    username = user.username if user else user_email
    owner = db.query(models.User).filter(models.User.username == "rubl").first()
    if owner:
        db.add(models.Notification(user_id=owner.id, from_user_id=user.id if user else None, type="support"))
        db.commit()
    send_support_confirmation(user_email, subject)
    return templates.TemplateResponse(request, "support.html", {"user": user, "unread": get_unread(user, db), "success": True})
@app.get("/auth/yandex/callback")
async def yandex_callback(code: str, request: Request, db: Session = Depends(get_db)):
    import httpx
    from yandex_auth import YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET, YANDEX_REDIRECT_URI, YANDEX_TOKEN_URL, YANDEX_USER_URL
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(YANDEX_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": YANDEX_CLIENT_ID,
            "client_secret": YANDEX_CLIENT_SECRET,
            "redirect_uri": YANDEX_REDIRECT_URI,
        })
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