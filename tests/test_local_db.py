from app.database.client import _MockDBClient


def test_local_sqlite_roundtrip_and_reopen(tmp_path):
    path = tmp_path / "data" / "aksan.db"
    db = _MockDBClient(path)
    row = db.insert("videos", {"chat_id": "1", "caption": "26.1_test", "status": "pending"})
    db.update("videos", {"id": row["id"]}, {"status": "done", "youtube_url": "https://y/1"})

    reopened = _MockDBClient(path)
    found = reopened.select("videos", {"id": row["id"]})
    assert found[0]["status"] == "done" and found[0]["youtube_url"] == "https://y/1"
    reopened.delete("videos", {"id": row["id"]})
    assert reopened.select("videos") == []
