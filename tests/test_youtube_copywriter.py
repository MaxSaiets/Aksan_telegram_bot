from config import settings
from app.services.youtube_copywriter import generate_youtube_description
import pytest
from app.services.youtube_copywriter import YouTubeCopyGenerationError


def test_fallback_copy_is_distinct_and_never_mentions_article(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    first = generate_youtube_description("26.3057_Aksan_штани_норма_байка", "Aksan")
    second = generate_youtube_description("26.3065_Aksan_лонгслів_норма_віскоза", "Aksan")

    assert first != second
    assert "26.3057" not in first
    assert "модель" not in first.casefold()


def test_copywriter_uses_gemini_when_configured(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{
                "text": (
                    "Живий опис для нового відео з акцентом на те, що справді вказано у підписі.\n"
                    "Короткий огляд допомагає побачити виріб ближче без зайвих рекламних обіцянок."
                )
            }]}}]}

    def fake_post(url, **kwargs):
        assert url.endswith("models/test-model:generateContent")
        assert kwargs["headers"]["x-goog-api-key"] == "key"
        return FakeResponse()

    monkeypatch.setattr("app.services.youtube_copywriter.httpx.post", fake_post)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(settings, "YOUTUBE_METADATA_AI_MODEL", "test-model")

    assert generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan") == (
        "Живий опис для нового відео з акцентом на те, що справді вказано у підписі.\n"
        "Короткий огляд допомагає побачити виріб ближче без зайвих рекламних обіцянок."
    )


def test_strict_copywriter_never_uses_fallback(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    with pytest.raises(YouTubeCopyGenerationError):
        generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan", require_ai=True)
