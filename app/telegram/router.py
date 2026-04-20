"""
Telegram bot handlers (aiogram v3 Router).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

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
    CB_FILES_CONVERT,
    CB_FILES_PRICES,
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
from app.telegram.states import PhotoUpload, PriceFileConvert, VideoUpload
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
_photo_state_locks: dict[str, asyncio.Lock] = {}


def _is_allowed(user_id: int) -> bool:
    allowed = settings.allowed_users
    return not allowed or user_id in allowed


def _is_private_chat(message: Message) -> bool:
    return getattr(message.chat, "type", None) == "private"


def _photo_lock(chat_id: int | str) -> asyncio.Lock:
    key = str(chat_id)
    if key not in _photo_state_locks:
        _photo_state_locks[key] = asyncio.Lock()
    return _photo_state_locks[key]


def _is_image_document(message: Message) -> bool:
    document = message.document
    if not document:
        return False
    mime = (document.mime_type or "").lower()
    name = (document.file_name or "").lower()
    return mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp"))


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    if not _is_private_chat(message):
        return
    if not _is_allowed(message.from_user.id):
        logger.warning("Blocked user_id=%s (not in whitelist)", message.from_user.id)
        await message.answer("У вас немає доступу до цього бота.")
        return

    await state.clear()
    name = message.from_user.first_name or "користувач"
    await message.answer(
        f"Привіт, {name}!\n\n"
        "Я вмію обробляти відео та фото для відправки в групу.\n"
        "Оберіть потрібну дію нижче.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == BTN_RESET)
async def btn_reset(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await state.clear()
    await message.answer("Стан скинуто.", reply_markup=main_menu_keyboard())


@router.message(F.text == BTN_CANCEL_PHOTOS)
async def btn_cancel_photos(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await state.clear()
    await message.answer("Режим фото скасовано.", reply_markup=main_menu_keyboard())


@router.message(F.text == BTN_DELETE_LAST_PHOTOS)
async def btn_delete_last_photos(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return

    batch = get_last_batch(str(message.chat.id))
    if not batch:
        await message.answer(
            "Немає попередньої пачки фото для видалення.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await delete_messages(batch["target_chat_id"], batch.get("message_ids", []))
    clear_last_batch(str(message.chat.id))
    await message.answer(
        f"Попередню пачку фото для коду {batch.get('code', '')} видалено.",
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
        await message.answer(
            "Немає оброблених відео для скасування.",
            reply_markup=main_menu_keyboard(),
        )
        return

    caption = last_video.get("caption", "без підпису")
    preview = caption[:80] + ("..." if len(caption) > 80 else "")
    youtube = last_video.get("youtube_url", "-")
    await state.update_data(undo_video_id=last_video["id"])

    await message.answer(
        f"Видалити останнє відео?\n\n"
        f"«{preview}»\n"
        f"{youtube}\n\n"
        "Це видалить відео з YouTube та бази даних.",
        reply_markup=undo_confirm_keyboard(),
    )


@router.callback_query(F.data == CB_UNDO_CONFIRM)
async def cb_undo_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    video_id = data.get("undo_video_id")
    if not video_id:
        await callback.message.edit_text("Відео для видалення не знайдено.")
        return

    await state.update_data(undo_video_id=None)
    await callback.message.edit_text("Видаляю відео з YouTube та бази даних...")

    from app.tasks.undo_task import run_undo_last_video

    run_undo_last_video.delay(chat_id=str(callback.message.chat.id), video_id=video_id)


@router.callback_query(F.data == CB_UNDO_CANCEL)
async def cb_undo_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(undo_video_id=None)
    await callback.message.edit_text("Видалення скасовано.")


@router.callback_query(F.data.startswith(CB_CANCEL_TASK))
async def cb_cancel_task(callback: CallbackQuery) -> None:
    await callback.answer()
    task_id = callback.data[len(CB_CANCEL_TASK):]

    try:
        from celery.contrib.abortable import AbortableAsyncResult
        from app.tasks.celery_app import celery_app

        result = AbortableAsyncResult(task_id, app=celery_app)
        if result.state in ("SUCCESS", "FAILURE"):
            await callback.message.edit_text("Цю задачу вже завершено.")
            return

        result.abort()
        await callback.message.edit_text("Обробку відео скасовано.")
        logger.info("Task %s aborted by user", task_id[:8])
    except Exception as exc:
        logger.warning("Cancel task %s failed: %s", task_id[:8], exc)
        await callback.message.edit_text(f"Не вдалося скасувати: {exc}")


@router.message(F.text == BTN_FILES)
async def btn_files(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await message.answer(
        "Оберіть тип файлу:\n\n"
        "Для Розетки, для сайту або звіт .xlsx.",
        reply_markup=files_keyboard(),
    )


@router.callback_query(F.data == CB_FILES_ROZETKA)
async def cb_files_rozetka(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text("Генерую файл для Розетки...")
    from app.tasks.files_task import run_generate_rozetka_file

    run_generate_rozetka_file.delay(chat_id=str(callback.message.chat.id))


@router.callback_query(F.data == CB_FILES_SITE)
async def cb_files_site(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text("Генерую файл для сайту...")
    from app.tasks.files_task import run_generate_site_file

    run_generate_site_file.delay(chat_id=str(callback.message.chat.id))


@router.callback_query(F.data == CB_FILES_REPORT)
async def cb_files_report(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text("Генерую звіт...")
    from app.tasks.export_task import run_export

    run_export.delay(chat_id=str(callback.message.chat.id))


@router.callback_query(F.data == CB_FILES_PRICES)
async def cb_files_prices(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "💰 Оновлення цін — генерую файл...\n\n"
        "📋 Як це працює:\n"
        "1. Отримайте файл з усіма товарами\n"
        "2. Відкрийте у Excel, відредагуйте потрібні поля\n"
        "   (Ціна, Знижка, Залишок, Ціна на маркетплейси тощо)\n"
        "3. Виділіть змінені рядки кольором заповнення\n"
        "4. Скористайтесь кнопкою 🎨 Конвертація файлу цін\n"
        "5. Отриманий файл завантажте в SalesDrive:\n"
        "   Товари та послуги → Імпорт → оберіть файл → Імпорт"
    )
    from app.tasks.files_task import run_generate_prices_file

    run_generate_prices_file.delay(chat_id=str(callback.message.chat.id))


@router.callback_query(F.data == CB_FILES_CONVERT)
async def cb_files_convert(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    await state.set_state(PriceFileConvert.waiting_file)
    await callback.message.edit_text(
        "🎨 Конвертація файлу цін\n\n"
        "Надішліть відредагований .xlsx файл де змінені товари виділені кольором заповнення.\n\n"
        "Я залишу тільки виділені рядки — і поверну готовий файл для імпорту.\n\n"
        "📥 Як завантажити в SalesDrive:\n"
        "Товари та послуги → Імпорт → оберіть файл → натисніть Імпорт"
    )


@router.message(PriceFileConvert.waiting_file, F.document)
async def handle_price_file(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return

    doc = message.document
    fname = (doc.file_name or "").lower()
    if not fname.endswith(".xlsx"):
        await message.answer("❌ Потрібен файл формату .xlsx")
        return

    await state.clear()
    await message.answer("⏳ Обробляю файл...")

    import tempfile
    from datetime import datetime
    from aiogram.types import BufferedInputFile

    from app.services.price_file_converter import filter_colored_rows
    from config import settings

    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / "input.xlsx"
        file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(file.file_path, destination=str(in_path))

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = settings.temp_dir / f"prices_filtered_{ts}.xlsx"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        kept, debug_info = filter_colored_rows(in_path, out_path)

    if kept == 0:
        await message.answer(
            "⚠️ Жодного кольорового рядка не знайдено.\n\n"
            f"🔍 Дебаг перших рядків:\n<code>{debug_info}</code>",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    with open(out_path, "rb") as f:
        await message.answer_document(
            BufferedInputFile(f.read(), filename=out_path.name),
            caption=f"✅ Готово: {kept} рядків з кольоровим заповненням",
        )
    await message.answer("Оберіть дію:", reply_markup=main_menu_keyboard())


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
        "Надішліть відео з підписом.\n"
        "Можна надсилати кілька відео підряд, вони автоматично стануть у чергу.",
    )


@router.message(F.text == BTN_SEND_PHOTOS)
async def btn_send_photos(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await state.set_state(PhotoUpload.waiting_photos)
    await state.update_data(photo_file_ids=[], photo_count=0)
    await message.answer(
        "Надсилайте фото по одному, альбомом або як файл.\n"
        "Коли всі фото додані, окремим повідомленням надішліть код, наприклад:\n"
        "<code>26.2888_норма_віа</code>\n\n"
        "Я стисну фото в JPG, зменшу до максимуму 600x900 і відправлю в групу.",
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
        f"Відео #{queue_count} прийнято в чергу.\n"
        f"«{preview}»\n"
        f"Task: {task.id[:8]}...",
        reply_markup=cancel_task_keyboard(task.id),
    )


async def _store_photo_id(message: Message, state: FSMContext, file_id: str) -> None:
    async with _photo_lock(message.chat.id):
        data = await state.get_data()
        photo_file_ids = list(data.get("photo_file_ids", []))
        photo_file_ids.append(file_id)
        photo_count = len(photo_file_ids)
        await state.update_data(photo_file_ids=photo_file_ids, photo_count=photo_count)
    await message.answer(
        f"Фото додано: {photo_count}.\n"
        "Коли все буде готово, надішліть код окремим повідомленням.",
        reply_markup=photo_mode_keyboard(),
    )


@router.message(PhotoUpload.waiting_photos, F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    await _store_photo_id(message, state, message.photo[-1].file_id)


@router.message(PhotoUpload.waiting_photos, F.document)
async def handle_photo_document(message: Message, state: FSMContext) -> None:
    if not _is_image_document(message):
        await message.answer("Очікую саме фото або код.", reply_markup=photo_mode_keyboard())
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
            "Спочатку додайте хоча б одне фото або фото як файл.",
            reply_markup=photo_mode_keyboard(),
        )
        return
    if not code:
        await message.answer("Надішліть непорожній код.", reply_markup=photo_mode_keyboard())
        return

    await state.clear()

    from app.tasks.photo_pipeline import run_photo_pipeline

    task = run_photo_pipeline.delay(
        chat_id=str(message.chat.id),
        file_ids=photo_file_ids,
        code=code,
    )
    await message.answer(
        f"Починаю обробку {len(photo_file_ids)} фото для коду {code}.\n"
        f"Task: {task.id[:8]}...",
        reply_markup=main_menu_keyboard(),
    )


@router.message(VideoUpload.waiting_video)
async def handle_non_video_in_video_state(message: Message) -> None:
    await message.answer("Очікую саме відео або натисніть Перезавантажити.")


@router.message(PhotoUpload.waiting_photos)
async def handle_non_photo_in_photo_state(message: Message) -> None:
    await message.answer("Очікую фото, фото-файл або текстовий код.", reply_markup=photo_mode_keyboard())


@router.message(F.video)
async def handle_unexpected_video(message: Message) -> None:
    await message.answer(
        "Спочатку натисніть «Відправити відео».",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.photo)
async def handle_unexpected_photo(message: Message) -> None:
    await message.answer(
        "Спочатку натисніть «Додати фото».",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Довідка:\n\n"
        "1. Для відео натисніть «Відправити відео» і надішліть ролик з підписом.\n"
        "2. Для фото натисніть «Додати фото», надішліть кілька фото, а потім окремо код.\n"
        "3. Кнопка «Відмінити фото» виходить із режиму фото.\n"
        "4. Кнопка «Видалити попереднє фото» прибирає останню пачку з групи.",
        reply_markup=main_menu_keyboard(),
    )


@router.message()
async def handle_unknown(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await message.answer(
        "Не розумію повідомлення. Скористайтесь меню нижче.",
        reply_markup=main_menu_keyboard(),
    )


