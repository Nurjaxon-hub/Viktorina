import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    ForeignKey,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session


# ==================================================
# 1. BAZA BILAN BOG'LANISH
# ==================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL sozlamasi topilmadi")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql://", 1
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


# ==================================================
# 2. FOYDALANUVCHILAR JADVALI
# ==================================================

class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True)
    first_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    xp = Column(Integer, default=0)
    best_score = Column(Integer, default=0)
    language = Column(String(2), default="uz")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ==================================================
# 3. O'YINLAR JADVALI
# ==================================================

class Game(Base):
    __tablename__ = "games"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id = Column(
        BigInteger,
        ForeignKey("users.telegram_id"),
        nullable=False,
    )
    mode = Column(String, default="classic")
    category = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)
    language = Column(String(2), default="uz")
    question_count = Column(Integer, default=10)
    answered = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    score = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


# ==================================================
# 4. SAVOLLAR JADVALI
# ==================================================

class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    option_a = Column(Text, nullable=False)
    option_b = Column(Text, nullable=False)
    option_c = Column(Text, nullable=False)
    option_d = Column(Text, nullable=False)
    correct_answer = Column(String(1), nullable=False)
    difficulty = Column(String, default="easy")
    category = Column(String, default="Umumiy bilim")
    language = Column(String(2), default="uz")
    created_at = Column(DateTime, default=datetime.utcnow)


# ==================================================
# 5. ESKI BAZANI YANGILASH
# ==================================================

Base.metadata.create_all(bind=engine)

