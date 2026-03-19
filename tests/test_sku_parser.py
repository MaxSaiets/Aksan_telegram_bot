from app.services.sku_parser import (
    allowed_sizes_for_category,
    extract_category,
    extract_model_code,
    extract_variant_size,
    variant_matches_category,
)


def test_extract_model_code():
    assert extract_model_code("25.2834_норма_ifsh") == "25.2834"
    assert extract_model_code("відео 56.1234 супер ботал") == "56.1234"


def test_extract_category():
    assert extract_category("25.2834_норма") == "норма"
    assert extract_category("25.2834 бот") == "ботал"
    assert extract_category("25.2834 супер ботал") == "супер ботал"


def test_extract_variant_size():
    assert extract_variant_size("25.2834_red_42(S)") == 42
    assert extract_variant_size("25.2834_black_56(3XL)") == 56


def test_allowed_sizes_for_norma():
    assert allowed_sizes_for_category("норма", {40, 42, 44}) == {40, 42, 44}
    assert allowed_sizes_for_category("норма", {42, 44, 46}) == {40, 42, 44, 46}


def test_variant_matches_category():
    available = {40, 42, 44, 46, 50, 52, 54, 56, 58, 60}
    assert variant_matches_category("25.2834_red_42(S)", "норма", available)
    assert variant_matches_category("25.2834_red_46(L)", "норма", {42, 44, 46})
    assert not variant_matches_category("25.2834_red_50(XL)", "норма", available)
    assert variant_matches_category("25.2834_red_52(2XL)", "ботал", available)
    assert variant_matches_category("25.2834_red_56(3XL)", "супер ботал", available)
