from urllib.parse import unquote

from app.services.communication import build_whatsapp_link


def test_build_whatsapp_link_normalizes_phone_and_encodes_message():
    link = build_whatsapp_link("+1 (809) 555-1234", "Hola, su cita es mañana a las 9:00")

    assert link.startswith("https://wa.me/18095551234?text=")
    assert unquote(link.split("?text=", 1)[1]) == "Hola, su cita es mañana a las 9:00"
