from email.message import EmailMessage
from smtplib import SMTP, SMTP_SSL
from urllib.parse import quote
from urllib.request import Request, urlopen
import json

from app.core.config import get_settings


def build_whatsapp_link(phone: str, message: str) -> str:
    normalized = "".join(ch for ch in phone if ch.isdigit())
    return f"https://wa.me/{normalized}?text={quote(message)}"


def send_email(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP no está configurado")

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    if settings.smtp_use_ssl:
        with SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password or "")
            server.send_message(message)
        return

    with SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.send_message(message)


def send_whatsapp(phone: str, message: str) -> str:
    settings = get_settings()
    action_url = build_whatsapp_link(phone, message)
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return action_url

    url = f"https://graph.facebook.com/v22.0/{settings.whatsapp_phone_number_id}/messages"
    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": "".join(ch for ch in phone if ch.isdigit()),
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
    ).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.whatsapp_access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=20):
        pass
    return action_url
