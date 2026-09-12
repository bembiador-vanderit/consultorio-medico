from email.message import EmailMessage
from smtplib import SMTP, SMTP_SSL
from urllib.parse import quote
from urllib.request import Request, urlopen
import json
import uuid

from app.core.config import get_settings


def build_whatsapp_link(phone: str, message: str) -> str:
    normalized = "".join(ch for ch in phone if ch.isdigit())
    return f"https://wa.me/{normalized}?text={quote(message)}"


def _smtp_send(message: EmailMessage) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP no está configurado")

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


def send_email(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from or ""
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    _smtp_send(message)


def send_email_with_attachment(
    to: str,
    subject: str,
    body: str,
    *,
    filename: str,
    content: bytes,
    content_type: str = "application/pdf",
) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from or ""
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    maintype, subtype = content_type.split("/", 1)
    message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    _smtp_send(message)


def _whatsapp_headers(token: str, content_type: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


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
    request = Request(url, data=payload, headers=_whatsapp_headers(settings.whatsapp_access_token, "application/json"), method="POST")
    with urlopen(request, timeout=20):
        pass
    return action_url


def send_whatsapp_document(phone: str, filename: str, content: bytes, caption: str) -> str:
    """Send a PDF through WhatsApp Cloud API, or return a wa.me fallback link."""
    settings = get_settings()
    action_url = build_whatsapp_link(phone, caption)
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return action_url

    token = settings.whatsapp_access_token
    phone_number_id = settings.whatsapp_phone_number_id
    boundary = f"----AtlasBoundary{uuid.uuid4().hex}"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"messaging_product\"\r\n\r\nwhatsapp\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\napplication/pdf\r\n".encode(),
        f"--{boundary}--\r\n".encode(),
    ]
    upload_request = Request(
        f"https://graph.facebook.com/v22.0/{phone_number_id}/media",
        data=b"".join(parts),
        headers=_whatsapp_headers(token, f"multipart/form-data; boundary={boundary}"),
        method="POST",
    )
    with urlopen(upload_request, timeout=30) as response:
        media = json.loads(response.read().decode("utf-8"))
    media_id = media.get("id")
    if not media_id:
        raise RuntimeError("WhatsApp no devolvió un identificador de documento")

    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": "".join(ch for ch in phone if ch.isdigit()),
            "type": "document",
            "document": {"id": media_id, "caption": caption, "filename": filename},
        }
    ).encode("utf-8")
    send_request = Request(
        f"https://graph.facebook.com/v22.0/{phone_number_id}/messages",
        data=payload,
        headers=_whatsapp_headers(token, "application/json"),
        method="POST",
    )
    with urlopen(send_request, timeout=20):
        pass
    return action_url
