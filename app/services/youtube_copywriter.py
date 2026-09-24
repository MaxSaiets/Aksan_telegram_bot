"""Generate human YouTube descriptions while keeping product claims grounded."""
from __future__ import annotations

import hashlib
import logging
import re
import time

import httpx

from config import settings


logger = logging.getLogger(__name__)
_SKU_PATTERN = re.compile(r"\b\d{2}\.\d{3,5}\b")
_BANNED_PHRASES = (
    "для комфортних і стильних образів",
    "у відео показані фактура тканини, посадка та деталі виробу",
    "якісне пошиття",
    "збереже свій",
    "після багатьох прань",
    "приємно прилягає до тіла",
    "максимальну свободу",
)
_LEADS = (
    "Добірка для тих, хто любить продумані речі без зайвого.",
    "Річ, яка легко стає основою повсякденного гардероба.",
    "Універсальний варіант для днів, коли хочеться виглядати зібрано.",
    "Лаконічний одяг, який залишає простір для власного стилю.",
    "Практична знахідка для щоденних образів і неспішних планів.",
    "Виріб для гардероба, де кожна річ працює в різних поєднаннях.",
    "Свіжа ідея для образів на робочий день, прогулянку чи зустріч.",
    "Вдалий акцент для тих, хто цінує зручність і акуратний силует.",
)
_DETAILS = (
    "Перегляньте ролик, щоб роздивитися крій, фактуру та настрій образу ближче.",
    "У відео можна оцінити, як річ виглядає в русі та з чим її легко поєднати.",
    "Дивіться огляд, щоб побачити деталі та уявити її у власних поєднаннях.",
    "Короткий огляд допоможе розгледіти силует і знайти нову ідею для стилізації.",
    "Зверніть увагу на деталі: саме вони роблять образ цілісним і доречним.",
    "Подивіться відео до кінця, щоб відчути характер речі та варіанти її стилізації.",
    "У кадрі добре видно посадку й деталі, важливі для щоденного вибору.",
    "Огляд без зайвих слів: річ у русі, її лінії та можливості для гардероба.",
)


class YouTubeCopyGenerationError(RuntimeError):
    """Raised when a strict batch must not fall back to local copy."""


def _thinking_config(model: str) -> dict[str, int | str]:
    """Use the thinking control supported by the configured Gemini model family."""
    if model.startswith("gemini-2.5-"):
        return {"thinkingBudget": 0}
    return {"thinkingLevel": "minimal"}


def _fallback_description(seed: str) -> str:
    """Return a deterministic distinct fallback when AI is unavailable."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return f"{_LEADS[digest[0] % len(_LEADS)]}\n{_DETAILS[digest[1] % len(_DETAILS)]}"


def _clean_description(text: str) -> str | None:
    lines = [line.strip() for line in (text or "").splitlines()]
    clean = "\n".join(line for line in lines if line and "#" not in line).strip()
    if len(clean) < 120 or len(clean) > 500:
        return None
    lowered = clean.casefold()
    if "модель" in lowered or _SKU_PATTERN.search(clean):
        return None
    if any(phrase in lowered for phrase in _BANNED_PHRASES):
        return None
    return clean


def generate_youtube_description(caption: str, brand: str, require_ai: bool = False) -> str:
    """Use Gemini for fresh copy and fall back safely when it is not configured."""
    fallback = _fallback_description(caption)
    if not settings.GEMINI_API_KEY or not settings.YOUTUBE_AI_METADATA_ENABLED:
        if require_ai:
            raise YouTubeCopyGenerationError("Gemini is not configured for strict metadata generation")
        return fallback

    try:
        instructions = (
            "Ти український e-commerce копірайтер бренду жіночого одягу. "
            "Напиши рівно два короткі речення українською, разом від 120 до 500 символів. "
            "Текст має бути живим, конкретним і відрізнятися від типових описів інших роликів. "
            "Дозволено згадувати лише бренд, тип виробу, комплектність і матеріал, прямо вказані у підписі. "
            "Не вигадуй посадку, колір, якість, довговічність, відчуття на тілі, догляд, властивості тканини чи ситуації використання. "
            "Не ставте запитань і не використовуйте пафос, штампи, рекламні обіцянки або згадку AI. "
            "Не пиши артикул, назву моделі, категорію розмірів, слово 'модель', хештеги, контакти чи URL. "
            "Не використовуй фрази 'для комфортних і стильних образів' або "
            "'У відео показані фактура тканини, посадка та деталі виробу'."
        )
        request = {
            "systemInstruction": {"parts": [{"text": instructions}]},
            "contents": [{"parts": [{"text": (
                f"Бренд: {brand}\nПідпис відео: {caption}\n"
                f"Внутрішній ключ різноманітності: {hashlib.sha256(caption.encode('utf-8')).hexdigest()[:12]}\n"
                "Не виводь внутрішній ключ у тексті.\n"
                "Поверни лише готовий текст опису українською."
            )}]}],
            # Copywriting is simple; disable/minimize thinking for the selected model family.
            "generationConfig": {
                "thinkingConfig": _thinking_config(settings.YOUTUBE_METADATA_AI_MODEL),
                "maxOutputTokens": 500,
            },
        }
        for attempt in range(3):
            response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{settings.YOUTUBE_METADATA_AI_MODEL}:generateContent",
                headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                json=request,
                timeout=45.0,
            )
            # A 429 consumes no useful retry budget: Gemini reports quota exhaustion,
            # so defer the strict batch instead of making two more identical requests.
            if response.status_code not in {500, 502, 503, 504} or attempt == 2:
                break
            time.sleep(attempt + 1)
        response.raise_for_status()
        payload = response.json()
        text = str(
            payload.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        description = _clean_description(text)
        if description:
            return description
        if require_ai:
            raise YouTubeCopyGenerationError("Gemini returned an invalid YouTube description")
        logger.warning("Gemini returned invalid YouTube description; using local fallback")
    except Exception as exc:
        if require_ai:
            logger.warning("Gemini YouTube copy generation failed during strict metadata generation")
            if isinstance(exc, YouTubeCopyGenerationError):
                raise
            raise YouTubeCopyGenerationError("Gemini did not return a valid YouTube description") from None
        logger.exception("Gemini YouTube copy generation failed; using local fallback")
    return fallback
