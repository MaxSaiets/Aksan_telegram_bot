import sys
from types import ModuleType, SimpleNamespace

from config import settings
from app.services.youtube_copywriter import generate_youtube_description


def test_fallback_copy_is_distinct_and_never_mentions_article(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    first = generate_youtube_description("26.3057_Aksan_штани_норма_байка", "Aksan")
    second = generate_youtube_description("26.3065_Aksan_лонгслів_норма_віскоза", "Aksan")

    assert first != second
    assert "26.3057" not in first
    assert "модель" not in first.casefold()


def test_copywriter_uses_gemini_when_configured(monkeypatch):
    class FakeResponse:
        output_text = "Живий опис для нового відео.\nБез технічних деталей."

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "key"
            self.responses = self
            self.models = self

        def generate_content(self, **kwargs):
            assert kwargs["model"] == "test-model"
            return FakeResponse()

    fake_google = ModuleType("google")
    fake_genai = ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_genai.types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(settings, "YOUTUBE_METADATA_AI_MODEL", "test-model")

    assert generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan") == (
        "Живий опис для нового відео.\nБез технічних деталей."
    )
