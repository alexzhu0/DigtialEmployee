from pydantic_settings import BaseSettings
from typing import Optional, Dict, List
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # API Keys
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    XUNFEI_APPID: str = os.getenv("XUNFEI_APPID", "")
    XUNFEI_APIKEY: str = os.getenv("XUNFEI_APIKEY", "")
    XUNFEI_APISECRET: str = os.getenv("XUNFEI_APISECRET", "")
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    SSL_CERT_PATH: str = "ssl/cert.pem"
    SSL_KEY_PATH: str = "ssl/key.pem"
    
    # 数据库配置
    DATABASE_URL: str = "sqlite:///./ai_toy.db"
    
    # 语音配置
    TTS_VOICE: str = "zh-CN-YunxiNeural"  # 使用更专业的男声
    TTS_RATE: str = "+0%"
    TTS_VOLUME: str = "+0%"
    
    # AI配置
    MAX_HISTORY_LENGTH: int = 10
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 1000
    
    # 安全配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # 数字员工配置
    EMPLOYEE_NAME: str = "元芳"
    EMPLOYEE_ID: str = "DE001"
    WORK_HOURS: Dict[str, str] = {
        "start": "09:00",
        "end": "18:00"
    }
    BREAK_HOURS: List[Dict[str, str]] = [
        {"start": "12:00", "end": "13:00"}
    ]
    MAX_CONCURRENT_TASKS: int = 5
    RESPONSE_TIMEOUT: int = 30  # 秒
    SKILL_SETS: List[str] = [
        "工作协调",
        "日程管理",
        "文档处理",
        "数据分析",
        "会议安排",
        "任务跟踪"
    ]

settings = Settings() 