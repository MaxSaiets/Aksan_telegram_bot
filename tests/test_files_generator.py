import pandas as pd

from config import settings


def test_parse_title_with_suffix_keeps_exact_model_and_category():
    from app.services.youtube_catalog import parse_title

    parsed = parse_title("25.2888_норма_aksan")

    assert parsed["model"] == "25.2888"
    assert parsed["category"] == "норма"


def test_generate_rozetka_file_uses_latest_video_snapshot(tmp_path, monkeypatch):
    from app.services import files_generator as fg

    monkeypatch.setattr(settings, "TEMP_VIDEO_DIR", str(tmp_path))
    monkeypatch.setattr(
        fg,
        "fetch_channel_videos",
        lambda: [
            {
                "video_id": "old1",
                "title": "25.2888_норма_old",
                "url": "https://www.youtube.com/watch?v=old1",
                "model": "25.2888",
                "category": "норма",
                "published_at": "2026-03-19T09:00:00Z",
            },
            {
                "video_id": "new1",
                "title": "25.2888_норма_aksan",
                "url": "https://www.youtube.com/watch?v=new1",
                "model": "25.2888",
                "category": "норма",
                "published_at": "2026-03-20T09:00:00Z",
            },
        ],
    )
    monkeypatch.setattr(
        fg,
        "_fetch_all_rozetka_variants",
        lambda: [
            {
                "rz_item_id": 1,
                "article": "25.2888_black_40(S)",
                "model": "25.2888",
                "name_ua": "Сукня 40 чорна",
                "url": "https://rozetka.com.ua/1/p1",
            },
            {
                "rz_item_id": 2,
                "article": "25.2888_black_42(M)",
                "model": "25.2888",
                "name_ua": "Сукня 42 чорна",
                "url": "https://rozetka.com.ua/2/p2",
            },
        ],
    )

    out, count = fg.generate_rozetka_file()

    assert count == 2
    df = pd.read_excel(out)
    assert len(df) == 2
    assert set(df["Посилання на відео"].tolist()) == {"https://www.youtube.com/watch?v=new1"}


def test_generate_site_file_ignores_old_export_state(tmp_path, monkeypatch):
    from app.services import files_generator as fg

    monkeypatch.setattr(settings, "TEMP_VIDEO_DIR", str(tmp_path))
    monkeypatch.setattr(
        fg,
        "fetch_channel_videos",
        lambda: [
            {
                "video_id": "new2",
                "title": "25.2888_норма_aksan",
                "url": "https://www.youtube.com/watch?v=new2",
                "model": "25.2888",
                "category": "норма",
                "published_at": "2026-03-20T09:00:00Z",
            },
        ],
    )
    monkeypatch.setattr(
        fg,
        "_fetch_all_rozetka_variants",
        lambda: [
            {
                "rz_item_id": 1,
                "article": "25.2888_black_40(S)",
                "model": "25.2888",
                "name_ua": "Сукня 40 чорна",
                "url": "https://rozetka.com.ua/1/p1",
            },
            {
                "rz_item_id": 2,
                "article": "25.2888_black_44(L)",
                "model": "25.2888",
                "name_ua": "Сукня 44 чорна",
                "url": "https://rozetka.com.ua/2/p2",
            },
        ],
    )

    out, count = fg.generate_site_file()

    assert count == 2
    df = pd.read_excel(out)
    assert len(df) == 2
    assert set(df["Посилання на відео"].tolist()) == {"https://www.youtube.com/watch?v=new2"}


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
    monkeypatch.setattr("app.services.files_generator.generate_rozetka_file", lambda on_progress=None: (output, 3))
    monkeypatch.setattr(settings, "USE_MOCKS", True)

    result = run_generate_rozetka_file.apply(kwargs={"chat_id": "123456789"}).get()

    assert result["status"] == "done"
    assert any("3 рядків" in message for message in sent_messages)


def test_site_task_reports_no_exact_matches(monkeypatch):
    from app.tasks.files_task import run_generate_site_file

    sent_messages = []

    async def capture_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent_messages.append(text)

    monkeypatch.setattr("app.tasks.files_task.send_text", capture_send)
    monkeypatch.setattr("app.services.files_generator.generate_site_file", lambda on_progress=None: (None, 0))

    result = run_generate_site_file.apply(kwargs={"chat_id": "123456789"}).get()

    assert result["status"] == "empty"
    assert any("exact model/category" in message for message in sent_messages)