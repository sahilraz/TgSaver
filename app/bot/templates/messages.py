"""HTML message templates with strict input escaping."""

from typing import Any, Dict, List, Optional
from app.security.validation import safe_html, mask_phone_number


def format_dashboard(user_name: str, is_connected: bool, stats: Dict[str, Any]) -> str:
    status_icon = "🟢 <b>Connected</b>" if is_connected else "🔴 <b>Not Connected</b>"
    total_processed = stats.get("total_completed", 0)
    total_mb = round((stats.get("total_bytes", 0) / (1024 * 1024)), 2)

    return (
        f"⚡ <b>TgSaverBot — Ultra-Fast Telegram Archive</b>\n\n"
        f"<b>Welcome, {safe_html(user_name)}!</b>\n"
        f"Telegram Account: {status_icon}\n\n"
        f"📊 <b>Personal Statistics:</b>\n"
        f"• Total Saved Items: <code>{total_processed}</code>\n"
        f"• Bytes Transferred: <code>{total_mb} MB</code>\n"
        f"• Active Mappings: <code>{stats.get('total_mappings', 0)}</code>\n\n"
        f"<i>Submit any Telegram post link directly to begin archiving immediately.</i>"
    )


def format_help() -> str:
    return (
        "📖 <b>TgSaverBot — Help & Documentation</b>\n\n"
        "<b>Supported Link Formats:</b>\n"
        "• Public: <code>https://t.me/channel/123</code>\n"
        "• Private: <code>https://t.me/c/1234567890/123</code>\n"
        "• Batch: Send multiple links separated by spaces or newlines.\n\n"
        "<b>Key Commands:</b>\n"
        "/save &lt;link&gt; — Archive one or multiple Telegram posts\n"
        "/queue — View pending and active jobs\n"
        "/history — View completed job history\n"
        "/archives — Manage private archive channels\n"
        "/stats — View transfer statistics and speed\n"
        "/login — Connect your Telegram user account\n"
        "/logout — Disconnect or fully log out\n"
        "/cancel &lt;id&gt; — Cancel active or pending job\n"
        "/ping — Check bot response latency\n"
        "/health — System diagnostics\n\n"
        "<i>Server-side copy optimization will avoid downloading media whenever permitted!</i>"
    )


def format_privacy() -> str:
    return (
        "🛡️ <b>Privacy & Session Isolation</b>\n\n"
        "• <b>Zero-Leakage Guarantee:</b> Your Telegram account session is strictly isolated from all other users.\n"
        "• <b>Encryption at Rest:</b> Sessions are stored encrypted using Fernet AES-128-CBC + HMAC-SHA256 authenticated encryption.\n"
        "• <b>Master Key Separation:</b> Encryption keys are held securely in environment memory, never in the database.\n"
        "• <b>Complete Data Deletion:</b> Using /logout revokes your session from Telegram and immediately wipes your encrypted token."
    )


def format_account_info(is_connected: bool, session_info: Optional[Dict[str, Any]]) -> str:
    if not is_connected or not session_info:
        return (
            "👤 <b>Account Connection Status</b>\n\n"
            "Status: 🔴 <b>Disconnected</b>\n\n"
            "You haven't connected your Telegram account yet.\n"
            "Click <b>Connect Telegram Account</b> below to authorize via this Bot."
        )

    phone = mask_phone_number(session_info.get("phone_number"))
    name = safe_html(session_info.get("account_first_name", "Telegram User"))
    acc_id = session_info.get("account_id", "N/A")

    return (
        "👤 <b>Account Connection Status</b>\n\n"
        "Status: 🟢 <b>Connected</b>\n"
        f"• Name: <b>{name}</b>\n"
        f"• Account ID: <code>{acc_id}</code>\n"
        f"• Phone: <code>{phone}</code>\n\n"
        "<i>Your account is authorized and ready for transfers.</i>"
    )


def format_batch_progress(
    batch_id: str,
    completed: int,
    failed: int,
    skipped: int,
    total: int,
    bytes_transferred: int,
    elapsed: float,
) -> str:
    percent = int((completed + failed + skipped) / max(1, total) * 100)
    bars = int(percent / 10)
    progress_bar = "█" * bars + "░" * (10 - bars)
    mb = round(bytes_transferred / (1024 * 1024), 2)
    speed = round(mb / max(0.1, elapsed), 2)

    return (
        f"⚡ <b>Archive Job: <code>{batch_id[:8]}</code></b>\n\n"
        f"Progress: [{progress_bar}] <b>{percent}%</b>\n\n"
        f"• Completed: <code>{completed}/{total}</code>\n"
        f"• Failed: <code>{failed}</code>\n"
        f"• Skipped: <code>{skipped}</code>\n"
        f"• Transferred: <code>{mb} MB</code>\n"
        f"• Elapsed: <code>{round(elapsed, 1)}s</code>\n"
        f"• Speed: <code>{speed} MB/s</code>"
    )


def format_batch_completed(
    batch_id: str,
    completed: int,
    failed: int,
    skipped: int,
    total: int,
    bytes_transferred: int,
    elapsed: float,
    status: str = "COMPLETED",
) -> str:
    mb = round(bytes_transferred / (1024 * 1024), 2)
    speed = round(mb / max(0.1, elapsed), 2)

    if status == "COMPLETED" or (failed == 0 and completed > 0):
        status_header = "🎉 <b>Archive Completed Successfully!</b>"
        icon = "✅"
    elif completed > 0:
        status_header = "⚠️ <b>Archive Partially Completed</b>"
        icon = "🟡"
    else:
        status_header = "❌ <b>Archive Job Failed</b>"
        icon = "🔴"

    return (
        f"{status_header}\n\n"
        f"🆔 <b>Job ID:</b> <code>{batch_id[:8]}</code>\n"
        f"📊 <b>Status:</b> {icon} <code>{status}</code>\n\n"
        f"• Saved Items: <b>{completed}/{total}</b>\n"
        f"• Failed Items: <code>{failed}</code>\n"
        f"• Skipped / Dupes: <code>{skipped}</code>\n"
        f"• Total Transferred: <b>{mb} MB</b>\n"
        f"• Total Time: <b>{round(elapsed, 1)}s</b>\n"
        f"• Average Speed: <b>{speed} MB/s</b>\n\n"
        f"📁 <i>All media has been organized in your private archive.</i>"
    )

