from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="")
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    avatar = Column(String, default="")
    bio = Column(String, default="")
    is_verified = Column(Boolean, default=False)
    is_owner = Column(Boolean, default=False)
    is_starred = Column(Boolean, default=False)
    is_verified_badge = Column(Boolean, default=False)
    is_moderator = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    blocked_until = Column(DateTime, nullable=True)
    is_plus = Column(Boolean, default=False)
    plus_until = Column(DateTime, nullable=True)
    plus_color = Column(String, default="#a855f7")
    created_at = Column(DateTime, default=datetime.utcnow)
    posts = relationship("Post", back_populates="author")
    followers = relationship("Follow", foreign_keys="Follow.following_id", back_populates="following")
    following = relationship("Follow", foreign_keys="Follow.follower_id", back_populates="follower")
    notifications = relationship("Notification", foreign_keys="Notification.user_id", back_populates="user")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    image = Column(String, default="")
    media_type = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="posts")
    likes = relationship("Like", back_populates="post")
    comments = relationship("Comment", back_populates="post")
    whales = relationship("Whale", back_populates="post")
    reactions = relationship("Reaction", back_populates="post")

class Follow(Base):
    __tablename__ = "follows"
    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("users.id"))
    following_id = Column(Integer, ForeignKey("users.id"))
    follower = relationship("User", foreign_keys=[follower_id], back_populates="following")
    following = relationship("User", foreign_keys=[following_id], back_populates="followers")

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    post = relationship("Post", back_populates="likes")

class Whale(Base):
    __tablename__ = "whales"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    post = relationship("Post", back_populates="whales")

class Reaction(Base):
    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    emoji = Column(String, default="")
    post = relationship("Post", back_populates="reactions")

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    author = relationship("User")
    post = relationship("Post", back_populates="comments")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text, default="")
    image = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    type = Column(String)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    text = Column(String, default="")
    reply_email = Column(String, default="")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", foreign_keys=[user_id], back_populates="notifications")
    from_user = relationship("User", foreign_keys=[from_user_id])
    post = relationship("Post")

class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    code = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Promocode(Base):
    __tablename__ = "promocodes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    days = Column(Integer, default=30)
    max_uses = Column(Integer, default=1)
    uses = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)