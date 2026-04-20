from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import engine, get_db, Base
from sqlalchemy import text
from datetime import datetime
import models
import auth
import re

Base.metadata.create_all(bind=engine)

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                from_user_id INTEGER REFERENCES users(id),
                type VARCHAR,
                post_id INTEGER REFERENCES posts(id),
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                id SERIAL PRIMARY KEY,
                email VARCHAR,
                code VARCHAR,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        try:
            conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS from_user_id INTEGER REFERENCES users(id)"))
            conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS type VARCHAR"))
            conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS post_id INTEGER REFERENCES posts(id)"))
            conn.execute(text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT FALSE"))
        except:
            pass
        conn.commit()
except:
    pass

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def validate_username(username: str):
    if len(username) < 3:
        return "Никнейм должен быть не короче 3 символов"
    if len(username) > 30:
        return "Никнейм должен быть не длиннее 30 символов"
    if not re.match(r'^[\w\.\-]+$', username, re.UNICODE):
        return "Никнейм может содержать только буквы, цифры, точку, дефис и подчёркивание"
    return None

def validate_password(password: str):
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

@app.get("/", response_class=HTMLResponse)
def home(request: Request, tab: str = "foryou", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if tab == "following" and user:
        following_ids = [f.following_id for f in user.following]
        posts = db.query(models.Post).filter(models.Post.user_id.in_(following_ids)).order_by(models.Post.created_at.desc()).all()
    else:
        posts = db.query(models.Post).order_by(models.Post.created_at.desc()).all()
    unread = 0
    if user:
        unread = db.query(models.Notification).filter(
            models.Notification.user_id == user.id,
            models.Notification.is_read == False
        ).count()
    return templates.TemplateResponse(request, "home.html", {"user": user, "posts": posts, "unread": unread, "tab": tab})

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
    from email_service import generate_code, send_verification_email
    code = generate_code()
    db.query(models.VerificationCode).filter(models.VerificationCode.email == email).delete()
    vc = models.VerificationCode(email=email, code=code)
    db.add(vc)
    db.commit()
    send_verification_email(email, code)
    return templates.TemplateResponse(request, "verify.html", {"request": request, "email": email, "username": username, "name": name, "password": password})

@app.post("/verify")
def verify(request: Request, email: str = Form(...), username: str = Form(...), name: str = Form(...), password: str = Form(...), code: str = Form(...), db: Session = Depends(get_db)):
    from datetime import timedelta
    vc = db.query(models.VerificationCode).filter(models.VerificationCode.email == email, models.VerificationCode.code == code).first()
    if not vc:
        return templates.TemplateResponse(request, "verify.html", {"email": email, "username": username, "name": name, "password": password, "error": "Неверный код"})
    if (datetime.utcnow() - vc.created_at).seconds > 600:
        return templates.TemplateResponse(request, "verify.html", {"email": email, "username": username, "name": name, "password": password, "error": "Код истёк, зарегистрируйся заново"})
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
def create_post(request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    post = models.Post(content=content, user_id=user.id)
    db.add(post)
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/delete/{post_id}")
def delete_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    post = db.query(models.Post).filter(models.Post.id == post_id, models.Post.user_id == user.id).first()
    if post:
        db.query(models.Like).filter(models.Like.post_id == post_id).delete()
        db.query(models.Comment).filter(models.Comment.post_id == post_id).delete()
        db.query(models.Notification).filter(models.Notification.post_id == post_id).delete()
        db.delete(post)
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
        like = models.Like(user_id=user.id, post_id=post_id)
        db.add(like)
        post = db.query(models.Post).filter(models.Post.id == post_id).first()
        if post and post.user_id != user.id:
            notif = models.Notification(user_id=post.user_id, from_user_id=user.id, type="like", post_id=post_id)
            db.add(notif)
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/comment/{post_id}")
def add_comment(post_id: int, request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    comment = models.Comment(content=content, user_id=user.id, post_id=post_id)
    db.add(comment)
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if post and post.user_id != user.id:
        notif = models.Notification(user_id=post.user_id, from_user_id=user.id, type="comment", post_id=post_id)
        db.add(notif)
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
        is_following = db.query(models.Follow).filter(
            models.Follow.follower_id == current_user.id,
            models.Follow.following_id == profile_user.id
        ).first() is not None
    unread = 0
    if current_user:
        unread = db.query(models.Notification).filter(
            models.Notification.user_id == current_user.id,
            models.Notification.is_read == False
        ).count()
    return templates.TemplateResponse(request, "profile.html", {
        "user": current_user,
        "profile_user": profile_user,
        "posts": posts,
        "is_following": is_following,
        "unread": unread
    })

@app.post("/follow/{username}")
def follow(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = auth.get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    target = db.query(models.User).filter(models.User.username == username).first()
    if not target or target.id == current_user.id:
        return RedirectResponse("/", status_code=302)
    existing = db.query(models.Follow).filter(
        models.Follow.follower_id == current_user.id,
        models.Follow.following_id == target.id
    ).first()
    if existing:
        db.delete(existing)
    else:
        f = models.Follow(follower_id=current_user.id, following_id=target.id)
        db.add(f)
        notif = models.Notification(user_id=target.id, from_user_id=current_user.id, type="follow")
        db.add(notif)
    db.commit()
    return RedirectResponse(f"/profile/{username}", status_code=302)

@app.get("/messages", response_class=HTMLResponse)
def messages_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    conversations = db.query(models.User).join(
        models.Message,
        (models.Message.sender_id == user.id) | (models.Message.receiver_id == user.id)
    ).filter(models.User.id != user.id).distinct().all()
    unread = db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.is_read == False
    ).count()
    return templates.TemplateResponse(request, "messages.html", {
        "user": user,
        "conversations": conversations,
        "unread": unread
    })

@app.get("/messages/{username}", response_class=HTMLResponse)
def conversation(username: str, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other:
        return RedirectResponse("/messages", status_code=302)
    msgs = db.query(models.Message).filter(
        ((models.Message.sender_id == user.id) & (models.Message.receiver_id == other.id)) |
        ((models.Message.sender_id == other.id) & (models.Message.receiver_id == user.id))
    ).order_by(models.Message.created_at).all()
    for msg in msgs:
        if msg.receiver_id == user.id and not msg.is_read:
            msg.is_read = True
    db.commit()
    unread = db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.is_read == False
    ).count()
    return templates.TemplateResponse(request, "conversation.html", {
        "user": user,
        "other": other,
        "messages": msgs,
        "unread": unread
    })

@app.post("/messages/{username}")
def send_message(username: str, request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    other = db.query(models.User).filter(models.User.username == username).first()
    if not other:
        return RedirectResponse("/messages", status_code=302)
    msg = models.Message(sender_id=user.id, receiver_id=other.id, content=content)
    db.add(msg)
    db.commit()
    return RedirectResponse(f"/messages/{username}", status_code=302)

@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    results = []
    if q:
        results = db.query(models.User).filter(
            models.User.username.ilike(f"%{q}%") |
            models.User.name.ilike(f"%{q}%")
        ).limit(20).all()
    unread = 0
    if user:
        unread = db.query(models.Notification).filter(
            models.Notification.user_id == user.id,
            models.Notification.is_read == False
        ).count()
    return templates.TemplateResponse(request, "search.html", {
        "user": user,
        "results": results,
        "q": q,
        "unread": unread
    })

@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    notifs = db.query(models.Notification).filter(
        models.Notification.user_id == user.id
    ).order_by(models.Notification.created_at.desc()).limit(50).all()
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
    unread = db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.is_read == False
    ).count()
    return templates.TemplateResponse(request, "settings.html", {"user": user, "unread": unread})

@app.post("/settings")
def settings_save(request: Request, name: str = Form(...), bio: str = Form(""), username: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    error = validate_username(username)
    if error:
        return templates.TemplateResponse(request, "settings.html", {"user": user, "error": error})
    existing = db.query(models.User).filter(models.User.username == username, models.User.id != user.id).first()
    if existing:
        return templates.TemplateResponse(request, "settings.html", {"user": user, "error": f"Никнейм @{username} уже занят"})
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

@app.post("/whale/{post_id}")
def whale_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    existing = db.query(models.Whale).filter(models.Whale.user_id == user.id, models.Whale.post_id == post_id).first()
    if existing:
        db.delete(existing)
    else:
        whale = models.Whale(user_id=user.id, post_id=post_id)
        db.add(whale)
    db.commit()
    return RedirectResponse("/", status_code=302)