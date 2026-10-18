import hashlib
import html
import time

import httpx


class TelegramError(Exception):
    def __init__(self, code, description="", retry=0):
        self.code, self.description, self.retry = code, description.lower(), retry


def message_text(payload):
    item = payload.get("item")
    if not payload.get("is_playing") or not item:
        return "Сейчас ничего не слушаю"
    artists = ", ".join(a["name"] for a in item.get("artists", []) if a.get("name"))
    label = html.escape(f"{artists or 'Неизвестный исполнитель'} - {item.get('name') or 'Без названия'}")
    # Construct the URL from the track ID, rather than interpolating arbitrary upstream HTML.
    url = html.escape(f"https://open.spotify.com/track/{item['id']}", quote=True)
    return f'<a href="{url}">{label}</a>'


class Telegram:
    def __init__(self, settings, store, client):
        self.settings, self.store, self.client = settings, store, client
        identity = settings.telegram_token + ":" + settings.telegram_chat
        self.key = "telegram:" + hashlib.sha256(identity.encode()).hexdigest()
        self.retry_at = 0

    async def request(self, method, data):
        try:
            response = await self.client.post(
                f"https://api.telegram.org/bot{self.settings.telegram_token}/{method}", json=data
            )
            result = response.json()
        except (httpx.RequestError, ValueError):
            raise TelegramError(502) from None
        if not result.get("ok"):
            raise TelegramError(
                result.get("error_code", response.status_code),
                result.get("description", ""),
                result.get("parameters", {}).get("retry_after", 0),
            )
        return result.get("result")

    async def publish(self, payload):
        if not self.settings.telegram_token or not payload.get("success") or time.monotonic() < self.retry_at:
            return
        text = message_text(payload)
        digest = hashlib.sha256(text.encode()).hexdigest()
        state = self.store.get(self.key, {})
        if state.get("digest") == digest:
            return
        data = {
            "chat_id": self.settings.telegram_chat,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        try:
            if state.get("message_id"):
                try:
                    await self.request("editMessageText", {**data, "message_id": state["message_id"]})
                except TelegramError as exc:
                    if exc.code == 400 and "message is not modified" in exc.description:
                        pass
                    elif exc.code == 400 and "message to edit not found" in exc.description:
                        result = await self.request("sendMessage", data)
                        state["message_id"] = result["message_id"]
                    else:
                        raise
            else:
                result = await self.request("sendMessage", data)
                state["message_id"] = result["message_id"]
        except TelegramError as exc:
            self.retry_at = time.monotonic() + max(10, exc.retry)
            raise
        self.store.set(self.key, {"message_id": state["message_id"], "digest": digest})
