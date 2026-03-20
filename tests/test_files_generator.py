import json

import pandas as pd

from config import settings


def test_parse_title_with_suffix_keeps_exact_model_and_category():
    from app.services.youtube_catalog import parse_title

    parsed = parse_title("25.2888_норма_aksan")

    assert parsed["model"] == "25.2888"
    assert parsed["category"] == "норма"


def test_generate_rozetka_file_uses_latest_video_for_same_model_when_video_changed(tmp_path, monkeypatch):
    from app.services import files_generator as fg

    monkeypatch.setattr(settings, "TEMP_VIDEO_DIR", str(tmp_path))
    monkeypatch.setattr(fg, "_ROZETKA_REPORT_STATE_PATH", tmp_path / "rozetka_state.json")
    (tmp_path / "rozetka_state.json").write_text(
        json.dumps({"25.2888::норма": "https://www.youtube.com/watch?v=old1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        fg,
        "fetch_channel_videos",
        lambda: [
            {"video_id": "old1", "title": "25.2888_норма_old", "url": "https://www.youtube.com/watch?v=old1", "model": "25.2888", "category": "норма", "published_at": "2026-03-19T09:00:00Z"},
            {"video_id": "new1", "title": "25.2888_норма_aksan", "url": "https://www.youtube.com/watch?v=new1", "model": "25.2888", "category": "норма", "published_at": "2026-03-20T09:00:00Z"},
        ],
    )
    monkeypatch.setattr(
        fg,
        "_fetch_all_rozetka_variants",
        lambda: [
            {"rz_item_id": 1, "article": "25.2888_black_40(S)", "model": "25.2888", "name_ua": "Сукня 40 чорна", "url": "https://rozetka.com.ua/1/p1"},
            {"rz_item_id": 2, "article": "25.2888_black_42(M)", "model": "25.2888", "name_ua": "Сукня 42 чорна", "url": "https://rozetka.com.ua/2/p2"},
        ],
    )

    out, count, changed_count = fg.generate_rozetka_file()

    assert changed_count == 1
    assert count == 2
    df = pd.read_excel(out)
    assert len(df) == 2
    assert set(df["Посилання на відео"].tolist()) == {"https://www.youtube.com/watch?v=new1"}


def test_generate_site_file_only_returns_new_models_since_last_report(tmp_path, monkeypatch):
    from app.services import files_generator as fg

    monkeypatch.setattr(settings, "TEMP_VIDEO_DIR", str(tmp_path))
    monkeypatch.setattr(fg, "_SITE_REPORT_STATE_PATH", tmp_path / "site_state.json")
    (tmp_path / "site_state.json").write_text(
        json.dumps({"25.1111::норма": "https://www.youtube.com/watch?v=v1111"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        fg,
        "fetch_channel_videos",
        lambda: [
            {"video_id": "v1111", "title": "25.1111_норма_aksan", "url": "https://www.youtube.com/watch?v=v1111", "model": "25.1111", "category": "норма", "published_at": "2026-03-19T09:00:00Z"},
            {"video_id": "v2222", "title": "25.2222_норма_aksan", "url": "https://www.youtube.com/watch?v=v2222", "model": "25.2222", "category": "норма", "published_at": "2026-03-20T09:00:00Z"},
        ],
    )
    monkeypatch.setattr(
        fg,
        "_fetch_all_site_variants",
        lambda: [
            {"article": "25.1111_black_40(S)", "model": "25.1111", "name_ua": "Сукня 1111"},
            {"article": "25.2222_black_40(S)", "model": "25.2222", "name_ua": "Сукня 2222"},
        ],
    )

    out, count, changed_count = fg.generate_site_file()

    assert changed_count == 1
    assert count == 1
    df = pd.read_excel(out)
    assert len(df) == 1
    assert df.iloc[0]["SKU"] == "25.2222_black_40(S)"
    assert df.iloc[0]["Посилання на відео"] == "https://www.youtube.com/watch?v=v2222"


def test_rozetka_task_reports_snapshot_count(monkeypatch, tmp_path):
    from app.tasks.files_task import run_generate_rozetka_file

    sent_messages = []

    async def capture_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent_messages.append(text)

    async def capture_document(chat_id, file_path, filename, caption=None):
        sent_messages.append(caption or "")

    output = tmp_path / "rozetka.xlsx"
    output.write_bytes(b"PK\x03\x04")

    monkeypatch.setattr("app.tasks.files_task.send_text", capture_send)
    monkeypatch.setattr("app.tasks.files_task.send_document", capture_document)
    monkeypatch.setattr("app.services.files_generator.generate_rozetka_file", lambda on_progress=None: (output, 3, 1))
    monkeypatch.setattr(settings, "USE_MOCKS", True)

    result = run_generate_rozetka_file.apply(kwargs={"chat_id": "123456789"}).get()

    assert result["status"] == "done"
    assert any("3 рядків" in message for message in sent_messages)


def test_rozetka_task_reports_no_new_models(monkeypatch):
    from app.tasks.files_task import run_generate_rozetka_file

    sent_messages = []

    async def capture_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent_messages.append(text)

    monkeypatch.setattr("app.tasks.files_task.send_text", capture_send)
    monkeypatch.setattr("app.services.files_generator.generate_rozetka_file", lambda on_progress=None: (None, 0, 0))

    result = run_generate_rozetka_file.apply(kwargs={"chat_id": "123456789"}).get()

    assert result["status"] == "empty"
    assert any("Нових моделей або оновлених відео" in message for message in sent_messages)


def test_site_task_reports_no_exact_matches_for_new_models(monkeypatch):
    from app.tasks.files_task import run_generate_site_file

    sent_messages = []

    async def capture_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent_messages.append(text)

    monkeypatch.setattr("app.tasks.files_task.send_text", capture_send)
    monkeypatch.setattr("app.services.files_generator.generate_site_file", lambda on_progress=None: (None, 0, 2))

    result = run_generate_site_file.apply(kwargs={"chat_id": "123456789"}).get()

    assert result["status"] == "empty"
    assert any("exact model/category" in message for message in sent_messages)