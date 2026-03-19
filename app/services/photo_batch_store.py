"""Store metadata for the last photo batch sent to Telegram."""
from __future__ import annotations

import json
from pathlib import Path

_STORE_PATH = Path("tmp/last_photo_batches.json")


def _load() -> dict[str, dict]:
    if not _STORE_PATH.exists():
        return {}
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict[str, dict]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_last_batch(source_chat_id: str, target_chat_id: str, message_ids: list[int], code: str) -> None:
    data = _load()
    data[str(source_chat_id)] = {
        "target_chat_id": str(target_chat_id),
        "message_ids": message_ids,
        "code": code,
    }
    _save(data)


def get_last_batch(source_chat_id: str) -> dict | None:
    return _load().get(str(source_chat_id))


def clear_last_batch(source_chat_id: str) -> None:
    data = _load()
    if str(source_chat_id) in data:
        del data[str(source_chat_id)]
        _save(data)
