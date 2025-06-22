from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import requests
import re

# -- Ganti dengan API KEY Gemini-mu
GEMINI_API_KEY = "ISI_API_KEY_GEMINI_MU"
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-pro:generateContent?key={GEMINI_API_KEY}"

# -- SQLite biar mudah deploy & GRATIS
DB_URL = "sqlite:///./db.sqlite3"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    password = Column(String(100))

class ChatHistory(Base):
    __tablename__ = 'chat_history'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    message = Column(Text)
    reply = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship('User')

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserIn(BaseModel):
    username: str
    password: str

class ChatIn(BaseModel):
    username: str
    message: str

@app.post("/register")
def register(user: UserIn):
    db = SessionLocal()
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        db.close()
        raise HTTPException(400, "User already exists")
    db.add(User(username=user.username, password=user.password))
    db.commit()
    db.close()
    return {"message": "Register success"}

@app.post("/login")
def login(user: UserIn):
    db = SessionLocal()
    user_db = db.query(User).filter(User.username == user.username, User.password == user.password).first()
    db.close()
    if not user_db:
        raise HTTPException(401, "Invalid login")
    return {"message": "Login success"}

@app.post("/chat")
def chat(chat: ChatIn):
    db = SessionLocal()
    user_db = db.query(User).filter(User.username == chat.username).first()
    if not user_db:
        db.close()
        raise HTTPException(401, "User not found")
    msg = chat.message
    try:
        payload = {
            "contents": [
                {"parts": [{"text": msg}]}
            ]
        }
        r = requests.post(GEMINI_ENDPOINT, json=payload)
        out = r.json()
        if "candidates" in out and out["candidates"]:
            reply = out["candidates"][0]["content"]["parts"][0]["text"]
        elif "error" in out:
            reply = f"Error Gemini: {out['error'].get('message', out['error'])}"
        else:
            reply = f"Error Gemini: unknown response {out}"
    except Exception as e:
        reply = f"Gagal panggil Gemini: {e}"

    # Bersihkan markdown aneh dari Gemini
    reply = re.sub(r'^> ?', '', reply, flags=re.MULTILINE)
    reply = reply.replace('**', '')

    chat_hist = ChatHistory(user_id=user_db.id, message=msg, reply=reply)
    db.add(chat_hist)
    db.commit()
    db.close()
    return {"reply": reply}

@app.get("/history/{username}")
def history(username: str):
    db = SessionLocal()
    user_db = db.query(User).filter(User.username == username).first()
    if not user_db:
        db.close()
        raise HTTPException(401, "User not found")
    chats = db.query(ChatHistory).filter(ChatHistory.user_id == user_db.id).order_by(ChatHistory.created_at).all()
    result = [{"question": c.message, "answer": c.reply, "at": str(c.created_at)} for c in chats]
    db.close()
    return result
