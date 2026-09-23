import sys
from types import ModuleType

from config import settings
from app.services.youtube_copywriter import generate_youtube_description


def test_fallback_copy_is_distinct_and_never_mentions_article(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    first = generate_youtube_description("26.3057_Aksan_штани_норма_байка", "Aksan")
    second = generate_youtube_description("26.3065_Aksan_лонгслів_норма_віскоза", "Aksan")

    assert first != second
    assert "26.3057" not in first
    assert "модель" not in first.casefold()


def test_copywriter_uses_openai_when_configured(monkeypatch):
    class FakeResponse:
        output_text = "Живий опис для нового відео.\nБез технічних деталей."

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "key"
            self.responses = self

        def create(self, **kwargs):
            assert kwargs["model"] == "test-model"
            return FakeResponse()

    fake_openai = ModuleType("openai")
    fake_openai.OpenAI = FakeClient
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "key")
    monkeypatch.setattr(settings, "YOUTUBE_METADATA_AI_MODEL", "test-model")

    assert generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan") == (
        "Живий опис для нового відео.\nБез технічних деталей."
    )
