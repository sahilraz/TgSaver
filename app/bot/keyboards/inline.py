"""Inline keyboards for interactive Telegram UI navigation."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_dashboard_keyboard(is_connected: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not is_connected:
        buttons.append([InlineKeyboardButton(text="🔑 Connect Telegram Account", callback_data="btn:login")])
    else:
        buttons.append([InlineKeyboardButton(text="⚡ Save Posts", callback_data="btn:save_guide")])

    buttons.extend([
        [
            InlineKeyboardButton(text="📋 My Queue", callback_data="btn:queue"),
            InlineKeyboardButton(text="📁 My Archives", callback_data="btn:archives"),
        ],
        [
            InlineKeyboardButton(text="📊 Statistics", callback_data="btn:stats"),
            InlineKeyboardButton(text="🚀 Speed Test", callback_data="btn:speed"),
        ],
        [
            InlineKeyboardButton(text="👤 My Account", callback_data="btn:account"),
            InlineKeyboardButton(text="⚙️ Settings", callback_data="btn:settings"),
        ],
        [
            InlineKeyboardButton(text="❓ Help", callback_data="btn:help"),
            InlineKeyboardButton(text="🛡️ Privacy", callback_data="btn:privacy"),
        ],
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def auth_keyboard(is_connected: bool) -> InlineKeyboardMarkup:
    if is_connected:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚪 Disconnect Account", callback_data="btn:logout_menu")],
                [InlineKeyboardButton(text="⬅️ Back to Dashboard", callback_data="btn:dashboard")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel Login", callback_data="btn:login_cancel")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="btn:dashboard")],
        ]
    )


def auth_code_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📲 Send via SMS / Resend Code", callback_data="btn:login_resend")],
            [InlineKeyboardButton(text="❌ Cancel Login", callback_data="btn:login_cancel")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="btn:dashboard")],
        ]
    )



def logout_options_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏸️ Disconnect (Keep Session)", callback_data="btn:disconnect_keep")],
            [InlineKeyboardButton(text="🗑️ Log Out Completely (Wipe Session)", callback_data="btn:logout_full")],
            [InlineKeyboardButton(text="⬅️ Cancel", callback_data="btn:account")],
        ]
    )


def batch_action_keyboard(batch_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Cancel Job", callback_data=f"job:cancel:{batch_id[:8]}")],
            [InlineKeyboardButton(text="🔄 Refresh Status", callback_data=f"job:refresh:{batch_id[:8]}")],
        ]
    )


def batch_completed_keyboard(view_url: str | None = None) -> InlineKeyboardMarkup:
    buttons = []
    if view_url:
        buttons.append([InlineKeyboardButton(text="🚀 View on Archive Channel", url=view_url)])
    buttons.append([
        InlineKeyboardButton(text="📁 My Archives", callback_data="btn:archives"),
        InlineKeyboardButton(text="⬅️ Dashboard", callback_data="btn:dashboard"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Dashboard", callback_data="btn:dashboard")]
        ]
    )

