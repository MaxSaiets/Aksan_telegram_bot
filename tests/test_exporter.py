"""Unit tests for the Excel exporter and export task."""
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from app.database.videos_repo import create_video, set_done
from app.database.products_repo import create_product
from app.services.excel_exporter import generate_report


class TestExcelExporter:
    def _seed_products(self, count: int = 3):
        """Insert `count` video+product pairs into the DB."""
        for i in range(count):
            v = create_video(f"10000000{i}", f"Model {i}", f"tg_file_id_seed_{i}")
            set_done(v["id"], f"https://youtube.com/watch?v=video{i}")
            create_product(
                video_id=v["id"],
                model_name=f"Model {i}",
                product_name=f"Товар {i}",
                sku=f"SKU-{i:03d}",
                youtube_url=f"https://youtube.com/watch?v=video{i}",
                rozetka_url=f"https://rozetka.com.ua/product{i}",
                match_confidence=0.80 + i * 0.05,
            )

    def test_generates_file(self, tmp_path):
        self._seed_products(3)
        out = generate_report(tmp_path / "test_report.xlsx")
        assert out.exists()
        assert out.suffix == ".xlsx"

    def test_correct_columns(self, tmp_path):
        self._seed_products(1)
        out = generate_report(tmp_path / "report.xlsx")
        df = pd.read_excel(out)
        expected_cols = {"SKU", "Назва товару", "YouTube URL", "Модель", "Rozetka URL", "Впевненість (%)"}
        assert expected_cols.issubset(set(df.columns))

    def test_correct_row_count(self, tmp_path):
        self._seed_products(5)
        out = generate_report(tmp_path / "report.xlsx")
        df = pd.read_excel(out)
        assert len(df) == 5

    def test_sku_values(self, tmp_path):
        self._seed_products(3)
        out = generate_report(tmp_path / "report.xlsx")
        df = pd.read_excel(out)
        skus = set(df["SKU"].tolist())
        assert "SKU-000" in skus
        assert "SKU-002" in skus

    def test_empty_db_produces_empty_file(self, tmp_path):
        out = generate_report(tmp_path / "empty.xlsx")
        df = pd.read_excel(out)
        assert len(df) == 0

    def test_confidence_is_percentage(self, tmp_path):
        self._seed_products(1)
        out = generate_report(tmp_path / "report.xlsx")
        df = pd.read_excel(out)
        confidence = df["Впевненість (%)"].iloc[0]
        assert 0 <= confidence <= 100

    def test_product_name_column_populated(self, tmp_path):
        self._seed_products(2)
        out = generate_report(tmp_path / "report.xlsx")
        df = pd.read_excel(out)
        assert "Назва товару" in df.columns
        assert "Товар 0" in df["Назва товару"].tolist()


class TestStorageUpload:
    def test_upload_file_mock_returns_url(self, tmp_path):
        import asyncio
        from app.services.storage import upload_file

        f = tmp_path / "test.xlsx"
        f.write_bytes(b"PK\x03\x04")  # minimal xlsx magic bytes

        url = asyncio.run(upload_file(f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
        assert url.startswith("https://mock.supabase.co")
        assert "test.xlsx" in url

    def test_upload_processed_video_still_works(self, tmp_path):
        import asyncio
        from app.services.storage import upload_processed_video

        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00" * 512)

        url = asyncio.run(upload_processed_video(f))
        assert url.startswith("https://mock.supabase.co")
        assert "video.mp4" in url


class TestExportTask:
    def _seed(self):
        v = create_video("123456789", "25.2834", "tg_file_id_export_seed")
        set_done(v["id"], "https://yt.com/v1")
        create_product(v["id"], "25.2834", "25.2834", "https://yt.com/v1",
                       product_name="Дриль", match_confidence=1.0)

    def test_export_mock_sends_text(self):
        self._seed()
        sent = []

        async def capture(chat_id, text, reply_markup=None, parse_mode=None):
            sent.append(text)

        with patch("app.tasks.export_task.send_text", side_effect=capture):
            from app.tasks.export_task import run_export
            result = run_export.apply(kwargs={"chat_id": "123456789"}).get()

        assert result["status"] == "done"
        assert any("Звіт" in m for m in sent)

    def test_export_creates_xlsx_file(self):
        self._seed()
        with patch("app.tasks.export_task.send_text", new_callable=AsyncMock):
            from app.tasks.export_task import run_export
            result = run_export.apply(kwargs={"chat_id": "123456789"}).get()

        path = Path(result["path"])
        assert path.exists()
        assert path.suffix == ".xlsx"
