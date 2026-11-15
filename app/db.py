"""Хранилище (SQLite, stdlib): игры, магазины, предложения, история цен, пользователи.

Схема та же, что в db/schema.sql для PostgreSQL (product / store / offer / price_history / app_user…).
Заполняется загрузчиком (python -m app.loader) и живыми поисками; при недоступности
источников сервис отвечает из базы.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from dataclasses import asdict, fields
from pathlib import Path

from . import sources as src

SCHEMA = """
CREATE TABLE IF NOT EXISTS product (
    id INTEGER PRIMARY KEY,
    steam_appid INTEGER UNIQUE,
    title TEXT NOT NULL,
    title_norm TEXT NOT NULL,
    genres TEXT NOT NULL DEFAULT '[]',
    image TEXT,
    metacritic INTEGER,
    steam_review_pct INTEGER,
    steam_reviews INTEGER,
    release TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS store (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    api_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offer (
    id TEXT PRIMARY KEY,                 -- «магазин:внешний id»
    product_id INTEGER REFERENCES product(id),
    store_id INTEGER NOT NULL REFERENCES store(id),
    title TEXT NOT NULL, price REAL NOT NULL, currency TEXT NOT NULL, url TEXT NOT NULL,
    seller TEXT, seller_rating REAL, sold INTEGER, reviews_pos INTEGER, reviews_neg INTEGER, returns INTEGER,
    kind TEXT NOT NULL, platform TEXT NOT NULL, trusted INTEGER NOT NULL, trust_score REAL NOT NULL,
    image TEXT, region TEXT, old_price REAL, note TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_offer_product ON offer(product_id);
CREATE TABLE IF NOT EXISTS price_history (
    offer_id TEXT NOT NULL,
    price REAL NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ph ON price_history(offer_id, fetched_at);
CREATE TABLE IF NOT EXISTS app_user (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    pw_hash TEXT NOT NULL,
    pw_salt TEXT NOT NULL,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_session (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_data (
    user_id INTEGER PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
    profile TEXT NOT NULL DEFAULT '{}',
    favorites TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    helpful INTEGER NOT NULL,
    place TEXT NOT NULL,
    offer_id TEXT,
    query TEXT,
    created_at TEXT NOT NULL
);
"""

OFFER_FIELDS = [f.name for f in fields(src.Offer)]
GOOD_KINDS = ("ключ", "гифт", "магазин")  # «лучшая цена» игры — без аккаунтов и прочего


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def api_type(store: str) -> str:
    return "plati" if store == "plati.market" else "cheapshark"


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    # ── игры и предложения ──────────────────────────────────────
    def save_game(self, g: src.Game) -> int:
        with self.lock, self.db:
            self.db.execute(
                """INSERT INTO product(steam_appid, title, title_norm, genres, image, metacritic, steam_review_pct,
                                       steam_reviews, release, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(steam_appid) DO UPDATE SET title=excluded.title, title_norm=excluded.title_norm,
                     genres=excluded.genres, image=excluded.image, metacritic=excluded.metacritic,
                     steam_review_pct=COALESCE(excluded.steam_review_pct, product.steam_review_pct),
                     steam_reviews=COALESCE(excluded.steam_reviews, product.steam_reviews),
                     release=excluded.release, updated_at=excluded.updated_at""",
                (g.appid, g.name, src.norm(g.name), json.dumps(g.genres, ensure_ascii=False), g.image, g.metacritic,
                 g.steam_review_pct, g.steam_reviews, g.release, now()))
            return self.db.execute("SELECT id FROM product WHERE steam_appid=?", (g.appid,)).fetchone()[0]

    def _store_id(self, name: str) -> int:
        self.db.execute("INSERT OR IGNORE INTO store(name, api_type) VALUES (?,?)", (name, api_type(name)))
        return self.db.execute("SELECT id FROM store WHERE name=?", (name,)).fetchone()[0]

    def save_offers(self, product_id: int | None, offers: list[src.Offer]) -> None:
        """Обновляет предложения; в историю пишет цену, только если она изменилась."""
        if not offers:
            return
        ts = now()
        with self.lock, self.db:
            last = self._last_prices([o.id for o in offers])
            for o in offers:
                d = asdict(o)
                d.update(product_id=product_id, store_id=self._store_id(o.store), updated_at=ts, trusted=int(o.trusted))
                d.pop("store")
                cols = list(d)
                self.db.execute(
                    f"INSERT INTO offer({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
                    f"ON CONFLICT(id) DO UPDATE SET " + ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
                    + (",product_id=COALESCE(excluded.product_id, offer.product_id)" if product_id is None else ""),
                    [d[c] for c in cols])
            rows = [(o.id, o.price, ts) for o in offers if last.get(o.id) != o.price]
            self.db.executemany("INSERT INTO price_history(offer_id, price, fetched_at) VALUES (?,?,?)", rows)

    def _last_prices(self, ids: list[str]) -> dict[str, float]:
        out = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            q = ("SELECT offer_id, price FROM price_history p WHERE offer_id IN (%s) AND fetched_at = "
                 "(SELECT MAX(fetched_at) FROM price_history WHERE offer_id = p.offer_id)") % ",".join("?" * len(chunk))
            out.update({r[0]: r[1] for r in self.db.execute(q, chunk)})
        return out

    def points(self, offer_id: str) -> list[tuple[str, float]]:
        return [(r["fetched_at"], r["price"]) for r in self.db.execute(
            "SELECT price, fetched_at FROM price_history WHERE offer_id=? ORDER BY fetched_at", (offer_id,))]

    def _offer(self, r: sqlite3.Row) -> src.Offer:
        d = {k: r[k] for k in r.keys() if k in OFFER_FIELDS}
        d["store"], d["trusted"] = r["store_name"], bool(r["trusted"])
        return src.Offer(**d)

    _OFFER_SQL = "SELECT o.*, s.name AS store_name FROM offer o JOIN store s ON s.id = o.store_id"

    def offers_for(self, product_id: int) -> list[src.Offer]:
        return [self._offer(r) for r in self.db.execute(self._OFFER_SQL + " WHERE o.product_id=?", (product_id,))]

    def current(self, ids: list[str]) -> list[src.Offer]:
        if not ids:
            return []
        q = self._OFFER_SQL + " WHERE o.id IN (%s)" % ",".join("?" * len(ids))
        return [self._offer(r) for r in self.db.execute(q, ids)]

    @staticmethod
    def game(r: sqlite3.Row) -> src.Game:
        return src.Game(appid=r["steam_appid"], name=r["title"], genres=json.loads(r["genres"]), image=r["image"],
                        metacritic=r["metacritic"], release=r["release"], steam_review_pct=r["steam_review_pct"],
                        steam_reviews=r["steam_reviews"])

    def find_product(self, query: str) -> sqlite3.Row | None:
        """Игра из базы по названию: точное совпадение, иначе самое короткое название, содержащее запрос."""
        q = src.norm(query)
        if not q:
            return None
        return (self.db.execute("SELECT * FROM product WHERE title_norm=?", (q,)).fetchone()
                or self.db.execute("SELECT * FROM product WHERE ' ' || title_norm || ' ' LIKE ? "
                                   "ORDER BY length(title_norm) LIMIT 1", (f"% {q} %",)).fetchone())

    def similar(self, appid: int, limit: int = 6) -> list[dict]:
        """Похожие игры: больше общих жанров, затем ближе по цене."""
        me = next((c for c in self.catalog(500) if c["appid"] == appid), None)
        row = self.product_by_appid(appid)
        if not row:
            return []
        genres = set(json.loads(row["genres"])) - {"Инди", "Бесплатные"} or set(json.loads(row["genres"]))
        price = (me or {}).get("best_price") or 0
        cand = [c for c in self.catalog(500) if c["appid"] != appid and c["best_price"] and genres & set(c["genres"])]
        cand.sort(key=lambda c: (-len(genres & set(c["genres"])), abs((c["best_price"] or 0) - price)))
        return cand[:limit]

    def add_feedback(self, helpful: bool, place: str, offer_id: str | None, query: str | None) -> None:
        with self.lock, self.db:
            self.db.execute("INSERT INTO feedback(helpful, place, offer_id, query, created_at) VALUES (?,?,?,?,?)",
                            (int(helpful), place, offer_id, query, now()))

    def feedback_stats(self) -> dict:
        rows = self.db.execute("SELECT place, helpful, COUNT(*) FROM feedback GROUP BY place, helpful").fetchall()
        by: dict[str, dict[str, int]] = {}
        for place, helpful, n in rows:
            by.setdefault(place, {"yes": 0, "no": 0})["yes" if helpful else "no"] += n
        total = sum(v["yes"] + v["no"] for v in by.values())
        yes = sum(v["yes"] for v in by.values())
        return {"total": total, "helpful": yes, "helpful_pct": round(100 * yes / total) if total else None, "by_place": by}

    def titles(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT title FROM product")]

    def best_offer(self, appid: int) -> src.Offer | None:
        """Самое дешёвое надёжное предложение игры в рублях (ключ или гифт), иначе — официальный магазин."""
        kinds = ",".join(f"'{k}'" for k in GOOD_KINDS)
        r = self.db.execute(self._OFFER_SQL + f" JOIN product p ON p.id = o.product_id WHERE p.steam_appid=? "
                            f"AND o.trusted=1 AND o.kind IN ({kinds}) ORDER BY o.currency != 'RUB', o.price LIMIT 1",
                            (appid,)).fetchone()
        return self._offer(r) if r else None

    def product_by_appid(self, appid: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM product WHERE steam_appid=?", (appid,)).fetchone()

    def catalog(self, limit: int = 60) -> list[dict]:
        kinds = ",".join(f"'{k}'" for k in GOOD_KINDS)
        rows = self.db.execute(f"""
            SELECT p.*, COUNT(o.id) AS n,
              MIN(CASE WHEN o.trusted=1 AND o.kind IN ({kinds}) AND o.currency='RUB' THEN o.price END) AS best,
              MIN(CASE WHEN o.kind='магазин' THEN o.price END) AS official,
              MAX(CASE WHEN o.kind='магазин' AND o.old_price > o.price
                       THEN ROUND(100.0 * (1 - o.price / o.old_price)) END) AS discount
            FROM product p LEFT JOIN offer o ON o.product_id = p.id
            GROUP BY p.id HAVING n > 0 ORDER BY n DESC, p.title LIMIT ?""", (limit,)).fetchall()
        out = []
        for r in rows:
            best_kind = None
            if r["best"] is not None:
                k = self.db.execute(f"SELECT kind FROM offer WHERE product_id=? AND trusted=1 AND kind IN ({kinds}) "
                                    "AND currency='RUB' ORDER BY price LIMIT 1", (r["id"],)).fetchone()
                best_kind = k[0] if k else None
            savings = int(r["discount"]) if r["discount"] else None  # скидка в официальном магазине, %
            out.append(dict(appid=r["steam_appid"], name=r["title"], image=r["image"], genres=json.loads(r["genres"]),
                            metacritic=r["metacritic"], steam_review_pct=r["steam_review_pct"], best_price=r["best"],
                            best_kind=best_kind, official_price=r["official"], offers=r["n"], savings_pct=savings,
                            updated_at=r["updated_at"]))
        return out

    def deals(self, limit: int = 12) -> list[dict]:
        """«Выгодно сегодня»: игры со скидкой в официальных магазинах (по данным CheapShark)."""
        items = [c for c in self.catalog(500) if c["savings_pct"]]
        return sorted(items, key=lambda c: -c["savings_pct"])[:limit]

    def stores(self) -> list[dict]:
        return [dict(name=r["name"], api_type=r["api_type"], offers=r["n"]) for r in self.db.execute(
            "SELECT s.name, s.api_type, COUNT(o.id) AS n FROM store s LEFT JOIN offer o ON o.store_id=s.id "
            "GROUP BY s.id ORDER BY n DESC")]

    # ── пользователи ────────────────────────────────────────────
    def create_user(self, email: str, name: str | None, pw_hash: str, salt: str) -> int | None:
        try:
            with self.lock, self.db:
                cur = self.db.execute("INSERT INTO app_user(email, name, pw_hash, pw_salt, created_at) VALUES (?,?,?,?,?)",
                                      (email, name, pw_hash, salt, now()))
                self.db.execute("INSERT INTO user_data(user_id) VALUES (?)", (cur.lastrowid,))
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def user_by_email(self, email: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM app_user WHERE email=?", (email,)).fetchone()

    def user_by_id(self, uid: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM app_user WHERE id=?", (uid,)).fetchone()

    def set_login_state(self, uid: int, failed: int, locked_until: str | None) -> None:
        with self.lock, self.db:
            self.db.execute("UPDATE app_user SET failed_logins=?, locked_until=? WHERE id=?", (failed, locked_until, uid))

    def add_session(self, token_hash: str, uid: int, expires_at: str) -> None:
        with self.lock, self.db:
            self.db.execute("DELETE FROM user_session WHERE expires_at < ?", (now(),))
            self.db.execute("INSERT INTO user_session VALUES (?,?,?)", (token_hash, uid, expires_at))

    def session_user(self, token_hash: str) -> int | None:
        r = self.db.execute("SELECT user_id FROM user_session WHERE token_hash=? AND expires_at > ?",
                            (token_hash, now())).fetchone()
        return r[0] if r else None

    def drop_session(self, token_hash: str) -> None:
        with self.lock, self.db:
            self.db.execute("DELETE FROM user_session WHERE token_hash=?", (token_hash,))

    def user_data(self, uid: int) -> tuple[dict, list]:
        r = self.db.execute("SELECT profile, favorites FROM user_data WHERE user_id=?", (uid,)).fetchone()
        return (json.loads(r[0]), json.loads(r[1])) if r else ({}, [])

    def put_user_data(self, uid: int, *, profile: dict | None = None, favorites: list | None = None) -> None:
        with self.lock, self.db:
            if profile is not None:
                self.db.execute("UPDATE user_data SET profile=? WHERE user_id=?", (json.dumps(profile, ensure_ascii=False), uid))
            if favorites is not None:
                self.db.execute("UPDATE user_data SET favorites=? WHERE user_id=?", (json.dumps(favorites, ensure_ascii=False), uid))
