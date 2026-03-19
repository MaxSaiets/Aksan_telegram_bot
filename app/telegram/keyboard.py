"""
Telegram keyboard definitions (aiogram v3).
"""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_SEND_VIDEO = "📤 Відправити відео"
BTN_SEND_PHOTOS = "📸 Додати фото"
BTN_CANCEL_PHOTOS = "❌ Відмінити фото"
BTN_DELETE_LAST_PHOTOS = "🗑 Видалити попереднє фото"
BTN_UNDO_LAST = "↩️ Скасувати останнє відео"
BTN_FILES = "📁 Отримати файли"
BTN_RESET = "🔄 Перезавантажити"

CB_CONFIRM = "btn_confirm"
CB_CANCEL = "btn_cancel"
CB_UNDO_CONFIRM = "undo:confirm"
CB_UNDO_CANCEL = "undo:cancel"
CB_FILES_ROZETKA = "files:rozetka"
CB_FILES_SITE = "files:site"
CB_FILES_REPORT = "files:report"
CB_FILES_BACK = "files:back"
CB_CANCEL_TASK = "cancel:"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SEND_VIDEO)],
            [KeyboardButton(text=BTN_SEND_PHOTOS)],
            [KeyboardButton(text=BTN_DELETE_LAST_PHOTOS)],
            [KeyboardButton(text=BTN_UNDO_LAST)],
            [KeyboardButton(text=BTN_FILES)],
            [KeyboardButton(text=BTN_RESET)],
        ],
        resize_keyboard=True,
        persistent=True,
        input_field_placeholder="Оберіть дію...",
    )


def photo_mode_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CANCEL_PHOTOS)],
            [KeyboardButton(text=BTN_DELETE_LAST_PHOTOS)],
            [KeyboardButton(text=BTN_RESET)],
        ],
        resize_keyboard=True,
        persistent=True,
        input_field_placeholder="Надсилайте фото або код...",
    )


def files_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Для Розетки", callback_data=CB_FILES_ROZETKA)],
            [InlineKeyboardButton(text="🌐 Для сайту", callback_data=CB_FILES_SITE)],
            [InlineKeyboardButton(text="📊 Звіт .xlsx", callback_data=CB_FILES_REPORT)],
            [InlineKeyboardButton(text="← Назад", callback_data=CB_FILES_BACK)],
        ]
    )


def undo_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так, видалити", callback_data=CB_UNDO_CONFIRM),
                InlineKeyboardButton(text="❌ Ні, залишити", callback_data=CB_UNDO_CANCEL),
            ]
        ]
    )


def cancel_task_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Скасувати обробку",
                    callback_data=f"{CB_CANCEL_TASK}{task_id}",
                )
            ]
        ]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Підтвердити", callback_data=CB_CONFIRM),
                InlineKeyboardButton(text="❌ Скасувати", callback_data=CB_CANCEL),
            ]
        ]
    )
