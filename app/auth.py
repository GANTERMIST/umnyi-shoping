"""Аутентификация без внешних зависимостей.

- пароль: PBKDF2-HMAC-SHA256, 200 000 итераций, случайная соль 16 байт;
- сессия: случайный токен 32 байта, в базе хранится только его SHA-256, срок 30 дней;
- токен отдаётся в cookie HttpOnly + SameSite=Lax (и в ответе — для клиентов без cookie);
- после 5 неудачных входов подряд аккаунт блокируется на 15 минут.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

from .db import Database

ITERATIONS = 200_000
SESSION_DAYS = 30
MAX_FAILS = 5
LOCK_MINUTES = 15
COOKIE = "us_session"


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(d: dt.datetime) -> str:
    return d.isoformat(timespec="seconds")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def register(db: Database, email: str, password: str, name: str | None) -> int:
    salt = secrets.token_bytes(16)
    uid = db.create_user(email.strip().lower(), name, _hash(password, salt), salt.hex())
    if uid is None:
        raise AuthError(409, "Пользователь с такой почтой уже есть")
    return uid


def login(db: Database, email: str, password: str) -> int:
    u = db.user_by_email(email.strip().lower())
    if not u:
        _hash(password, b"0" * 16)  # одинаковое время ответа для существующих и несуществующих почт
        raise AuthError(401, "Неверная почта или пароль")
    if u["locked_until"] and u["locked_until"] > _iso(_now()):
        raise AuthError(429, "Слишком много неудачных попыток — попробуйте через 15 минут")
    if not hmac.compare_digest(_hash(password, bytes.fromhex(u["pw_salt"])), u["pw_hash"]):
        fails = u["failed_logins"] + 1
        locked = _iso(_now() + dt.timedelta(minutes=LOCK_MINUTES)) if fails >= MAX_FAILS else None
        db.set_login_state(u["id"], 0 if locked else fails, locked)
        raise AuthError(401, "Неверная почта или пароль")
    db.set_login_state(u["id"], 0, None)
    return u["id"]


def new_session(db: Database, uid: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add_session(_token_hash(token), uid, _iso(_now() + dt.timedelta(days=SESSION_DAYS)))
    return token


def user_from_token(db: Database, token: str | None) -> int | None:
    return db.session_user(_token_hash(token)) if token else None


def logout(db: Database, token: str | None) -> None:
    if token:
        db.drop_session(_token_hash(token))


# ── вход через Telegram (Telegram Login Widget) ─────────────────
# Данные виджета подписаны ботом: hash = HMAC-SHA256(data_check_string, SHA256(bot_token)).
# Без проверки подписи любой мог бы прислать чужой id, поэтому без токена бота вход выключен.
TG_MAX_AGE = 86400  # подпись действительна сутки


def telegram_login(db: Database, data: dict, bot_token: str | None) -> int:
    if not bot_token:
        raise AuthError(503, "Вход через Telegram не настроен на сервере")
    data = {k: str(v) for k, v in data.items() if v is not None}
    got = data.pop("hash", "")
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    want = hmac.new(hashlib.sha256(bot_token.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    if not got or not hmac.compare_digest(want, got):
        raise AuthError(401, "Подпись Telegram не сошлась")
    if _now().timestamp() - int(data.get("auth_date", 0)) > TG_MAX_AGE:
        raise AuthError(401, "Данные Telegram устарели — войдите ещё раз")
    name = " ".join(x for x in (data.get("first_name"), data.get("last_name")) if x) or data.get("username")
    return telegram_user(db, int(data["id"]), name)


def telegram_user(db: Database, tg_id: int, name: str | None) -> int:
    """Аккаунт по Telegram id: найти или создать (регистрация происходит при первом входе)."""
    login_id = f"tg:{tg_id}"  # вместо почты; пароля у такого аккаунта нет
    u = db.user_by_email(login_id)
    if u:
        return u["id"]
    uid = db.create_user(login_id, name, "", secrets.token_hex(16))  # пустой хэш: войти паролем нельзя
    if uid is None:
        u = db.user_by_email(login_id)  # параллельный запрос успел создать
        if not u:
            raise AuthError(409, "Не удалось создать аккаунт")
        return u["id"]
    return uid
