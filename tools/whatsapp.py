import httpx

from config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_API_VERSION, WHATSAPP_ALLOWED_SENDERS, WHATSAPP_ENABLED, WHATSAPP_PHONE_NUMBER_ID


def configured():
    return bool(WHATSAPP_ENABLED and WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID)


def send_text(recipient, text):
    if not configured():
        return "WhatsApp Business is not configured or enabled."
    recipient = str(recipient).strip()
    if not WHATSAPP_ALLOWED_SENDERS or recipient not in WHATSAPP_ALLOWED_SENDERS:
        return "WhatsApp recipient is not on the allowed-senders list."
    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    try:
        response = httpx.post(url, headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": recipient, "type": "text", "text": {"body": str(text)}}, timeout=20)
        response.raise_for_status()
        return "WhatsApp message sent."
    except httpx.HTTPError as exc:
        return f"WhatsApp API error: {exc}"


def parse_incoming(payload):
    try:
        message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        if message.get("type") != "text":
            return None
        return message["from"], message["text"]["body"]
    except (KeyError, IndexError, TypeError):
        return None
