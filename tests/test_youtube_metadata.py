from config import settings
from app.services.youtube_metadata import build_youtube_metadata, tag_character_count


def _disable_ai(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")


def test_metadata_preserves_exact_title_and_uses_natural_seo_description(monkeypatch):
    _disable_ai(monkeypatch)
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
    assert 450 <= tag_character_count(metadata.tags) <= 500
    assert "Завантажено через Telegram" not in metadata.description


def test_metadata_appends_configured_footer_and_tags(monkeypatch):
    _disable_ai(monkeypatch)
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "Замовлення: example.com")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "мода Україна, Aksan fashion")

    metadata = build_youtube_metadata("25.2888_ботал_aksan")

    assert metadata.description.endswith("Замовлення: example.com")
    assert "мода Україна" in metadata.tags
    assert "Aksan fashion" in metadata.tags


def test_metadata_uses_specific_product_copy_when_title_has_product_details(monkeypatch):
    _disable_ai(monkeypatch)
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "")

    metadata = build_youtube_metadata("26.3067_Aksan_костюм_норма_трійка_велюр")

    assert "#костюмтрійка" in metadata.description
    assert "26.3067" not in metadata.description
    assert metadata.description.count("#") == 5


def test_metadata_recognizes_long_sleeve_and_corduroy_costume(monkeypatch):
    _disable_ai(monkeypatch)
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "")

    long_sleeve = build_youtube_metadata("26.3065_Aksan_лонгслів_норма_віскоза")
    corduroy = build_youtube_metadata("26.3051_Aksan_костюм_норма_вельвет")

    assert "жіночий лонгслів" in long_sleeve.tags
    assert "вельветовий костюм" in corduroy.tags


def test_metadata_uses_material_when_title_confirms_it(monkeypatch):
    _disable_ai(monkeypatch)
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "")

    fleece_pants = build_youtube_metadata("26.3057_Aksan_штани_норма_байка")
    viscose_long_sleeve = build_youtube_metadata("26.3065_Aksan_лонгслів_норма_віскоза")

    assert "штани на байці" in fleece_pants.tags
    assert "#віскоза" in viscose_long_sleeve.description
    assert "лонгслів з віскози" in viscose_long_sleeve.tags


def test_material_specific_descriptions_do_not_repeat(monkeypatch):
    _disable_ai(monkeypatch)
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "")

    descriptions = {
        build_youtube_metadata("26.3057_Aksan_штани_норма_байка").description,
        build_youtube_metadata("26.3065_Aksan_лонгслів_норма_віскоза").description,
        build_youtube_metadata("26.3051_Aksan_костюм_норма_вельвет").description,
    }

    assert len(descriptions) == 3


def test_metadata_uses_ai_generated_copy_when_available(monkeypatch):
    _disable_ai(monkeypatch)
    monkeypatch.setattr(settings, "YOUTUBE_DESCRIPTION_FOOTER", "")
    monkeypatch.setattr(settings, "YOUTUBE_EXTRA_TAGS", "")
    monkeypatch.setattr(
        "app.services.youtube_metadata.generate_youtube_description",
        lambda caption, brand: "Свіжий текст без технічних деталей.\nУ ролику легко відчути характер речі.",
    )

    metadata = build_youtube_metadata("26.3067_Aksan_костюм_норма_трійка_велюр")

    assert metadata.description.startswith("Свіжий текст без технічних деталей.")
    assert metadata.description.count("#") == 5
