"""
Telegram bot handlers (aiogram v3 Router).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import settings
from app.services.photo_batch_store import clear_last_batch, get_last_batch
from app.services.telegram_sender import delete_messages
from app.telegram.keyboard import (
    BTN_CANCEL_PHOTOS,
    BTN_DELETE_LAST_PHOTOS,
    BTN_FILES,
    BTN_RESET,
    BTN_SEND_PHOTOS,
    BTN_SEND_VIDEO,
    BTN_UNDO_LAST,
    CB_CANCEL_TASK,
    CB_FILES_BACK,
    CB_FILES_REPORT,
    CB_FILES_ROZETKA,
    CB_FILES_SITE,
    CB_UNDO_CANCEL,
    CB_UNDO_CONFIRM,
    cancel_task_keyboard,
    files_keyboard,
    main_menu_keyboard,
    photo_mode_keyboard,
    undo_confirm_keyboard,
)
from app.telegram.states import PhotoUpload, VideoUpload
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = Router()


def _is_allowed(user_id: int) -> bool:
    allowed = settings.allowed_users
    return not allowed or user_id in allowed


def _is_image_document(message: Message) -> bool:
    document = message.document
    if not document:
        return False
    mime = (document.mime_type or "").lower()
    name = (document.file_name or "").lower()
    return mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp"))


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        logger.warning("Blocked user_id=%s (not in whitelist)", message.from_user.id)
        await message.answer("РЈ РІР°СЃ РЅРµРјР°С” РґРѕСЃС‚СѓРїСѓ РґРѕ С†СЊРѕРіРѕ Р±РѕС‚Р°.")
        return

    await state.clear()
    name = message.from_user.first_name or "РєРѕСЂРёСЃС‚СѓРІР°С‡"
    await message.answer(
        f"РџСЂРёРІС–С‚, {name}!\n\n"
        "РЇ РІРјС–СЋ РѕР±СЂРѕР±Р»СЏС‚Рё РІС–РґРµРѕ С‚Р° С„РѕС‚Рѕ РґР»СЏ РІС–РґРїСЂР°РІРєРё РІ РіСЂСѓРїСѓ.\n"
        "РћР±РµСЂС–С‚СЊ РїРѕС‚СЂС–Р±РЅСѓ РґС–СЋ РЅРёР¶С‡Рµ.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == BTN_RESET)
async def btn_reset(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await state.clear()
    await message.answer("РЎС‚Р°РЅ СЃРєРёРЅСѓС‚Рѕ.", reply_markup=main_menu_keyboard())


@router.message(F.text == BTN_CANCEL_PHOTOS)
async def btn_cancel_photos(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await state.clear()
    await message.answer("Р РµР¶РёРј С„РѕС‚Рѕ СЃРєР°СЃРѕРІР°РЅРѕ.", reply_markup=main_menu_keyboard())


@router.message(F.text == BTN_DELETE_LAST_PHOTOS)
async def btn_delete_last_photos(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return

    batch = get_last_batch(str(message.chat.id))
    if not batch:
        await message.answer("РќРµРјР°С” РїРѕРїРµСЂРµРґРЅСЊРѕС— РїР°С‡РєРё С„РѕС‚Рѕ РґР»СЏ РІРёРґР°Р»РµРЅРЅСЏ.", reply_markup=main_menu_keyboard())
        return

    await delete_messages(batch["target_chat_id"], batch.get("message_ids", []))
    clear_last_batch(str(message.chat.id))
    await message.answer(
        f"РџРѕРїРµСЂРµРґРЅСЋ РїР°С‡РєСѓ С„РѕС‚Рѕ РґР»СЏ РєРѕРґСѓ {batch.get('code', '')} РІРёРґР°Р»РµРЅРѕ.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == BTN_UNDO_LAST)
async def btn_undo_last(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return

    from app.database.videos_repo import get_last_done_by_chat

    chat_id = str(message.chat.id)
    last_video = get_last_done_by_chat(chat_id)
    if not last_video:
        await message.answer("РќРµРјР°С” РѕР±СЂРѕР±Р»РµРЅРёС… РІС–РґРµРѕ РґР»СЏ СЃРєР°СЃСѓРІР°РЅРЅСЏ.", reply_markup=main_menu_keyboard())
        return

    caption = last_video.get("caption", "Р±РµР· РїС–РґРїРёСЃСѓ")
    preview = caption[:80] + ("..." if len(caption) > 80 else "")
    youtube = last_video.get("youtube_url", "вЂ”")
    await state.update_data(undo_video_id=last_video["id"])

    await message.answer(
        f"Р’РёРґР°Р»РёС‚Рё РѕСЃС‚Р°РЅРЅС” РІС–РґРµРѕ?\n\n"
        f"В«{preview}В»\n"
        f"{youtube}\n\n"
        f"Р¦Рµ РІРёРґР°Р»РёС‚СЊ РІС–РґРµРѕ Р· YouTube С‚Р° Р±Р°Р·Рё РґР°РЅРёС….",
        reply_markup=undo_confirm_keyboard(),
    )


@router.callback_query(F.data == CB_UNDO_CONFIRM)
async def cb_undo_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    video_id = data.get("undo_video_id")
    if not video_id:
        await callback.message.edit_text("Р’С–РґРµРѕ РґР»СЏ РІРёРґР°Р»РµРЅРЅСЏ РЅРµ Р·РЅР°Р№РґРµРЅРѕ.")
        return

    await state.update_data(undo_video_id=None)
    await callback.message.edit_text("Р’РёРґР°Р»СЏСЋ РІС–РґРµРѕ Р· YouTube С‚Р° Р±Р°Р·Рё РґР°РЅРёС…...")

    from app.tasks.undo_task import run_undo_last_video

    run_undo_last_video.delay(chat_id=str(callback.message.chat.id), video_id=video_id)


@router.callback_query(F.data == CB_UNDO_CANCEL)
async def cb_undo_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(undo_video_id=None)
    await callback.message.edit_text("Р’РёРґР°Р»РµРЅРЅСЏ СЃРєР°СЃРѕРІР°РЅРѕ.")


@router.callback_query(F.data.startswith(CB_CANCEL_TASK))
async def cb_cancel_task(callback: CallbackQuery) -> None:
    await callback.answer()
    task_id = callback.data[len(CB_CANCEL_TASK):]

    try:
        from celery.contrib.abortable import AbortableAsyncResult
        from app.tasks.celery_app import celery_app

        result = AbortableAsyncResult(task_id, app=celery_app)
        if result.state in ("SUCCESS", "FAILURE"):
            await callback.message.edit_text("Р¦СЋ Р·Р°РґР°С‡Сѓ РІР¶Рµ Р·Р°РІРµСЂС€РµРЅРѕ.")
            return

        result.abort()
        await callback.message.edit_text("РћР±СЂРѕР±РєСѓ РІС–РґРµРѕ СЃРєР°СЃРѕРІР°РЅРѕ.")
        logger.info("Task %s aborted by user", task_id[:8])
    except Exception as exc:
        logger.warning("Cancel task %s failed: %s", task_id[:8], exc)
        await callback.message.edit_text(f"РќРµ РІРґР°Р»РѕСЃСЏ СЃРєР°СЃСѓРІР°С‚Рё: {exc}")


@router.message(F.text == BTN_FILES)
async def btn_files(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await message.answer(
        "РћР±РµСЂС–С‚СЊ С‚РёРї С„Р°Р№Р»Сѓ:\n\n"
        "Р”Р»СЏ Р РѕР·РµС‚РєРё, РґР»СЏ СЃР°Р№С‚Сѓ Р°Р±Рѕ Р·РІС–С‚ .xlsx.",
        reply_markup=files_keyboard(),
    )


@router.callback_query(F.data == CB_FILES_ROZETKA)
async def cb_files_rozetka(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text("Р“РµРЅРµСЂСѓСЋ С„Р°Р№Р» РґР»СЏ Р РѕР·РµС‚РєРё...")
    from app.tasks.files_task import run_generate_rozetka_file

    run_generate_rozetka_file.delay(chat_id=str(callback.message.chat.id))


@router.callback_query(F.data == CB_FILES_SITE)
async def cb_files_site(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text("Р“РµРЅРµСЂСѓСЋ С„Р°Р№Р» РґР»СЏ СЃР°Р№С‚Сѓ...")
    from app.tasks.files_task import run_generate_site_file

    run_generate_site_file.delay(chat_id=str(callback.message.chat.id))


@router.callback_query(F.data == CB_FILES_REPORT)
async def cb_files_report(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text("Р“РµРЅРµСЂСѓСЋ Р·РІС–С‚...")
    from app.tasks.export_task import run_export

    run_export.delay(chat_id=str(callback.message.chat.id))


@router.callback_query(F.data == CB_FILES_BACK)
async def cb_files_back(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.delete()


@router.message(F.text == BTN_SEND_VIDEO)
async def btn_send_video(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await state.set_state(VideoUpload.waiting_video)
    await state.update_data(queue_count=0)
    await message.answer(
        "РќР°РґС–С€Р»С–С‚СЊ РІС–РґРµРѕ Р· РїС–РґРїРёСЃРѕРј.\n"
        "РњРѕР¶РЅР° РЅР°РґСЃРёР»Р°С‚Рё РєС–Р»СЊРєР° РІС–РґРµРѕ РїС–РґСЂСЏРґ, РІРѕРЅРё Р°РІС‚РѕРјР°С‚РёС‡РЅРѕ СЃС‚Р°РЅСѓС‚СЊ Сѓ С‡РµСЂРіСѓ.",
    )


@router.message(F.text == BTN_SEND_PHOTOS)
async def btn_send_photos(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await state.set_state(PhotoUpload.waiting_photos)
    await state.update_data(photo_file_ids=[], photo_count=0)
    await message.answer(
        "РќР°РґСЃРёР»Р°Р№С‚Рµ С„РѕС‚Рѕ РїРѕ РѕРґРЅРѕРјСѓ, Р°Р»СЊР±РѕРјРѕРј Р°Р±Рѕ СЏРє С„Р°Р№Р».\n"
        "РљРѕР»Рё РІСЃС– С„РѕС‚Рѕ РґРѕРґР°РЅС–, РѕРєСЂРµРјРёРј РїРѕРІС–РґРѕРјР»РµРЅРЅСЏРј РЅР°РґС–С€Р»С–С‚СЊ РєРѕРґ, РЅР°РїСЂРёРєР»Р°Рґ:\n"
        "<code>26.2888_РЅРѕСЂРјР°_РІС–Р°</code>\n\n"
        "РЇ СЃС‚РёСЃРЅСѓ С„РѕС‚Рѕ РІ JPG, Р·РјРµРЅС€Сѓ РґРѕ РјР°РєСЃРёРјСѓРјСѓ 600x900 С– РІС–РґРїСЂР°РІР»СЋ РІ РіСЂСѓРїСѓ.",
        parse_mode="HTML",
        reply_markup=photo_mode_keyboard(),
    )


@router.message(VideoUpload.waiting_video, F.video)
async def handle_video(message: Message, state: FSMContext) -> None:
    file_id = message.video.file_id
    caption = (message.caption or "").strip()
    chat_id = str(message.chat.id)

    if not caption:
        await message.answer("Напишіть назву.")
        return

    data = await state.get_data()
    queue_count = data.get("queue_count", 0) + 1
    await state.update_data(queue_count=queue_count)

    from app.tasks.video_pipeline import run_video_pipeline

    task = run_video_pipeline.delay(
        chat_id=chat_id,
        file_id=file_id,
        caption=caption,
        message_id=message.message_id,
    )

    preview = caption[:80] + ("..." if len(caption) > 80 else "")
    await message.answer(
        f"Р’С–РґРµРѕ #{queue_count} РїСЂРёР№РЅСЏС‚Рѕ РІ С‡РµСЂРіСѓ.\n"
        f"В«{preview}В»\n"
        f"Task: {task.id[:8]}...",
        reply_markup=cancel_task_keyboard(task.id),
    )


async def _store_photo_id(message: Message, state: FSMContext, file_id: str) -> None:
    data = await state.get_data()
    photo_file_ids = list(data.get("photo_file_ids", []))
    photo_file_ids.append(file_id)
    photo_count = len(photo_file_ids)
    await state.update_data(photo_file_ids=photo_file_ids, photo_count=photo_count)
    await message.answer(
        f"Р¤РѕС‚Рѕ РґРѕРґР°РЅРѕ: {photo_count}.\n"
        "РљРѕР»Рё РІСЃРµ Р±СѓРґРµ РіРѕС‚РѕРІРѕ, РЅР°РґС–С€Р»С–С‚СЊ РєРѕРґ РѕРєСЂРµРјРёРј РїРѕРІС–РґРѕРјР»РµРЅРЅСЏРј.",
        reply_markup=photo_mode_keyboard(),
    )


@router.message(PhotoUpload.waiting_photos, F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    await _store_photo_id(message, state, message.photo[-1].file_id)


@router.message(PhotoUpload.waiting_photos, F.document)
async def handle_photo_document(message: Message, state: FSMContext) -> None:
    if not _is_image_document(message):
        await message.answer("РћС‡С–РєСѓСЋ СЃР°РјРµ С„РѕС‚Рѕ Р°Р±Рѕ РєРѕРґ.", reply_markup=photo_mode_keyboard())
        return
    await _store_photo_id(message, state, message.document.file_id)


@router.message(PhotoUpload.waiting_photos, F.text)
async def handle_photo_code(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photo_file_ids = list(data.get("photo_file_ids", []))
    code = (message.text or "").strip()

    if code in {BTN_CANCEL_PHOTOS, BTN_DELETE_LAST_PHOTOS, BTN_RESET}:
        return
    if not photo_file_ids:
        await message.answer(
            "РЎРїРѕС‡Р°С‚РєСѓ РґРѕРґР°Р№С‚Рµ С…РѕС‡Р° Р± РѕРґРЅРµ С„РѕС‚Рѕ Р°Р±Рѕ С„РѕС‚Рѕ СЏРє С„Р°Р№Р».",
            reply_markup=photo_mode_keyboard(),
        )
        return
    if not code:
        await message.answer("РќР°РґС–С€Р»С–С‚СЊ РЅРµРїРѕСЂРѕР¶РЅС–Р№ РєРѕРґ.", reply_markup=photo_mode_keyboard())
        return

    await state.clear()

    from app.tasks.photo_pipeline import run_photo_pipeline

    task = run_photo_pipeline.delay(
        chat_id=str(message.chat.id),
        file_ids=photo_file_ids,
        code=code,
    )
    await message.answer(
        f"РџРѕС‡РёРЅР°СЋ РѕР±СЂРѕР±РєСѓ {len(photo_file_ids)} С„РѕС‚Рѕ РґР»СЏ РєРѕРґСѓ {code}.\n"
        f"Task: {task.id[:8]}...",
        reply_markup=main_menu_keyboard(),
    )


@router.message(VideoUpload.waiting_video)
async def handle_non_video_in_video_state(message: Message) -> None:
    await message.answer("РћС‡С–РєСѓСЋ СЃР°РјРµ РІС–РґРµРѕ Р°Р±Рѕ РЅР°С‚РёСЃРЅС–С‚СЊ РџРµСЂРµР·Р°РІР°РЅС‚Р°Р¶РёС‚Рё.")


@router.message(PhotoUpload.waiting_photos)
async def handle_non_photo_in_photo_state(message: Message) -> None:
    await message.answer("РћС‡С–РєСѓСЋ С„РѕС‚Рѕ, С„РѕС‚Рѕ-С„Р°Р№Р» Р°Р±Рѕ С‚РµРєСЃС‚РѕРІРёР№ РєРѕРґ.", reply_markup=photo_mode_keyboard())


@router.message(F.video)
async def handle_unexpected_video(message: Message) -> None:
    await message.answer(
        "РЎРїРѕС‡Р°С‚РєСѓ РЅР°С‚РёСЃРЅС–С‚СЊ В«Р’С–РґРїСЂР°РІРёС‚Рё РІС–РґРµРѕВ».",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.photo)
async def handle_unexpected_photo(message: Message) -> None:
    await message.answer(
        "РЎРїРѕС‡Р°С‚РєСѓ РЅР°С‚РёСЃРЅС–С‚СЊ В«Р”РѕРґР°С‚Рё С„РѕС‚РѕВ».",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Р”РѕРІС–РґРєР°:\n\n"
        "1. Р”Р»СЏ РІС–РґРµРѕ РЅР°С‚РёСЃРЅС–С‚СЊ В«Р’С–РґРїСЂР°РІРёС‚Рё РІС–РґРµРѕВ» С– РЅР°РґС–С€Р»С–С‚СЊ СЂРѕР»РёРє Р· РїС–РґРїРёСЃРѕРј.\n"
        "2. Р”Р»СЏ С„РѕС‚Рѕ РЅР°С‚РёСЃРЅС–С‚СЊ В«Р”РѕРґР°С‚Рё С„РѕС‚РѕВ», РЅР°РґС–С€Р»С–С‚СЊ РєС–Р»СЊРєР° С„РѕС‚Рѕ, Р° РїРѕС‚С–Рј РѕРєСЂРµРјРѕ РєРѕРґ.\n"
        "3. РљРЅРѕРїРєР° В«Р’С–РґРјС–РЅРёС‚Рё С„РѕС‚РѕВ» РІРёС…РѕРґРёС‚СЊ С–Р· СЂРµР¶РёРјСѓ С„РѕС‚Рѕ.\n"
        "4. РљРЅРѕРїРєР° В«Р’РёРґР°Р»РёС‚Рё РїРѕРїРµСЂРµРґРЅС” С„РѕС‚РѕВ» РїСЂРёР±РёСЂР°С” РѕСЃС‚Р°РЅРЅСЋ РїР°С‡РєСѓ Р· РіСЂСѓРїРё.",
        reply_markup=main_menu_keyboard(),
    )


@router.message()
async def handle_unknown(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await message.answer("РќРµ СЂРѕР·СѓРјС–СЋ РїРѕРІС–РґРѕРјР»РµРЅРЅСЏ. РЎРєРѕСЂРёСЃС‚Р°Р№С‚РµСЃСЊ РјРµРЅСЋ РЅРёР¶С‡Рµ.", reply_markup=main_menu_keyboard())

