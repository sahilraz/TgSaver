"""Input validation, HTML escaping, and link parsing utilities."""

import html
import re
from typing import List, NamedTuple, Optional


class ParsedTelegramLink(NamedTuple):
    raw_url: str
    channel_ref: str  # Either username e.g. 'durov' or private ID str e.g. '-1001234567890'
    message_id: int
    is_private: bool


# Matches:
# https://t.me/username/123
# https://t.me/c/1234567890/123
# tg://resolve?domain=username&post=123
LINK_REGEX = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:c/(\d+)|([a-zA-Z0-9_]{4,}))/(\d+)",
    re.IGNORECASE,
)

PHONE_REGEX = re.compile(r"^\+?[1-9]\d{7,14}$")


def safe_html(text: Optional[str]) -> str:
    """Escapes HTML special characters to prevent Telegram formatting injection."""
    if not text:
        return ""
    return html.escape(str(text), quote=True)


def parse_telegram_link(url: str) -> Optional[ParsedTelegramLink]:
    """Parses a single Telegram post link into channel reference and message ID."""
    match = LINK_REGEX.search(url.strip())
    if not match:
        return None

    private_id, username, msg_id_str = match.groups()
    msg_id = int(msg_id_str)

    if private_id:
        # Private channel links format in Telegram MTProto is prefixed with -100
        full_channel_id = f"-100{private_id}"
        return ParsedTelegramLink(
            raw_url=url.strip(),
            channel_ref=full_channel_id,
            message_id=msg_id,
            is_private=True,
        )
    elif username:
        return ParsedTelegramLink(
            raw_url=url.strip(),
            channel_ref=username.lower(),
            message_id=msg_id,
            is_private=False,
        )

    return None


def extract_telegram_links(text: str) -> List[ParsedTelegramLink]:
    """Extracts all valid Telegram post links from a multi-line or space-separated string."""
    results: List[ParsedTelegramLink] = []
    seen = set()

    # Split by whitespace, newlines, or commas
    tokens = re.split(r"[\s,\n]+", text.strip())
    for token in tokens:
        if not token:
            continue
        parsed = parse_telegram_link(token)
        if parsed:
            key = (parsed.channel_ref, parsed.message_id)
            if key not in seen:
                seen.add(key)
                results.append(parsed)

    return results


def validate_phone_number(phone: str) -> Optional[str]:
    """Validates and formats an international phone number with leading plus."""
    cleaned = re.sub(r"[\s\-\(\)]", "", phone.strip())
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    if PHONE_REGEX.match(cleaned):
        return cleaned
    return None


def mask_phone_number(phone: Optional[str]) -> str:
    """Masks a phone number for privacy, e.g. +1 •••• ••89."""
    if not phone or len(phone) < 6:
        return "Unknown"
    return f"{phone[:3]}••••••{phone[-2:]}"
