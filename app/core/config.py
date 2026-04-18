"""
Core configuration module for the Taxi Backend System.
Handles all environment variables and application settings.
"""
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

_DEFAULT_SECRET_KEY = "dev_secret_key_987654321"
_DEFAULT_ADMIN_PASSWORD = "changeme"
_DEFAULT_ADMIN_LOGIN_TOKEN = "default_token_123"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        case_sensitive=True,
    )

    # Application
    APP_NAME: str = "TaxiBackend"
    PROJECT_NAME: str = "Timgo Taxi"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://taxi_user:taxi_password@db:5432/taxi_db"
    )
    DB_ECHO: bool = False
    
     # Payme Integration
    PAYME_MERCHANT_ID: str = ""
    PAYME_SECRET_KEY: str = ""
    PAYME_API_URL: str = "https://checkout.paycom.uz/api"
    PAYME_TIMEOUT: int = 30
    
    # Redis
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_WEBHOOK_URL: Optional[str] = None
    
    # Admin IDs - Telegram ID raqamlari (env: "878590210,8219777626" yoki "[878590210, 8219777626]")
    ADMIN_IDS: List[int] = [878590210, 8219777626]

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            return _DEFAULT_SECRET_KEY
        return s

    @field_validator("ADMIN_PASSWORD")
    @classmethod
    def validate_admin_password(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            return _DEFAULT_ADMIN_PASSWORD
        return s

    @field_validator("ADMIN_LOGIN_TOKEN")
    @classmethod
    def validate_admin_login_token(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            return _DEFAULT_ADMIN_LOGIN_TOKEN
        return s

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            s = v.strip().strip("[]")
            if not s:
                return []
            return [int(x.strip()) for x in s.split(",") if x.strip()]
        return v
    # Admin ham haydovchi bo'lsa buyurtma oladi (tekshirish uchun True, ishlab chiqarishda False)
    ADMIN_CAN_RECEIVE_ORDERS: bool = True
    ADMIN_PASSWORD: str = Field(
        default=_DEFAULT_ADMIN_PASSWORD,
        description="Admin panel login password; must be set in environment (non-empty).",
    )
    ADMIN_LOGIN_TOKEN: str = Field(
        default=_DEFAULT_ADMIN_LOGIN_TOKEN,
        description="Second admin login secret (token); must be set in environment (non-empty).",
    )

    # Security
    SECRET_KEY: str = Field(
        default=_DEFAULT_SECRET_KEY,
        description="JWT signing key; must be a strong secret, not the placeholder value.",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Business Logic (narxlarni faqat DB settings id=1 dan oling)
    FIXED_COMMISSION: float = 0.0   # Fiksirlangan komissiya (0 bo'lsa foiz ishlatiladi)
    MIN_BALANCE: float = 5000.0   # Haydovchi uchun minimal balans (so'm)
    ORDER_TIMEOUT_SECONDS: int = 300   # 5 minutes to find a driver
    SEARCH_RADIUS_KM: float = 10.0   # Search radius for driver matching
    RELAX_VERIFIED_FOR_MATCHING: bool = True   # Include unverified drivers in matching (False = verified only)
    LOCATION_FRESHNESS_SECONDS: int = 600
    # Test / dev: yumshoq matching (ishlab chiqarishda .env orqali MATCHING_TEST_MODE=false)
    MATCHING_TEST_MODE: bool = True
    MATCHING_LOCATION_AGE_SECONDS: int = 36000  # test rejimida yosh filtri qoldirilsa — 10 soat

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # WebApp / Ngrok (Telegram bot uchun)
    WEBAPP_BASE_URL: str = Field(default="https://candid-semiexposed-dung.ngrok-free.dev")
    WORKERS: int = 4


# Global settings instance
settings = Settings()