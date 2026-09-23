from config import settings
from app.services.youtube_metadata import build_youtube_metadata


def test_metadata_preserves_exact_title_and_uses_natural_seo_description(monkeypatch):
    monkeypatch.setattr(settings, "YOUTUBE_BRAND_NAME", "Aksan")
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "")

    metadata = build_youtube_metadata("26.3048_Aksan_костюм_норма_фрісПолар")

    assert metadata.title == "26.3048_Aksan_костюм_норма_фрісПолар"
    assert "26.3048" not in metadata.description
    assert "Розмірна група" not in metadata.description
    assert "модель" not in metadata.description.casefold()
    assert metadata.description.count("#") == 5
    assert "жіночий костюм" in metadata.tags
    assert "жіночий одяг" in metadata.tags
    assert len(metadata.tags) > 10
    assert "Завантажено через Telegram" not in metadata.description


def test_metadata_appends_configured_footer_and_tags(monkeypatch):
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "Замовлення: example.com")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "мода Україна, Aksan fashion")

    metadata = build_youtube_metadata("25.2888_ботал_aksan")

    assert metadata.description.endswith("Замовлення: example.com")
    assert "мода Україна" in metadata.tags
    assert "Aksan fashion" in metadata.tags


def test_metadata_uses_specific_product_copy_when_title_has_product_details(monkeypatch):
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "")

    metadata = build_youtube_metadata("26.3067_Aksan_костюм_норма_трійка_велюр")

    assert metadata.description.startswith("Велюровий костюм-трійка Aksan")
    assert "26.3067" not in metadata.description
    assert metadata.description.count("#") == 5
