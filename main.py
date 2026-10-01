import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import (
    create_engine,
    Column,
    BigInteger,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL o'zgaruvchisi topilmadi")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)

Base = declarative_base()


# =========================
# DATABASE MODELS
# =========================

class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True)
    first_name = Column(String(255), nullable=False, default="Mehmon")
    username = Column(String(255), nullable=True)

    xp = Column(Integer, nullable=False, default=0)
    best_score = Column(Integer, nullable=False, default=0)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )


class Game(Base):
    __tablename__ = "games"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    telegram_id = Column(
        BigInteger,
        ForeignKey("users.telegram_id"),
        nullable=False
    )

    mode = Column(String(50), nullable=False)
    category = Column(String(100), nullable=True)
    difficulty = Column(String(50), nullable=True)

    question_count = Column(Integer, nullable=False, default=0)
    answered = Column(Integer, nullable=False, default=0)
    correct = Column(Integer, nullable=False, default=0)

    score = Column(Integer, nullable=False, default=0)

    started_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    finished_at = Column(DateTime, nullable=True)


Base.metadata.create_all(bind=engine)


# =========================
# FASTAPI
# =========================

app = FastAPI(
    title="Viktorina API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# MODELS
# =========================

class UserRequest(BaseModel):
    telegram_id: int
    first_name: str = "Mehmon"
    username: Optional[str] = None


class GameStartRequest(BaseModel):
    telegram_id: int
    mode: str
    category: Optional[str] = None
    difficulty: Optional[str] = None
    question_count: int = 0


class GameFinishRequest(BaseModel):
    telegram_id: int
    game_id: int

    score: int = 0
    correct: int = 0
    answered: int = 0

    xp: int = 0


# =========================
# HEALTH
# =========================

@app.get("/")
def root():
    return {
        "ok": True,
        "name": "Viktorina API",
        "version": "1.0.0"
    }


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "database": True
    }


# =========================
# USER
# =========================

@app.post("/api/user")
def create_or_update_user(data: UserRequest):

    db = SessionLocal()

    try:
        user = db.query(User).filter(
            User.telegram_id == data.telegram_id
        ).first()

        now = datetime.now(timezone.utc)

        if user is None:
            user = User(
                telegram_id=data.telegram_id,
                first_name=data.first_name or "Mehmon",
                username=data.username,
                xp=0,
                best_score=0,
                created_at=now,
                updated_at=now
            )

            db.add(user)

        else:
            user.first_name = data.first_name or user.first_name
            user.username = data.username
            user.updated_at = now

        db.commit()
        db.refresh(user)

        return {
            "ok": True,
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "username": user.username,
            "xp": user.xp,
            "best_score": user.best_score
        }

    finally:
        db.close()


# =========================
# GAME START
# =========================

@app.post("/api/game/start")
def start_game(data: GameStartRequest):

    db = SessionLocal()

    try:
        user = db.query(User).filter(
            User.telegram_id == data.telegram_id
        ).first()

        if user is None:
            user = User(
                telegram_id=data.telegram_id,
                first_name="Mehmon",
                xp=0,
                best_score=0
            )

            db.add(user)
            db.commit()

        game = Game(
            telegram_id=data.telegram_id,
            mode=data.mode,
            category=data.category,
            difficulty=data.difficulty,
            question_count=max(0, data.question_count),
            answered=0,
            correct=0,
            score=0,
            started_at=datetime.now(timezone.utc)
        )

        db.add(game)
        db.commit()
        db.refresh(game)

        return {
            "ok": True,
            "game_id": game.id
        }

    finally:
        db.close()


# =========================
# GAME FINISH
# =========================

@app.post("/api/game/finish")
def finish_game(data: GameFinishRequest):

    db = SessionLocal()

    try:
        game = db.query(Game).filter(
            Game.id == data.game_id
        ).first()

        if game is None:
            raise HTTPException(
                status_code=404,
                detail="O'yin topilmadi"
            )

        if game.telegram_id != data.telegram_id:
            raise HTTPException(
                status_code=403,
                detail="Bu o'yin boshqa foydalanuvchiga tegishli"
            )

        game.score = max(0, data.score)
        game.correct = max(0, data.correct)
        game.answered = max(0, data.answered)

        game.finished_at = datetime.now(timezone.utc)

        user = db.query(User).filter(
            User.telegram_id == data.telegram_id
        ).first()

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="Foydalanuvchi topilmadi"
            )

        user.xp += max(0, data.xp)

        if game.score > user.best_score:
            user.best_score = game.score

        user.updated_at = datetime.now(timezone.utc)

        db.commit()

        return {
            "ok": True,
            "game_id": game.id,
            "score": game.score,
            "correct": game.correct,
            "answered": game.answered,
            "xp": user.xp,
            "best_score": user.best_score
        }

    finally:
        db.close()


# =========================
# LEADERBOARD
# =========================

@app.get("/api/leaderboard")
def leaderboard(limit: int = 20):

    limit = max(1, min(limit, 100))

    db = SessionLocal()

    try:
        users = (
            db.query(User)
            .filter(User.best_score > 0)
            .order_by(User.best_score.desc())
            .limit(limit)
            .all()
        )

        result = []

        for position, user in enumerate(users, start=1):
            result.append({
                "position": position,
                "telegram_id": user.telegram_id,
                "first_name": user.first_name,
                "username": user.username,
                "score": user.best_score,
                "xp": user.xp
            })

        return {
            "ok": True,
            "items": result
        }

    finally:
        db.close()


# =========================
# USER STATISTICS
# =========================

@app.get("/api/user/{telegram_id}")
def get_user(telegram_id: int):

    db = SessionLocal()

    try:
        user = db.query(User).filter(
            User.telegram_id == telegram_id
        ).first()

        if user is None:
            return {
                "ok": False,
                "message": "Foydalanuvchi topilmadi"
            }

        games_count = db.query(Game).filter(
            Game.telegram_id == telegram_id,
            Game.finished_at.isnot(None)
        ).count()

        return {
            "ok": True,
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "username": user.username,
            "xp": user.xp,
            "best_score": user.best_score,
            "games": games_count
        }

    finally:
        db.close()
