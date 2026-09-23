from config import settings
from app.services.youtube_metadata import build_youtube_metadata


def test_metadata_preserves_exact_title_and_adds_product_context(monkeypatch):
    monkeypatch.setattr(settings, "YOUTUBE_BRAND_NAME", "Aksan")
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "")

    metadata = build_youtube_metadata("26.3048_Aksan_костюм_норма_фрісПолар")

    assert metadata.title == "26.3048_Aksan_костюм_норма_фрісПолар"
    assert "модель 26.3048" in metadata.description
    assert "Розмірна група: норма" in metadata.description
    assert "26.3048" in metadata.tags
    assert "костюм" in metadata.tags
    assert "жіночий одяг" in metadata.tags
    assert "Завантажено через Telegram" not in metadata.description


def test_metadata_appends_configured_footer_and_tags(monkeypatch):
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "Замовлення: example.com")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "мода Україна, Aksan fashion")

    metadata = build_youtube_metadata("25.2888_ботал_aksan")

    assert metadata.description.endswith("Замовлення: example.com")
    assert "мода Україна" in metadata.tags
    assert "Aksan fashion" in metadata.tags
