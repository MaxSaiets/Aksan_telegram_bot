from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # ── Telegram ──────────────────────────────────────────────────────────────
    # Отримати токен у @BotFather
    TELEGRAM_BOT_TOKEN: str = Field(default="123456789:MOCK_TELEGRAM_BOT_TOKEN_XXXXXXXXXXX")

    # ID групи/каналу, куди надсилати оброблені відео (наприклад -1001234567890)
    TELEGRAM_TARGET_CHAT_ID: str = Field(default="-1001234567890")

    # Публічна URL вашого сервера (без trailing slash), де буде зареєстровано вебхук
    TELEGRAM_WEBHOOK_URL: str = Field(default="https://example.com")

    # Секретний рядок для верифікації запитів від Telegram (будь-який UUID/рядок)
    TELEGRAM_WEBHOOK_SECRET: str = Field(default="MOCK_WEBHOOK_SECRET_TOKEN_32CHARS")

    # Comma-separated Telegram user ID (цілі числа) тих, хто може використовувати бота.
    # Залиш порожнім — доступ для всіх.
    # Приклад: TELEGRAM_ALLOWED_USERS=123456789,987654321
    TELEGRAM_ALLOWED_USERS: str = Field(default="")

    # ── Telegram MTProto (для завантаження файлів > 20 МБ) ─────────────────
    # Отримати на https://my.telegram.org → API development tools
    TELEGRAM_API_ID: int = Field(default=0)
    TELEGRAM_API_HASH: str = Field(default="")

    # ── YouTube ───────────────────────────────────────────────────────────────
    YOUTUBE_CHANNEL_ID: str = Field(default="MOCK_CHANNEL_ID")
    YOUTUBE_CLIENT_SECRETS_FILE: str = Field(default="client_secrets.json")

    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL: str = Field(default="https://mock.supabase.co")
    SUPABASE_SERVICE_KEY: str = Field(default="MOCK_SUPABASE_KEY")

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # ── SalesDrive CRM ────────────────────────────────────────────────────────
    # Публічний YML-експорт (SalesDrive → Інтеграції → YML → публічне посилання)
    SALESDRIVE_YML_URL: str = Field(default="")

    # ── Rozetka ───────────────────────────────────────────────────────────────
    # API-ключ продавця (Rozetka Seller → Налаштування → API → Згенерувати ключ)
    ROZETKA_API_KEY: str = Field(default="MOCK_ROZETKA_KEY")

    # ── Supabase Storage ──────────────────────────────────────────────────────
    # Створити в Supabase Dashboard → Storage → New bucket → Public: ON
    SUPABASE_STORAGE_BUCKET: str = Field(default="processed-videos")

    # ── App ───────────────────────────────────────────────────────────────────
    # true  → всі зовнішні сервіси імітуються (для розробки/тестування)
    # false → реальні API виклики
    USE_MOCKS: bool = Field(default=True)
    TEMP_VIDEO_DIR: str = Field(default="tmp/videos")
    LOG_LEVEL: str = Field(default="INFO")

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def temp_dir(self) -> Path:
        p = Path(self.TEMP_VIDEO_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def allowed_users(self) -> set[int]:
        """
        Set of Telegram user IDs (integers) permitted to use the bot.
        Empty set = no whitelist (everyone allowed).
        """
        if not self.TELEGRAM_ALLOWED_USERS.strip():
            return set()
        return {
            int(uid.strip())
            for uid in self.TELEGRAM_ALLOWED_USERS.split(",")
            if uid.strip().lstrip("-").isdigit()
        }


settings = Settings()
