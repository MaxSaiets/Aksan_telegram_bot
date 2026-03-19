from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # в”Ђв”Ђ Telegram в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    # РћС‚СЂРёРјР°С‚Рё С‚РѕРєРµРЅ Сѓ @BotFather
    TELEGRAM_BOT_TOKEN: str = Field(default="123456789:MOCK_TELEGRAM_BOT_TOKEN_XXXXXXXXXXX")

    # ID РіСЂСѓРїРё/РєР°РЅР°Р»Сѓ, РєСѓРґРё РЅР°РґСЃРёР»Р°С‚Рё РѕР±СЂРѕР±Р»РµРЅС– РІС–РґРµРѕ (РЅР°РїСЂРёРєР»Р°Рґ -1001234567890)
    TELEGRAM_TARGET_CHAT_ID: str = Field(default="-1001234567890")

    # РџСѓР±Р»С–С‡РЅР° URL РІР°С€РѕРіРѕ СЃРµСЂРІРµСЂР° (Р±РµР· trailing slash), РґРµ Р±СѓРґРµ Р·Р°СЂРµС”СЃС‚СЂРѕРІР°РЅРѕ РІРµР±С…СѓРє
    TELEGRAM_WEBHOOK_URL: str = Field(default="https://example.com")

    # РЎРµРєСЂРµС‚РЅРёР№ СЂСЏРґРѕРє РґР»СЏ РІРµСЂРёС„С–РєР°С†С–С— Р·Р°РїРёС‚С–РІ РІС–Рґ Telegram (Р±СѓРґСЊ-СЏРєРёР№ UUID/СЂСЏРґРѕРє)
    TELEGRAM_WEBHOOK_SECRET: str = Field(default="MOCK_WEBHOOK_SECRET_TOKEN_32CHARS")

    # Comma-separated Telegram user ID (С†С–Р»С– С‡РёСЃР»Р°) С‚РёС…, С…С‚Рѕ РјРѕР¶Рµ РІРёРєРѕСЂРёСЃС‚РѕРІСѓРІР°С‚Рё Р±РѕС‚Р°.
    # Р—Р°Р»РёС€ РїРѕСЂРѕР¶РЅС–Рј вЂ” РґРѕСЃС‚СѓРї РґР»СЏ РІСЃС–С….
    # РџСЂРёРєР»Р°Рґ: TELEGRAM_ALLOWED_USERS=123456789,987654321
    TELEGRAM_ALLOWED_USERS: str = Field(default="")
    DEPLOY_NOTIFY_CHAT_ID: str = Field(default="")

    # в”Ђв”Ђ Telegram MTProto (РґР»СЏ Р·Р°РІР°РЅС‚Р°Р¶РµРЅРЅСЏ С„Р°Р№Р»С–РІ > 20 РњР‘) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    # РћС‚СЂРёРјР°С‚Рё РЅР° https://my.telegram.org в†’ API development tools
    TELEGRAM_API_ID: int = Field(default=0)
    TELEGRAM_API_HASH: str = Field(default="")

    # в”Ђв”Ђ YouTube в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    YOUTUBE_CHANNEL_ID: str = Field(default="MOCK_CHANNEL_ID")
    YOUTUBE_CLIENT_SECRETS_FILE: str = Field(default="client_secrets.json")

    # в”Ђв”Ђ Supabase в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    SUPABASE_URL: str = Field(default="https://mock.supabase.co")
    SUPABASE_SERVICE_KEY: str = Field(default="MOCK_SUPABASE_KEY")

    # в”Ђв”Ђ Redis / Celery в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # в”Ђв”Ђ SalesDrive CRM в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    # РџСѓР±Р»С–С‡РЅРёР№ YML-РµРєСЃРїРѕСЂС‚ (SalesDrive в†’ Р†РЅС‚РµРіСЂР°С†С–С— в†’ YML в†’ РїСѓР±Р»С–С‡РЅРµ РїРѕСЃРёР»Р°РЅРЅСЏ)
    SALESDRIVE_YML_URL: str = Field(default="")

    # в”Ђв”Ђ Rozetka в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    # API-РєР»СЋС‡ РїСЂРѕРґР°РІС†СЏ (Rozetka Seller в†’ РќР°Р»Р°С€С‚СѓРІР°РЅРЅСЏ в†’ API в†’ Р—РіРµРЅРµСЂСѓРІР°С‚Рё РєР»СЋС‡)
    ROZETKA_API_KEY: str = Field(default="MOCK_ROZETKA_KEY")

    # в”Ђв”Ђ Supabase Storage в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    # РЎС‚РІРѕСЂРёС‚Рё РІ Supabase Dashboard в†’ Storage в†’ New bucket в†’ Public: ON
    SUPABASE_STORAGE_BUCKET: str = Field(default="processed-videos")

    # в”Ђв”Ђ App в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    # true  в†’ РІСЃС– Р·РѕРІРЅС–С€РЅС– СЃРµСЂРІС–СЃРё С–РјС–С‚СѓСЋС‚СЊСЃСЏ (РґР»СЏ СЂРѕР·СЂРѕР±РєРё/С‚РµСЃС‚СѓРІР°РЅРЅСЏ)
    # false в†’ СЂРµР°Р»СЊРЅС– API РІРёРєР»РёРєРё
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


