"""Unit tests for database repositories."""
import pytest
from app.database.videos_repo import (
    create_video, get_video, set_processing, set_done, set_error, get_all_done,
    find_duplicate,
)
from app.database.products_repo import (
    create_product, get_all_products, get_all_with_sku, get_products_for_video
)


class TestVideosRepo:
    def test_create_video(self):
        v = create_video("123456789", "iPhone 15 Pro", "tg_file_id_abc123")
        assert v["id"] is not None
        assert v["status"] == "pending"
        assert v["caption"] == "iPhone 15 Pro"
        assert v["chat_id"] == "123456789"

    def test_get_video(self):
        v = create_video("123456789", "Caption", "file_id_1")
        fetched = get_video(v["id"])
        assert fetched is not None
        assert fetched["id"] == v["id"]

    def test_get_video_not_found(self):
        assert get_video("nonexistent-id") is None

    def test_set_processing(self):
        v = create_video("111111111", "Caption", "file_id_2")
        updated = set_processing(v["id"])
        assert updated["status"] == "processing"

    def test_set_done(self):
        v = create_video("111111111", "Caption", "file_id_3")
        updated = set_done(v["id"], "https://youtube.com/watch?v=abc")
        assert updated["status"] == "done"
        assert updated["youtube_url"] == "https://youtube.com/watch?v=abc"

    def test_set_error(self):
        v = create_video("111111111", "Caption", "file_id_5")
        updated = set_error(v["id"], "Connection timeout")
        assert updated["status"] == "error"
        assert "timeout" in updated["error_message"]

    def test_get_all_done(self):
        v1 = create_video("111", "A", "file_id_done_1")
        v2 = create_video("222", "B", "file_id_done_2")
        set_done(v1["id"], "https://yt.com/1")
        # v2 stays pending
        done = get_all_done()
        assert len(done) == 1
        assert done[0]["id"] == v1["id"]

    def test_find_duplicate(self):
        file_id = "file_id_unique_dup_test"
        v = create_video("111111111", "Caption", file_id)
        set_done(v["id"], "https://yt.com/x")

        dup = find_duplicate(file_id)
        assert dup is not None
        assert dup["id"] == v["id"]

    def test_find_duplicate_not_found_for_pending(self):
        v = create_video("111111111", "Caption", "file_id_pending_dup")
        # Not done yet — should NOT be found as duplicate
        dup = find_duplicate("file_id_pending_dup")
        assert dup is None


class TestProductsRepo:
    def test_create_product(self):
        v = create_video("111111111", "Galaxy S24", "file_id_prod_1")
        p = create_product(
            video_id=v["id"],
            model_name="Samsung Galaxy S24",
            sku="SAM-S24",
            youtube_url="https://yt.com/abc",
            match_confidence=0.95,
        )
        assert p["sku"] == "SAM-S24"
        assert p["match_confidence"] == 0.95

    def test_get_all_products(self):
        v = create_video("111111111", "Test", "file_id_prod_2")
        create_product(v["id"], "Model A", "SKU-A", "yt_url_a")
        create_product(v["id"], "Model B", "SKU-B", "yt_url_b")
        all_p = get_all_products()
        assert len(all_p) == 2

    def test_get_all_with_sku_filters_nulls(self):
        v = create_video("111111111", "Test", "file_id_prod_3")
        create_product(v["id"], "Model A", "SKU-A", "yt_url_a")
        create_product(v["id"], "No Match", None, None)
        matched = get_all_with_sku()
        assert len(matched) == 1
        assert matched[0]["sku"] == "SKU-A"

    def test_get_products_for_video(self):
        v1 = create_video("111", "A", "file_id_prod_v1")
        v2 = create_video("222", "B", "file_id_prod_v2")
        create_product(v1["id"], "M1", "S1", "y1")
        create_product(v2["id"], "M2", "S2", "y2")
        result = get_products_for_video(v1["id"])
        assert len(result) == 1
        assert result[0]["model_name"] == "M1"