with engine.begin() as connection:
    connection.execute(text("""
        ALTER TABLE questions
        ADD COLUMN IF NOT EXISTS language VARCHAR(2)
        DEFAULT 'uz'
    """))

    connection.execute(text("""
        UPDATE questions
        SET language = 'uz'
        WHERE language IS NULL OR language = ''
    """))

    connection.execute(text("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS language VARCHAR(2)
        DEFAULT 'uz'
    """))

    connection.execute(text("""
        ALTER TABLE games
        ADD COLUMN IF NOT EXISTS language VARCHAR(2)
        DEFAULT 'uz'
    """))


# ==================================================
# 6. FASTAPI
# ==================================================

app = FastAPI(
    title="Viktorina API",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SUPPORTED_LANGUAGES = {"uz", "ru", "en"}


def check_language(language: str) -> str:
    language = language.lower().strip()

    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Til uz, ru yoki en bo'lishi kerak",
        )

    return language


# ==================================================
# 7. SO'ROV MODELLARI
# ==================================================

class UserRequest(BaseModel):
    telegram_id: int
    first_name: Optional[str] = None
    username: Optional[str] = None
    language: str = "uz"


class GameStartRequest(BaseModel):
    telegram_id: int
    mode: str = "classic"
    category: Optional[str] = None
    difficulty: Optional[str] = None
    question_count: int = 10
    language: str = "uz"


class GameFinishRequest(BaseModel):
    game_id: int
    answered: int = 0
    correct: int = 0
    score: int = 0


# ==================================================
# 8. ASOSIY MANZILLAR
# ==================================================

@app.get("/")
def home():
    return {
        "ok": True,
        "name": "Viktorina API",
        "version": "1.2.0",
    }


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {
            "ok": True,
            "database": True,
        }
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Baza bilan bog'lanishda xatolik",
        )


@app.get("/api/languages")
def get_languages():
    return [
        {"code": "uz", "name": "O'zbekcha"},
        {"code": "ru", "name": "Русский"},
        {"code": "en", "name": "English"},
    ]


# ==================================================
# 9. FOYDALANUVCHINI YARATISH / YANGILASH
# ==================================================

@app.post("/api/user")
def create_or_update_user(
    data: UserRequest,
    db: Session = Depends(get_db),
):
    language = check_language(data.language)

    user = db.query(User).filter(
        User.telegram_id == data.telegram_id
    ).first()

    if user is None:
        user = User(
            telegram_id=data.telegram_id,
            first_name=data.first_name,
            username=data.username,
            language=language,
        )
        db.add(user)
    else:
        user.first_name = data.first_name
        user.username = data.username
        user.language = language
        user.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(user)

    return {
        "ok": True,
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "username": user.username,
        "xp": user.xp,
        "best_score": user.best_score,
        "language": user.language,
    }


# ==================================================
# 10. SAVOLLARNI OLISH
# ==================================================

@app.get("/api/questions")
def get_questions(
    count: int = Query(default=10, ge=1, le=100),
    language: str = "uz",
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    language = check_language(language)

    query = db.query(Question).filter(
        Question.language == language
    )

    if category:
        query = query.filter(Question.category == category)

    if difficulty:
        query = query.filter(
            Question.difficulty == difficulty
        )

    questions = query.order_by(
        Question.id
    ).limit(count).all()

    return [
        {
            "id": q.id,
            "question": q.question,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_answer": q.correct_answer,
            "difficulty": q.difficulty,
            "category": q.category,
            "language": q.language,
        }
        for q in questions
    ]


# ==================================================
# 11. KATEGORIYALAR
# ==================================================

@app.get("/api/questions/categories")
def get_categories(
    language: str = "uz",
    db: Session = Depends(get_db),
):
    language = check_language(language)

    categories = (
        db.query(Question.category)
        .filter(Question.language == language)
        .distinct()
        .order_by(Question.category)
        .all()
    )

    return [row[0] for row in categories if row[0]]


# ==================================================
# 12. QIYINLIK DARAJALARI
# ==================================================

@app.get("/api/questions/difficulties")
def get_difficulties(
    language: str = "uz",
    db: Session = Depends(get_db),
):
    language = check_language(language)

    difficulties = (
        db.query(Question.difficulty)
        .filter(Question.language == language)
        .distinct()
        .order_by(Question.difficulty)
        .all()
    )

    return [row[0] for row in difficulties if row[0]]


# ==================================================
# 13. O'YINNI BOSHLASH
# ==================================================

@app.post("/api/game/start")
def start_game(
    data: GameStartRequest,
    db: Session = Depends(get_db),
):
    language = check_language(data.language)

    user = db.query(User).filter(
        User.telegram_id == data.telegram_id
    ).first()

    if user is None:
        user = User(
            telegram_id=data.telegram_id,
            language=language,
        )
        db.add(user)
        db.flush()
    else:
        user.language = language

    game = Game(
        telegram_id=data.telegram_id,
        mode=data.mode,
        category=data.category,
        difficulty=data.difficulty,
        language=language,
        question_count=max(1, min(data.question_count, 100)),
    )

    db.add(game)
    db.commit()
    db.refresh(game)

    return {
        "ok": True,
        "game_id": game.id,
        "language": game.language,
        "mode": game.mode,
    }


# ==================================================
# 14. O'YINNI YAKUNLASH
# ==================================================

@app.post("/api/game/finish")
def finish_game(
    data: GameFinishRequest,
    db: Session = Depends(get_db),
):
    game = db.query(Game).filter(
        Game.id == data.game_id
    ).first()

    if game is None:
        raise HTTPException(
            status_code=404,
            detail="O'yin topilmadi",
        )

    if game.finished_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Bu o'yin avval yakunlangan",
        )

    game.answered = max(0, data.answered)
    game.correct = max(0, data.correct)
    game.score = max(0, data.score)
    game.finished_at = datetime.utcnow()

    user = db.query(User).filter(
        User.telegram_id == game.telegram_id
    ).first()

    if user:
        user.xp = (user.xp or 0) + game.score
        user.best_score = max(
            user.best_score or 0,
            game.score,
        )
        user.updated_at = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "game_id": game.id,
        "score": game.score,
        "correct": game.correct,
        "answered": game.answered,
    }


# ==================================================
# 15. REYTING
# ==================================================

@app.get("/api/leaderboard")
def leaderboard(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    users = (
        db.query(User)
        .order_by(
            User.xp.desc(),
            User.best_score.desc(),
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "username": user.username,
            "xp": user.xp,
            "best_score": user.best_score,
        }
        for user in users
    ]


# ==================================================
# 16. FOYDALANUVCHI STATISTIKASI
# ==================================================

@app.get("/api/user/{telegram_id}")
def get_user_stats(
    telegram_id: int,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.telegram_id == telegram_id
    ).first()

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Foydalanuvchi topilmadi",
        )

    games = db.query(Game).filter(
        Game.telegram_id == telegram_id,
        Game.finished_at.isnot(None),
    ).all()

    return {
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "username": user.username,
        "xp": user.xp,
        "best_score": user.best_score,
        "language": user.language,
        "games_played": len(games),
        "total_correct": sum(g.correct or 0 for g in games),
        "total_score": sum(g.score or 0 for g in games),
    }
