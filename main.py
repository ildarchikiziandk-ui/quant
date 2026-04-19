from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import engine, get_db, Base
import models
import auth
import re

Base.metadata.create_all(bind=engine)

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
def home(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    posts = db.query(models.Post).order_by(models.Post.created_at.desc()).all()
    return templates.TemplateResponse(request, "home.html", {"user": user, "posts": posts})

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
        return templates.TemplateResponse(request, "register.html", {"error": f"Никнейм @{username} уже занят, попробуй другой"})
    if db.query(models.User).filter(models.User.email == email).first():
        return templates.TemplateResponse(request, "register.html", {"error": "Этот email уже зарегистрирован"})
    user = models.User(name=name, username=username, email=email, password=auth.hash_password(password))
    db.add(user)
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
    return templates.TemplateResponse(request, "profile.html", {
        "user": current_user,
        "profile_user": profile_user,
        "posts": posts,
        "is_following": is_following
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
        follow = models.Follow(follower_id=current_user.id, following_id=target.id)
        db.add(follow)
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
    return templates.TemplateResponse(request, "messages.html", {
        "user": user,
        "conversations": conversations
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
    return templates.TemplateResponse(request, "conversation.html", {
        "user": user,
        "other": other,
        "messages": msgs
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

@app.post("/comment/{post_id}")
def add_comment(post_id: int, request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    comment = models.Comment(content=content, user_id=user.id, post_id=post_id)
    db.add(comment)
    db.commit()
    return RedirectResponse("/", status_code=302)