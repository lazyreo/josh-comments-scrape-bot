"""Resend helpers for per-forward email notifications."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import List, Tuple

import resend

from bot.config import settings

logger = logging.getLogger(__name__)

MAX_EMAILS = 3
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_emails(raw: str) -> Tuple[List[str] | None, str | None]:
    """
    Parse up to 3 emails from space/newline-separated input.
    Returns (emails, None) on success, or (None, error_message).
    """
    if not raw or not raw.strip():
        return None, "Envie pelo menos um e-mail."

    tokens = [t.strip().lower() for t in re.split(r"[\s,;]+", raw.strip()) if t.strip()]
    if not tokens:
        return None, "Envie pelo menos um e-mail."

    if len(tokens) > MAX_EMAILS:
        return None, f"Você pode adicionar no máximo {MAX_EMAILS} e-mails por vez."

    seen = set()
    emails: List[str] = []
    for token in tokens:
        if not EMAIL_RE.match(token):
            return None, f"E-mail inválido: `{token}`"
        if token in seen:
            continue
        seen.add(token)
        emails.append(token)

    if not emails:
        return None, "Envie pelo menos um e-mail."

    return emails, None


def build_forward_email_body(message, *, source_title: str, dest_title: str) -> str:
    text = message.text or message.caption
    if text:
        body = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    else:
        media = getattr(message, "media", None)
        media_name = media.value if media else "media"
        link = getattr(message, "link", None)
        body = f"[mensagem de {media_name}]"
        if link:
            body += f"\n{link}"

    # Subject already has source → dest; body is message content only
    return body


def _send_sync(*, to: str, subject: str, body: str) -> None:
    resend.api_key = settings.RESEND_API_KEY
    # Escape only; keep original newlines (do not also insert <br> or pre doubles spacing)
    safe = html.escape(body).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = "".join(
        f"<p style=\"margin:0 0 0.6em 0\">{p.replace(chr(10), '<br>')}</p>"
        if p
        else "<br>"
        for p in safe.split("\n\n")
    )
    resend.Emails.send(
        {
            "from": settings.RESEND_FROM,
            "to": [to],
            "subject": subject,
            "html": f'<div style="font-family:inherit;line-height:1.4">{paragraphs}</div>',
            "text": body.replace("\r\n", "\n").replace("\r", "\n"),
        }
    )


async def send_forward_email(to: str, *, subject: str, body: str) -> bool:
    """Send one email via Resend. Returns False on failure (logs, does not raise)."""
    try:
        await asyncio.to_thread(_send_sync, to=to, subject=subject, body=body)
        return True
    except Exception as e:
        logger.warning("Resend failed for %s: %s", to, e)
        return False


async def notify_forward_emails(
    emails: list,
    *,
    subject: str,
    body: str,
) -> None:
    for address in emails or []:
        await send_forward_email(address, subject=subject, body=body)
