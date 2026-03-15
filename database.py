from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///bot.db')
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if 'sqlite' in DATABASE_URL else {})
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    chats_count = Column(Integer, default=0)
    codes_count = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)

class Chat(Base):
    __tablename__ = 'chats'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    telegram_id = Column(Integer)
    message = Column(Text)
    response = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    type = Column(String(20), default='text')

class Code(Base):
    __tablename__ = 'codes'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    telegram_id = Column(Integer)
    language = Column(String(50))
    description = Column(Text)
    code = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Setting(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)

def init_db():
    Base.metadata.create_all(engine)
    session = Session()
    defaults = [
        ('welcome_message', 'مرحباً بك في بوت المبرمج الذكي 🤖\nأنا هنا لمساعدتك في البرمجة والمحادثة!'),
        ('bot_active', 'true'),
        ('bot_name', 'بوت المبرمج الذكي'),
        ('admin_password', 'admin123'),
    ]
    for key, value in defaults:
        if not session.query(Setting).filter_by(key=key).first():
            session.add(Setting(key=key, value=value))
    session.commit()
    session.close()
