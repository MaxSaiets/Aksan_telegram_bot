"""Generate human YouTube descriptions while keeping product claims grounded."""
from __future__ import annotations

import hashlib
import logging
import re

from config import settings


logger = logging.getLogger(__name__)
_SKU_PATTERN = re.compile(r"\b\d{2}\.\d{3,5}\b")
_BANNED_PHRASES = (
    "для комфортних і стильних образів",
    "у відео показані фактура тканини, посадка та деталі виробу",
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


def _fallback_description(seed: str) -> str:
    """Return a deterministic distinct fallback when AI is unavailable."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return f"{_LEADS[digest[0] % len(_LEADS)]}\n{_DETAILS[digest[1] % len(_DETAILS)]}"


def _clean_description(text: str) -> str | None:
    lines = [line.strip() for line in (text or "").splitlines()]
    clean = "\n".join(line for line in lines if line and "#" not in line).strip()
    if not clean or len(clean) > 650:
        return None
    lowered = clean.casefold()
    if "модель" in lowered or _SKU_PATTERN.search(clean):
        return None
    if any(phrase in lowered for phrase in _BANNED_PHRASES):
        return None
    return clean


def generate_youtube_description(caption: str, brand: str) -> str:
    """Use Gemini for fresh copy and fall back safely when it is not configured."""
    fallback = _fallback_description(caption)
    if not settings.GEMINI_API_KEY or not settings.YOUTUBE_AI_METADATA_ENABLED:
        return fallback

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.YOUTUBE_METADATA_AI_MODEL,
            contents=(
                f"Бренд: {brand}\n"
                f"Підпис відео: {caption}\n"
                "Поверни лише готовий текст опису українською."
            ),
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Ти український e-commerce копірайтер бренду жіночого одягу. "
                    "Напиши свіжий, природний, конкретний опис для YouTube у двох коротких абзацах. "
                    "Не повторюй шаблони, не використовуй штучно-пафосний тон і не згадуй AI. "
                    "Не вигадуй матеріал, фасон, колір, розміри або інші характеристики, яких немає у підписі. "
                    "Не пиши артикул, назву моделі, категорію розмірів, слово 'модель', хештеги, CTA, контакти чи URL. "
                    "Не використовуй фрази 'для комфортних і стильних образів' або "
                    "'У відео показані фактура тканини, посадка та деталі виробу'."
                ),
                temperature=0.9,
                max_output_tokens=220,
            ),
        )
        description = _clean_description(response.output_text)
        if description:
            return description
        logger.warning("Gemini returned invalid YouTube description; using local fallback")
    except Exception:
        logger.exception("Gemini YouTube copy generation failed; using local fallback")
    return fallback
