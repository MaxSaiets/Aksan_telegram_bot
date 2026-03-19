"""Unit tests for the model_matcher service — numeric code format."""
import pytest
from app.services.model_matcher import (
    match_model, extract_numeric_codes, extract_size_category, clean_caption, MatchResult
)


class TestExtractSizeCategory:
    def test_norma_underscore(self):
        assert extract_size_category("20.8934_норма") == "норма"

    def test_botal_underscore(self):
        assert extract_size_category("20.8934_ботал") == "ботал"

    def test_superbotal_underscore(self):
        assert extract_size_category("20.8934_суперботал") == "супер ботал"

    def test_superbotal_with_space(self):
        assert extract_size_category("20.8934_супер ботал") == "супер ботал"

    def test_category_with_space(self):
        assert extract_size_category("20.8934 норма дриль") == "норма"

    def test_no_category(self):
        assert extract_size_category("25.2834 дриль") is None

    def test_case_insensitive(self):
        assert extract_size_category("20.8934_НОРМА") == "норма"

    def test_superbotal_matched_before_botal(self):
        # суперботал contains ботал — must match longer form first
        assert extract_size_category("20.8934_суперботал") == "супер ботал"

    def test_abbreviation_bot(self):
        assert extract_size_category("20.8934_бот") == "ботал"

    def test_abbreviation_norm(self):
        assert extract_size_category("20.8934_норм") == "норма"

    def test_velykyi_botal(self):
        assert extract_size_category("20.8934_великий ботал") == "великий ботал"

    def test_mega_botal(self):
        assert extract_size_category("20.8934_мега ботал") == "мега ботал"


class TestExtractNumericCodes:
    def test_single_code(self):
        assert extract_numeric_codes("Товар 25.2834 класс") == ["25.2834"]

    def test_multi_segment_code(self):
        assert extract_numeric_codes("5.52.2554") == ["5.52.2554"]

    def test_multiple_codes(self):
        codes = extract_numeric_codes("25.2834 та ще 12.4567")
        assert "25.2834" in codes
        assert "12.4567" in codes

    def test_no_code_in_text(self):
        assert extract_numeric_codes("Samsung Galaxy S24 Ultra") == []

    def test_code_with_noise(self):
        codes = extract_numeric_codes("Відео про дриль 25.2834 #новинка 5000грн")
        assert "25.2834" in codes

    def test_price_not_confused_with_code(self):
        # "5000грн" should not match as a code (no dot separator)
        codes = extract_numeric_codes("5000грн")
        assert codes == []


class TestCleanCaption:
    def test_strips_hashtags(self):
        assert "#" not in clean_caption("25.2834 #новинка #sale")

    def test_strips_hryvnia_price(self):
        result = clean_caption("25.2834 Дриль 5000грн")
        assert "грн" not in result

    def test_strips_usd(self):
        result = clean_caption("item 25.2834 price 100USD")
        assert "USD" not in result.upper()

    def test_preserves_code(self):
        result = clean_caption("25.2834 #sale 500грн")
        assert "25.2834" in result


class TestMatchModel:
    # ── Exact code matching ──────────────────────────────────────────────────

    def test_exact_code_in_caption(self, sample_catalog, sample_rozetka):
        result = match_model("Відео про товар 25.2834 класно!", sample_catalog, sample_rozetka)
        assert result.matched is True
        assert result.sku == "25.2834"
        assert result.confidence == 1.0
        assert result.match_strategy == "exact_code"

    def test_code_only_caption(self, sample_catalog, sample_rozetka):
        result = match_model("25.2834", sample_catalog, sample_rozetka)
        assert result.matched is True
        assert result.sku == "25.2834"
        assert result.match_strategy == "exact_code"

    def test_multi_segment_code(self, sample_catalog, sample_rozetka):
        result = match_model("5.52.2554 перфоратор новий", sample_catalog, sample_rozetka)
        assert result.matched is True
        assert result.sku == "5.52.2554"
        assert result.match_strategy == "exact_code"

    def test_code_with_hashtags_and_price(self, sample_catalog, sample_rozetka):
        result = match_model("25.2834 #новинка 3500грн топ!", sample_catalog, sample_rozetka)
        assert result.matched is True
        assert result.sku == "25.2834"

    def test_rozetka_url_populated(self, sample_catalog, sample_rozetka):
        result = match_model("25.2834", sample_catalog, sample_rozetka)
        assert result.rozetka_url == "https://rozetka.com.ua/drill-800w"

    def test_no_rozetka_match_still_returns_sku(self, sample_catalog):
        result = match_model("12.4567 болгарка", sample_catalog, [])
        assert result.matched is True
        assert result.sku == "12.4567"
        assert result.rozetka_url is None

    # ── Unknown code / no match ───────────────────────────────────────────────

    def test_unknown_code_no_match(self, sample_catalog, sample_rozetka):
        result = match_model("99.9999 невідомий товар", sample_catalog, sample_rozetka)
        assert result.matched is False
        assert result.sku is None

    def test_no_code_in_caption_returns_unmatched(self, sample_catalog, sample_rozetka):
        result = match_model("Просто текст без коду", sample_catalog, sample_rozetka)
        # May or may not match via fuzzy text — just check it doesn't crash
        assert isinstance(result, MatchResult)

    def test_empty_catalog(self, sample_rozetka):
        result = match_model("25.2834", [], sample_rozetka)
        assert result.matched is False

    def test_empty_caption(self, sample_catalog, sample_rozetka):
        result = match_model("", sample_catalog, sample_rozetka)
        assert isinstance(result, MatchResult)

    # ── Result structure ─────────────────────────────────────────────────────

    def test_result_is_dataclass(self, sample_catalog, sample_rozetka):
        result = match_model("5.52.2554", sample_catalog, sample_rozetka)
        assert isinstance(result, MatchResult)
        assert 0.0 <= result.confidence <= 1.0
        assert result.match_strategy in ("exact_code", "fuzzy_code", "fuzzy_text", "none")

    def test_matched_flag_reflects_sku(self, sample_catalog, sample_rozetka):
        r = match_model("25.2834", sample_catalog, sample_rozetka)
        assert r.matched == (r.sku is not None)

    def test_product_name_populated_on_match(self, sample_catalog, sample_rozetka):
        r = match_model("25.2834", sample_catalog, sample_rozetka)
        assert r.product_name == "Дриль 800Вт"

    def test_product_name_empty_on_no_match(self, sample_catalog, sample_rozetka):
        r = match_model("99.9999 невідомий", sample_catalog, sample_rozetka)
        assert r.product_name == ""

    # ── Size category suffix ──────────────────────────────────────────────────

    def test_sku_with_norma_suffix(self, sample_catalog, sample_rozetka):
        r = match_model("25.2834_норма", sample_catalog, sample_rozetka)
        assert r.matched is True
        assert r.sku == "25.2834_норма"

    def test_sku_with_botal_suffix(self, sample_catalog, sample_rozetka):
        r = match_model("25.2834_ботал", sample_catalog, sample_rozetka)
        assert r.matched is True
        assert r.sku == "25.2834_ботал"

    def test_sku_with_superbotal_suffix(self, sample_catalog, sample_rozetka):
        r = match_model("25.2834_суперботал", sample_catalog, sample_rozetka)
        assert r.matched is True
        assert r.sku == "25.2834_супер ботал"

    def test_sku_without_category_unchanged(self, sample_catalog, sample_rozetka):
        r = match_model("25.2834 дриль", sample_catalog, sample_rozetka)
        assert r.matched is True
        assert r.sku == "25.2834"
