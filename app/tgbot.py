"""Вход через Telegram-бота (deep link), без отдельного процесса с ботом.

1. Сайт генерирует случайный код и открывает t.me/<бот>?start=<код>.
2. Пользователь жмёт «Старт» — Telegram присылает это на наш вебхук /api/telegram/webhook.
3. Сервер находит или создаёт аккаунт по Telegram id и привязывает к коду.
4. Вкладка сайта опрашивает /api/auth/telegram/poll и получает сессию — вход выполнен.

Бот отвечает прямо в ответе на вебхук (sendMessage в теле ответа), поэтому исходящих запросов нет.
В ответе есть кнопка «Открыть сайт» с подписанной ссылкой: она входит, даже если вкладка закрыта
или опрос попал на другой экземпляр сервера (на Vercel у каждого экземпляра своя база в /tmp).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time

import httpx

log = logging.getLogger("tgbot")
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
CODE_TTL = 600        # код из кнопки действует 10 минут
LINK_TTL = 600        # подписанная ссылка из бота — тоже 10 минут


def token() -> str | None:
    return os.getenv("TELEGRAM_BOT_TOKEN") or None


def bot_username() -> str | None:
    b = os.getenv("TELEGRAM_BOT_USERNAME")
    return b.lstrip("@") if b and token() else None


def webhook_secret(tok: str) -> str:
    """Секрет заголовка X-Telegram-Bot-Api-Secret-Token: выводится из токена, хранить отдельно не нужно."""
    return hashlib.sha256(b"webhook:" + tok.encode()).hexdigest()[:48]


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _link_key(tok: str) -> bytes:
    return hashlib.sha256(b"link:" + tok.encode()).digest()


def sign_link(tok: str, tg_id: int, name: str | None, now: float | None = None) -> str:
    payload = _b64(json.dumps({"i": tg_id, "n": name, "e": int((now or time.time()) + LINK_TTL)},
                              ensure_ascii=False).encode())
    return payload + "." + _b64(hmac.new(_link_key(tok), payload.encode(), hashlib.sha256).digest())


def check_link(tok: str, t: str) -> tuple[int, str | None] | None:
    try:
        payload, sig = t.split(".", 1)
        want = _b64(hmac.new(_link_key(tok), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(want, sig):
            return None
        d = json.loads(_unb64(payload))
        if d["e"] < time.time():
            return None
        return int(d["i"]), d.get("n")
    except (ValueError, KeyError, TypeError):
        return None


def tg_name(user: dict) -> str | None:
    return " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x) or user.get("username")


def reply(chat_id: int, text: str, button: tuple[str, str] | None = None) -> dict:
    """Ответ бота прямо в теле ответа на вебхук."""
    out = {"method": "sendMessage", "chat_id": chat_id, "text": text}
    if button:
        out["reply_markup"] = {"inline_keyboard": [[{"text": button[0], "url": button[1]}]]}
    return out


_hooked: set[str] = set()


async def ensure_webhook(base_url: str) -> None:
    """Один раз на процесс: направить обновления бота на наш вебхук (если ещё не направлены)."""
    tok = token()
    if not tok or base_url in _hooked or not base_url.startswith("https://") \
            or any(h in base_url for h in ("localhost", "127.0.0.1", "testserver")):
        return
    url = base_url.rstrip("/") + "/api/telegram/webhook"
    api = f"https://api.telegram.org/bot{tok}"
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            info = (await c.get(f"{api}/getWebhookInfo")).json().get("result") or {}
            if info.get("url") != url:
                r = (await c.post(f"{api}/setWebhook", json={
                    "url": url, "secret_token": webhook_secret(tok), "allowed_updates": ["message"],
                    "drop_pending_updates": True})).json()
                log.info("setWebhook: %s", r.get("description") or r.get("ok"))
        _hooked.add(base_url)
    except (httpx.HTTPError, ValueError) as e:  # не получилось — попробуем при следующем запросе
        log.warning("webhook не настроен: %s", e)
