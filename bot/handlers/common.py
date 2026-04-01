from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import Challenge


def challenge_choose_kb(challenges: list[Challenge]) -> InlineKeyboardMarkup:
    """Build an InlineKeyboard for choosing between multiple challenges."""
    buttons = [
        [InlineKeyboardButton(
            text=f"📌 {c.title}",
            callback_data=f"switch_challenge:{c.id}",
        )]
        for c in challenges
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
