from config import settings
from app.services.youtube_copywriter import generate_youtube_description
import httpx
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


def test_copywriter_uses_zero_thinking_budget_for_gemini_25(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": (
                "Живий опис для нового відео з акцентом на те, що справді вказано у підписі. "
                "Короткий огляд допомагає побачити виріб ближче без зайвих рекламних обіцянок."
            )}]}}]}

    request_data = {}
    monkeypatch.setattr(
        "app.services.youtube_copywriter.httpx.post",
        lambda url, **kwargs: request_data.update(kwargs["json"]) or FakeResponse(),
    )
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(settings, "YOUTUBE_METADATA_AI_MODEL", "gemini-2.5-flash")

    generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan")

    assert request_data["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


def test_copywriter_never_sends_sku_or_size_category_to_gemini(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": (
                "Живий опис для нового відео з акцентом на те, що справді вказано у підписі. "
                "Короткий огляд допомагає побачити виріб ближче без зайвих рекламних обіцянок."
            )}]}}]}

    request_data = {}
    monkeypatch.setattr(
        "app.services.youtube_copywriter.httpx.post",
        lambda url, **kwargs: request_data.update(kwargs["json"]) or FakeResponse(),
    )
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")

    generate_youtube_description("26.3067_Aksan_костюм_норма_трійка_велюр", "Aksan")

    prompt = request_data["contents"][0]["parts"][0]["text"]
    assert "26.3067" not in prompt
    assert "норма" not in prompt
    assert "костюм" in prompt
    assert "велюр" in prompt


def test_copywriter_normalizes_generic_model_word_in_generated_copy(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": (
                "Цей виріб показано у відео без зайвих технічних деталей, щоб легше оцінити його в кадрі. "
                "Огляд допоможе роздивитися річ ближче та звернути увагу на головні акценти."
            )}]}}]}

    monkeypatch.setattr("app.services.youtube_copywriter.httpx.post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")

    description = generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan", require_ai=True)

    assert "модель" not in description.casefold()
    assert "виріб" in description


def test_copywriter_combines_all_gemini_text_parts(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [
                {"text": "Живий опис для нового відео з акцентом на те, що справді вказано у підписі. "},
                {"text": "Короткий огляд допомагає побачити виріб ближче без зайвих рекламних обіцянок."},
            ]}}]}

    monkeypatch.setattr("app.services.youtube_copywriter.httpx.post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")

    description = generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan", require_ai=True)

    assert description.startswith("Живий опис")
    assert description.endswith("рекламних обіцянок.")


def test_strict_copywriter_retries_invalid_generated_text(monkeypatch):
    class FakeResponse:
        status_code = 200

        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": self.text}]}}]}

    responses = iter([
        FakeResponse("Надто коротко."),
        FakeResponse(
            "Живий опис для нового відео з акцентом на те, що справді вказано у підписі. "
            "Короткий огляд допомагає побачити виріб ближче без зайвих рекламних обіцянок."
        ),
    ])
    monkeypatch.setattr("app.services.youtube_copywriter.httpx.post", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr("app.services.youtube_copywriter.time.sleep", lambda _: None)

    description = generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan", require_ai=True)

    assert description.startswith("Живий опис")


def test_strict_copywriter_never_uses_fallback(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    with pytest.raises(YouTubeCopyGenerationError):
        generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan", require_ai=True)


def test_strict_copywriter_does_not_retry_quota_exhaustion(monkeypatch):
    class QuotaResponse:
        status_code = 429

        def raise_for_status(self):
            raise httpx.HTTPStatusError("quota exhausted", request=None, response=None)

    calls = []
    monkeypatch.setattr("app.services.youtube_copywriter.httpx.post", lambda *args, **kwargs: calls.append(1) or QuotaResponse())
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(settings, "YOUTUBE_METADATA_AI_FALLBACK_MODELS", "")

    with pytest.raises(YouTubeCopyGenerationError):
        generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan", require_ai=True)

    assert calls == [1]


def test_copywriter_switches_to_next_model_after_quota_exhaustion(monkeypatch):
    import app.services.youtube_copywriter as copywriter

    class Response:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("error", request=None, response=None)

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": self.text}]}}]}

    calls = []
    responses = iter([
        Response(429),
        Response(200, "Живий опис для нового відео з акцентом на те, що справді вказано у підписі. Короткий огляд допомагає побачити виріб ближче без зайвих рекламних обіцянок."),
    ])
    monkeypatch.setattr("app.services.youtube_copywriter.httpx.post", lambda url, **kwargs: calls.append(url) or next(responses))
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(settings, "YOUTUBE_METADATA_AI_MODEL", "first-model")
    monkeypatch.setattr(settings, "YOUTUBE_METADATA_AI_FALLBACK_MODELS", "second-model")
    monkeypatch.setattr(copywriter, "_EXHAUSTED_MODELS", set())

    assert generate_youtube_description("26.3065_Aksan_лонгслів", "Aksan", require_ai=True).startswith("Живий опис")
    assert calls[0].endswith("models/first-model:generateContent")
    assert calls[1].endswith("models/second-model:generateContent")
